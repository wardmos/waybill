"""Markdown rendering helpers for Waybill Bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validation import ValidationIssue, validate_bundle


def render_bundle(
    bundle_path: str | Path,
    validation_issues: list[ValidationIssue] | None = None,
) -> str:
    bundle = Path(bundle_path)
    issues = (
        validation_issues
        if validation_issues is not None
        else validate_bundle(bundle)
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]

    lines = [
        "# Waybill Bundle Report",
        "",
        f"- Bundle: `{bundle}`",
        f"- Validation: {len(errors)} error(s), {len(warnings)} warning(s)",
        "",
    ]

    metadata, metadata_error = _read_metadata(bundle)
    lines.extend(_render_metadata(metadata, metadata_error))
    lines.extend(_render_artifacts(bundle, metadata))
    lines.extend(_render_validation(issues))
    lines.extend(_render_waybill(bundle))

    return "\n".join(lines).rstrip() + "\n"


def _read_metadata(bundle: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = bundle / "metadata.json"
    if not path.is_file():
        return None, "metadata.json is missing"
    try:
        metadata = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, f"metadata.json is invalid JSON: {exc}"
    if not isinstance(metadata, dict):
        return None, "metadata.json must contain an object"
    return metadata, None


def _render_metadata(
    metadata: dict[str, Any] | None,
    metadata_error: str | None,
) -> list[str]:
    lines = ["## Metadata", ""]
    if metadata_error:
        lines.extend([metadata_error, ""])
        return lines

    metadata = metadata or {}
    git = metadata.get("git") if isinstance(metadata.get("git"), dict) else {}
    rows = [
        ("Schema status", metadata.get("schema_version")),
        ("Source agent", metadata.get("source_agent")),
        ("Created at", metadata.get("created_at")),
        ("Repo root", metadata.get("repo_root")),
        ("Git branch", git.get("branch")),
        ("Git base ref", git.get("base_ref")),
        ("Git head SHA", git.get("head_sha")),
        ("Git dirty", git.get("dirty")),
    ]

    lines.extend(["| Field | Value |", "| --- | --- |"])
    for field, value in rows:
        lines.append(f"| {field} | {_markdown_cell(value)} |")
    lines.append("")
    return lines


def _render_artifacts(bundle: Path, metadata: dict[str, Any] | None) -> list[str]:
    lines = ["## Artifacts", ""]
    artifacts = metadata.get("artifacts") if isinstance(metadata, dict) else None

    if not isinstance(artifacts, dict):
        lines.extend(["No artifact metadata found.", ""])
        return lines

    lines.extend(["| Name | Path | Status | Bytes |", "| --- | --- | --- | ---: |"])
    for name, artifact in artifacts.items():
        if not isinstance(artifact, str):
            lines.append(f"| {_markdown_cell(name)} | invalid | invalid | 0 |")
            continue
        path = bundle / artifact
        status = "present" if path.is_file() else "missing"
        size = path.stat().st_size if path.is_file() else 0
        lines.append(
            f"| {_markdown_cell(name)} | `{_markdown_cell(artifact)}` | "
            f"{status} | {size} |"
        )
    lines.append("")
    return lines


def _render_validation(issues: list[ValidationIssue]) -> list[str]:
    lines = ["## Validation", ""]
    if not issues:
        lines.extend(["No validation issues found.", ""])
        return lines

    for issue in issues:
        path = f" `{issue.path}`" if issue.path else ""
        lines.append(f"- {issue.severity.upper()}{path}: {issue.message}")
    lines.append("")
    return lines


def _render_waybill(bundle: Path) -> list[str]:
    lines = ["## WAYBILL.md", ""]
    path = bundle / "WAYBILL.md"
    if not path.is_file():
        lines.extend(["WAYBILL.md is missing.", ""])
        return lines

    try:
        text = path.read_text()
    except UnicodeDecodeError:
        lines.extend(["WAYBILL.md is not UTF-8 text.", ""])
        return lines

    lines.extend(["```markdown", text.rstrip(), "```", ""])
    return lines


def _markdown_cell(value: object) -> str:
    if value is None or value == "":
        return "unknown"
    return str(value).replace("|", "\\|").replace("\n", " ")
