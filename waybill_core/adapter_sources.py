"""Canonical adapter source manifest and mirror synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdapterSource:
    """One canonical adapter file and its generated repository mirrors."""

    adapter: str
    canonical: str
    install_target: str
    workspace_mirror: str
    packaged_mirror: str

    @property
    def mirrors(self) -> tuple[str, str]:
        return (self.workspace_mirror, self.packaged_mirror)


@dataclass(frozen=True)
class AdapterMirrorIssue:
    """A missing or byte-different adapter mirror."""

    canonical: str
    mirror: str
    reason: str


ADAPTER_SOURCES = (
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/handoff/SKILL.md",
        install_target=".claude/skills/handoff/SKILL.md",
        workspace_mirror=".claude/skills/handoff/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.claude/skills/handoff/SKILL.md"
        ),
    ),
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/waybill/SKILL.md",
        install_target=".claude/skills/waybill/SKILL.md",
        workspace_mirror=".claude/skills/waybill/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.claude/skills/waybill/SKILL.md"
        ),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/handoff.md",
        install_target=".opencode/commands/handoff.md",
        workspace_mirror=".opencode/commands/handoff.md",
        packaged_mirror=(
            "waybill_core/template-files/.opencode/commands/handoff.md"
        ),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/waybill.md",
        install_target=".opencode/commands/waybill.md",
        workspace_mirror=".opencode/commands/waybill.md",
        packaged_mirror=(
            "waybill_core/template-files/.opencode/commands/waybill.md"
        ),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/handoff/SKILL.md",
        install_target=".opencode/skills/handoff/SKILL.md",
        workspace_mirror=".opencode/skills/handoff/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.opencode/skills/handoff/SKILL.md"
        ),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/waybill/SKILL.md",
        install_target=".opencode/skills/waybill/SKILL.md",
        workspace_mirror=".opencode/skills/waybill/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.opencode/skills/waybill/SKILL.md"
        ),
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/handoff.mdc",
        install_target=".cursor/rules/handoff.mdc",
        workspace_mirror=".cursor/rules/handoff.mdc",
        packaged_mirror="waybill_core/template-files/.cursor/rules/handoff.mdc",
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/waybill.mdc",
        install_target=".cursor/rules/waybill.mdc",
        workspace_mirror=".cursor/rules/waybill.mdc",
        packaged_mirror="waybill_core/template-files/.cursor/rules/waybill.mdc",
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/handoff/SKILL.md",
        install_target=".gemini/skills/handoff/SKILL.md",
        workspace_mirror=".gemini/skills/handoff/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.gemini/skills/handoff/SKILL.md"
        ),
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/waybill/SKILL.md",
        install_target=".gemini/skills/waybill/SKILL.md",
        workspace_mirror=".gemini/skills/waybill/SKILL.md",
        packaged_mirror=(
            "waybill_core/template-files/.gemini/skills/waybill/SKILL.md"
        ),
    ),
)

# Codex is already delivered directly from its canonical plugin under
# adapters/codex, so it has no generated workspace or package-template mirror.
INSTALL_ADAPTERS = ("claude-code", "opencode", "cursor", "gemini-cli")
PACKAGE_TEMPLATE_ROOT = Path(__file__).resolve().parent / "template-files"


def sources_for_adapter(adapter: str) -> tuple[AdapterSource, ...]:
    """Return canonical file mappings for one init-supported adapter."""

    if adapter not in INSTALL_ADAPTERS:
        raise ValueError(f"unsupported adapter: {adapter}")
    return tuple(source for source in ADAPTER_SOURCES if source.adapter == adapter)


def resolve_adapter_source(
    source_root: str | Path,
    source: AdapterSource,
) -> Path:
    """Resolve a checkout canonical source or its installed package fallback."""

    canonical = Path(source_root) / source.canonical
    if canonical.is_file():
        return canonical

    packaged = PACKAGE_TEMPLATE_ROOT / source.install_target
    if packaged.is_file():
        return packaged

    return canonical


def find_adapter_drift(repo_root: str | Path) -> list[AdapterMirrorIssue]:
    """Return missing and byte-different mirrors under a repository root."""

    root = Path(repo_root)
    issues: list[AdapterMirrorIssue] = []
    for source in ADAPTER_SOURCES:
        canonical = root / source.canonical
        if not canonical.is_file():
            issues.append(
                AdapterMirrorIssue(
                    canonical=source.canonical,
                    mirror=source.canonical,
                    reason="canonical-missing",
                )
            )
            continue

        canonical_content = canonical.read_bytes()
        for mirror_relative in source.mirrors:
            mirror = root / mirror_relative
            if not mirror.is_file():
                issues.append(
                    AdapterMirrorIssue(
                        canonical=source.canonical,
                        mirror=mirror_relative,
                        reason="missing",
                    )
                )
            elif mirror.read_bytes() != canonical_content:
                issues.append(
                    AdapterMirrorIssue(
                        canonical=source.canonical,
                        mirror=mirror_relative,
                        reason="different",
                    )
                )
    return issues


def sync_adapter_mirrors(repo_root: str | Path) -> list[str]:
    """Rewrite missing or different mirrors from their canonical sources."""

    root = Path(repo_root)
    missing_canonical = [
        source.canonical
        for source in ADAPTER_SOURCES
        if not (root / source.canonical).is_file()
    ]
    if missing_canonical:
        missing = ", ".join(missing_canonical)
        raise FileNotFoundError(f"canonical adapter source does not exist: {missing}")

    updated: list[str] = []
    for source in ADAPTER_SOURCES:
        canonical_content = (root / source.canonical).read_bytes()
        for mirror_relative in source.mirrors:
            mirror = root / mirror_relative
            if mirror.is_file() and mirror.read_bytes() == canonical_content:
                continue
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror.write_bytes(canonical_content)
            updated.append(mirror_relative)
    return updated
