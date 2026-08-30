"""Build self-contained adapter distributions from canonical source files."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .adapter_sources import (
    ADAPTER_SOURCES,
    CANONICAL_SKILL,
    CANONICAL_SKILL_ROOT,
    SHARED_RESOURCE_PATHS,
    SUPPORTED_AGENT_ADAPTERS,
)


BUNDLE_ADAPTERS = SUPPORTED_AGENT_ADAPTERS


@dataclass(frozen=True)
class AdapterBundleSource:
    """One canonical file and its path inside a standalone adapter bundle."""

    adapter: str
    canonical: str
    target: str


@dataclass(frozen=True)
class AdapterBundleReport:
    """Files written for one complete adapter build."""

    output: Path
    files: tuple[str, ...]


def _claude_command_sources() -> tuple[AdapterBundleSource, ...]:
    return (
        AdapterBundleSource(
            "claude-code",
            "adapters/claude-code/commands/handoff-export.md",
            "commands/handoff-export.md",
        ),
        AdapterBundleSource(
            "claude-code",
            "adapters/claude-code/commands/handoff-import.md",
            "commands/handoff-import.md",
        ),
    )


def _codex_sources() -> tuple[AdapterBundleSource, ...]:
    return (
        AdapterBundleSource(
            "codex",
            ".codex-plugin/plugin.json",
            ".codex-plugin/plugin.json",
        ),
        AdapterBundleSource(
            "codex",
            CANONICAL_SKILL,
            "skills/handoff/SKILL.md",
        ),
        *(
            AdapterBundleSource(
                "codex",
                f"{CANONICAL_SKILL_ROOT}/{relative}",
                f"skills/handoff/{relative}",
            )
            for relative in SHARED_RESOURCE_PATHS
        ),
    )


ADAPTER_BUNDLE_SOURCES = tuple(
    AdapterBundleSource(source.adapter, source.canonical, source.bundle_target)
    for source in ADAPTER_SOURCES
) + _claude_command_sources() + _codex_sources()


def bundle_sources_for_adapter(adapter: str) -> tuple[AdapterBundleSource, ...]:
    """Return the deterministic source manifest for one standalone adapter."""

    if adapter not in BUNDLE_ADAPTERS:
        raise ValueError(f"unsupported adapter: {adapter}")
    return tuple(
        source for source in ADAPTER_BUNDLE_SOURCES if source.adapter == adapter
    )


def _safe_relative(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError(f"unsafe adapter bundle path: {value}")
    return relative


def _read_source(root: Path, relative: str) -> tuple[bytes, int]:
    path = root.joinpath(*_safe_relative(relative).parts)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"adapter bundle source is not a regular file: {relative}")
    return path.read_bytes(), stat.S_IMODE(metadata.st_mode)


def build_adapter_bundles(
    source_root: str | Path,
    output_root: str | Path,
) -> AdapterBundleReport:
    """Atomically build every standalone adapter into a new output directory."""

    source = Path(source_root)
    output = Path(output_root)
    source_metadata = source.lstat()
    if stat.S_ISLNK(source_metadata.st_mode) or not stat.S_ISDIR(source_metadata.st_mode):
        raise NotADirectoryError(f"source root is not a regular directory: {source}")
    try:
        output.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"adapter output already exists: {output}")

    planned: list[tuple[PurePosixPath, bytes, int]] = []
    seen: set[PurePosixPath] = set()
    for item in ADAPTER_BUNDLE_SOURCES:
        relative = PurePosixPath(item.adapter) / _safe_relative(item.target)
        if relative in seen:
            raise ValueError(f"duplicate adapter bundle target: {relative.as_posix()}")
        seen.add(relative)
        content, mode = _read_source(source, item.canonical)
        planned.append((relative, content, mode))

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.building-",
            dir=output.parent,
        )
    )
    try:
        for relative, content, mode in planned:
            target = staging.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            os.chmod(target, mode)
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return AdapterBundleReport(
        output=output,
        files=tuple(sorted(path.as_posix() for path in seen)),
    )
