"""Prepare shareable Waybill Bundle archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .limits import list_bundle_files
from .packing import PackReport, pack_bundle
from .paths import ensure_safe_output_path
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
