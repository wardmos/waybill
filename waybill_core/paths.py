"""Filesystem path safety helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_safe_output_path(
    source_path: str | Path,
    output_path: str | Path,
) -> None:
    """Reject output paths that overlap a source or are symbolic links."""

    source = Path(source_path)
    output = Path(output_path)

    if output.is_symlink():
        raise ValueError(f"output path must not be a symbolic link: {output}")

    source_resolved = source.resolve()
    output_resolved = output.resolve()

    if output_resolved == source_resolved:
        raise ValueError("output path must be different from the source path")
    if source_resolved in output_resolved.parents:
        raise ValueError("output path must not be inside the source path")
    if output_resolved in source_resolved.parents:
        raise ValueError("output path must not contain the source path")
