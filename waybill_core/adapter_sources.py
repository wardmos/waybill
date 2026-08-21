"""Canonical Skill and agent-specific adapter source mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


CANONICAL_SKILL = "skills/handoff/SKILL.md"
CANONICAL_SKILL_ROOT = "skills/handoff"
REFERENCE_NAMES = ("bundle-format.md", "export.md", "import.md")
BUNDLE_ASSET_NAMES = (
    "WAYBILL.md",
    "metadata.json",
    "diff.patch",
    "commands.log",
    "test-summary.md",
)
CHECKER_SCRIPT_NAMES = ("check_bundle.py",)
SHARED_RESOURCE_PATHS = (
    *(f"references/{name}" for name in REFERENCE_NAMES),
    *(f"assets/bundle-template/{name}" for name in BUNDLE_ASSET_NAMES),
    *(f"scripts/{name}" for name in CHECKER_SCRIPT_NAMES),
)

AGENT_ADAPTER_ENTRYPOINTS = {
    "claude-code": "adapters/claude-code/skills/handoff/SKILL.md",
    "codex": "adapters/codex/skills/handoff/SKILL.md",
    "cursor": "adapters/cursor/rules/handoff.mdc",
    "gemini-cli": "adapters/gemini-cli/skills/handoff/SKILL.md",
    "opencode": "adapters/opencode/skills/handoff/SKILL.md",
}
SUPPORTED_AGENT_ADAPTERS = tuple(AGENT_ADAPTER_ENTRYPOINTS)


@dataclass(frozen=True)
class AdapterSource:
    """One canonical adapter file and its install/distribution targets."""

    adapter: str
    canonical: str
    install_target: str
    bundle_target: str


def _shared_resource_sources(
    adapter: str,
    *,
    install_root: str,
    bundle_root: str,
) -> tuple[AdapterSource, ...]:
    return tuple(
        AdapterSource(
            adapter=adapter,
            canonical=f"{CANONICAL_SKILL_ROOT}/{relative_path}",
            install_target=f"{install_root}/{relative_path}",
            bundle_target=f"{bundle_root}/{relative_path}",
        )
        for relative_path in SHARED_RESOURCE_PATHS
    )


ADAPTER_SOURCES = (
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/handoff/SKILL.md",
        install_target=".claude/skills/handoff/SKILL.md",
        bundle_target="skills/handoff/SKILL.md",
    ),
    *_shared_resource_sources(
        "claude-code",
        install_root=".claude/skills/handoff",
        bundle_root="skills/handoff",
    ),
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/waybill/SKILL.md",
        install_target=".claude/skills/waybill/SKILL.md",
        bundle_target="skills/waybill/SKILL.md",
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/handoff.md",
        install_target=".opencode/commands/handoff.md",
        bundle_target="commands/handoff.md",
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/waybill.md",
        install_target=".opencode/commands/waybill.md",
        bundle_target="commands/waybill.md",
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/handoff/SKILL.md",
        install_target=".opencode/skills/handoff/SKILL.md",
        bundle_target="skills/handoff/SKILL.md",
    ),
    *_shared_resource_sources(
        "opencode",
        install_root=".opencode/skills/handoff",
        bundle_root="skills/handoff",
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/waybill/SKILL.md",
        install_target=".opencode/skills/waybill/SKILL.md",
        bundle_target="skills/waybill/SKILL.md",
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/handoff.mdc",
        install_target=".cursor/rules/handoff.mdc",
        bundle_target="rules/handoff.mdc",
    ),
    *_shared_resource_sources(
        "cursor",
        install_root=".cursor/rules/waybill-handoff",
        bundle_root="rules/waybill-handoff",
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/waybill.mdc",
        install_target=".cursor/rules/waybill.mdc",
        bundle_target="rules/waybill.mdc",
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/handoff/SKILL.md",
        install_target=".gemini/skills/handoff/SKILL.md",
        bundle_target="skills/handoff/SKILL.md",
    ),
    *_shared_resource_sources(
        "gemini-cli",
        install_root=".gemini/skills/handoff",
        bundle_root="skills/handoff",
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/waybill/SKILL.md",
        install_target=".gemini/skills/waybill/SKILL.md",
        bundle_target="skills/waybill/SKILL.md",
    ),
)

# Codex uses the repository-root plugin. The CLI manages only adapters that
# install project-local files.
INSTALL_ADAPTERS = ("claude-code", "opencode", "cursor", "gemini-cli")
PACKAGE_ADAPTER_ROOT = Path(__file__).resolve().parent / "_adapter_wrappers"
PACKAGE_SKILL_ROOT = Path(__file__).resolve().parent / "_handoff_skill"


def sources_for_adapter(adapter: str) -> tuple[AdapterSource, ...]:
    """Return installable source mappings for one managed adapter."""

    if adapter not in INSTALL_ADAPTERS:
        raise ValueError(f"unsupported adapter: {adapter}")
    return tuple(source for source in ADAPTER_SOURCES if source.adapter == adapter)


def resolve_adapter_source(
    source_root: str | Path,
    source: AdapterSource,
) -> Path:
    """Resolve a checkout canonical source or its installed package fallback."""

    canonical_path = Path(source_root) / source.canonical
    if canonical_path.is_file():
        return canonical_path

    canonical_relative = PurePosixPath(source.canonical)
    if canonical_relative.is_relative_to(CANONICAL_SKILL_ROOT):
        skill_root = PurePosixPath(CANONICAL_SKILL_ROOT)
        relative = canonical_relative.relative_to(skill_root)
        packaged = PACKAGE_SKILL_ROOT.joinpath(*relative.parts)
    else:
        relative = canonical_relative.relative_to("adapters")
        packaged = PACKAGE_ADAPTER_ROOT.joinpath(*relative.parts)
    if packaged.is_file():
        return packaged

    return canonical_path
