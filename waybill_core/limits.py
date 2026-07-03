"""Resource limits for local Waybill operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MAX_DIFF_BYTES = 1_000_000
MAX_BUNDLE_FILES = 100
MAX_BUNDLE_FILE_BYTES = 5_000_000
MAX_BUNDLE_BYTES = 10_000_000


class BundleLimitError(ValueError):
    """Raised when a bundle exceeds supported local resource limits."""


@dataclass(frozen=True)
class BundleFile:
    path: Path
    relative_path: Path
    size: int


def format_bytes(size: int) -> str:
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} GiB"


def list_bundle_files(
    root: str | Path,
    *,
    max_files: int = MAX_BUNDLE_FILES,
    max_file_bytes: int = MAX_BUNDLE_FILE_BYTES,
    max_total_bytes: int = MAX_BUNDLE_BYTES,
) -> list[BundleFile]:
    bundle = Path(root)
    files: list[BundleFile] = []
    total_bytes = 0

    for path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        relative = path.relative_to(bundle)
        if len(files) + 1 > max_files:
            raise BundleLimitError(
                f"bundle contains more than {max_files} files"
            )

        size = path.stat().st_size
        if size > max_file_bytes:
            raise BundleLimitError(
                f"bundle file is too large: {relative} is "
                f"{format_bytes(size)}, limit is {format_bytes(max_file_bytes)}"
            )

        total_bytes += size
        if total_bytes > max_total_bytes:
            raise BundleLimitError(
                f"bundle is too large: {format_bytes(total_bytes)}, "
                f"limit is {format_bytes(max_total_bytes)}"
            )

        files.append(BundleFile(path, relative, size))

    return files
