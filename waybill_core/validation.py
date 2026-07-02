"""Validation helpers for Waybill Bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_BUNDLE_FILES = ["WAYBILL.md", "metadata.json"]

RECOMMENDED_BUNDLE_FILES = ["diff.patch", "commands.log", "test-summary.md"]

WAYBILL_SECTIONS = [
    "Original Goal",
    "Current Status",
    "User Constraints",
    "Repo State",
    "Changed Files",
    "Commands Run",
    "Test State",
    "Failed Attempts",
    "Current Hypothesis",
    "Next Recommended Step",
    "Risks / Unknowns",
    "Instructions For Next Agent",
]

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"sk-[A-Za-z0-9_-]{10,}",
        r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]+",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"(?<!\S)/(?:home|Users)/[^\s\"'`<>]+",
        r"\b[A-Za-z]:\\Users\\[^\s\"'`<>]+",
        (
            r"(?<![A-Za-z0-9_-])"
            r"['\"]?(api[_-]?key|password|secret|token|cookie)['\"]?"
            r"(?![A-Za-z0-9_-])"
            r"\s*[:=]\s*['\"]?(?!\[REDACTED\])[^\"'\s,}]+"
        ),
    ]
]

BAD_AGENT_PHRASES = [
    "Claude should",
    "Claude must",
    "Codex should",
    "Codex must",
]

COMMAND_LOG_TERMS = [
    "read-only",
    "bundle-writing",
]


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    message: str
    path: str | None = None

    def format(self) -> str:
        location = f" {self.path}" if self.path else ""
        return f"{self.severity.upper()}{location}: {self.message}"


def validate_bundle(bundle_path: str | Path) -> list[ValidationIssue]:
    """Validate a Waybill Bundle directory.

    Returns a list of errors and warnings. A bundle is valid when there are no
    issues with severity ``error``.
    """

    bundle = Path(bundle_path)
    issues: list[ValidationIssue] = []

    if not bundle.exists():
        return [ValidationIssue("error", "bundle path does not exist", str(bundle))]
    if not bundle.is_dir():
        return [ValidationIssue("error", "bundle path is not a directory", str(bundle))]

    _validate_required_files(bundle, issues)
    metadata = _validate_metadata(bundle, issues)
    _validate_artifacts(bundle, metadata, issues)
    _validate_waybill(bundle, issues)
    _validate_commands_log(bundle, issues)
    _validate_recommended_files(bundle, issues)
    _scan_for_sensitive_content(bundle, issues)

    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _validate_required_files(bundle: Path, issues: list[ValidationIssue]) -> None:
    for name in REQUIRED_BUNDLE_FILES:
        if not (bundle / name).is_file():
            issues.append(
                ValidationIssue("error", f"missing required file {name}", str(bundle / name))
            )


def _validate_recommended_files(bundle: Path, issues: list[ValidationIssue]) -> None:
    for name in RECOMMENDED_BUNDLE_FILES:
        if not (bundle / name).is_file():
            issues.append(
                ValidationIssue("warning", f"missing recommended file {name}", str(bundle / name))
            )


def _validate_metadata(bundle: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    path = bundle / "metadata.json"
    if not path.is_file():
        return None

    try:
        metadata = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        issues.append(ValidationIssue("error", f"metadata.json is invalid JSON: {exc}", str(path)))
        return None

    required = ["schema_version", "source_agent", "created_at", "repo_root", "git", "artifacts"]
    for key in required:
        if key not in metadata:
            issues.append(ValidationIssue("error", f"metadata.json missing {key}", str(path)))

    if metadata.get("schema_version") != "draft":
        issues.append(ValidationIssue("error", "metadata schema_version must be draft", str(path)))

    if not isinstance(metadata.get("source_agent"), str) or not metadata.get("source_agent"):
        issues.append(ValidationIssue("error", "metadata source_agent must be a non-empty string", str(path)))

    git = metadata.get("git")
    if not isinstance(git, dict):
        issues.append(ValidationIssue("error", "metadata git must be an object", str(path)))
    else:
        for key in ["branch", "base_ref", "head_sha", "dirty"]:
            if key not in git:
                issues.append(ValidationIssue("error", f"metadata git missing {key}", str(path)))
        if "dirty" in git and not isinstance(git.get("dirty"), bool):
            issues.append(ValidationIssue("error", "metadata git.dirty must be boolean", str(path)))

    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict):
        issues.append(ValidationIssue("error", "metadata artifacts must be an object", str(path)))
    elif artifacts.get("waybill") != "WAYBILL.md":
        issues.append(ValidationIssue("error", "metadata artifacts.waybill must be WAYBILL.md", str(path)))

    return metadata


def _validate_artifacts(
    bundle: Path,
    metadata: dict[str, Any] | None,
    issues: list[ValidationIssue],
) -> None:
    if not metadata or not isinstance(metadata.get("artifacts"), dict):
        return

    for artifact in metadata["artifacts"].values():
        if not isinstance(artifact, str):
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata artifact paths must be strings",
                    str(bundle / "metadata.json"),
                )
            )
            continue
        if artifact.startswith("/") or ".." in Path(artifact).parts:
            issues.append(
                ValidationIssue(
                    "error",
                    f"artifact path must stay inside bundle: {artifact}",
                    str(bundle / "metadata.json"),
                )
            )
            continue
        if not (bundle / artifact).is_file():
            issues.append(
                ValidationIssue(
                    "error",
                    f"metadata artifact does not exist: {artifact}",
                    str(bundle / artifact),
                )
            )


def _validate_waybill(bundle: Path, issues: list[ValidationIssue]) -> None:
    path = bundle / "WAYBILL.md"
    if not path.is_file():
        return

    text = path.read_text()
    for section in WAYBILL_SECTIONS:
        if f"## {section}" not in text:
            issues.append(
                ValidationIssue("error", f"WAYBILL.md missing section: {section}", str(path))
            )

    for phrase in BAD_AGENT_PHRASES:
        if phrase in text:
            issues.append(ValidationIssue("error", f"agent-specific phrase found: {phrase}", str(path)))


def _validate_commands_log(bundle: Path, issues: list[ValidationIssue]) -> None:
    path = bundle / "commands.log"
    if not path.is_file():
        return

    text = " ".join(path.read_text().split()).lower()
    for term in COMMAND_LOG_TERMS:
        if term not in text:
            issues.append(
                ValidationIssue(
                    "warning",
                    f"commands.log should mention {term} commands/actions",
                    str(path),
                )
            )


def _scan_for_sensitive_content(bundle: Path, issues: list[ValidationIssue]) -> None:
    for path in bundle.iterdir():
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            issues.append(ValidationIssue("warning", "could not scan binary or non-UTF-8 file", str(path)))
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(ValidationIssue("error", f"possible secret matching {pattern.pattern}", str(path)))
