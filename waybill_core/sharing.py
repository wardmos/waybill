"""Prepare shareable Waybill Bundle archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .packing import PackReport, pack_bundle
from .redaction import RedactionReport, redact_bundle
from .validation import ValidationIssue, has_errors, validate_bundle


@dataclass(frozen=True)
class ShareReport:
    source: Path
    redacted: Path
    archive: Path
    redaction: RedactionReport
    pack: PackReport
    validation_issues: list[ValidationIssue]


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

    _check_archive_output(archive, force)
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


def _check_archive_output(archive: Path, force: bool) -> None:
    if archive.suffix.lower() != ".zip":
        raise ValueError("output path must end with .zip")
    if archive.exists() and not force:
        raise FileExistsError(f"output path already exists: {archive}")
