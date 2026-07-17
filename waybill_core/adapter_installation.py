"""Deterministic manifests for Waybill adapter installations."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .adapter_sources import INSTALL_ADAPTERS, sources_for_adapter


MANIFEST_FILENAME = ".waybill-adapters.json"
MANIFEST_FORMAT_VERSION = 1
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class InstallationManifestError(ValueError):
    """Raised when an adapter installation manifest is unsafe or malformed."""


@dataclass(frozen=True)
class AdapterFileRecord:
    """The adapter and installed-content digest for one managed file."""

    adapter: str
    sha256: str


@dataclass(frozen=True)
class AdapterInstallationManifest:
    """A deterministic record of files written by ``waybill init``."""

    format_version: int
    waybill_version: str
    files: dict[str, AdapterFileRecord]


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise InstallationManifestError(f"duplicate manifest field: {key}")
        document[key] = value
    return document


def _validate_target_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InstallationManifestError("manifest file paths must be strings")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise InstallationManifestError(f"unsafe manifest file path: {value!r}")

    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or value == "."
        or path.as_posix() != value
    ):
        raise InstallationManifestError(f"unsafe manifest file path: {value!r}")
    return value


def _record_from_document(path: str, value: object) -> AdapterFileRecord:
    if not isinstance(value, dict) or set(value) != {"adapter", "sha256"}:
        raise InstallationManifestError(
            f"manifest record for {path} must contain adapter and sha256"
        )

    adapter = value["adapter"]
    digest = value["sha256"]
    if not isinstance(adapter, str) or adapter not in INSTALL_ADAPTERS:
        raise InstallationManifestError(
            f"manifest record for {path} has an unsupported adapter"
        )
    expected_paths = {
        source.install_target for source in sources_for_adapter(adapter)
    }
    if path not in expected_paths:
        raise InstallationManifestError(
            f"manifest path {path} does not belong to adapter {adapter}"
        )
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise InstallationManifestError(
            f"manifest record for {path} has an invalid sha256"
        )
    return AdapterFileRecord(adapter=adapter, sha256=digest)


def _manifest_from_document(document: object) -> AdapterInstallationManifest:
    if not isinstance(document, dict):
        raise InstallationManifestError("installation manifest must be a JSON object")
    if set(document) != {"format_version", "waybill_version", "files"}:
        raise InstallationManifestError(
            "installation manifest must contain only format_version, "
            "waybill_version, and files"
        )

    format_version = document["format_version"]
    if type(format_version) is not int or format_version != MANIFEST_FORMAT_VERSION:
        raise InstallationManifestError(
            f"unsupported installation manifest format: {format_version!r}"
        )

    waybill_version = document["waybill_version"]
    if not isinstance(waybill_version, str) or not waybill_version:
        raise InstallationManifestError("manifest waybill_version must be a string")

    raw_files = document["files"]
    if not isinstance(raw_files, dict):
        raise InstallationManifestError("manifest files must be an object")

    files: dict[str, AdapterFileRecord] = {}
    for raw_path in sorted(raw_files):
        path = _validate_target_path(raw_path)
        files[path] = _record_from_document(path, raw_files[raw_path])

    return AdapterInstallationManifest(
        format_version=format_version,
        waybill_version=waybill_version,
        files=files,
    )


def _manifest_document(
    manifest: AdapterInstallationManifest,
) -> dict[str, object]:
    document = {
        "format_version": manifest.format_version,
        "waybill_version": manifest.waybill_version,
        "files": {
            path: {
                "adapter": record.adapter,
                "sha256": record.sha256,
            }
            for path, record in sorted(manifest.files.items())
        },
    }
    validated = _manifest_from_document(document)
    return {
        "format_version": validated.format_version,
        "waybill_version": validated.waybill_version,
        "files": {
            path: {
                "adapter": record.adapter,
                "sha256": record.sha256,
            }
            for path, record in validated.files.items()
        },
    }


def serialize_installation_manifest(
    manifest: AdapterInstallationManifest,
) -> bytes:
    """Return stable UTF-8 JSON bytes for an installation manifest."""

    return (
        json.dumps(
            _manifest_document(manifest),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _manifest_path_state(path: Path) -> os.stat_result | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        raise InstallationManifestError(
            f"installation manifest must not be a symbolic link: {path}"
        )
    if not stat.S_ISREG(metadata.st_mode):
        raise InstallationManifestError(
            f"installation manifest must be a regular file: {path}"
        )
    return metadata


def load_installation_manifest(
    target_root: str | Path,
) -> AdapterInstallationManifest | None:
    """Read and strictly validate a target repository's installation manifest."""

    path = Path(target_root) / MANIFEST_FILENAME
    if _manifest_path_state(path) is None:
        return None

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except InstallationManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise InstallationManifestError(
            f"could not read installation manifest {path}: {exc}"
        ) from exc
    return _manifest_from_document(document)


def write_installation_manifest(
    target_root: str | Path,
    manifest: AdapterInstallationManifest,
) -> None:
    """Atomically replace a regular manifest without following symlinks."""

    target = Path(target_root)
    if not target.is_dir():
        raise NotADirectoryError(f"target path is not a directory: {target}")

    path = target / MANIFEST_FILENAME
    _manifest_path_state(path)
    content = serialize_installation_manifest(manifest)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target,
        prefix=f"{MANIFEST_FILENAME}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
