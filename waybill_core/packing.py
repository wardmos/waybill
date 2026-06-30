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


@dataclass(frozen=True)
class UnpackReport:
    source: Path
    output: Path
    bundle: Path
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


def unpack_bundle(
    archive_path: str | Path,
    output_path: str | Path,
    *,
    force: bool = False,
) -> UnpackReport:
    source = Path(archive_path)
    output = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(f"archive path does not exist: {source}")
    if not source.is_file():
        raise FileNotFoundError(f"archive path is not a file: {source}")
    if source.suffix.lower() != ".zip":
        raise ValueError("archive path must end with .zip")

    try:
        with zipfile.ZipFile(source) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos:
                raise ValueError("archive does not contain files")

            roots = {_safe_archive_path(info.filename).parts[0] for info in infos}
            if len(roots) != 1:
                raise ValueError(
                    "archive must contain exactly one top-level directory"
                )

            archive_root = next(iter(roots))
            if output.exists():
                if not force:
                    raise FileExistsError(f"output path already exists: {output}")
                if output.is_dir():
                    shutil.rmtree(output)
                else:
                    output.unlink()

            output.mkdir(parents=True, exist_ok=True)
            files: list[PackedFile] = []

            for info in infos:
                relative = _safe_archive_path(info.filename)
                target = output / relative
                if output.resolve() not in target.resolve().parents:
                    raise ValueError(
                        f"archive path escapes output directory: {info.filename}"
                    )

                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.open(info) as source_file,
                    target.open("wb") as target_file,
                ):
                    shutil.copyfileobj(source_file, target_file)
                files.append(PackedFile(relative.as_posix(), info.file_size))
    except zipfile.BadZipFile as exc:
        raise ValueError("archive is not a valid zip file") from exc

    return UnpackReport(source, output, output / archive_root, archive_root, files)


def _safe_archive_path(name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive path: {name}")
    if len(path.parts) < 2:
        raise ValueError("archive files must live under one top-level directory")
    return path
