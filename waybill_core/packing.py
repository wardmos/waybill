"""Archive helpers for Waybill Bundles."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackedFile:
    path: str
    size: int


@dataclass(frozen=True)
class PackReport:
    source: Path
    output: Path
    archive_root: str
    files: list[PackedFile]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def byte_count(self) -> int:
        return sum(file.size for file in self.files)


def pack_bundle(
    bundle_path: str | Path,
    output_path: str | Path,
    *,
    force: bool = False,
) -> PackReport:
    source = Path(bundle_path)
    output = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(f"bundle path does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"bundle path is not a directory: {source}")
    if output.suffix.lower() != ".zip":
        raise ValueError("output path must end with .zip")

    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if source_resolved in output_resolved.parents:
        raise ValueError("output path must not be inside the source bundle")

    if output.exists():
        if not force:
            raise FileExistsError(f"output path already exists: {output}")
        if output.is_dir():
            shutil.rmtree(output)
        else:
            output.unlink()

    output.parent.mkdir(parents=True, exist_ok=True)
    archive_root = source.name or "waybill"
    files: list[PackedFile] = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_file in sorted(path for path in source.rglob("*") if path.is_file()):
            relative = source_file.relative_to(source)
            archive_path = Path(archive_root) / relative
            archive.write(source_file, archive_path.as_posix())
            files.append(
                PackedFile(archive_path.as_posix(), source_file.stat().st_size)
            )

    return PackReport(source, output, archive_root, files)
