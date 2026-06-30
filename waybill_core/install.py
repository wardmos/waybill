"""Install Waybill adapter files into another repository."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_ADAPTERS = ["claude-code", "opencode"]


@dataclass(frozen=True)
class InstallAction:
    path: str
    action: str


@dataclass(frozen=True)
class InstallReport:
    target: Path
    adapters: list[str]
    actions: list[InstallAction]


def install_adapters(
    source_root: str | Path,
    target_root: str | Path,
    adapters: list[str],
    *,
    force: bool = False,
) -> InstallReport:
    source = Path(source_root)
    target = Path(target_root)

    if not source.is_dir():
        raise NotADirectoryError(f"source root is not a directory: {source}")
    if not target.exists():
        raise FileNotFoundError(f"target path does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"target path is not a directory: {target}")

    selected = _normalize_adapters(adapters)
    actions: list[InstallAction] = []

    for adapter in selected:
        for source_rel, target_rel in _adapter_files(adapter):
            _copy_file(
                source / source_rel,
                target / target_rel,
                target,
                force,
                actions,
            )

    _ensure_waybill_gitignore(target, actions)
    return InstallReport(target, selected, actions)


def _normalize_adapters(adapters: list[str]) -> list[str]:
    if not adapters:
        return list(SUPPORTED_ADAPTERS)
    if "all" in adapters:
        return list(SUPPORTED_ADAPTERS)

    selected: list[str] = []
    for adapter in adapters:
        if adapter not in SUPPORTED_ADAPTERS:
            raise ValueError(f"unsupported adapter: {adapter}")
        if adapter not in selected:
            selected.append(adapter)
    return selected


def _adapter_files(adapter: str) -> list[tuple[str, str]]:
    if adapter == "claude-code":
        return [
            (
                ".claude/skills/handoff/SKILL.md",
                ".claude/skills/handoff/SKILL.md",
            ),
            (
                ".claude/skills/waybill/SKILL.md",
                ".claude/skills/waybill/SKILL.md",
            ),
        ]

    if adapter == "opencode":
        return [
            (
                ".opencode/commands/handoff.md",
                ".opencode/commands/handoff.md",
            ),
            (
                ".opencode/commands/waybill.md",
                ".opencode/commands/waybill.md",
            ),
            (
                ".opencode/skills/handoff/SKILL.md",
                ".opencode/skills/handoff/SKILL.md",
            ),
            (
                ".opencode/skills/waybill/SKILL.md",
                ".opencode/skills/waybill/SKILL.md",
            ),
        ]

    raise ValueError(f"unsupported adapter: {adapter}")


def adapter_target_files(adapter: str) -> list[str]:
    return [target for _source, target in _adapter_files(adapter)]


def _copy_file(
    source: Path,
    destination: Path,
    target_root: Path,
    force: bool,
    actions: list[InstallAction],
) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"adapter source file does not exist: {source}")

    if destination.exists() and not force:
        raise FileExistsError(f"target file already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    action = "updated" if destination.exists() else "created"
    shutil.copy2(source, destination)
    actions.append(InstallAction(str(destination.relative_to(target_root)), action))


def _ensure_waybill_gitignore(target_root: Path, actions: list[InstallAction]) -> None:
    path = target_root / ".gitignore"
    if path.exists():
        text = path.read_text()
        lines = text.splitlines()
        if ".waybill/" in lines:
            actions.append(InstallAction(".gitignore", "unchanged"))
            return

        prefix = "" if text.endswith("\n") or text == "" else "\n"
        path.write_text(f"{text}{prefix}.waybill/\n")
        actions.append(InstallAction(".gitignore", "updated"))
        return

    path.write_text(".waybill/\n")
    actions.append(InstallAction(".gitignore", "created"))
