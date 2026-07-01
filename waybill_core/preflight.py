"""Import preflight checks for Waybill Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .repo import RepoVerificationReport, verify_repo_state
from .validation import ValidationIssue, has_errors, validate_bundle


@dataclass(frozen=True)
class ImportPreflightReport:
    bundle: Path
    repo: Path
    validation_issues: list[ValidationIssue]
    repo_report: RepoVerificationReport

    @property
    def validation_errors(self) -> list[ValidationIssue]:
        return [
            issue for issue in self.validation_issues if issue.severity == "error"
        ]

    @property
    def validation_warnings(self) -> list[ValidationIssue]:
        return [
            issue for issue in self.validation_issues if issue.severity == "warning"
        ]

    @property
    def has_errors(self) -> bool:
        return has_errors(self.validation_issues) or self.repo_report.has_errors


def run_import_preflight(
    bundle_path: str | Path,
    repo_path: str | Path,
) -> ImportPreflightReport:
    bundle = Path(bundle_path)
    repo = Path(repo_path)
    validation_issues = validate_bundle(bundle)
    repo_report = verify_repo_state(bundle, repo)
    return ImportPreflightReport(bundle, repo, validation_issues, repo_report)
