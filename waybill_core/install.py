"""Plan and apply Waybill adapter installations."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import __version__
from .adapter_installation import (
    MANIFEST_FILENAME,
    AdapterFileRecord,
    AdapterInstallationManifest,
    InstallationManifestError,
    load_installation_manifest,
    serialize_installation_manifest,
    write_installation_manifest,
)
from .adapter_sources import (
    INSTALL_ADAPTERS,
    resolve_adapter_source,
    sources_for_adapter,
)


SUPPORTED_ADAPTERS = list(INSTALL_ADAPTERS)


class InstallConflictError(ValueError):
    """Raised after planning finds target files that cannot be safely replaced."""

    def __init__(self, conflicts: list[str]) -> None:
        self.conflicts = tuple(sorted(conflicts))
        super().__init__(
            "adapter installation conflicts: " + ", ".join(self.conflicts)
        )


@dataclass(frozen=True)
class InstallAction:
    path: str
    action: str


@dataclass(frozen=True)
class _PlannedWrite:
    path: str
    content: bytes
    mode: int


@dataclass(frozen=True)
class InstallPlan:
    """A complete, read-only installation plan ready to be applied."""

    target: Path
    adapters: list[str]
    actions: list[InstallAction]
    writes: tuple[_PlannedWrite, ...]
    manifest: AdapterInstallationManifest | None

    @property
    def has_conflicts(self) -> bool:
        return any(action.action == "would-conflict" for action in self.actions)


@dataclass(frozen=True)
class InstallReport:
    target: Path
    adapters: list[str]
    actions: list[InstallAction]
    dry_run: bool = False

    @property
    def has_conflicts(self) -> bool:
        return any(action.action == "would-conflict" for action in self.actions)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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


def _adapter_files(adapter: str) -> list[tuple[str, str]]:
    return [
        (source.canonical, source.install_target)
        for source in sources_for_adapter(adapter)
    ]


def adapter_target_files(adapter: str) -> list[str]:
    return [target for _source, target in _adapter_files(adapter)]


def _unsafe_parent(target: Path, relative: str) -> str | None:
    current = target
    for part in PurePosixPath(relative).parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode):
            return f"parent path is a symbolic link: {current}"
        if not stat.S_ISDIR(metadata.st_mode):
            return f"parent path is not a directory: {current}"
    return None


def _destination_metadata(target: Path, relative: str) -> os.stat_result | None:
    if _unsafe_parent(target, relative) is not None:
        return None
    try:
        return (target / relative).lstat()
    except FileNotFoundError:
        return None


def _plan_content_file(
    target: Path,
    relative: str,
    content: bytes,
    *,
    previous_digest: str | None,
    force: bool,
    create_mode: int,
) -> tuple[InstallAction, _PlannedWrite | None]:
    if _unsafe_parent(target, relative) is not None:
        return InstallAction(relative, "would-conflict"), None

    destination = target / relative
    try:
        metadata = destination.lstat()
    except FileNotFoundError:
        return (
            InstallAction(relative, "would-create"),
            _PlannedWrite(relative, content, create_mode),
        )

    if not stat.S_ISREG(metadata.st_mode):
        return InstallAction(relative, "would-conflict"), None

    try:
        installed = destination.read_bytes()
    except OSError:
        return InstallAction(relative, "would-conflict"), None

    if installed == content:
        return InstallAction(relative, "unchanged"), None

    installed_digest = _sha256(installed)
    if force or (
        previous_digest is not None and installed_digest == previous_digest
    ):
        return (
            InstallAction(relative, "would-update"),
            _PlannedWrite(relative, content, stat.S_IMODE(metadata.st_mode)),
        )
    return InstallAction(relative, "would-conflict"), None


def _plan_gitignore(
    target: Path,
) -> tuple[InstallAction, _PlannedWrite | None]:
    relative = ".gitignore"
    if _unsafe_parent(target, relative) is not None:
        return InstallAction(relative, "would-conflict"), None

    path = target / relative
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return (
            InstallAction(relative, "would-create"),
            _PlannedWrite(relative, b".waybill/\n", 0o644),
        )
    if not stat.S_ISREG(metadata.st_mode):
        return InstallAction(relative, "would-conflict"), None

    try:
        content = path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeError):
        return InstallAction(relative, "would-conflict"), None
    if ".waybill/" in text.splitlines():
        return InstallAction(relative, "unchanged"), None

    prefix = b"" if content.endswith(b"\n") or not content else b"\n"
    return (
        InstallAction(relative, "would-update"),
        _PlannedWrite(
            relative,
            content + prefix + b".waybill/\n",
            stat.S_IMODE(metadata.st_mode),
        ),
    )


def _plan_manifest(
    target: Path,
    manifest: AdapterInstallationManifest,
    *,
    existing_manifest: AdapterInstallationManifest | None,
    manifest_invalid: bool,
) -> InstallAction:
    if manifest_invalid or _unsafe_parent(target, MANIFEST_FILENAME) is not None:
        return InstallAction(MANIFEST_FILENAME, "would-conflict")

    path = target / MANIFEST_FILENAME
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return InstallAction(MANIFEST_FILENAME, "would-create")
    if not stat.S_ISREG(metadata.st_mode) or existing_manifest is None:
        return InstallAction(MANIFEST_FILENAME, "would-conflict")

    try:
        current = path.read_bytes()
    except OSError:
        return InstallAction(MANIFEST_FILENAME, "would-conflict")
    if current == serialize_installation_manifest(manifest):
        return InstallAction(MANIFEST_FILENAME, "unchanged")
    return InstallAction(MANIFEST_FILENAME, "would-update")


def plan_adapter_installation(
    source_root: str | Path,
    target_root: str | Path,
    adapters: list[str],
    *,
    force: bool = False,
) -> InstallPlan:
    """Inspect every target and return a plan without changing the filesystem."""

    source = Path(source_root)
    target = Path(target_root)
    if not source.is_dir():
        raise NotADirectoryError(f"source root is not a directory: {source}")
    if not target.exists():
        raise FileNotFoundError(f"target path does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"target path is not a directory: {target}")

    selected = _normalize_adapters(adapters)
    try:
        existing_manifest = load_installation_manifest(target)
    except InstallationManifestError:
        existing_manifest = None
        manifest_invalid = True
    else:
        manifest_invalid = False

    records = dict(existing_manifest.files) if existing_manifest is not None else {}
    actions: list[InstallAction] = []
    writes: list[_PlannedWrite] = []

    for adapter in selected:
        for adapter_source in sources_for_adapter(adapter):
            source_path = resolve_adapter_source(source, adapter_source)
            if not source_path.is_file():
                raise FileNotFoundError(
                    f"adapter source file does not exist: {source_path}"
                )
            content = source_path.read_bytes()
            relative = adapter_source.install_target
            previous = records.get(relative)
            action, planned_write = _plan_content_file(
                target,
                relative,
                content,
                previous_digest=(previous.sha256 if previous is not None else None),
                force=force,
                create_mode=stat.S_IMODE(source_path.stat().st_mode),
            )
            actions.append(action)
            if planned_write is not None:
                writes.append(planned_write)
            records[relative] = AdapterFileRecord(
                adapter=adapter,
                sha256=_sha256(content),
            )

    gitignore_action, gitignore_write = _plan_gitignore(target)
    actions.append(gitignore_action)
    if gitignore_write is not None:
        writes.append(gitignore_write)

    manifest = AdapterInstallationManifest(
        format_version=1,
        waybill_version=__version__,
        files={path: records[path] for path in sorted(records)},
    )
    actions.append(
        _plan_manifest(
            target,
            manifest,
            existing_manifest=existing_manifest,
            manifest_invalid=manifest_invalid,
        )
    )
    return InstallPlan(
        target=target,
        adapters=selected,
        actions=actions,
        writes=tuple(writes),
        manifest=manifest,
    )


def _atomic_write(target: Path, planned: _PlannedWrite) -> None:
    destination = target / planned.path
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, planned.mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(planned.content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def apply_adapter_installation(plan: InstallPlan) -> InstallReport:
    """Apply a conflict-free plan, writing the manifest after adapter files."""

    conflicts = [
        action.path
        for action in plan.actions
        if action.action == "would-conflict"
    ]
    if conflicts:
        raise InstallConflictError(conflicts)

    for planned_write in plan.writes:
        _atomic_write(plan.target, planned_write)

    manifest_action = next(
        action for action in plan.actions if action.path == MANIFEST_FILENAME
    )
    if manifest_action.action != "unchanged":
        assert plan.manifest is not None
        write_installation_manifest(plan.target, plan.manifest)

    applied_actions = [
        InstallAction(
            action.path,
            {
                "would-create": "created",
                "would-update": "updated",
            }.get(action.action, action.action),
        )
        for action in plan.actions
    ]
    return InstallReport(
        target=plan.target,
        adapters=plan.adapters,
        actions=applied_actions,
        dry_run=False,
    )


def install_adapters(
    source_root: str | Path,
    target_root: str | Path,
    adapters: list[str],
    *,
    force: bool = False,
    dry_run: bool = False,
) -> InstallReport:
    """Plan an adapter installation and either preview or apply it."""

    plan = plan_adapter_installation(
        source_root,
        target_root,
        adapters,
        force=force,
    )
    if dry_run:
        return InstallReport(
            target=plan.target,
            adapters=plan.adapters,
            actions=plan.actions,
            dry_run=True,
        )
    return apply_adapter_installation(plan)
