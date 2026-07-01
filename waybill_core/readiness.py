"""Export readiness checks for Waybill Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .repo import RepoVerificationReport, verify_repo_state
from .validation import ValidationIssue, has_errors, validate_bundle


PLACEHOLDER_PHRASES = [
    "TODO:",
    "Draft bundle created by `waybill new`",
    "Not recorded yet.",
    "state the user's original task",
    "Replace this section",
]


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class ExportReadinessReport:
    bundle: Path
    repo: Path
    validation_issues: list[ValidationIssue]
    repo_report: RepoVerificationReport
    content_checks: list[ReadinessCheck]

    @property
    def has_errors(self) -> bool:
        return (
            has_errors(self.validation_issues)
            or self.repo_report.has_errors
            or any(check.status == "error" for check in self.content_checks)
        )


def check_export_readiness(
    bundle_path: str | Path,
    repo_path: str | Path,
) -> ExportReadinessReport:
    bundle = Path(bundle_path)
    repo = Path(repo_path)
    validation_issues = validate_bundle(bundle)
    repo_report = verify_repo_state(bundle, repo)
    content_checks = _check_content(bundle)
    return ExportReadinessReport(
        bundle,
        repo,
        validation_issues,
        repo_report,
        content_checks,
    )


def _check_content(bundle: Path) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    _check_no_placeholders(bundle / "WAYBILL.md", "WAYBILL.md", checks)
    _check_no_placeholders(bundle / "test-summary.md", "test-summary.md", checks)
    _check_no_placeholders(bundle / "commands.log", "commands.log", checks)
    if not checks:
        checks.append(ReadinessCheck("content", "ok", "no draft placeholders found"))
    return checks


def _check_no_placeholders(
    path: Path,
    label: str,
    checks: list[ReadinessCheck],
) -> None:
    if not path.is_file():
        return

    try:
        text = path.read_text()
    except UnicodeDecodeError:
        checks.append(
            ReadinessCheck(
                label,
                "warning",
                "could not scan non-UTF-8 text",
                str(path),
            )
        )
        return

    found = [phrase for phrase in PLACEHOLDER_PHRASES if phrase in text]
    if found:
        joined = ", ".join(repr(phrase) for phrase in found)
        checks.append(
            ReadinessCheck(
                label,
                "error",
                f"draft placeholder found: {joined}",
                str(path),
            )
        )
