#!/usr/bin/env python3
"""Validate the Waybill repository shape without third-party packages."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    ".gitignore",
    "INSTALL.md",
    "TESTING.md",
    "spec/waybill-bundle.md",
    "spec/waybill-template.md",
    "spec/metadata.schema.json",
    ".agents/plugins/marketplace.json",
    ".claude/skills/handoff/SKILL.md",
    ".claude/skills/waybill/SKILL.md",
    "adapters/claude-code/README.md",
    "adapters/claude-code/commands/handoff-export.md",
    "adapters/claude-code/commands/handoff-import.md",
    "adapters/codex/README.md",
    "adapters/codex/.codex-plugin/plugin.json",
    "adapters/codex/skills/handoff/SKILL.md",
]

EXAMPLES = [
    "examples/claude-to-codex",
    "examples/codex-to-claude",
]

WAYBILL_SECTIONS = [
    "Original Goal",
    "Current Status",
    "User Constraints",
    "Repo State",
    "Changed Files",
    "Commands Run",
    "Test State",
    "Failed Attempts",
    "Current Hypothesis",
    "Next Recommended Step",
    "Risks / Unknowns",
    "Instructions For Next Agent",
]

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"sk-[A-Za-z0-9_-]{10,}",
        r"api[_-]?key\s*[:=]",
        r"password\s*[:=]",
        r"secret\s*[:=]",
        r"token\s*[:=]",
        r"cookie\s*[:=]",
    ]
]

BAD_AGENT_PHRASES = [
    "Claude should",
    "Claude must",
    "Codex should",
    "Codex must",
]

COMMAND_CLASSIFICATION_TERMS = [
    "read-only inspection",
    "bundle-writing",
    "commands.log",
]


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"{path.relative_to(ROOT)} is invalid JSON: {exc}")


def require_file(path: str) -> Path:
    file_path = ROOT / path
    if not file_path.is_file():
        fail(f"missing required file: {path}")
    return file_path


def has_command_classification_rule(text: str) -> bool:
    normalized = " ".join(text.split()).lower()
    return all(term in normalized for term in COMMAND_CLASSIFICATION_TERMS)


def validate_structure() -> None:
    for path in REQUIRED_FILES:
        require_file(path)

    gitignore = (ROOT / ".gitignore").read_text()
    if ".waybill/" not in gitignore:
        fail(".gitignore must ignore .waybill/")

    bundle_spec = (ROOT / "spec/waybill-bundle.md").read_text()
    if not has_command_classification_rule(bundle_spec):
        fail("bundle spec must require command log action classification")


def validate_metadata_schema() -> None:
    schema = read_json(ROOT / "spec/metadata.schema.json")
    required = schema.get("required")
    if required != ["schema_version", "source_agent", "created_at", "repo_root", "git", "artifacts"]:
        fail("metadata schema required fields changed unexpectedly")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "draft":
        fail("metadata schema must require draft schema_version")


def validate_codex_plugin() -> None:
    manifest_path = ROOT / "adapters/codex/.codex-plugin/plugin.json"
    manifest = read_json(manifest_path)

    for key in ["name", "version", "description", "author", "skills", "interface"]:
        if key not in manifest:
            fail(f"Codex plugin manifest missing {key}")

    if manifest["name"] != "waybill":
        fail("Codex plugin name must be waybill")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
        fail("Codex plugin version must be strict semver")
    if manifest["skills"] != "./skills/":
        fail("Codex plugin skills path must be ./skills/")

    interface = manifest["interface"]
    for key in ["displayName", "shortDescription", "longDescription", "developerName", "category"]:
        if key not in interface:
            fail(f"Codex plugin interface missing {key}")

    skill_path = ROOT / "adapters/codex/skills/handoff/SKILL.md"
    skill = skill_path.read_text()
    if not skill.startswith("---\n"):
        fail("Codex handoff skill must start with frontmatter")
    if "name: handoff" not in skill:
        fail("Codex handoff skill frontmatter must name the skill")
    for command in ["/handoff export", "/waybill export", "/handoff import", "/waybill import"]:
        if command not in skill:
            fail(f"Codex handoff skill missing command trigger: {command}")
    if not has_command_classification_rule(skill):
        fail("Codex handoff skill must require command log action classification")


def validate_codex_marketplace() -> None:
    marketplace = read_json(ROOT / ".agents/plugins/marketplace.json")

    if marketplace.get("name") != "waybill-local":
        fail("repo marketplace name must be waybill-local")
    if marketplace.get("interface", {}).get("displayName") != "Waybill Local":
        fail("repo marketplace displayName must be Waybill Local")

    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        fail("repo marketplace must contain exactly one plugin entry")

    plugin = plugins[0]
    if plugin.get("name") != "waybill":
        fail("repo marketplace plugin name must be waybill")
    if plugin.get("source", {}).get("source") != "local":
        fail("repo marketplace plugin source must be local")
    if plugin.get("source", {}).get("path") != "./adapters/codex":
        fail("repo marketplace plugin path must be ./adapters/codex")
    if not (ROOT / "adapters/codex/.codex-plugin/plugin.json").is_file():
        fail("repo marketplace plugin path does not contain a Codex manifest")

    policy = plugin.get("policy", {})
    if policy.get("installation") != "AVAILABLE":
        fail("repo marketplace installation policy must be AVAILABLE")
    if policy.get("authentication") != "ON_INSTALL":
        fail("repo marketplace authentication policy must be ON_INSTALL")
    if plugin.get("category") != "Productivity":
        fail("repo marketplace category must be Productivity")


def validate_claude_skills() -> None:
    skills = {
        "handoff": ROOT / ".claude/skills/handoff/SKILL.md",
        "waybill": ROOT / ".claude/skills/waybill/SKILL.md",
    }

    for name, path in skills.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"Claude skill {name} must start with frontmatter")
        if "argument-hint:" not in text:
            fail(f"Claude skill {name} must declare argument-hint")
        if "export" not in text or "import" not in text:
            fail(f"Claude skill {name} must cover export and import")
        if "Do not automatically apply `diff.patch`" not in text:
            fail(f"Claude skill {name} must forbid automatic patch application")
        if "Verify the current repository state" not in text and "verify current repo state" not in text:
            fail(f"Claude skill {name} must require repo state verification")
        if ".waybill/" not in text:
            fail(f"Claude skill {name} must mention .waybill/")
        if name == "handoff" and not has_command_classification_rule(text):
            fail("Claude handoff skill must require command log action classification")
        if name == "waybill" and not has_command_classification_rule(text):
            fail("Claude waybill alias must require command log action classification")


def validate_example(example_dir: Path) -> None:
    for name in ["WAYBILL.md", "metadata.json"]:
        if not (example_dir / name).is_file():
            fail(f"{example_dir.relative_to(ROOT)} missing {name}")

    metadata = read_json(example_dir / "metadata.json")
    for key in ["schema_version", "source_agent", "created_at", "repo_root", "git", "artifacts"]:
        if key not in metadata:
            fail(f"{example_dir.relative_to(ROOT)} metadata missing {key}")

    if metadata["schema_version"] != "draft":
        fail(f"{example_dir.relative_to(ROOT)} metadata schema_version must be draft")
    if not isinstance(metadata.get("git", {}).get("dirty"), bool):
        fail(f"{example_dir.relative_to(ROOT)} metadata git.dirty must be boolean")
    if metadata.get("artifacts", {}).get("waybill") != "WAYBILL.md":
        fail(f"{example_dir.relative_to(ROOT)} metadata artifacts.waybill must be WAYBILL.md")

    for artifact in metadata["artifacts"].values():
        if not (example_dir / artifact).is_file():
            fail(f"{example_dir.relative_to(ROOT)} missing artifact {artifact}")

    waybill = (example_dir / "WAYBILL.md").read_text()
    for section in WAYBILL_SECTIONS:
        if f"## {section}" not in waybill:
            fail(f"{example_dir.relative_to(ROOT)} WAYBILL.md missing section: {section}")

    combined = "\n".join(path.read_text() for path in example_dir.iterdir() if path.is_file())
    for pattern in SECRET_PATTERNS:
        if pattern.search(combined):
            fail(f"{example_dir.relative_to(ROOT)} may contain a secret matching {pattern.pattern}")

    for phrase in BAD_AGENT_PHRASES:
        if phrase in waybill:
            fail(f"{example_dir.relative_to(ROOT)} contains agent-specific phrase: {phrase}")


def validate_examples() -> None:
    for example in EXAMPLES:
        validate_example(ROOT / example)


def main() -> int:
    checks = [
        ("structure", validate_structure),
        ("metadata schema", validate_metadata_schema),
        ("Codex plugin", validate_codex_plugin),
        ("Codex marketplace", validate_codex_marketplace),
        ("Claude skills", validate_claude_skills),
        ("examples", validate_examples),
    ]

    try:
        for name, check in checks:
            check()
            print(f"PASS {name}")
    except ValidationError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    print("PASS Waybill repository validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
