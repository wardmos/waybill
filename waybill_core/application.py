"""Transport-neutral application facade for Waybill use cases.

The facade exposes operation outcomes, stable problem codes, and the filesystem
roots an operation is allowed to read or write.  It deliberately contains no
argument parsing, terminal output, or JSON rendering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Literal, TypeVar

from .delegation import DelegationPairReport, verify_delegation_pair
from .preflight import ImportPreflightReport, run_import_preflight
from .readiness import ExportReadinessReport, check_export_readiness
from .repo import RepoVerificationReport, verify_repo_state
from .validation import ValidationIssue, has_errors, validate_bundle


T = TypeVar("T")
AccessIntentName = Literal["read", "write"]


@dataclass(frozen=True)
class AccessIntent:
    """Filesystem authority required by one application operation."""

    operation: str
    roots: tuple[Path, ...]
    intent: AccessIntentName


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
    payload: T
    problems: tuple[Problem, ...]
    access: AccessIntent


@dataclass(frozen=True)
class InspectBundleReport:
    """Bundle metadata and validation evidence used by inspect renderers."""

    bundle: Path
    metadata: dict[str, object] | None
    metadata_error: str | None
    validation_issues: list[ValidationIssue]


def _roots(*paths: str | Path) -> tuple[Path, ...]:
    return tuple(Path(path).resolve() for path in paths)


def _result(
    *,
    operation: str,
    roots: tuple[Path, ...],
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
        access=AccessIntent(operation=operation, roots=roots, intent="read"),
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


class WaybillApplication:
    """Run Waybill use cases without assuming a CLI or another transport."""

    def validate(self, bundle: str | Path) -> OperationResult[list[ValidationIssue]]:
        issues = validate_bundle(bundle)
        valid = not has_errors(issues)
        return _result(
            operation="validate",
            roots=_roots(bundle),
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
        report = verify_repo_state(bundle, repo)
        return _result(
            operation="verify-repo",
            roots=_roots(bundle, repo),
            payload=report,
            valid=not report.has_errors,
            problem_code="repository_mismatch",
            problem_message="bundle repository state does not match",
        )

    def verify_pair(
        self,
        request: str | Path,
        result: str | Path,
    ) -> OperationResult[DelegationPairReport]:
        report = verify_delegation_pair(request, result)
        return _result(
            operation="verify-pair",
            roots=_roots(request, result),
            payload=report,
            valid=not report.has_errors,
            problem_code="delegation_pair_mismatch",
            problem_message="delegation result does not match request",
        )

    def preflight(
        self,
        bundle: str | Path,
        repo: str | Path,
    ) -> OperationResult[ImportPreflightReport]:
        report = run_import_preflight(bundle, repo)
        return _result(
            operation="preflight",
            roots=_roots(bundle, repo),
            payload=report,
            valid=not report.has_errors,
            problem_code="import_preflight_failed",
            problem_message="import preflight found blocking issues",
        )

    def ready(
        self,
        bundle: str | Path,
        repo: str | Path,
    ) -> OperationResult[ExportReadinessReport]:
        report = check_export_readiness(bundle, repo)
        return _result(
            operation="ready",
            roots=_roots(bundle, repo),
            payload=report,
            valid=not report.has_errors,
            problem_code="bundle_not_ready",
            problem_message="bundle is not ready for handoff",
        )

    def inspect(self, bundle: str | Path) -> OperationResult[InspectBundleReport]:
        bundle_path = Path(bundle)
        issues = validate_bundle(bundle_path)
        metadata, metadata_error = read_bundle_metadata(bundle_path)
        report = InspectBundleReport(
            bundle=bundle_path,
            metadata=metadata,
            metadata_error=metadata_error,
            validation_issues=issues,
        )
        return _result(
            operation="inspect",
            roots=_roots(bundle_path),
            payload=report,
            valid=not has_errors(issues),
            problem_code="bundle_inspection_failed",
            problem_message="bundle inspection found blocking issues",
        )
