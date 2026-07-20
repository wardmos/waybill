"""Prepare shareable Waybill Bundle archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .limits import BundleLimitError, list_bundle_files
from .packing import PackReport, pack_bundle
from .paths import ensure_safe_output_path
from .redaction import RedactionReport, redact_bundle, redact_text
from .validation import ValidationIssue, has_errors, validate_bundle


@dataclass(frozen=True)
class ShareFinding:
    """A value-free finding from a read-only shareability check."""

    kind: str
    path: str
    count: int
    blocking: bool


@dataclass(frozen=True)
class ShareCheckReport:
    """Read-only assessment of whether a bundle can be safely shared."""

    source: Path
    findings: list[ShareFinding]

    @property
    def has_errors(self) -> bool:
        return any(finding.blocking for finding in self.findings)

    @property
    def shareable(self) -> bool:
        return not self.has_errors

    @property
    def replacement_count(self) -> int:
        return sum(
            finding.count
            for finding in self.findings
            if finding.kind == "planned-redaction"
        )

    @property
    def error_count(self) -> int:
        return sum(
            finding.count for finding in self.findings if finding.blocking
        )

    @property
    def finding_count(self) -> int:
        return sum(finding.count for finding in self.findings)


@dataclass(frozen=True)
class ShareReport:
    source: Path
    redacted: Path
    archive: Path
    redaction: RedactionReport
    pack: PackReport
    validation_issues: list[ValidationIssue]


def check_shareability(bundle_path: str | Path) -> ShareCheckReport:
    """Inspect a bundle without modifying it or creating share outputs.

    Sensitive values that the existing redaction pipeline can remove are
    reported only as aggregate planned-redaction counts. Unsafe paths, resource
    limit failures, unscannable files, and structural validation errors are
    blocking findings.
    """

    source = Path(bundle_path)
    findings: list[ShareFinding] = []

    try:
        bundle_files = list_bundle_files(source)
    except BundleLimitError as exc:
        findings.append(_limit_finding(exc))
        return ShareCheckReport(source, _sorted_findings(findings))
    except OSError:
        findings.append(ShareFinding("read-error", ".", 1, True))
        return ShareCheckReport(source, _sorted_findings(findings))

    planned_paths: set[str] = set()
    has_unscannable_files = False
    for bundle_file in bundle_files:
        relative = bundle_file.relative_path.as_posix()
        try:
            text = bundle_file.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _add_finding(
                findings,
                ShareFinding("unscannable-file", relative, 1, True),
            )
            has_unscannable_files = True
            continue
        except OSError:
            _add_finding(
                findings,
                ShareFinding("read-error", relative, 1, True),
            )
            has_unscannable_files = True
            continue

        _redacted, replacements = redact_text(text)
        if replacements:
            planned_paths.add(relative)
            _add_finding(
                findings,
                ShareFinding(
                    "planned-redaction",
                    relative,
                    replacements,
                    False,
                ),
            )

    # Validation reads required text files directly. Stop after the complete
    # scannability pass rather than risk decoding an already-blocking file.
    if has_unscannable_files:
        return ShareCheckReport(source, _sorted_findings(findings))

    try:
        issues = validate_bundle(source)
    except (BundleLimitError, OSError, UnicodeError):
        _add_finding(
            findings,
            ShareFinding("read-error", ".", 1, True),
        )
        return ShareCheckReport(source, _sorted_findings(findings))

    for issue in issues:
        relative = _relative_issue_path(source, issue.path)
        if _is_planned_sensitive_issue(issue, relative, planned_paths):
            continue
        _add_finding(
            findings,
            ShareFinding(
                (
                    "validation-error"
                    if issue.severity == "error"
                    else "validation-warning"
                ),
                relative,
                1,
                issue.severity == "error",
            ),
        )

    return ShareCheckReport(source, _sorted_findings(findings))


def share_bundle(
    bundle_path: str | Path,
    output_path: str | Path,
    *,
    redacted_output: str | Path | None = None,
    force: bool = False,
) -> ShareReport:
    source = Path(bundle_path)
    archive = Path(output_path)
    redacted = (
        Path(redacted_output)
        if redacted_output is not None
        else _default_redacted_output(archive)
    )

    _check_archive_output(source, archive, force)
    _check_scannable_files(source)
    redaction = redact_bundle(source, redacted, force=force)
    validation_issues = validate_bundle(redacted)
    if has_errors(validation_issues):
        message = validation_issues[0].format()
        raise ValueError(f"redacted bundle is invalid: {message}")

    pack = pack_bundle(redacted, archive, force=force)
    return ShareReport(
        source=source,
        redacted=redacted,
        archive=archive,
        redaction=redaction,
        pack=pack,
        validation_issues=validation_issues,
    )


def _default_redacted_output(archive: Path) -> Path:
    name = archive.name
    if archive.suffix:
        name = archive.with_suffix("").name
    return archive.with_name(f"{name}-redacted")


def _check_archive_output(source: Path, archive: Path, force: bool) -> None:
    if archive.suffix.lower() != ".zip":
        raise ValueError("output path must end with .zip")
    ensure_safe_output_path(source, archive)
    if archive.exists() and not force:
        raise FileExistsError(f"output path already exists: {archive}")


def _check_scannable_files(source: Path) -> None:
    unscannable: list[str] = []
    for file in list_bundle_files(source):
        try:
            file.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unscannable.append(file.relative_path.as_posix())

    if unscannable:
        paths = ", ".join(unscannable)
        raise ValueError(
            "cannot safely share unscannable binary or non-UTF-8 files: "
            f"{paths}"
        )


def _add_finding(
    findings: list[ShareFinding],
    finding: ShareFinding,
) -> None:
    for index, current in enumerate(findings):
        if (
            current.kind == finding.kind
            and current.path == finding.path
            and current.blocking == finding.blocking
        ):
            findings[index] = ShareFinding(
                current.kind,
                current.path,
                current.count + finding.count,
                current.blocking,
            )
            return
    findings.append(finding)


def _sorted_findings(findings: Iterable[ShareFinding]) -> list[ShareFinding]:
    return sorted(
        findings,
        key=lambda finding: (
            finding.path,
            finding.kind,
            finding.blocking,
        ),
    )


def _limit_finding(exc: BundleLimitError) -> ShareFinding:
    message = str(exc)
    if message == "bundle root must not be a symbolic link":
        return ShareFinding("unsafe-symlink", ".", 1, True)
    if message.startswith("bundle contains symbolic link: "):
        return ShareFinding(
            "unsafe-symlink",
            message.removeprefix("bundle contains symbolic link: "),
            1,
            True,
        )
    if message.startswith("bundle contains unsupported file type: "):
        return ShareFinding(
            "unsupported-file-type",
            message.removeprefix("bundle contains unsupported file type: "),
            1,
            True,
        )
    if message.startswith("bundle file resolves outside bundle: "):
        return ShareFinding(
            "unsafe-path",
            message.removeprefix("bundle file resolves outside bundle: "),
            1,
            True,
        )
    if message.startswith("bundle file is too large: "):
        relative = message.removeprefix("bundle file is too large: ").split(
            " is ",
            1,
        )[0]
        return ShareFinding("resource-limit", relative, 1, True)
    return ShareFinding("resource-limit", ".", 1, True)


def _relative_issue_path(source: Path, issue_path: str | None) -> str:
    if not issue_path:
        return "."

    candidate = Path(issue_path)
    if not candidate.is_absolute():
        normalized = candidate.as_posix()
        if normalized in {"", "."}:
            return "."
        if ".." not in candidate.parts:
            return normalized
        return "."

    try:
        relative = candidate.resolve().relative_to(source.resolve())
    except (OSError, ValueError):
        return "."
    normalized = relative.as_posix()
    return normalized if normalized not in {"", "."} else "."


def _is_planned_sensitive_issue(
    issue: ValidationIssue,
    relative_path: str,
    planned_paths: set[str],
) -> bool:
    return (
        issue.severity == "error"
        and issue.message.startswith("possible secret matching ")
        and relative_path in planned_paths
    )
