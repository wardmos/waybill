"""Transport-neutral application facade for Waybill use cases.

The facade exposes operation outcomes, stable problem codes, and the filesystem
roots an operation is allowed to read or write.  It deliberately contains no
argument parsing, terminal output, or JSON rendering.
"""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Generic, Literal, Sequence, TypeVar

from .delegation import DelegationPairReport, verify_delegation_pair
from .doctor import DoctorReport, doctor_repository
from .install import InstallReport, install_adapters
from .limits import MAX_DIFF_BYTES
from .packing import PackReport, UnpackReport, pack_bundle, unpack_bundle
from .preflight import ImportPreflightReport, run_import_preflight
from .readiness import ExportReadinessReport, check_export_readiness
from .redaction import RedactionReport, redact_bundle
from .rendering import render_bundle
from .repo import RepoVerificationReport, verify_repo_state
from .scaffold import DraftBundleReport, create_draft_bundle
from .sharing import ShareCheckReport, ShareReport, check_shareability, share_bundle
from .validation import ValidationIssue, has_errors, validate_bundle


T = TypeVar("T")
RootIntentName = Literal["read", "write"]
AccessIntentName = Literal["read", "write", "mixed"]
OPERATIONAL_ERRORS = (OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class RootAccess:
    """One allowed filesystem root and the strongest intended access."""

    root: Path
    intent: RootIntentName


@dataclass(frozen=True)
class AccessIntent:
    """Filesystem authority required by one application operation."""

    operation: str
    roots: tuple[Path, ...]
    intent: AccessIntentName
    root_intents: tuple[RootAccess, ...]


@dataclass(frozen=True)
class Problem:
    """A transport-neutral problem with a stable machine-readable code."""

    code: str
    message: str


@dataclass(frozen=True)
class OperationResult(Generic[T]):
    """Stable result envelope returned by an application use case."""

    success: bool
    valid: bool | None
    payload: T | None
    problems: tuple[Problem, ...]
    access: AccessIntent


@dataclass(frozen=True)
class InspectArtifactReport:
    """Artifact evidence captured while the inspect controller owns I/O."""

    name: str
    path: str | None
    status: Literal["present", "missing", "invalid"]
    byte_count: int


@dataclass(frozen=True)
class InspectBundleReport:
    """Bundle metadata and validation evidence used by inspect renderers."""

    bundle: Path
    metadata: dict[str, object] | None
    metadata_error: str | None
    validation_issues: list[ValidationIssue]
    artifacts: tuple[InspectArtifactReport, ...] = ()


@dataclass(frozen=True)
class PackBundleReport:
    """Validation evidence and an optional archive result."""

    validation_issues: list[ValidationIssue]
    pack: PackReport | None


@dataclass(frozen=True)
class UnpackBundleReport:
    """Extraction result plus validation of the extracted bundle."""

    unpack: UnpackReport
    validation_issues: list[ValidationIssue]


@dataclass(frozen=True)
class RenderBundleReport:
    """Rendered review text and its optional output path."""

    bundle: Path
    output: Path | None
    rendered: str
    validation_issues: list[ValidationIssue]


def _best_effort_access_root(candidate: Path) -> Path:
    """Return the strongest available root without leaking filesystem errors."""

    try:
        return candidate.resolve()
    except (OSError, RuntimeError):
        pass
    try:
        return candidate.absolute()
    except (OSError, RuntimeError):
        return candidate


def _access(
    operation: str,
    *entries: tuple[str | Path, RootIntentName],
) -> AccessIntent:
    ordered: list[RootAccess] = []
    indexes: dict[Path, int] = {}
    for path, intent in entries:
        candidate = Path(path)
        root = _best_effort_access_root(candidate)
        existing = indexes.get(root)
        if existing is None:
            indexes[root] = len(ordered)
            ordered.append(RootAccess(root, intent))
        elif intent == "write" and ordered[existing].intent != "write":
            ordered[existing] = RootAccess(root, "write")
    intents = {entry.intent for entry in ordered}
    overall: AccessIntentName
    if not intents or intents == {"read"}:
        overall = "read"
    elif intents == {"write"}:
        overall = "write"
    else:
        overall = "mixed"
    return AccessIntent(
        operation=operation,
        roots=tuple(entry.root for entry in ordered),
        intent=overall,
        root_intents=tuple(ordered),
    )


def _result(
    *,
    access: AccessIntent,
    payload: T,
    valid: bool,
    problem_code: str,
    problem_message: str,
) -> OperationResult[T]:
    problems = () if valid else (Problem(problem_code, problem_message),)
    return OperationResult(
        success=valid,
        valid=valid,
        payload=payload,
        problems=problems,
        access=access,
    )


def _operation_result(
    *,
    access: AccessIntent,
    payload: T | None,
    success: bool,
    valid: bool | None,
    problem_code: str,
    problem_message: str,
) -> OperationResult[T]:
    return OperationResult(
        success=success,
        valid=valid,
        payload=payload,
        problems=() if success else (Problem(problem_code, problem_message),),
        access=access,
    )


def _operational_failure(
    *,
    access: AccessIntent,
    problem_code: str,
    error: OSError | RuntimeError | ValueError,
    payload: T | None = None,
    valid: bool | None = None,
) -> OperationResult[T]:
    """Convert an expected environmental failure into the stable envelope."""

    return _operation_result(
        access=access,
        payload=payload,
        success=False,
        valid=valid,
        problem_code=problem_code,
        problem_message=str(error),
    )


def read_bundle_metadata(
    bundle: str | Path,
) -> tuple[dict[str, object] | None, str | None]:
    """Read metadata for inspection without coupling the use case to the CLI."""

    path = Path(bundle) / "metadata.json"
    if not path.is_file():
        return None, "metadata.json is missing"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeError:
        return None, "metadata.json must be UTF-8 text"
    except OSError:
        return None, "metadata.json could not be read"
    except json.JSONDecodeError as exc:
        return None, f"metadata.json is invalid JSON: {exc}"
    if not isinstance(metadata, dict):
        return None, "metadata.json must contain an object"
    return metadata, None


def _inspect_artifacts(
    bundle: Path,
    metadata: dict[str, object] | None,
) -> tuple[InspectArtifactReport, ...]:
    """Capture artifact status before the result crosses into a renderer."""

    if metadata is None or not isinstance(metadata.get("artifacts"), dict):
        return ()

    artifacts: list[InspectArtifactReport] = []
    for name, artifact in metadata["artifacts"].items():
        if not isinstance(artifact, str):
            artifacts.append(InspectArtifactReport(name, None, "invalid", 0))
            continue
        relative_path = PurePosixPath(artifact)
        if (
            not artifact.strip()
            or "\\" in artifact
            or any(ord(character) < 32 for character in artifact)
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative_path.as_posix() != artifact
        ):
            artifacts.append(InspectArtifactReport(name, artifact, "invalid", 0))
            continue

        path = bundle.joinpath(*relative_path.parts)
        try:
            path_metadata = path.lstat()
        except FileNotFoundError:
            artifacts.append(InspectArtifactReport(name, artifact, "missing", 0))
            continue
        if stat.S_ISLNK(path_metadata.st_mode):
            artifacts.append(InspectArtifactReport(name, artifact, "invalid", 0))
            continue
        if not stat.S_ISREG(path_metadata.st_mode):
            artifacts.append(InspectArtifactReport(name, artifact, "missing", 0))
            continue
        artifacts.append(
            InspectArtifactReport(name, artifact, "present", path_metadata.st_size)
        )
    return tuple(artifacts)


class WaybillApplication:
    """Run Waybill use cases without assuming a CLI or another transport."""

    def validate(self, bundle: str | Path) -> OperationResult[list[ValidationIssue]]:
        access = _access("validate", (bundle, "read"))
        try:
            issues = validate_bundle(bundle)
            valid = not has_errors(issues)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="bundle_validation_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=issues,
            valid=valid,
            problem_code="bundle_invalid",
            problem_message="bundle validation found blocking issues",
        )

    def verify_repo(
        self,
        bundle: str | Path,
        repo: str | Path,
    ) -> OperationResult[RepoVerificationReport]:
        access = _access("verify-repo", (bundle, "read"), (repo, "read"))
        try:
            report = verify_repo_state(bundle, repo)
            valid = not report.has_errors
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="repository_verification_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=report,
            valid=valid,
            problem_code="repository_mismatch",
            problem_message="bundle repository state does not match",
        )

    def verify_pair(
        self,
        request: str | Path,
        result: str | Path,
    ) -> OperationResult[DelegationPairReport]:
        access = _access("verify-pair", (request, "read"), (result, "read"))
        try:
            report = verify_delegation_pair(request, result)
            valid = not report.has_errors
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="delegation_pair_verification_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=report,
            valid=valid,
            problem_code="delegation_pair_mismatch",
            problem_message="delegation result does not match request",
        )

    def preflight(
        self,
        bundle: str | Path,
        repo: str | Path,
    ) -> OperationResult[ImportPreflightReport]:
        access = _access("preflight", (bundle, "read"), (repo, "read"))
        try:
            report = run_import_preflight(bundle, repo)
            valid = not report.has_errors
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="import_preflight_execution_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=report,
            valid=valid,
            problem_code="import_preflight_failed",
            problem_message="import preflight found blocking issues",
        )

    def ready(
        self,
        bundle: str | Path,
        repo: str | Path,
    ) -> OperationResult[ExportReadinessReport]:
        access = _access("ready", (bundle, "read"), (repo, "read"))
        try:
            report = check_export_readiness(bundle, repo)
            valid = not report.has_errors
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="export_readiness_check_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=report,
            valid=valid,
            problem_code="bundle_not_ready",
            problem_message="bundle is not ready for handoff",
        )

    def inspect(self, bundle: str | Path) -> OperationResult[InspectBundleReport]:
        bundle_path = Path(bundle)
        access = _access("inspect", (bundle_path, "read"))
        try:
            issues = validate_bundle(bundle_path)
            metadata, metadata_error = read_bundle_metadata(bundle_path)
            report = InspectBundleReport(
                bundle=bundle_path,
                metadata=metadata,
                metadata_error=metadata_error,
                artifacts=_inspect_artifacts(bundle_path, metadata),
                validation_issues=issues,
            )
            valid = not has_errors(issues)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="bundle_inspection_failed",
                error=exc,
            )
        return _result(
            access=access,
            payload=report,
            valid=valid,
            problem_code="bundle_inspection_failed",
            problem_message="bundle inspection found blocking issues",
        )

    def install_adapters(
        self,
        source_root: str | Path,
        target: str | Path,
        adapters: Sequence[str],
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> OperationResult[InstallReport]:
        access = _access(
            "init",
            (source_root, "read"),
            (target, "read" if dry_run else "write"),
        )
        try:
            report = install_adapters(
                source_root,
                target,
                list(adapters),
                force=force,
                dry_run=dry_run,
            )
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="adapter_installation_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=not report.has_conflicts,
            valid=not report.has_conflicts,
            problem_code="adapter_installation_conflict",
            problem_message="adapter installation has conflicts",
        )

    def doctor(
        self,
        target: str | Path,
        adapters: Sequence[str],
        *,
        source_root: str | Path,
    ) -> OperationResult[DoctorReport]:
        access = _access("doctor", (target, "read"), (source_root, "read"))
        try:
            report = doctor_repository(
                target,
                list(adapters),
                source_root=source_root,
            )
        except ValueError as exc:
            return _operation_result(
                access=access,
                payload=None,
                success=False,
                valid=None,
                problem_code="doctor_request_invalid",
                problem_message=str(exc),
            )
        except (OSError, RuntimeError) as exc:
            return _operational_failure(
                access=access,
                problem_code="doctor_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=not report.has_errors,
            valid=not report.has_errors,
            problem_code="adapter_installation_invalid",
            problem_message="adapter installation has problems",
        )

    def create_draft(
        self,
        output: str | Path,
        repo: str | Path,
        *,
        source_agent: str = "waybill-cli",
        goal: str | None = None,
        force: bool = False,
        max_diff_bytes: int = MAX_DIFF_BYTES,
    ) -> OperationResult[DraftBundleReport]:
        access = _access("new", (repo, "read"), (output, "write"))
        try:
            report = create_draft_bundle(
                output,
                repo,
                source_agent=source_agent,
                goal=goal,
                force=force,
                max_diff_bytes=max_diff_bytes,
            )
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="draft_creation_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=True,
            valid=True,
            problem_code="draft_creation_failed",
            problem_message="draft creation failed",
        )

    def redact(
        self,
        bundle: str | Path,
        output: str | Path,
        *,
        force: bool = False,
    ) -> OperationResult[RedactionReport]:
        access = _access("redact", (bundle, "read"), (output, "write"))
        try:
            report = redact_bundle(bundle, output, force=force)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="redaction_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=True,
            valid=True,
            problem_code="redaction_failed",
            problem_message="bundle redaction failed",
        )

    def pack(
        self,
        bundle: str | Path,
        output: str | Path,
        *,
        force: bool = False,
    ) -> OperationResult[PackBundleReport]:
        access = _access("pack", (bundle, "read"), (output, "write"))
        try:
            issues = validate_bundle(bundle)
            invalid = has_errors(issues)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="bundle_validation_failed",
                error=exc,
            )
        if invalid:
            return _operation_result(
                access=access,
                payload=PackBundleReport(issues, None),
                success=False,
                valid=False,
                problem_code="bundle_invalid",
                problem_message="bundle is invalid; refusing to pack",
            )
        try:
            report = pack_bundle(bundle, output, force=force)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                payload=PackBundleReport(issues, None),
                valid=True,
                problem_code="pack_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=PackBundleReport(issues, report),
            success=True,
            valid=True,
            problem_code="pack_failed",
            problem_message="bundle packing failed",
        )

    def share_check(self, bundle: str | Path) -> OperationResult[ShareCheckReport]:
        access = _access("share-check", (bundle, "read"))
        try:
            report = check_shareability(bundle)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                payload=None,
                problem_code="share_check_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=report.shareable,
            valid=report.shareable,
            problem_code="bundle_not_shareable",
            problem_message="bundle is not shareable",
        )

    def share(
        self,
        bundle: str | Path,
        output: str | Path,
        *,
        redacted_output: str | Path | None = None,
        force: bool = False,
    ) -> OperationResult[ShareReport]:
        redacted = (
            Path(redacted_output)
            if redacted_output is not None
            else _default_redacted_output(Path(output))
        )
        access = _access(
            "share",
            (bundle, "read"),
            (output, "write"),
            (redacted, "write"),
        )
        try:
            report = share_bundle(
                bundle,
                output,
                redacted_output=redacted_output,
                force=force,
            )
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="share_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=report,
            success=True,
            valid=True,
            problem_code="share_failed",
            problem_message="bundle sharing failed",
        )

    def unpack(
        self,
        archive: str | Path,
        output: str | Path,
        *,
        force: bool = False,
    ) -> OperationResult[UnpackBundleReport]:
        access = _access("unpack", (archive, "read"), (output, "write"))
        try:
            report = unpack_bundle(archive, output, force=force)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="unpack_failed",
                error=exc,
            )
        try:
            issues = validate_bundle(report.bundle)
            valid = not has_errors(issues)
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="unpacked_bundle_validation_failed",
                error=exc,
            )
        return _operation_result(
            access=access,
            payload=UnpackBundleReport(report, issues),
            success=valid,
            valid=valid,
            problem_code="unpacked_bundle_invalid",
            problem_message="unpacked bundle is invalid",
        )

    def render(
        self,
        bundle: str | Path,
        *,
        output: str | Path | None = None,
        force: bool = False,
    ) -> OperationResult[RenderBundleReport]:
        entries: list[tuple[str | Path, RootIntentName]] = [(bundle, "read")]
        if output is not None:
            entries.append((output, "write"))
        access = _access("render", *entries)
        bundle_path = Path(bundle)
        output_path = Path(output) if output is not None else None
        try:
            issues = validate_bundle(bundle_path)
            rendered = render_bundle(bundle_path, validation_issues=issues)
            if output_path is not None:
                if bundle_path.resolve() in output_path.resolve().parents:
                    raise ValueError("output path must not be inside the source bundle")
                if output_path.exists() and not force:
                    raise FileExistsError(
                        f"output path already exists: {output_path}"
                    )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered, encoding="utf-8")
        except OPERATIONAL_ERRORS as exc:
            return _operational_failure(
                access=access,
                problem_code="render_failed",
                error=exc,
            )
        return OperationResult(
            success=True,
            valid=not has_errors(issues),
            payload=RenderBundleReport(bundle_path, output_path, rendered, issues),
            problems=(),
            access=access,
        )


def _default_redacted_output(archive: Path) -> Path:
    name = archive.with_suffix("").name if archive.suffix else archive.name
    return archive.with_name(f"{name}-redacted")
