"""Canonical Skill sources, adapter wrappers, and generated mirror mapping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class AdapterSource:
    """One installable adapter file and its generated repository copies."""

    adapter: str
    canonical: str
    install_target: str
    packaged_mirror: str
    repository_mirror: str | None = None

    @property
    def mirrors(self) -> tuple[str, ...]:
        mirrors = () if self.repository_mirror is None else (self.repository_mirror,)
        return (*mirrors, self.packaged_mirror)


@dataclass(frozen=True)
class MirrorSource:
    """One canonical file and every generated copy kept in the repository."""

    canonical: str
    mirrors: tuple[str, ...]


@dataclass(frozen=True)
class AdapterMirrorIssue:
    """A missing canonical source or a missing or byte-different mirror."""

    canonical: str
    mirror: str
    reason: str


def _packaged(install_target: str) -> str:
    return f"waybill_core/template-files/{install_target}"


def _shared_resource_sources(
    adapter: str,
    *,
    install_root: str,
    adapter_root: str,
) -> tuple[AdapterSource, ...]:
    return tuple(
        AdapterSource(
            adapter=adapter,
            canonical=f"{CANONICAL_SKILL_ROOT}/{relative_path}",
            install_target=f"{install_root}/{relative_path}",
            repository_mirror=f"{adapter_root}/{relative_path}",
            packaged_mirror=_packaged(f"{install_root}/{relative_path}"),
        )
        for relative_path in SHARED_RESOURCE_PATHS
    )


ADAPTER_SOURCES = (
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/handoff/SKILL.md",
        install_target=".claude/skills/handoff/SKILL.md",
        packaged_mirror=_packaged(".claude/skills/handoff/SKILL.md"),
    ),
    *_shared_resource_sources(
        "claude-code",
        install_root=".claude/skills/handoff",
        adapter_root="adapters/claude-code/skills/handoff",
    ),
    AdapterSource(
        adapter="claude-code",
        canonical="adapters/claude-code/skills/waybill/SKILL.md",
        install_target=".claude/skills/waybill/SKILL.md",
        packaged_mirror=_packaged(".claude/skills/waybill/SKILL.md"),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/handoff.md",
        install_target=".opencode/commands/handoff.md",
        packaged_mirror=_packaged(".opencode/commands/handoff.md"),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/commands/waybill.md",
        install_target=".opencode/commands/waybill.md",
        packaged_mirror=_packaged(".opencode/commands/waybill.md"),
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/handoff/SKILL.md",
        install_target=".opencode/skills/handoff/SKILL.md",
        packaged_mirror=_packaged(".opencode/skills/handoff/SKILL.md"),
    ),
    *_shared_resource_sources(
        "opencode",
        install_root=".opencode/skills/handoff",
        adapter_root="adapters/opencode/skills/handoff",
    ),
    AdapterSource(
        adapter="opencode",
        canonical="adapters/opencode/skills/waybill/SKILL.md",
        install_target=".opencode/skills/waybill/SKILL.md",
        packaged_mirror=_packaged(".opencode/skills/waybill/SKILL.md"),
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/handoff.mdc",
        install_target=".cursor/rules/handoff.mdc",
        packaged_mirror=_packaged(".cursor/rules/handoff.mdc"),
    ),
    *_shared_resource_sources(
        "cursor",
        install_root=".cursor/rules/waybill-handoff",
        adapter_root="adapters/cursor/rules/waybill-handoff",
    ),
    AdapterSource(
        adapter="cursor",
        canonical="adapters/cursor/rules/waybill.mdc",
        install_target=".cursor/rules/waybill.mdc",
        packaged_mirror=_packaged(".cursor/rules/waybill.mdc"),
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/handoff/SKILL.md",
        install_target=".gemini/skills/handoff/SKILL.md",
        packaged_mirror=_packaged(".gemini/skills/handoff/SKILL.md"),
    ),
    *_shared_resource_sources(
        "gemini-cli",
        install_root=".gemini/skills/handoff",
        adapter_root="adapters/gemini-cli/skills/handoff",
    ),
    AdapterSource(
        adapter="gemini-cli",
        canonical="adapters/gemini-cli/skills/waybill/SKILL.md",
        install_target=".gemini/skills/waybill/SKILL.md",
        packaged_mirror=_packaged(".gemini/skills/waybill/SKILL.md"),
    ),
)

CODEX_RESOURCE_MIRRORS = tuple(
    MirrorSource(
        canonical=f"{CANONICAL_SKILL_ROOT}/{relative_path}",
        mirrors=(f"adapters/codex/skills/handoff/{relative_path}",),
    )
    for relative_path in SHARED_RESOURCE_PATHS
)

MIRROR_SOURCES = tuple(
    MirrorSource(source.canonical, source.mirrors) for source in ADAPTER_SOURCES
) + CODEX_RESOURCE_MIRRORS

# Codex is delivered directly from its plugin under adapters/codex. The CLI
# manages only adapters that install project-local files.
INSTALL_ADAPTERS = ("claude-code", "opencode", "cursor", "gemini-cli")
PACKAGE_TEMPLATE_ROOT = Path(__file__).resolve().parent / "template-files"


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

    canonical = Path(source_root) / source.canonical
    if canonical.is_file():
        return canonical

    packaged = PACKAGE_TEMPLATE_ROOT / source.install_target
    if packaged.is_file():
        return packaged

    return canonical


def find_adapter_drift(repo_root: str | Path) -> list[AdapterMirrorIssue]:
    """Return missing and byte-different generated adapter files."""

    root = Path(repo_root)
    issues: list[AdapterMirrorIssue] = []
    missing_canonical: set[str] = set()
    for source in MIRROR_SOURCES:
        canonical = root / source.canonical
        if not canonical.is_file():
            if source.canonical not in missing_canonical:
                missing_canonical.add(source.canonical)
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
    """Rewrite generated adapter and package files from canonical sources."""

    root = Path(repo_root)
    missing_canonical = sorted(
        {
            source.canonical
            for source in MIRROR_SOURCES
            if not (root / source.canonical).is_file()
        }
    )
    if missing_canonical:
        missing = ", ".join(missing_canonical)
        raise FileNotFoundError(f"canonical adapter source does not exist: {missing}")

    updated: list[str] = []
    for source in MIRROR_SOURCES:
        canonical_content = (root / source.canonical).read_bytes()
        for mirror_relative in source.mirrors:
            mirror = root / mirror_relative
            if mirror.is_file() and mirror.read_bytes() == canonical_content:
                continue
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror.write_bytes(canonical_content)
            updated.append(mirror_relative)
    return updated
