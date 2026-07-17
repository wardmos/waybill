"""Read-only repository checks for Waybill adapter installations."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .adapter_installation import (
    MANIFEST_FILENAME,
    AdapterInstallationManifest,
    InstallationManifestError,
    load_installation_manifest,
)
from .adapter_sources import resolve_adapter_source, sources_for_adapter
from .install import SUPPORTED_ADAPTERS


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str
    state: str


@dataclass(frozen=True)
class DoctorReport:
    target: Path
    adapters: list[str]
    checks: list[DoctorCheck]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)

    @property
    def codex_plugin_managed_by_init(self) -> bool:
        return False

    @property
    def codex_plugin_message(self) -> str:
        return "The Codex plugin is not managed by waybill init."


def _normalize_adapters(adapters: list[str]) -> list[str]:
    if not adapters or "all" in adapters:
        return list(SUPPORTED_ADAPTERS)

    selected: list[str] = []
    for adapter in adapters:
        if adapter not in SUPPORTED_ADAPTERS:
            raise ValueError(f"unsupported adapter: {adapter}")
        if adapter not in selected:
            selected.append(adapter)
    return selected


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _unsafe_parent(target: Path, relative: str) -> bool:
    current = target
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return True
    return False


def _check_gitignore(target: Path, checks: list[DoctorCheck]) -> None:
    relative = ".gitignore"
    path = target / relative
    if _unsafe_parent(target, relative):
        checks.append(
            DoctorCheck(relative, "error", "unsafe parent path", "modified")
        )
        return
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        checks.append(
            DoctorCheck(relative, "error", "missing .waybill/ ignore", "missing")
        )
        return
    if not stat.S_ISREG(metadata.st_mode):
        checks.append(
            DoctorCheck(relative, "error", "must be a regular file", "modified")
        )
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        checks.append(
            DoctorCheck(relative, "error", "could not read .gitignore", "modified")
        )
        return
    if ".waybill/" in lines:
        checks.append(
            DoctorCheck(relative, "ok", "contains .waybill/", "current")
        )
    else:
        checks.append(
            DoctorCheck(relative, "error", "missing .waybill/ ignore", "modified")
        )


def _load_manifest_check(
    target: Path,
    checks: list[DoctorCheck],
) -> AdapterInstallationManifest | None:
    try:
        manifest = load_installation_manifest(target)
    except InstallationManifestError as exc:
        checks.append(
            DoctorCheck(MANIFEST_FILENAME, "error", str(exc), "invalid")
        )
        return None
    if manifest is None:
        checks.append(
            DoctorCheck(
                MANIFEST_FILENAME,
                "ok",
                "legacy installation without a manifest",
                "legacy",
            )
        )
        return None
    checks.append(
        DoctorCheck(
            MANIFEST_FILENAME,
            "ok",
            "installation manifest is valid",
            "current",
        )
    )
    return manifest


def _check_adapter_file(
    target: Path,
    source_root: Path,
    adapter: str,
    relative: str,
    canonical_path: Path,
    manifest: AdapterInstallationManifest | None,
) -> DoctorCheck:
    path = target / relative
    if _unsafe_parent(target, relative):
        return DoctorCheck(relative, "error", "unsafe parent path", "modified")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return DoctorCheck(relative, "error", "missing", "missing")
    if not stat.S_ISREG(metadata.st_mode):
        return DoctorCheck(relative, "error", "must be a regular file", "modified")
    if not canonical_path.is_file():
        return DoctorCheck(
            relative,
            "error",
            f"adapter source is missing for {adapter}",
            "missing",
        )

    try:
        installed_digest = _sha256(path.read_bytes())
        canonical_digest = _sha256(canonical_path.read_bytes())
    except OSError:
        return DoctorCheck(relative, "error", "could not read file", "modified")

    if installed_digest == canonical_digest:
        return DoctorCheck(relative, "ok", "matches current adapter", "current")

    record = manifest.files.get(relative) if manifest is not None else None
    if record is not None and installed_digest == record.sha256:
        return DoctorCheck(
            relative,
            "error",
            "installed adapter is older than the current source",
            "stale",
        )
    return DoctorCheck(
        relative,
        "warning",
        "installed adapter differs from managed content",
        "modified",
    )


def doctor_repository(
    target_root: str | Path,
    adapters: list[str],
    *,
    source_root: str | Path | None = None,
) -> DoctorReport:
    """Classify installed adapters without changing the target repository."""

    target = Path(target_root)
    source = SOURCE_ROOT if source_root is None else Path(source_root)
    selected = _normalize_adapters(adapters)
    checks: list[DoctorCheck] = []

    if not target.exists():
        return DoctorReport(
            target,
            selected,
            [
                DoctorCheck(
                    "target",
                    "error",
                    f"target path does not exist: {target}",
                    "missing",
                )
            ],
        )
    if not target.is_dir():
        return DoctorReport(
            target,
            selected,
            [
                DoctorCheck(
                    "target",
                    "error",
                    f"target path is not a directory: {target}",
                    "modified",
                )
            ],
        )

    checks.append(
        DoctorCheck("target", "ok", f"target directory exists: {target}", "current")
    )
    _check_gitignore(target, checks)
    manifest = _load_manifest_check(target, checks)

    for adapter in selected:
        for adapter_source in sources_for_adapter(adapter):
            canonical = resolve_adapter_source(source, adapter_source)
            checks.append(
                _check_adapter_file(
                    target,
                    source,
                    adapter,
                    adapter_source.install_target,
                    canonical,
                    manifest,
                )
            )

    return DoctorReport(target, selected, checks)
