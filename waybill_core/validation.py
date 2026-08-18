"""Validation helpers for Waybill Bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .limits import BundleLimitError, list_bundle_files
from .schema_versions import (
    CURRENT_SCHEMA_VERSION,
    KNOWN_UNSUPPORTED_SCHEMA_VERSIONS,
    schema_version_status,
)


REQUIRED_BUNDLE_FILES = ["WAYBILL.md", "metadata.json"]

RECOMMENDED_BUNDLE_FILES = ["diff.patch", "commands.log", "test-summary.md"]

HANDOFF_KINDS = ["handoff", "delegation_request", "delegation_result"]
DELEGATION_RESULT_STATUSES = ["completed", "partial", "blocked"]

RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

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

DELEGATION_REQUEST_SECTIONS = [
    "Delegation Request",
    "Child Agent Task",
    "Acceptance Criteria",
    "Return Instructions",
]

DELEGATION_RESULT_SECTIONS = [
    "Delegation Result",
    "Work Completed",
    "Parent Review Notes",
    "Parent Next Step",
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

COMMAND_LOG_MARKERS = [
    ("read-only", re.compile(r"\bread(?:-|\s+)only\b")),
    (
        "bundle-writing",
        re.compile(r"\bbundle(?:-|\s+)writing\b|\bbundle\s+writes?\b"),
    ),
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

    if not _validate_bundle_limits(bundle, issues):
        return _with_bundle_relative_paths(bundle, issues)

    _validate_required_files(bundle, issues)
    metadata, version_status = _validate_metadata(bundle, issues)
    if version_status in {"invalid", "unsupported"}:
        _validate_recommended_files(bundle, issues)
        _scan_for_sensitive_content(bundle, issues)
        return _with_bundle_relative_paths(bundle, issues)

    _validate_artifacts(bundle, metadata, issues)
    _validate_waybill(bundle, issues, metadata)
    _validate_commands_log(bundle, issues)
    _validate_recommended_files(bundle, issues)
    _scan_for_sensitive_content(bundle, issues)

    return _with_bundle_relative_paths(bundle, issues)


def _with_bundle_relative_paths(
    bundle: Path,
    issues: list[ValidationIssue],
) -> list[ValidationIssue]:
    normalized: list[ValidationIssue] = []
    for issue in issues:
        path = issue.path
        if path is not None:
            try:
                relative = Path(path).relative_to(bundle)
            except ValueError:
                pass
            else:
                path = relative.as_posix()
        normalized.append(ValidationIssue(issue.severity, issue.message, path))
    return normalized


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _validate_bundle_limits(bundle: Path, issues: list[ValidationIssue]) -> bool:
    try:
        list_bundle_files(bundle)
    except BundleLimitError as exc:
        issues.append(ValidationIssue("error", str(exc), str(bundle)))
        return False
    return True


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


def _validate_metadata(
    bundle: Path,
    issues: list[ValidationIssue],
) -> tuple[dict[str, Any] | None, str]:
    path = bundle / "metadata.json"
    if not path.is_file():
        return None, "invalid"

    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeError:
        issues.append(
            ValidationIssue(
                "error",
                "metadata.json must be UTF-8 text",
                str(path),
            )
        )
        return None, "invalid"
    except OSError:
        issues.append(
            ValidationIssue(
                "error",
                "metadata.json could not be read",
                str(path),
            )
        )
        return None, "invalid"
    except json.JSONDecodeError as exc:
        issues.append(ValidationIssue("error", f"metadata.json is invalid JSON: {exc}", str(path)))
        return None, "invalid"

    if not isinstance(metadata, dict):
        issues.append(
            ValidationIssue(
                "error",
                "metadata.json must contain an object",
                str(path),
            )
        )
        return None, "invalid"

    required = ["schema_version", "source_agent", "created_at", "repo_root", "git", "artifacts"]
    for key in required:
        if key not in metadata:
            issues.append(ValidationIssue("error", f"metadata.json missing {key}", str(path)))

    version = metadata.get("schema_version")
    version_status = schema_version_status(version)
    if version_status == "invalid":
        if "schema_version" in metadata:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata schema_version must be a non-empty string",
                    str(path),
                )
            )
        return metadata, version_status
    if version_status == "legacy":
        issues.append(
            ValidationIssue(
                "warning",
                f"metadata schema_version {version} is legacy; "
                f"current version is {CURRENT_SCHEMA_VERSION}",
                str(path),
            )
        )
    elif version_status == "unsupported":
        if version in KNOWN_UNSUPPORTED_SCHEMA_VERSIONS:
            message = (
                f"metadata schema_version {version} is unsupported; migrate or "
                f"regenerate the bundle with schema_version {CURRENT_SCHEMA_VERSION}"
            )
        else:
            message = (
                f"metadata schema_version {version} is unsupported; "
                f"current version is {CURRENT_SCHEMA_VERSION}"
            )
        issues.append(ValidationIssue("error", message, str(path)))
        return metadata, version_status

    if "source_agent" in metadata and not _is_non_empty_string(metadata.get("source_agent")):
        issues.append(
            ValidationIssue(
                "error",
                "metadata source_agent must be a non-empty string",
                str(path),
            )
        )
    if "created_at" in metadata and not _is_rfc3339_date_time(metadata.get("created_at")):
        issues.append(
            ValidationIssue(
                "error",
                "metadata created_at must be an RFC 3339 date-time",
                str(path),
            )
        )
    if "repo_root" in metadata and not _is_non_empty_string(metadata.get("repo_root")):
        issues.append(
            ValidationIssue(
                "error",
                "metadata repo_root must be a non-empty string",
                str(path),
            )
        )

    git = metadata.get("git")
    if not isinstance(git, dict):
        issues.append(ValidationIssue("error", "metadata git must be an object", str(path)))
    else:
        for key in ["branch", "base_ref", "head_sha", "dirty"]:
            if key not in git:
                issues.append(ValidationIssue("error", f"metadata git missing {key}", str(path)))
        for key in ["branch", "base_ref", "head_sha"]:
            if key in git and not _is_non_empty_string(git.get(key)):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"metadata git.{key} must be a non-empty string",
                        str(path),
                    )
                )
        if "dirty" in git and not isinstance(git.get("dirty"), bool):
            issues.append(ValidationIssue("error", "metadata git.dirty must be boolean", str(path)))
        for key in ["status_digest", "repo_state_digest"]:
            if key in git and not _is_sha256_digest(git.get(key)):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"metadata git.{key} must be a sha256 digest",
                        str(path),
                    )
                )

    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict):
        issues.append(ValidationIssue("error", "metadata artifacts must be an object", str(path)))
    else:
        if "waybill" not in artifacts:
            issues.append(ValidationIssue("error", "metadata artifacts missing waybill", str(path)))
        for name, artifact in artifacts.items():
            if not _is_non_empty_string(artifact):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"metadata artifacts.{name} must be a non-empty string",
                        str(path),
                    )
                )
        if "waybill" in artifacts and artifacts.get("waybill") != "WAYBILL.md":
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata artifacts.waybill must be WAYBILL.md",
                    str(path),
                )
            )

    _validate_handoff_metadata(metadata, path, issues)

    return metadata, version_status


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_rfc3339_date_time(value: Any) -> bool:
    if not isinstance(value, str) or RFC3339_DATE_TIME.fullmatch(value) is None:
        return False

    normalized = value
    if normalized[-1] in {"Z", "z"}:
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and SHA256_DIGEST.fullmatch(value) is not None


def _validate_handoff_metadata(
    metadata: dict[str, Any],
    metadata_path: Path,
    issues: list[ValidationIssue],
) -> None:
    if "handoff" not in metadata:
        return

    handoff = metadata.get("handoff")
    if not isinstance(handoff, dict):
        issues.append(
            ValidationIssue(
                "error",
                "metadata handoff must be an object",
                str(metadata_path),
            )
        )
        return

    kind = handoff.get("kind", "handoff")
    if "kind" in handoff:
        if not isinstance(kind, str):
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata handoff.kind must be a string",
                    str(metadata_path),
                )
            )
        elif kind not in HANDOFF_KINDS:
            allowed = ", ".join(HANDOFF_KINDS)
            issues.append(
                ValidationIssue(
                    "error",
                    f"metadata handoff.kind must be one of: {allowed}",
                    str(metadata_path),
                )
            )

    for field in ["parent_agent", "child_agent", "request_id", "result_for"]:
        if field in handoff and not _is_non_empty_string(handoff.get(field)):
            issues.append(
                ValidationIssue(
                    "error",
                    f"metadata handoff.{field} must be a non-empty string",
                    str(metadata_path),
                )
            )

    if "result_status" in handoff and handoff.get(
        "result_status"
    ) not in DELEGATION_RESULT_STATUSES:
        allowed = ", ".join(DELEGATION_RESULT_STATUSES)
        issues.append(
            ValidationIssue(
                "error",
                f"metadata handoff.result_status must be one of: {allowed}",
                str(metadata_path),
            )
        )

    if kind == "delegation_request":
        _require_handoff_fields(
            handoff,
            ["request_id", "parent_agent", "child_agent"],
            kind,
            metadata_path,
            issues,
        )
        parent = handoff.get("parent_agent")
        if _is_non_empty_string(parent) and metadata.get("source_agent") != parent:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata source_agent must match handoff.parent_agent "
                    "for delegation_request",
                    str(metadata_path),
                )
            )
    elif kind == "delegation_result":
        _require_handoff_fields(
            handoff,
            ["result_for", "result_status", "parent_agent", "child_agent"],
            kind,
            metadata_path,
            issues,
        )
        child = handoff.get("child_agent")
        if _is_non_empty_string(child) and metadata.get("source_agent") != child:
            issues.append(
                ValidationIssue(
                    "error",
                    "metadata source_agent must match handoff.child_agent "
                    "for delegation_result",
                    str(metadata_path),
                )
            )


def _require_handoff_fields(
    handoff: dict[str, Any],
    fields: list[str],
    kind: str,
    metadata_path: Path,
    issues: list[ValidationIssue],
) -> None:
    for field in fields:
        if field not in handoff:
            issues.append(
                ValidationIssue(
                    "error",
                    f"metadata handoff.{field} is required for {kind}",
                    str(metadata_path),
                )
            )


def _handoff_kind(metadata: dict[str, Any] | None) -> str:
    if not metadata or "handoff" not in metadata:
        return "handoff"

    handoff = metadata.get("handoff")
    if not isinstance(handoff, dict):
        return "handoff"

    kind = handoff.get("kind", "handoff")
    if not isinstance(kind, str):
        return "handoff"
    if kind not in HANDOFF_KINDS:
        return "handoff"
    return kind


def _validate_artifacts(
    bundle: Path,
    metadata: dict[str, Any] | None,
    issues: list[ValidationIssue],
) -> None:
    if not metadata or not isinstance(metadata.get("artifacts"), dict):
        return

    for artifact in metadata["artifacts"].values():
        if not _is_non_empty_string(artifact):
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


def _validate_waybill(
    bundle: Path,
    issues: list[ValidationIssue],
    metadata: dict[str, Any] | None = None,
) -> None:
    path = bundle / "WAYBILL.md"
    if not path.is_file():
        return

    text = path.read_text()
    for section in WAYBILL_SECTIONS:
        if f"## {section}" not in text:
            issues.append(
                ValidationIssue("error", f"WAYBILL.md missing section: {section}", str(path))
            )

    kind = _handoff_kind(metadata)
    if kind == "delegation_request":
        _validate_waybill_sections(text, DELEGATION_REQUEST_SECTIONS, path, issues)
    elif kind == "delegation_result":
        _validate_waybill_sections(text, DELEGATION_RESULT_SECTIONS, path, issues)

    for phrase in BAD_AGENT_PHRASES:
        if phrase in text:
            issues.append(ValidationIssue("error", f"agent-specific phrase found: {phrase}", str(path)))


def _validate_waybill_sections(
    text: str,
    sections: list[str],
    path: Path,
    issues: list[ValidationIssue],
) -> None:
    for section in sections:
        if f"## {section}" not in text:
            issues.append(
                ValidationIssue("error", f"WAYBILL.md missing section: {section}", str(path))
            )


def _validate_commands_log(bundle: Path, issues: list[ValidationIssue]) -> None:
    path = bundle / "commands.log"
    if not path.is_file():
        return

    text = " ".join(path.read_text().split()).lower()
    for label, pattern in COMMAND_LOG_MARKERS:
        if pattern.search(text) is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    f"commands.log should identify {label} commands/actions",
                    str(path),
                )
            )


def _scan_for_sensitive_content(bundle: Path, issues: list[ValidationIssue]) -> None:
    for file in list_bundle_files(bundle):
        path = file.path
        relative_path = file.relative_path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(
                ValidationIssue(
                    "warning",
                    "could not scan binary or non-UTF-8 file",
                    relative_path,
                )
            )
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"possible secret matching {pattern.pattern}",
                        relative_path,
                    )
                )
