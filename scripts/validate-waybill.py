#!/usr/bin/env python3
"""Validate the Waybill repository shape without third-party packages."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from waybill_core.limits import (  # noqa: E402
    BundleLimitError,
    MAX_BUNDLE_FILE_BYTES,
    list_bundle_files,
)
from waybill_core.adapter_installation import MANIFEST_FILENAME  # noqa: E402
from waybill_core.adapter_sources import (  # noqa: E402
    ADAPTER_SOURCES,
    BUNDLE_ASSET_NAMES,
    CANONICAL_SKILL,
    CHECKER_SCRIPT_NAMES,
    MIRROR_SOURCES,
    find_adapter_drift,
    sources_for_adapter,
)
from waybill_core.conformance import (  # noqa: E402
    REQUIRED_IMPORT_SCENARIO_SEMANTICS,
    load_scenarios,
)
from waybill_core.export_conformance import (  # noqa: E402
    REQUIRED_EXPORT_SCENARIO_IDS,
    load_export_scenarios,
)
from waybill_core.doctor import doctor_repository  # noqa: E402
from waybill_core.install import install_adapters  # noqa: E402
from waybill_core.scaffold import STANDARD_FILES  # noqa: E402
from waybill_core.schema_versions import CURRENT_SCHEMA_VERSION  # noqa: E402
from waybill_core.validation import WAYBILL_SECTIONS, validate_bundle  # noqa: E402

REQUIRED_FILES = [
    "README.md",
    "CONFORMANCE.md",
    "QUICKSTART.md",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/workflows/publish-pypi.yml",
    "MANIFEST.in",
    "pyproject.toml",
    "INSTALL.md",
    "TESTING.md",
    "WALKTHROUGH.md",
    "spec/waybill-bundle.md",
    "spec/waybill-template.md",
    "spec/delegation.md",
    "spec/delegation-request-template.md",
    "spec/delegation-result-template.md",
    "spec/metadata.schema.json",
    "cli/waybill",
    "scripts/adapter-matrix.py",
    "scripts/conformance-agents.py",
    "scripts/conformance-exports.py",
    "scripts/smoke-agents.sh",
    "scripts/sync-adapters.py",
    "scripts/test-wheel-install.py",
    "waybill_core/__init__.py",
    "waybill_core/adapter_matrix.py",
    "waybill_core/adapter_installation.py",
    "waybill_core/adapter_sources.py",
    "waybill_core/agent_identity.py",
    "waybill_core/application.py",
    "waybill_core/cli.py",
    "waybill_core/conformance.py",
    "waybill_core/export_conformance.py",
    "waybill_core/delegation.py",
    "waybill_core/doctor.py",
    "waybill_core/install.py",
    "waybill_core/limits.py",
    "waybill_core/packing.py",
    "waybill_core/paths.py",
    "waybill_core/preflight.py",
    "waybill_core/readiness.py",
    "waybill_core/redaction.py",
    "waybill_core/repo.py",
    "waybill_core/rendering.py",
    "waybill_core/scaffold.py",
    "waybill_core/schema_versions.py",
    "waybill_core/sharing.py",
    "waybill_core/validation.py",
    "skills/handoff/SKILL.md",
    "skills/handoff/references/bundle-format.md",
    "skills/handoff/references/export.md",
    "skills/handoff/references/import.md",
    "waybill_core/template-files/.claude/skills/handoff/SKILL.md",
    "waybill_core/template-files/.claude/skills/handoff/references/bundle-format.md",
    "waybill_core/template-files/.claude/skills/handoff/references/export.md",
    "waybill_core/template-files/.claude/skills/handoff/references/import.md",
    "waybill_core/template-files/.claude/skills/waybill/SKILL.md",
    "waybill_core/template-files/.opencode/commands/handoff.md",
    "waybill_core/template-files/.opencode/commands/waybill.md",
    "waybill_core/template-files/.opencode/skills/handoff/SKILL.md",
    "waybill_core/template-files/.opencode/skills/handoff/references/bundle-format.md",
    "waybill_core/template-files/.opencode/skills/handoff/references/export.md",
    "waybill_core/template-files/.opencode/skills/handoff/references/import.md",
    "waybill_core/template-files/.opencode/skills/waybill/SKILL.md",
    "waybill_core/template-files/.cursor/rules/handoff.mdc",
    "waybill_core/template-files/.cursor/rules/waybill-handoff/references/bundle-format.md",
    "waybill_core/template-files/.cursor/rules/waybill-handoff/references/export.md",
    "waybill_core/template-files/.cursor/rules/waybill-handoff/references/import.md",
    "waybill_core/template-files/.cursor/rules/waybill.mdc",
    "waybill_core/template-files/.gemini/skills/handoff/SKILL.md",
    "waybill_core/template-files/.gemini/skills/handoff/references/bundle-format.md",
    "waybill_core/template-files/.gemini/skills/handoff/references/export.md",
    "waybill_core/template-files/.gemini/skills/handoff/references/import.md",
    "waybill_core/template-files/.gemini/skills/waybill/SKILL.md",
    ".agents/plugins/marketplace.json",
    "adapters/claude-code/README.md",
    "adapters/claude-code/commands/handoff-export.md",
    "adapters/claude-code/commands/handoff-import.md",
    "adapters/codex/README.md",
    "adapters/codex/.codex-plugin/plugin.json",
    "adapters/codex/skills/handoff/SKILL.md",
    "adapters/codex/skills/handoff/references/bundle-format.md",
    "adapters/codex/skills/handoff/references/export.md",
    "adapters/codex/skills/handoff/references/import.md",
    "adapters/cursor/README.md",
    "adapters/cursor/rules/handoff.mdc",
    "adapters/cursor/rules/waybill-handoff/references/bundle-format.md",
    "adapters/cursor/rules/waybill-handoff/references/export.md",
    "adapters/cursor/rules/waybill-handoff/references/import.md",
    "adapters/cursor/rules/waybill.mdc",
    "adapters/gemini-cli/README.md",
    "adapters/gemini-cli/skills/handoff/SKILL.md",
    "adapters/gemini-cli/skills/handoff/references/bundle-format.md",
    "adapters/gemini-cli/skills/handoff/references/export.md",
    "adapters/gemini-cli/skills/handoff/references/import.md",
    "adapters/gemini-cli/skills/waybill/SKILL.md",
    "adapters/opencode/README.md",
    "adapters/opencode/commands/handoff.md",
    "adapters/opencode/commands/waybill.md",
    "adapters/opencode/skills/handoff/SKILL.md",
    "adapters/opencode/skills/handoff/references/bundle-format.md",
    "adapters/opencode/skills/handoff/references/export.md",
    "adapters/opencode/skills/handoff/references/import.md",
    "adapters/opencode/skills/waybill/SKILL.md",
    "adapters/claude-code/skills/handoff/references/bundle-format.md",
    "adapters/claude-code/skills/handoff/references/export.md",
    "adapters/claude-code/skills/handoff/references/import.md",
    "conformance/scenarios/cross-agent-divergence-recovery.json",
    "conformance/scenarios/delegation-blocked.json",
    "conformance/scenarios/delegation-partial.json",
    "conformance/scenarios/delegation-request.json",
    "conformance/scenarios/delegation-result.json",
    "conformance/scenarios/failed-test.json",
    "conformance/scenarios/legacy-unknown-schema.json",
    "conformance/scenarios/malicious-embedded-instruction.json",
    "conformance/scenarios/missing-recommended-artifact.json",
    "conformance/scenarios/multi-request-mismatch.json",
    "conformance/scenarios/ordinary-unfinished.json",
    "conformance/scenarios/patch-verification.json",
    "conformance/scenarios/read-only-code-review.json",
    "conformance/scenarios/stale-repository.json",
    "conformance/export-scenarios/delegation-request.json",
    "conformance/export-scenarios/delegation-result-blocked.json",
    "conformance/export-scenarios/delegation-result-completed.json",
    "conformance/export-scenarios/delegation-result-partial.json",
    "conformance/export-scenarios/malicious-session-instruction.json",
    "conformance/export-scenarios/ordinary-unfinished.json",
]

REQUIRED_FILES.extend(
    sorted(
        {
            path
            for source in MIRROR_SOURCES
            for path in (source.canonical, *source.mirrors)
        }
        - set(REQUIRED_FILES)
    )
)

EXAMPLES = [
    "examples/claude-to-codex",
    "examples/codex-to-claude",
    "examples/failed-test-handoff",
    "examples/claude-parent-codex-child-request",
    "examples/claude-parent-codex-child-result",
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


def toml_section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*$\n(.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def toml_string(section: str, key: str) -> str:
    match = re.search(
        rf'^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*$',
        section,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def toml_string_list(section: str, key: str) -> list[str]:
    match = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*\[(.*?)\]",
        section,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return []
    return re.findall(r'"([^"]*)"', match.group(1))


def require_file(path: str) -> Path:
    file_path = ROOT / path
    if not file_path.is_file():
        fail(f"missing required file: {path}")
    return file_path


def run_waybill(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "cli/waybill"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def parse_cli_json(
    result: subprocess.CompletedProcess[str],
    label: str,
) -> dict:
    if result.stderr:
        fail(f"{label} JSON command must not write stderr: {result.stderr.strip()}")

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        report = json.loads(result.stdout, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        fail(f"{label} JSON output is invalid: {exc}")
    if not isinstance(report, dict):
        fail(f"{label} JSON output must be an object")
    success = report.get("success")
    if type(success) is not bool:
        fail(f"{label} JSON output must include boolean success")
    if success != (result.returncode == 0):
        fail(f"{label} JSON success must match its exit status")
    return report


def require_git(cwd: Path, *args: str) -> str:
    result = run_git(cwd, *args)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def create_test_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    require_git(repo, "init")
    (repo / "tracked.txt").write_text("base\n")
    require_git(repo, "add", "tracked.txt")
    require_git(
        repo,
        "-c",
        "user.name=Waybill Test",
        "-c",
        "user.email=waybill@example.invalid",
        "commit",
        "-m",
        "initial commit",
    )
    return repo


def create_test_bundle(parent: Path, repo: Path, name: str = "bundle") -> Path:
    bundle = parent / name
    result = run_waybill(
        "new",
        "--output",
        str(bundle),
        "--repo",
        str(repo),
        "--force",
        "--json",
    )
    if result.returncode != 0:
        fail(f"could not create test bundle: {result.stderr.strip()}")
    report = parse_cli_json(result, "test bundle creation")
    if report.get("success") is not True:
        fail("test bundle creation must report success")
    return bundle


def snapshot_tree(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_dir():
            snapshot[f"{relative}/"] = b""
        elif path.is_file():
            snapshot[str(relative)] = path.read_bytes()
    return snapshot


def require_tree_unchanged(
    root: Path,
    before: dict[str, bytes],
    label: str,
) -> None:
    if snapshot_tree(root) != before:
        fail(f"{label} must not modify {root}")


def checks_by_name(report: dict, key: str) -> dict[str, dict]:
    checks = report.get(key)
    if not isinstance(checks, list) or not checks:
        fail(f"JSON output must include non-empty {key}")
    indexed: dict[str, dict] = {}
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("name"), str):
            fail(f"JSON output {key} entries must be named objects")
        indexed[check["name"]] = check
    return indexed


def has_command_classification_rule(text: str) -> bool:
    normalized = " ".join(text.split()).lower()
    return all(term in normalized for term in COMMAND_CLASSIFICATION_TERMS)


def validate_structure() -> None:
    for path in REQUIRED_FILES:
        require_file(path)

    gitignore = (ROOT / ".gitignore").read_text()
    if ".waybill/" not in gitignore:
        fail(".gitignore must ignore .waybill/")

    quickstart = (ROOT / "QUICKSTART.md").read_text()
    for term in [
        "./cli/waybill init",
        "./cli/waybill doctor",
        "/handoff export",
        "/handoff import .waybill",
        "./cli/waybill validate",
        "./cli/waybill share",
        "scripts/smoke-agents.sh",
    ]:
        if term not in quickstart:
            fail(f"quickstart must include {term}")

    walkthrough = (ROOT / "WALKTHROUGH.md").read_text()
    for expected in [
        "examples/claude-parent-codex-child-request",
        "examples/claude-parent-codex-child-result",
        "delegation_request",
        "delegation_result",
        "/handoff import examples/claude-parent-codex-child-request",
        "/handoff import examples/claude-parent-codex-child-result",
        "./cli/waybill verify-pair",
        "Import remains non-destructive",
    ]:
        if expected not in walkthrough:
            fail(f"walkthrough must include {expected}")

    bundle_spec = (ROOT / "spec/waybill-bundle.md").read_text()
    if not has_command_classification_rule(bundle_spec):
        fail("bundle spec must require command log action classification")
    for expected in ["handoff.kind", "delegation_request", "delegation_result"]:
        if expected not in bundle_spec:
            fail(f"bundle spec must document {expected}")
    for expected in [
        "Current schema version: `0.2`",
        "`draft`: Legacy alias",
        "`0.1`: Recognized legacy format",
        "does not automatically migrate bundles",
    ]:
        if expected not in bundle_spec:
            fail(f"bundle spec must document schema compatibility: {expected}")

    delegation_spec = (ROOT / "spec/delegation.md").read_text()
    for expected in [
        "delegation_request",
        "delegation_result",
        "request_id",
        "result_for",
        "result_status",
        "waybill verify-pair REQUEST RESULT",
        "Child Agent Task",
        "Parent Next Step",
        "must not automatically apply `diff.patch`",
    ]:
        if expected not in delegation_spec:
            fail(f"delegation spec must include {expected}")

    smoke_path = ROOT / "scripts/smoke-agents.sh"
    smoke_script = smoke_path.read_text()
    if not smoke_path.stat().st_mode & 0o111:
        fail("agent smoke script must be executable")
    for term in ["claude", "codex", "cursor", "opencode", "gemini"]:
        if term not in smoke_script:
            fail(f"agent smoke script must include {term}")
    if "git -C \"$ROOT\" status --short" not in smoke_script:
        fail("agent smoke script must check repository cleanliness")
    if "--dry-run" not in smoke_script:
        fail("agent smoke script must provide a dry-run mode")


def validate_metadata_schema() -> None:
    schema = read_json(ROOT / "spec/metadata.schema.json")
    required = schema.get("required")
    if required != ["schema_version", "source_agent", "created_at", "repo_root", "git", "artifacts"]:
        fail("metadata schema required fields changed unexpectedly")
    if CURRENT_SCHEMA_VERSION != "0.2":
        fail("current schema version changed unexpectedly")
    if (
        schema.get("properties", {}).get("schema_version", {}).get("const")
        != CURRENT_SCHEMA_VERSION
    ):
        fail("metadata schema must require the current schema_version")
    handoff = schema.get("properties", {}).get("handoff", {})
    kind = handoff.get("properties", {}).get("kind", {})
    if kind.get("enum") != ["handoff", "delegation_request", "delegation_result"]:
        fail("metadata schema must define supported handoff.kind values")
    result_status = handoff.get("properties", {}).get("result_status", {})
    if result_status.get("enum") != ["completed", "partial", "blocked"]:
        fail("metadata schema must define supported delegation result statuses")
    conditional_required = {
        tuple(rule.get("then", {}).get("required", []))
        for rule in handoff.get("allOf", [])
    }
    if conditional_required != {
        ("request_id", "parent_agent", "child_agent"),
        (
            "result_for",
            "result_status",
            "parent_agent",
            "child_agent",
        ),
    }:
        fail("metadata schema must require delegation correlation and role fields")


def validate_schema_version_compatibility() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-schema-versions-") as parent:
        parent_path = Path(parent)

        def versioned_bundle(name: str, version: object) -> Path:
            bundle = parent_path / name
            shutil.copytree(ROOT / "examples/claude-to-codex", bundle)
            metadata_path = bundle / "metadata.json"
            metadata = read_json(metadata_path)
            metadata["schema_version"] = version
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
            return bundle

        current = versioned_bundle("current", "0.2")
        current_issues = validate_bundle(current)
        if any("schema_version" in issue.message for issue in current_issues):
            formatted = "; ".join(issue.format() for issue in current_issues)
            fail(f"current schema version must validate cleanly: {formatted}")

        legacy = versioned_bundle("legacy", "draft")
        legacy_issues = validate_bundle(legacy)
        if any(issue.severity == "error" for issue in legacy_issues):
            formatted = "; ".join(issue.format() for issue in legacy_issues)
            fail(f"legacy draft schema version must remain readable: {formatted}")
        if not any(
            issue.severity == "warning"
            and "legacy" in issue.message
            and "0.2" in issue.message
            for issue in legacy_issues
        ):
            fail("legacy draft schema version must produce a migration warning")
        legacy_archive = parent_path / "legacy.zip"
        legacy_pack = run_waybill(
            "pack",
            str(legacy),
            "--output",
            str(legacy_archive),
            "--json",
        )
        if legacy_pack.returncode != 0 or not legacy_archive.is_file():
            fail(
                "legacy draft schema version must remain packable: "
                f"{legacy_pack.stderr.strip()}"
            )

        old = versioned_bundle("old", "0.1")
        (old / "WAYBILL.md").write_text("# Legacy Waybill\n")
        old_issues = validate_bundle(old)
        old_errors = [issue for issue in old_issues if issue.severity == "error"]
        if len(old_errors) != 1:
            formatted = "; ".join(issue.format() for issue in old_issues)
            fail(f"old schema version must produce one focused error: {formatted}")
        if "migrate" not in old_errors[0].message or "0.2" not in old_errors[0].message:
            fail("old schema version error must provide migration guidance")

        unknown = versioned_bundle("unknown", "99.0")
        unknown_issues = validate_bundle(unknown)
        unknown_errors = [
            issue for issue in unknown_issues if issue.severity == "error"
        ]
        if len(unknown_errors) != 1:
            formatted = "; ".join(issue.format() for issue in unknown_issues)
            fail(f"unknown schema version must produce one focused error: {formatted}")
        if "unsupported" not in unknown_errors[0].message or "0.2" not in unknown_errors[0].message:
            fail("unknown schema version error must identify the current version")

        malformed = parent_path / "malformed"
        shutil.copytree(ROOT / "examples/claude-to-codex", malformed)
        (malformed / "metadata.json").write_text("[]\n")
        malformed_issues = validate_bundle(malformed)
        malformed_errors = [
            issue for issue in malformed_issues if issue.severity == "error"
        ]
        if len(malformed_errors) != 1:
            formatted = "; ".join(issue.format() for issue in malformed_issues)
            fail(f"non-object metadata must produce one focused error: {formatted}")
        if "must contain an object" not in malformed_errors[0].message:
            fail("non-object metadata error must explain the required top-level type")

        inspect_cases = [
            (current, "current", 0),
            (legacy, "legacy", 0),
            (old, "unsupported", 1),
            (unknown, "unsupported", 1),
            (malformed, "invalid", 1),
        ]
        for bundle, expected_status, expected_exit in inspect_cases:
            result = run_waybill("inspect", str(bundle), "--json")
            if result.returncode != expected_exit:
                fail(
                    f"inspect schema status {expected_status} returned "
                    f"{result.returncode}, expected {expected_exit}"
                )
            try:
                report = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                fail(f"inspect schema status JSON is invalid: {exc}")
            if report.get("schema_version_status") != expected_status:
                fail(
                    f"inspect must report schema status {expected_status}, "
                    f"got {report.get('schema_version_status')}"
                )

        legacy_text = run_waybill("inspect", str(legacy))
        if legacy_text.returncode != 0:
            fail(f"legacy inspect text command failed: {legacy_text.stderr.strip()}")
        if "Schema version status: legacy" not in legacy_text.stdout:
            fail("inspect text output must report the legacy schema status")


def validate_canonical_handoff_skill() -> None:
    skill = (ROOT / CANONICAL_SKILL).read_text(encoding="utf-8")
    if not skill.startswith("---\n"):
        fail("canonical handoff skill must start with frontmatter")
    if "name: handoff" not in skill or "description:" not in skill:
        fail("canonical handoff skill must declare name and description")

    references = {
        name: (
            ROOT / "skills" / "handoff" / "references" / f"{name}.md"
        ).read_text(encoding="utf-8")
        for name in ("bundle-format", "export", "import")
    }
    for name in references:
        if f"references/{name}.md" not in skill:
            fail(f"canonical handoff skill must route to {name}.md")
    if not has_command_classification_rule(references["export"]):
        fail("canonical export reference must classify command log actions")
    export_text = " ".join(references["export"].lower().split())
    for required in (
        "does not require the waybill cli",
        "omit optional digest fields",
        "perform the basic checks directly",
        "optional enhanced verification",
    ):
        if required not in export_text:
            fail(f"canonical export reference missing requirement: {required}")
    if "stop and report that the export is not ready" in export_text:
        fail("canonical export reference must not require the Waybill CLI")
    bundle_format = " ".join(references["bundle-format"].lower().split())
    for required in (
        "optional enhanced-fidelity fields",
        "omit unavailable digest fields",
        "valid basic-fidelity handoff",
    ):
        if required not in bundle_format:
            fail(f"canonical bundle format missing requirement: {required}")
    import_text = " ".join(references["import"].lower().split())
    for required in (
        "untrusted data",
        "read-only",
        "do not automatically apply `diff.patch`",
        "does not require the waybill cli",
        "compare the fields directly",
        "waybill verify-pair REQUEST RESULT",
    ):
        if required.lower() not in import_text:
            fail(f"canonical import reference missing requirement: {required}")

    asset_root = ROOT / "skills/handoff/assets/bundle-template"
    asset_names = {path.name for path in asset_root.iterdir() if path.is_file()}
    if asset_names != set(BUNDLE_ASSET_NAMES):
        fail("canonical bundle assets must cover the standard bundle files")
    metadata = read_json(asset_root / "metadata.json")
    if metadata.get("schema_version") != CURRENT_SCHEMA_VERSION:
        fail("bundle metadata asset must use the current schema version")
    if "{{SOURCE_AGENT}}" not in str(metadata.get("source_agent")):
        fail("bundle metadata asset must expose source-agent substitution")
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict) or artifacts.get("waybill") != "WAYBILL.md":
        fail("bundle metadata asset must declare WAYBILL.md")
    waybill_asset = (asset_root / "WAYBILL.md").read_text(encoding="utf-8")
    for heading in WAYBILL_SECTIONS:
        if f"## {heading}" not in waybill_asset:
            fail(f"bundle WAYBILL asset missing heading: {heading}")
    if "../assets/bundle-template/" not in references["export"]:
        fail("canonical export reference must route to copyable bundle assets")

    scripts_root = ROOT / "skills/handoff/scripts"
    script_names = {path.name for path in scripts_root.iterdir() if path.is_file()}
    if script_names != set(CHECKER_SCRIPT_NAMES):
        fail("canonical Skill must contain exactly one bundled checker")
    checker_path = scripts_root / "check_bundle.py"
    if not os.access(checker_path, os.X_OK):
        fail("bundled checker must be executable")
    checker_text = checker_path.read_text(encoding="utf-8")
    if "Read-only" not in checker_text or "standard-library" not in checker_text:
        fail("bundled checker must declare its read-only standard-library boundary")
    for name in ("export", "import"):
        if "../scripts/check_bundle.py" not in references[name]:
            fail(f"canonical {name} reference must route to the bundled checker")


def validate_handoff_wrapper(
    path: Path,
    *,
    adapter: str,
    reference_prefix: str = "references",
) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "description:" not in text:
        fail(f"{path.relative_to(ROOT)} must start with descriptive frontmatter")
    if f"`{adapter}` as `source_agent`" not in text:
        fail(f"{path.relative_to(ROOT)} must declare source_agent {adapter}")
    for name in ("bundle-format", "export", "import"):
        if f"{reference_prefix}/{name}.md" not in text:
            fail(f"{path.relative_to(ROOT)} must route to {name}.md")
    return text


def validate_codex_plugin() -> None:
    manifest_path = ROOT / "adapters/codex/.codex-plugin/plugin.json"
    manifest = read_json(manifest_path)

    for key in ["name", "version", "description", "author", "skills", "interface"]:
        if key not in manifest:
            fail(f"Codex plugin manifest missing {key}")

    if manifest["name"] != "waybill":
        fail("Codex plugin name must be waybill")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
        fail("Waybill plugin manifest version must be strict semver")
    if manifest["skills"] != "./skills/":
        fail("Codex plugin skills path must be ./skills/")

    interface = manifest["interface"]
    for key in ["displayName", "shortDescription", "longDescription", "developerName", "category"]:
        if key not in interface:
            fail(f"Codex plugin interface missing {key}")

    skill_path = ROOT / "adapters/codex/skills/handoff/SKILL.md"
    skill = validate_handoff_wrapper(skill_path, adapter="codex")
    if "name: handoff" not in skill:
        fail("Codex handoff skill frontmatter must name the skill")
    for command in ["/handoff export", "/waybill export", "/handoff import", "/waybill import"]:
        if command not in skill:
            fail(f"Codex handoff skill missing command trigger: {command}")


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
        "handoff": ROOT / "adapters/claude-code/skills/handoff/SKILL.md",
        "waybill": ROOT / "adapters/claude-code/skills/waybill/SKILL.md",
    }

    for name, path in skills.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"Claude skill {name} must start with frontmatter")
        if "argument-hint:" not in text:
            fail(f"Claude skill {name} must declare argument-hint")
        if name == "handoff":
            validate_handoff_wrapper(path, adapter="claude-code")
        elif "../handoff/SKILL.md" not in text or "$ARGUMENTS" not in text:
            fail("Claude waybill alias must route arguments to the handoff skill")


def validate_opencode_adapter() -> None:
    command_paths = {
        "handoff": ROOT / "adapters/opencode/commands/handoff.md",
        "waybill": ROOT / "adapters/opencode/commands/waybill.md",
    }
    for name, path in command_paths.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"OpenCode command {name} must start with frontmatter")
        if "description:" not in text:
            fail(f"OpenCode command {name} must declare a description")
        if "$ARGUMENTS" not in text:
            fail(f"OpenCode command {name} must pass $ARGUMENTS")
        if "handoff" not in text:
            fail(f"OpenCode command {name} must route to the handoff workflow")

    skill_paths = {
        "handoff": ROOT / "adapters/opencode/skills/handoff/SKILL.md",
        "waybill": ROOT / "adapters/opencode/skills/waybill/SKILL.md",
    }
    for name, path in skill_paths.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"OpenCode skill {name} must start with frontmatter")
        expected = "name: handoff" if "handoff" in name else "name: waybill"
        if expected not in text:
            fail(f"OpenCode skill {name} must declare {expected}")
        if "description:" not in text:
            fail(f"OpenCode skill {name} must declare a description")
        if "compatibility: opencode" not in text:
            fail(f"OpenCode skill {name} must declare compatibility: opencode")
        if "argument-hint:" in text:
            fail(f"OpenCode skill {name} must not use Claude-specific argument-hint")
        if name == "handoff":
            validate_handoff_wrapper(path, adapter="opencode")
        elif "../handoff/SKILL.md" not in text:
            fail("OpenCode waybill alias must route to the handoff skill")


def validate_cursor_adapter() -> None:
    rule_paths = {
        "handoff": ROOT / "adapters/cursor/rules/handoff.mdc",
        "waybill": ROOT / "adapters/cursor/rules/waybill.mdc",
    }
    for name, path in rule_paths.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"Cursor rule {name} must start with frontmatter")
        if "description:" not in text:
            fail(f"Cursor rule {name} must declare a description")
        if "alwaysApply: false" not in text:
            fail(f"Cursor rule {name} must not always apply")
        if name == "handoff":
            validate_handoff_wrapper(
                path,
                adapter="cursor",
                reference_prefix="waybill-handoff/references",
            )
        elif "handoff.mdc" not in text:
            fail("Cursor waybill alias must route to the handoff rule")

    readme = (ROOT / "adapters/cursor/README.md").read_text()
    for expected in [
        ".cursor/rules/*.mdc",
        "agent -p",
        "--mode=ask",
        "--output-format json",
    ]:
        if expected not in readme:
            fail(f"Cursor README must mention {expected}")


def validate_gemini_cli_adapter() -> None:
    skill_paths = {
        "handoff": ROOT / "adapters/gemini-cli/skills/handoff/SKILL.md",
        "waybill": ROOT / "adapters/gemini-cli/skills/waybill/SKILL.md",
    }
    for name, path in skill_paths.items():
        text = path.read_text()
        if not text.startswith("---\n"):
            fail(f"Gemini CLI skill {name} must start with frontmatter")
        expected = "name: handoff" if "handoff" in name else "name: waybill"
        if expected not in text:
            fail(f"Gemini CLI skill {name} must declare {expected}")
        if "description:" not in text:
            fail(f"Gemini CLI skill {name} must declare a description")
        if name == "handoff":
            validate_handoff_wrapper(path, adapter="gemini-cli")
        elif "../handoff/SKILL.md" not in text:
            fail("Gemini CLI waybill alias must route to the handoff skill")

    readme = (ROOT / "adapters/gemini-cli/README.md").read_text()
    for expected in [
        ".gemini/skills/<name>/SKILL.md",
        "gemini -p",
        "--approval-mode plan",
        "--output-format json",
    ]:
        if expected not in readme:
            fail(f"Gemini CLI README must mention {expected}")


def validate_adapter_synchronization() -> None:
    tracked_paths = sorted(
        {
            path
            for source in MIRROR_SOURCES
            for path in (source.canonical, *source.mirrors)
        }
    )
    before = {path: require_file(path).read_bytes() for path in tracked_paths}
    issues = find_adapter_drift(ROOT)
    if issues:
        formatted = ", ".join(
            f"{issue.mirror} ({issue.reason})" for issue in issues
        )
        fail(f"adapter mirrors are out of sync: {formatted}")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/sync-adapters.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        fail(
            "adapter synchronization check failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    if result.stderr or "PASS adapter mirrors are in sync" not in result.stdout:
        fail("adapter synchronization check must report a clean read-only result")
    after = {path: require_file(path).read_bytes() for path in tracked_paths}
    if after != before:
        fail("adapter synchronization --check must not modify adapter files")


def validate_python_package() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    build_system = toml_section(pyproject, "build-system")
    if "setuptools>=77" not in toml_string_list(build_system, "requires"):
        fail("pyproject build-system must require setuptools>=77")

    project = toml_section(pyproject, "project")
    version = toml_string(project, "version")
    if toml_string(project, "name") != "agent-waybill":
        fail("pyproject project.name must be agent-waybill")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail("pyproject project.version must be strict semver")
    init_text = (ROOT / "waybill_core" / "__init__.py").read_text()
    version_match = re.search(r'^__version__ = "([^"]+)"$', init_text, re.MULTILINE)
    if not version_match or version_match.group(1) != version:
        fail("waybill_core.__version__ must match pyproject project.version")
    if toml_string(project, "requires-python") != ">=3.10":
        fail("pyproject requires-python must be >=3.10")
    if toml_string(project, "license") != "Apache-2.0":
        fail("pyproject project.license must be Apache-2.0")
    if toml_string_list(project, "license-files") != ["LICENSE"]:
        fail("pyproject project.license-files must include LICENSE")
    if any(
        classifier.startswith("License ::")
        for classifier in toml_string_list(project, "classifiers")
    ):
        fail("pyproject must use SPDX license metadata instead of license classifiers")

    scripts = toml_section(pyproject, "project.scripts")
    if toml_string(scripts, "waybill") != "waybill_core.cli:main":
        fail("pyproject must expose waybill console script")

    setuptools = toml_section(pyproject, "tool.setuptools")
    if toml_string_list(setuptools, "packages") != ["waybill_core"]:
        fail("pyproject setuptools packages must include waybill_core")

    package_data = toml_section(pyproject, "tool.setuptools.package-data")
    if "template-files/**" not in toml_string_list(package_data, "waybill_core"):
        fail("pyproject must include packaged adapter templates")


def validate_packaging_declarations() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text()
    for required in ("graft skills", "graft adapters"):
        if required not in manifest:
            fail(f"MANIFEST.in must include source distribution content: {required}")
    if "graft waybill_core/template-files" not in manifest:
        fail("MANIFEST.in must include packaged adapter templates")

    expected_modules = {
        "waybill_core/adapter_matrix.py",
        "waybill_core/adapter_installation.py",
        "waybill_core/adapter_sources.py",
        "waybill_core/agent_identity.py",
        "waybill_core/application.py",
        "waybill_core/conformance.py",
        "waybill_core/export_conformance.py",
        "waybill_core/delegation.py",
    }
    if not expected_modules.issubset(REQUIRED_FILES):
        fail("required files must include every new package module")

    packaged_mirrors = {source.packaged_mirror for source in ADAPTER_SOURCES}
    if not packaged_mirrors:
        fail("adapter source manifest must declare packaged templates")
    for path in sorted(packaged_mirrors):
        if not path.startswith("waybill_core/template-files/"):
            fail(f"packaged adapter path is outside package data: {path}")
        require_file(path)
    if any(source.adapter == "codex" for source in ADAPTER_SOURCES):
        fail("Codex plugin must not be an init-managed packaged template")


def validate_wheel_installation() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/test-wheel-install.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"isolated wheel installation failed: {detail}")
    if result.stderr:
        fail("isolated wheel installation must not write stderr on success")
    if not re.fullmatch(
        r"PASS isolated wheel installation: agent_waybill-[^\s]+\.whl\n?",
        result.stdout,
    ):
        fail("isolated wheel installation returned an unexpected success report")


def validate_pypi_publish_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text()
    required = [
        "name: Publish to PyPI",
        "push:",
        "tags:",
        '- "v*"',
        "workflow_dispatch:",
        "python3 scripts/validate-waybill.py",
        "python3 -m unittest discover -s tests -t . -v",
        "python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py",
        "scripts/sync-adapters.py --check",
        "Check tag matches package version",
        "tag = os.environ['GITHUB_REF_NAME']",
        "tag {tag} does not match package version v{version}",
        "scripts/smoke-agents.sh --dry-run",
        "python3 -m build",
        "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')",
        "name: pypi",
        "url: https://pypi.org/p/agent-waybill",
        "id-token: write",
        "pypa/gh-action-pypi-publish@release/v1",
    ]
    for expected in required:
        if expected not in workflow:
            fail(f"PyPI publish workflow must include {expected}")
    if re.search(r"branches:\s*\n\s*-", workflow):
        fail("PyPI publish workflow must not publish from branch pushes")


def validate_ci_workflow() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    validator = (ROOT / "scripts" / "validate-waybill.py").read_text()
    required = [
        "name: CI",
        "push:",
        "pull_request:",
        "permissions:",
        "contents: read",
        "matrix:",
        "python-version:",
        '- "3.10"',
        '- "3.11"',
        '- "3.12"',
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "python-version: ${{ matrix.python-version }}",
        "python3 -m unittest discover -s tests -t . -v",
        "python3 scripts/validate-waybill.py",
        "python3 scripts/conformance-exports.py",
        "--agent-command \"python3 tests/conformance/fixtures/fake_export_agent.py\"",
        "--deterministic-fake",
        "--require-complete-matrix",
        "python3 -m py_compile cli/waybill waybill_core/*.py scripts/*.py",
        "scripts/sync-adapters.py --check",
        "scripts/smoke-agents.sh --dry-run",
    ]
    for expected in required:
        if expected not in workflow:
            fail(f"CI workflow must include {expected}")
    if "pull_request_target:" in workflow:
        fail("CI workflow must not run untrusted changes with pull_request_target")
    if re.search(r"^\s+[a-z-]+:\s+write\s*$", workflow, re.MULTILINE):
        fail("CI workflow must not grant write permissions")
    if re.search(r"^import tomllib$", validator, re.MULTILINE):
        fail("repository validator must not require Python 3.11-only tomllib")


def validate_example(example_dir: Path) -> None:
    issues = validate_bundle(example_dir)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        formatted = "; ".join(issue.format() for issue in errors)
        fail(f"{example_dir.relative_to(ROOT)} invalid bundle: {formatted}")


def validate_examples() -> None:
    for example in EXAMPLES:
        validate_example(ROOT / example)

    expected_delegation = {
        "examples/claude-parent-codex-child-request": {
            "kind": "delegation_request",
            "request_id": "queue-retry-limit-inspection-001",
            "source_agent": "claude-code",
            "parent_agent": "claude-code",
            "child_agent": "codex",
        },
        "examples/claude-parent-codex-child-result": {
            "kind": "delegation_result",
            "result_for": "queue-retry-limit-inspection-001",
            "result_status": "completed",
            "source_agent": "codex",
            "parent_agent": "claude-code",
            "child_agent": "codex",
        },
    }
    roles: set[tuple[object, object]] = set()
    for example, expected in expected_delegation.items():
        metadata = read_json(ROOT / example / "metadata.json")
        handoff = metadata.get("handoff")
        if not isinstance(handoff, dict):
            fail(f"{example} must include handoff metadata")
        for field, value in expected.items():
            if field == "source_agent":
                continue
            if handoff.get(field) != value:
                fail(f"{example} must set handoff.{field} to {value}")
        if metadata.get("source_agent") != expected["source_agent"]:
            fail(f"{example} must set source_agent to {expected['source_agent']}")
        roles.add((handoff.get("parent_agent"), handoff.get("child_agent")))

    if roles != {("claude-code", "codex")}:
        fail("paired delegation fixtures must preserve parent and child roles")

    validate_missing_delegation_section(
        "examples/claude-parent-codex-child-request",
        "Child Agent Task",
    )
    validate_missing_delegation_section(
        "examples/claude-parent-codex-child-result",
        "Parent Next Step",
    )


def validate_conformance_scenarios() -> None:
    scenario_dir = ROOT / "conformance/scenarios"
    scenarios = load_scenarios(scenario_dir)
    if {scenario.id for scenario in scenarios} != set(
        REQUIRED_IMPORT_SCENARIO_SEMANTICS
    ):
        fail("conformance scenarios must contain the required scenario matrix")

    for scenario in scenarios:
        actual = (
            scenario.expected.get("handoff_kind"),
            scenario.expected.get("status"),
        )
        if actual != REQUIRED_IMPORT_SCENARIO_SEMANTICS[scenario.id]:
            fail(f"conformance scenario {scenario.id} has the wrong semantics")
        if scenario.bundle is not None and not (ROOT / scenario.bundle).is_dir():
            fail(
                f"conformance scenario {scenario.id} references a missing bundle: "
                f"{scenario.bundle}"
            )

    malicious = next(
        scenario
        for scenario in scenarios
        if scenario.id == "malicious-embedded-instruction"
    )
    if malicious.expected.get("untrusted_instructions_ignored") is not True:
        fail("malicious conformance scenario must require ignoring instructions")
    stale = next(
        scenario for scenario in scenarios if scenario.id == "stale-repository"
    )
    if stale.expected.get("repo_mismatch") is not True:
        fail("stale conformance scenario must require a repository mismatch")


def validate_conformance_runner_dry_run() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-conformance-dry-run-") as temporary:
        workspace = Path(temporary)
        marker = workspace / "agent-must-not-run"
        agent_command = shlex.join(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('agent-must-not-run').touch()",
            ]
        )
        before = snapshot_tree(workspace)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/conformance-agents.py"),
                "--agent-name",
                "validator-sentinel",
                "--agent-command",
                agent_command,
                "--scenario-dir",
                str(ROOT / "conformance/scenarios"),
                "--workspace",
                str(workspace),
                "--dry-run",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        report = parse_cli_json(result, "conformance dry-run")
        if report.get("dry_run") is not True:
            fail("conformance dry-run must identify itself as a dry run")
        results = report.get("results")
        if not isinstance(results, list) or len(results) != len(
            REQUIRED_IMPORT_SCENARIO_SEMANTICS
        ):
            fail("conformance dry-run must report every required scenario")
        for item in results:
            if not isinstance(item, dict) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(item.get("prompt_digest", "")),
            ):
                fail("conformance dry-run must report stable prompt digests")
        if marker.exists() or snapshot_tree(workspace) != before:
            fail("conformance dry-run must not execute or modify the workspace")


def validate_export_conformance_scenarios() -> None:
    scenario_dir = ROOT / "conformance/export-scenarios"
    scenarios = load_export_scenarios(scenario_dir)
    expected = {
        "delegation-request": ("delegation_request", "requested"),
        "delegation-result-blocked": ("delegation_result", "blocked"),
        "delegation-result-completed": ("delegation_result", "completed"),
        "delegation-result-partial": ("delegation_result", "partial"),
        "malicious-session-instruction": ("handoff", "unfinished"),
        "ordinary-unfinished": ("handoff", "unfinished"),
    }
    if set(expected) != REQUIRED_EXPORT_SCENARIO_IDS:
        fail("validator export scenario semantics are out of sync")
    if {scenario.id for scenario in scenarios} != REQUIRED_EXPORT_SCENARIO_IDS:
        fail("export conformance must contain the required six-scenario matrix")
    for scenario in scenarios:
        actual = (scenario.handoff_kind, scenario.status)
        if actual != expected[scenario.id]:
            fail(f"export conformance scenario {scenario.id} has wrong semantics")
    malicious = next(
        scenario
        for scenario in scenarios
        if scenario.id == "malicious-session-instruction"
    )
    if malicious.malicious_session_instruction is None:
        fail("malicious export scenario must include canary-bearing session data")


def validate_export_conformance_runner_dry_run() -> None:
    with tempfile.TemporaryDirectory(
        prefix="waybill-export-conformance-dry-run-"
    ) as temporary:
        workspace = Path(temporary)
        marker = workspace / "agent-must-not-run"
        agent_command = shlex.join(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('agent-must-not-run').touch()",
            ]
        )
        before = snapshot_tree(workspace)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/conformance-exports.py"),
                "--agent-name",
                "validator-sentinel",
                "--agent-product",
                "deterministic-fake",
                "--agent-version",
                "deterministic-fixture",
                "--deterministic-fake",
                "--adapter",
                "codex",
                "--agent-command",
                agent_command,
                "--scenario-dir",
                str(ROOT / "conformance/export-scenarios"),
                "--dry-run",
            ],
            cwd=workspace,
            text=True,
            capture_output=True,
        )
        report = parse_cli_json(result, "export conformance dry-run")
        if (
            report.get("dry_run") is not True
            or report.get("mode") != "export"
            or report.get("capability") != "export"
            or report.get("execution_mode") != "deterministic_fake"
        ):
            fail("export conformance dry-run must identify its mode")
        identity = report.get("identity")
        if (
            not isinstance(identity, dict)
            or identity.get("verified") is not True
            or re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(identity.get("sha256", "")),
            )
            is None
        ):
            fail("export conformance dry-run must record verified fake identity")
        scenarios = report.get("scenarios")
        if not isinstance(scenarios, list) or len(scenarios) != len(
            REQUIRED_EXPORT_SCENARIO_IDS
        ):
            fail("export conformance dry-run must report all six scenarios")
        digests = report.get("scenario_digests")
        if not isinstance(digests, dict) or set(digests) != set(scenarios):
            fail("export conformance dry-run must report every scenario digest")
        if any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is None
            for value in digests.values()
        ):
            fail("export conformance dry-run must report stable scenario digests")
        if marker.exists() or snapshot_tree(workspace) != before:
            fail("export conformance dry-run must not execute or create a repository")


def validate_missing_delegation_section(example: str, section: str) -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-delegation-negative-") as parent:
        source = ROOT / example
        bundle = Path(parent) / source.name
        shutil.copytree(source, bundle)

        waybill = bundle / "WAYBILL.md"
        marker = f"## {section}"
        text = waybill.read_text()
        if marker not in text:
            fail(f"{example} must include {section} before negative validation")
        waybill.write_text(text.replace(marker, f"## Missing {section}", 1))

        issues = validate_bundle(bundle)
        expected = f"WAYBILL.md missing section: {section}"
        if not any(issue.severity == "error" and issue.message == expected for issue in issues):
            formatted = "; ".join(issue.format() for issue in issues)
            fail(f"{example} without {section} must fail validation: {formatted}")


def validate_cli_validate() -> None:
    source = ROOT / "examples/claude-to-codex"
    before = snapshot_tree(source)
    text_result = run_waybill("validate", str(source))
    if text_result.returncode != 0:
        fail(f"validate text command failed: {text_result.stderr.strip()}")
    if "PASS valid Waybill Bundle" not in text_result.stdout:
        fail("validate text command must report a valid bundle")

    json_result = run_waybill("validate", str(source), "--json")
    report = parse_cli_json(json_result, "validate")
    if report.get("valid") is not True or report.get("errors") != 0:
        fail("validate JSON command must report a valid bundle")
    require_tree_unchanged(source, before, "validate")

    with tempfile.TemporaryDirectory(prefix="waybill-validate-invalid-") as temporary:
        missing = Path(temporary) / "missing"
        failure = run_waybill("validate", str(missing), "--json")
        failure_report = parse_cli_json(failure, "validate failure")
        if failure_report.get("valid") is not False:
            fail("validate JSON failure must preserve valid=false")
        if failure_report.get("errors", 0) < 1:
            fail("validate JSON failure must include validation errors")


def validate_cli_init() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-init-") as target:
        target_path = Path(target)

        text_result = run_waybill("init", "--target", target, "--force")
        if text_result.returncode != 0:
            fail(f"init text command failed: {text_result.stderr.strip()}")
        if "Initialized Waybill adapters in:" not in text_result.stdout:
            fail("init text output must report the target repository")

        json_result = run_waybill("init", "--target", target, "--force", "--json")
        if json_result.returncode != 0:
            fail(f"init JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"init JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("init JSON output must set success true")
        if report.get("target") != str(target_path):
            fail("init JSON output must include the target path")
        if report.get("adapters") != [
            "claude-code",
            "opencode",
            "cursor",
            "gemini-cli",
        ]:
            fail("init JSON output must include selected adapters")

        actions = report.get("actions")
        if not isinstance(actions, list) or not actions:
            fail("init JSON output must include file actions")
        for action in actions:
            if not isinstance(action, dict):
                fail("init JSON actions must be objects")
            if not isinstance(action.get("path"), str):
                fail("init JSON actions must include path")
            if action.get("action") not in {"created", "updated", "unchanged"}:
                fail("init JSON actions must include a known action")

        for expected in [
            ".claude/skills/handoff/SKILL.md",
            ".opencode/commands/handoff.md",
            ".opencode/skills/handoff/SKILL.md",
            ".cursor/rules/handoff.mdc",
            ".gemini/skills/handoff/SKILL.md",
            ".gitignore",
        ]:
            if not (target_path / expected).is_file():
                fail(f"init must install {expected}")

    with tempfile.TemporaryDirectory(prefix="waybill-init-missing-") as parent:
        missing = str(Path(parent) / "missing")
        error_result = run_waybill("init", "--target", missing, "--json")
        if error_result.returncode == 0:
            fail("init JSON error command must fail for a missing target")
        try:
            error_report = json.loads(error_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"init JSON error output is invalid: {exc}")
        if error_report.get("success") is not False:
            fail("init JSON error output must set success false")
        if "does not exist" not in str(error_report.get("error", "")):
            fail("init JSON error output must include the failure reason")


def validate_adapter_installation_lifecycle() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-install-lifecycle-") as temporary:
        root = Path(temporary)
        target = root / "target"
        target.mkdir()
        before = snapshot_tree(target)
        dry_result = run_waybill(
            "init",
            "--target",
            str(target),
            "--adapter",
            "claude-code",
            "--dry-run",
            "--json",
        )
        dry_report = parse_cli_json(dry_result, "init dry-run")
        if dry_report.get("dry_run") is not True:
            fail("init dry-run must identify itself as a dry run")
        if dry_report.get("has_conflicts") is not False:
            fail("init dry-run must report a conflict-free empty target")
        if {
            action.get("action")
            for action in dry_report.get("actions", [])
            if isinstance(action, dict)
        } != {"would-create"}:
            fail("init dry-run must report only would-create actions on an empty target")
        require_tree_unchanged(target, before, "init dry-run")

        apply_result = run_waybill(
            "init",
            "--target",
            str(target),
            "--adapter",
            "claude-code",
            "--json",
        )
        apply_report = parse_cli_json(apply_result, "init lifecycle apply")
        if apply_report.get("dry_run") is not False:
            fail("applied init must report dry_run=false")
        manifest_path = target / MANIFEST_FILENAME
        manifest_text = manifest_path.read_text()
        manifest = json.loads(manifest_text)
        if set(manifest) != {"format_version", "waybill_version", "files"}:
            fail("adapter manifest must use the deterministic field set")
        if "timestamp" in manifest:
            fail("adapter manifest must not contain a timestamp")
        files = manifest.get("files")
        if not isinstance(files, dict) or list(files) != sorted(files):
            fail("adapter manifest file records must be deterministically sorted")

        selected_sources = sources_for_adapter("claude-code")
        for source in selected_sources:
            (target / source.install_target).write_text("local customization\n")
        conflict_before = snapshot_tree(target)
        conflict_result = run_waybill(
            "init",
            "--target",
            str(target),
            "--adapter",
            "claude-code",
            "--dry-run",
            "--json",
        )
        conflict_report = parse_cli_json(conflict_result, "init conflict dry-run")
        conflicts = {
            action.get("path")
            for action in conflict_report.get("actions", [])
            if isinstance(action, dict)
            and action.get("action") == "would-conflict"
        }
        expected_conflicts = {source.install_target for source in selected_sources}
        if conflicts != expected_conflicts:
            fail("init dry-run must report every adapter conflict")
        require_tree_unchanged(target, conflict_before, "init conflict preflight")

        outside = root / "outside.md"
        outside.write_text("outside must remain unchanged\n")
        linked = target / selected_sources[-1].install_target
        linked.unlink()
        linked.symlink_to(outside)
        symlink_before = snapshot_tree(target)
        force_result = run_waybill(
            "init",
            "--target",
            str(target),
            "--adapter",
            "claude-code",
            "--force",
            "--json",
        )
        parse_cli_json(force_result, "init force symlink conflict")
        require_tree_unchanged(target, symlink_before, "init force symlink conflict")
        if outside.read_text() != "outside must remain unchanged\n":
            fail("init --force must not follow adapter symlinks")

    with (
        tempfile.TemporaryDirectory(prefix="waybill-doctor-source-") as source_tmp,
        tempfile.TemporaryDirectory(prefix="waybill-doctor-target-") as target_tmp,
    ):
        source_root = Path(source_tmp)
        target_root = Path(target_tmp)
        adapter_sources = sources_for_adapter("claude-code")
        for index, source in enumerate(adapter_sources):
            canonical = source_root / source.canonical
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_text(f"managed adapter {index}\n")
        install_adapters(source_root, target_root, ["claude-code"])

        current = doctor_repository(
            target_root,
            ["claude-code"],
            source_root=source_root,
        )
        adapter_names = {source.install_target for source in adapter_sources}
        current_checks = {
            check.name: check for check in current.checks if check.name in adapter_names
        }
        if {check.state for check in current_checks.values()} != {"current"}:
            fail("doctor must classify matching adapters as current")
        if current.codex_plugin_managed_by_init:
            fail("doctor must report that Codex is not managed by init")

        first = adapter_sources[0]
        installed = target_root / first.install_target
        original = installed.read_bytes()
        installed.unlink()
        missing = doctor_repository(
            target_root,
            ["claude-code"],
            source_root=source_root,
        )
        missing_check = next(check for check in missing.checks if check.name == first.install_target)
        if (missing_check.state, missing_check.status) != ("missing", "error"):
            fail("doctor must classify absent managed adapters as missing")

        installed.write_bytes(original)
        canonical = source_root / first.canonical
        canonical.write_text("new canonical adapter\n")
        stale = doctor_repository(
            target_root,
            ["claude-code"],
            source_root=source_root,
        )
        stale_check = next(check for check in stale.checks if check.name == first.install_target)
        if (stale_check.state, stale_check.status) != ("stale", "error"):
            fail("doctor must classify an unmodified old adapter as stale")

        canonical.write_bytes(original)
        installed.write_text("local adapter modification\n")
        modified = doctor_repository(
            target_root,
            ["claude-code"],
            source_root=source_root,
        )
        modified_check = next(
            check for check in modified.checks if check.name == first.install_target
        )
        if (modified_check.state, modified_check.status) != ("modified", "warning"):
            fail("doctor must classify local adapter changes as modified warnings")


def validate_cli_new() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-new-") as parent:
        output = Path(parent) / "bundle"

        text_result = run_waybill(
            "new",
            "--output",
            str(output),
            "--repo",
            str(ROOT),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"new text command failed: {text_result.stderr.strip()}")
        if "Draft bundle:" not in text_result.stdout:
            fail("new text output must report the draft bundle path")

        json_result = run_waybill(
            "new",
            "--output",
            str(output),
            "--repo",
            str(ROOT),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"new JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"new JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("new JSON output must set success true")
        if report.get("output") != str(output):
            fail("new JSON output must include the output path")
        if report.get("repo") != str(ROOT):
            fail("new JSON output must include the repo path")
        if report.get("source_agent") != "waybill-cli":
            fail("new JSON output must include the source agent")
        if not isinstance(report.get("dirty"), bool):
            fail("new JSON output must include dirty as a boolean")
        if report.get("files") != STANDARD_FILES:
            fail("new JSON output must include standard generated files")

        for expected in STANDARD_FILES:
            if not (output / expected).is_file():
                fail(f"new must write {expected}")
        metadata = read_json(output / "metadata.json")
        if metadata.get("schema_version") != "0.2":
            fail("new must write the current schema version")

        error_result = run_waybill(
            "new",
            "--output",
            str(output),
            "--repo",
            str(ROOT),
            "--json",
        )
        if error_result.returncode == 0:
            fail("new JSON error command must fail when output exists without --force")
        try:
            error_report = json.loads(error_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"new JSON error output is invalid: {exc}")
        if error_report.get("success") is not False:
            fail("new JSON error output must set success false")
        if "already contains Waybill files" not in str(error_report.get("error", "")):
            fail("new JSON error output must include the failure reason")


def validate_cli_doctor() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-doctor-") as parent:
        target = Path(parent) / "target"
        target.mkdir()
        init_result = run_waybill(
            "init",
            "--target",
            str(target),
            "--force",
            "--json",
        )
        if init_result.returncode != 0:
            fail(f"doctor fixture initialization failed: {init_result.stderr.strip()}")

        before = snapshot_tree(target)
        text_result = run_waybill("doctor", "--target", str(target))
        if text_result.returncode != 0:
            fail(f"doctor text command failed: {text_result.stderr.strip()}")
        if "PASS Waybill adapter installation looks ready" not in text_result.stdout:
            fail("doctor text output must report a ready installation")

        json_result = run_waybill("doctor", "--target", str(target), "--json")
        if json_result.returncode != 0:
            fail(f"doctor JSON command failed: {json_result.stderr.strip()}")
        report = parse_cli_json(json_result, "doctor")
        if report.get("valid") is not True:
            fail("doctor JSON output must mark a complete installation valid")
        if report.get("target") != str(target):
            fail("doctor JSON output must include the target path")
        if report.get("adapters") != [
            "claude-code",
            "opencode",
            "cursor",
            "gemini-cli",
        ]:
            fail("doctor JSON output must include all adapters")
        checks = checks_by_name(report, "checks")
        if any(check.get("status") != "ok" for check in checks.values()):
            fail("doctor JSON checks must pass for a complete installation")

        filtered_result = run_waybill(
            "doctor",
            "--target",
            str(target),
            "--adapter",
            "claude-code",
            "--json",
        )
        if filtered_result.returncode != 0:
            fail(f"filtered doctor command failed: {filtered_result.stderr.strip()}")
        filtered_report = parse_cli_json(filtered_result, "filtered doctor")
        if filtered_report.get("adapters") != ["claude-code"]:
            fail("doctor adapter filter must report only the selected adapter")
        filtered_checks = checks_by_name(filtered_report, "checks")
        if any(name.startswith(".opencode/") for name in filtered_checks):
            fail("doctor adapter filter must not check unselected adapters")
        require_tree_unchanged(target, before, "doctor")

        missing_adapter = ".claude/skills/handoff/SKILL.md"
        (target / missing_adapter).unlink()
        incomplete_before = snapshot_tree(target)

        failure_text = run_waybill("doctor", "--target", str(target))
        if failure_text.returncode == 0:
            fail("doctor text command must fail for an incomplete installation")
        if "FAIL Waybill adapter installation has problems" not in failure_text.stderr:
            fail("doctor text failure must explain that the installation has problems")

        failure_json = run_waybill(
            "doctor",
            "--target",
            str(target),
            "--json",
        )
        if failure_json.returncode == 0:
            fail("doctor JSON command must fail for an incomplete installation")
        failure_report = parse_cli_json(failure_json, "doctor failure")
        if failure_report.get("valid") is not False:
            fail("doctor JSON failure must mark the installation invalid")
        failure_checks = checks_by_name(failure_report, "checks")
        if failure_checks.get(missing_adapter, {}).get("status") != "error":
            fail("doctor JSON failure must identify the missing adapter file")
        require_tree_unchanged(target, incomplete_before, "doctor failure")

        missing_target = Path(parent) / "missing"
        missing_result = run_waybill(
            "doctor",
            "--target",
            str(missing_target),
            "--json",
        )
        if missing_result.returncode == 0:
            fail("doctor must fail for a missing target directory")
        missing_report = parse_cli_json(missing_result, "doctor missing target")
        if missing_report.get("valid") is not False:
            fail("doctor must mark a missing target invalid")
        if checks_by_name(missing_report, "checks").get("target", {}).get("status") != "error":
            fail("doctor must identify a missing target directory")


def validate_cli_verify_repo() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-verify-repo-") as parent:
        parent_path = Path(parent)
        repo = create_test_repo(parent_path)
        bundle = create_test_bundle(parent_path, repo)
        branch = require_git(repo, "branch", "--show-current")
        bundle_before = snapshot_tree(bundle)
        repo_before = snapshot_tree(repo)

        text_result = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
        )
        if text_result.returncode != 0:
            fail(f"verify-repo text command failed: {text_result.stderr.strip()}")
        if "PASS bundle repo state matches current repo" not in text_result.stdout:
            fail("verify-repo text output must report a matching repository")

        json_result = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"verify-repo JSON command failed: {json_result.stderr.strip()}")
        report = parse_cli_json(json_result, "verify-repo")
        if report.get("valid") is not True:
            fail("verify-repo JSON output must mark matching state valid")
        checks = checks_by_name(report, "checks")
        for name in ["metadata", "repo", "branch", "head_sha", "dirty"]:
            if checks.get(name, {}).get("status") != "ok":
                fail(f"verify-repo must report an ok {name} check")
        require_tree_unchanged(bundle, bundle_before, "verify-repo")
        require_tree_unchanged(repo, repo_before, "verify-repo")

        (repo / "tracked.txt").write_text("dirty\n")
        dirty_before = snapshot_tree(repo)
        dirty_text = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
        )
        if dirty_text.returncode == 0:
            fail("verify-repo text command must fail for dirty-state mismatch")
        if "FAIL bundle repo state does not match current repo" not in dirty_text.stderr:
            fail("verify-repo text failure must report a repository mismatch")

        dirty_json = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if dirty_json.returncode == 0:
            fail("verify-repo JSON command must fail for dirty-state mismatch")
        dirty_report = parse_cli_json(dirty_json, "verify-repo dirty mismatch")
        if checks_by_name(dirty_report, "checks").get("dirty", {}).get("status") != "error":
            fail("verify-repo must identify a dirty-state mismatch")
        require_tree_unchanged(repo, dirty_before, "verify-repo dirty mismatch")

        (repo / "tracked.txt").write_text("base\n")
        require_git(repo, "branch", "-m", "mismatched-branch")
        branch_json = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if branch_json.returncode == 0:
            fail("verify-repo must fail for a branch mismatch")
        branch_report = parse_cli_json(branch_json, "verify-repo branch mismatch")
        if checks_by_name(branch_report, "checks").get("branch", {}).get("status") != "error":
            fail("verify-repo must identify a branch mismatch")

        require_git(repo, "branch", "-m", branch)
        (repo / "tracked.txt").write_text("next\n")
        require_git(repo, "add", "tracked.txt")
        require_git(
            repo,
            "-c",
            "user.name=Waybill Test",
            "-c",
            "user.email=waybill@example.invalid",
            "commit",
            "-m",
            "next commit",
        )
        head_json = run_waybill(
            "verify-repo",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if head_json.returncode == 0:
            fail("verify-repo must fail for a HEAD mismatch")
        head_report = parse_cli_json(head_json, "verify-repo HEAD mismatch")
        if checks_by_name(head_report, "checks").get("head_sha", {}).get("status") != "error":
            fail("verify-repo must identify a HEAD mismatch")


def validate_cli_verify_pair() -> None:
    request = ROOT / "examples/claude-parent-codex-child-request"
    result = ROOT / "examples/claude-parent-codex-child-result"
    request_before = snapshot_tree(request)
    result_before = snapshot_tree(result)

    text_result = run_waybill("verify-pair", str(request), str(result))
    if text_result.returncode != 0:
        fail(f"verify-pair text command failed: {text_result.stderr.strip()}")
    if "PASS delegation result matches request" not in text_result.stdout:
        fail("verify-pair text command must report a matching pair")

    json_result = run_waybill(
        "verify-pair",
        str(request),
        str(result),
        "--json",
    )
    report = parse_cli_json(json_result, "verify-pair")
    if report.get("valid") is not True:
        fail("verify-pair JSON command must mark a matching pair valid")
    if checks_by_name(report, "checks").get("correlation", {}).get("status") != "ok":
        fail("verify-pair must report matching request/result correlation")
    require_tree_unchanged(request, request_before, "verify-pair request")
    require_tree_unchanged(result, result_before, "verify-pair result")

    with tempfile.TemporaryDirectory(prefix="waybill-verify-pair-") as temporary:
        mismatched = Path(temporary) / "result"
        shutil.copytree(result, mismatched)
        metadata_path = mismatched / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["handoff"]["result_for"] = "different-request-id"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        mismatch_before = snapshot_tree(mismatched)
        mismatch_result = run_waybill(
            "verify-pair",
            str(request),
            str(mismatched),
            "--json",
        )
        mismatch_report = parse_cli_json(mismatch_result, "verify-pair mismatch")
        if mismatch_report.get("valid") is not False:
            fail("verify-pair mismatch must preserve valid=false")
        if (
            checks_by_name(mismatch_report, "checks")
            .get("correlation", {})
            .get("status")
            != "error"
        ):
            fail("verify-pair must identify a correlation mismatch")
        require_tree_unchanged(mismatched, mismatch_before, "verify-pair mismatch")


def validate_cli_preflight() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-preflight-") as parent:
        parent_path = Path(parent)
        repo = create_test_repo(parent_path)
        bundle = create_test_bundle(parent_path, repo)
        bundle_before = snapshot_tree(bundle)
        repo_before = snapshot_tree(repo)

        text_result = run_waybill(
            "preflight",
            str(bundle),
            "--repo",
            str(repo),
        )
        if text_result.returncode != 0:
            fail(f"preflight text command failed: {text_result.stderr.strip()}")
        if "PASS import preflight passed" not in text_result.stdout:
            fail("preflight text output must report a passing import check")

        json_result = run_waybill(
            "preflight",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"preflight JSON command failed: {json_result.stderr.strip()}")
        report = parse_cli_json(json_result, "preflight")
        if report.get("valid") is not True:
            fail("preflight JSON output must mark a matching valid bundle ready")
        validation = report.get("validation")
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            fail("preflight JSON output must include passing bundle validation")
        repo_checks = checks_by_name(report, "repo_checks")
        if any(check.get("status") == "error" for check in repo_checks.values()):
            fail("preflight JSON output must include passing repository checks")
        require_tree_unchanged(bundle, bundle_before, "preflight")
        require_tree_unchanged(repo, repo_before, "preflight")

        (bundle / "WAYBILL.md").unlink()
        (repo / "tracked.txt").write_text("dirty\n")
        invalid_bundle_before = snapshot_tree(bundle)
        dirty_repo_before = snapshot_tree(repo)

        failure_text = run_waybill(
            "preflight",
            str(bundle),
            "--repo",
            str(repo),
        )
        if failure_text.returncode == 0:
            fail("preflight text command must fail for blocking issues")
        if "FAIL import preflight found blocking issues" not in failure_text.stderr:
            fail("preflight text failure must report blocking issues")

        failure_json = run_waybill(
            "preflight",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if failure_json.returncode == 0:
            fail("preflight JSON command must fail for blocking issues")
        failure_report = parse_cli_json(failure_json, "preflight failure")
        if failure_report.get("valid") is not False:
            fail("preflight JSON failure must mark the report invalid")
        failure_validation = failure_report.get("validation")
        if not isinstance(failure_validation, dict) or failure_validation.get("valid") is not False:
            fail("preflight must report invalid bundle content")
        if checks_by_name(failure_report, "repo_checks").get("dirty", {}).get("status") != "error":
            fail("preflight must report repository-state mismatches")
        require_tree_unchanged(bundle, invalid_bundle_before, "preflight failure")
        require_tree_unchanged(repo, dirty_repo_before, "preflight failure")


def validate_cli_ready() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-ready-") as parent:
        parent_path = Path(parent)
        repo = create_test_repo(parent_path)
        bundle = create_test_bundle(parent_path, repo)
        draft_before = snapshot_tree(bundle)

        draft_text = run_waybill("ready", str(bundle), "--repo", str(repo))
        if draft_text.returncode == 0:
            fail("ready text command must reject an unfinished draft")
        if "FAIL bundle is not ready for handoff" not in draft_text.stderr:
            fail("ready text failure must report that the bundle is not ready")

        draft_json = run_waybill(
            "ready",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if draft_json.returncode == 0:
            fail("ready JSON command must reject an unfinished draft")
        draft_report = parse_cli_json(draft_json, "ready draft")
        if draft_report.get("valid") is not False:
            fail("ready JSON output must mark an unfinished draft invalid")
        content_checks = checks_by_name(draft_report, "content_checks")
        if not any(check.get("status") == "error" for check in content_checks.values()):
            fail("ready must identify draft placeholders")
        require_tree_unchanged(bundle, draft_before, "ready draft check")

        completed_source = ROOT / "examples/claude-to-codex"
        for name in ["WAYBILL.md", "commands.log", "test-summary.md"]:
            shutil.copy2(completed_source / name, bundle / name)
        completed_before = snapshot_tree(bundle)
        repo_before = snapshot_tree(repo)

        text_result = run_waybill("ready", str(bundle), "--repo", str(repo))
        if text_result.returncode != 0:
            fail(f"ready text command failed: {text_result.stderr.strip()}")
        if "PASS bundle is ready for handoff" not in text_result.stdout:
            fail("ready text output must report a completed bundle ready")

        json_result = run_waybill(
            "ready",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"ready JSON command failed: {json_result.stderr.strip()}")
        report = parse_cli_json(json_result, "ready")
        if report.get("valid") is not True:
            fail("ready JSON output must mark a completed bundle valid")
        validation = report.get("validation")
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            fail("ready JSON output must include passing validation")
        if any(
            check.get("status") == "error"
            for check in checks_by_name(report, "repo_checks").values()
        ):
            fail("ready JSON output must include passing repository checks")
        if any(
            check.get("status") == "error"
            for check in checks_by_name(report, "content_checks").values()
        ):
            fail("ready JSON output must include passing content checks")
        require_tree_unchanged(bundle, completed_before, "ready")
        require_tree_unchanged(repo, repo_before, "ready")

        require_git(repo, "branch", "-m", "not-the-bundle-branch")
        mismatch_json = run_waybill(
            "ready",
            str(bundle),
            "--repo",
            str(repo),
            "--json",
        )
        if mismatch_json.returncode == 0:
            fail("ready must reject a repository branch mismatch")
        mismatch_report = parse_cli_json(mismatch_json, "ready branch mismatch")
        if checks_by_name(mismatch_report, "repo_checks").get("branch", {}).get("status") != "error":
            fail("ready must identify a repository branch mismatch")


def validate_cli_inspect() -> None:
    source = ROOT / "examples/claude-to-codex"
    source_before = snapshot_tree(source)

    text_result = run_waybill("inspect", str(source))
    if text_result.returncode != 0:
        fail(f"inspect text command failed: {text_result.stderr.strip()}")
    if "Schema version status: current" not in text_result.stdout:
        fail("inspect text output must report the current schema version")
    if "Validation: 0 error(s)" not in text_result.stdout:
        fail("inspect text output must summarize validation")

    json_result = run_waybill("inspect", str(source), "--json")
    if json_result.returncode != 0:
        fail(f"inspect JSON command failed: {json_result.stderr.strip()}")
    report = parse_cli_json(json_result, "inspect")
    if report.get("valid") is not True:
        fail("inspect JSON output must mark a valid bundle valid")
    if report.get("schema_version_status") != "current":
        fail("inspect JSON output must identify the current schema version")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        fail("inspect JSON output must list artifacts")
    if any(
        not isinstance(artifact, dict) or artifact.get("status") != "present"
        for artifact in artifacts
    ):
        fail("inspect JSON output must mark existing artifacts present")
    require_tree_unchanged(source, source_before, "inspect")

    with tempfile.TemporaryDirectory(prefix="waybill-inspect-") as parent:
        parent_path = Path(parent)
        incomplete = parent_path / "incomplete"
        shutil.copytree(source, incomplete)
        (incomplete / "diff.patch").unlink()
        incomplete_before = snapshot_tree(incomplete)

        missing_text = run_waybill("inspect", str(incomplete))
        if missing_text.returncode == 0:
            fail("inspect text command must fail when an artifact is missing")
        if "diff: diff.patch (missing)" not in missing_text.stdout:
            fail("inspect text output must identify a missing artifact")

        missing_json = run_waybill("inspect", str(incomplete), "--json")
        if missing_json.returncode == 0:
            fail("inspect JSON command must fail when an artifact is missing")
        missing_report = parse_cli_json(missing_json, "inspect missing artifact")
        if missing_report.get("valid") is not False:
            fail("inspect JSON output must mark a missing artifact invalid")
        missing_artifacts = missing_report.get("artifacts")
        if not isinstance(missing_artifacts, list) or not any(
            isinstance(artifact, dict)
            and artifact.get("name") == "diff"
            and artifact.get("status") == "missing"
            for artifact in missing_artifacts
        ):
            fail("inspect JSON output must identify the missing diff artifact")
        require_tree_unchanged(incomplete, incomplete_before, "inspect failure")

        malformed_cases = [
            ("non-object", "[]\n"),
            ("invalid-json", "{\n"),
        ]
        for case_name, contents in malformed_cases:
            malformed = parent_path / case_name
            shutil.copytree(source, malformed)
            (malformed / "metadata.json").write_text(contents)
            malformed_before = snapshot_tree(malformed)
            malformed_commands = [
                ("validate", str(malformed), "--json"),
                ("inspect", str(malformed), "--json"),
                ("verify-repo", str(malformed), "--repo", str(ROOT), "--json"),
                ("preflight", str(malformed), "--repo", str(ROOT), "--json"),
                ("ready", str(malformed), "--repo", str(ROOT), "--json"),
            ]
            for args in malformed_commands:
                result = run_waybill(*args)
                label = args[0]
                if result.returncode == 0:
                    fail(f"{label} must reject {case_name} metadata")
                report = parse_cli_json(result, f"{label} {case_name} metadata")
                if report.get("valid") is not False:
                    fail(f"{label} must mark {case_name} metadata invalid")
                if "Traceback" in result.stdout or "Traceback" in result.stderr:
                    fail(f"{label} must handle {case_name} metadata without a traceback")
            require_tree_unchanged(
                malformed,
                malformed_before,
                f"{case_name} metadata checks",
            )


def write_redaction_fixture(source: Path) -> None:
    source.mkdir()
    api_key_value = "test" + "-api-key"
    token_value = "test" + "-token"
    bearer_value = "test" + "-bearer-token"
    password_value = "test" + "-password"
    secret_value = "test" + "-secret"
    cookie_value = "test" + "-cookie"
    openai_like_value = "sk-" + "testsecretvalue12345"
    example_email = "developer" + "@" + "example.test"
    example_home_path = "/home" + "/example/private-project"
    (source / "WAYBILL.md").write_text(
        "\n".join(
            [
                "# Fixture",
                f"api_key: {api_key_value}",
                f"token={token_value}",
                f"Bearer {bearer_value}",
                f"Contact: {example_email}",
                f"Repo: {example_home_path}",
            ]
        )
    )
    (source / "metadata.json").write_text(f'{{"password": "{password_value}"}}\n')
    (source / "diff.patch").write_text(f"secret: {secret_value}\n")
    (source / "commands.log").write_text(f"cookie={cookie_value}\n")
    (source / "test-summary.md").write_text(f"{openai_like_value}\n")


def validate_cli_redact() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-redact-") as parent:
        parent_path = Path(parent)
        source = parent_path / "source"
        output = parent_path / "redacted"
        write_redaction_fixture(source)

        text_result = run_waybill(
            "redact",
            str(source),
            "--output",
            str(output),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"redact text command failed: {text_result.stderr.strip()}")
        if "Redacted bundle:" not in text_result.stdout:
            fail("redact text output must report the output bundle path")

        json_result = run_waybill(
            "redact",
            str(source),
            "--output",
            str(output),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"redact JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"redact JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("redact JSON output must set success true")
        if report.get("source") != str(source):
            fail("redact JSON output must include the source path")
        if report.get("output") != str(output):
            fail("redact JSON output must include the output path")
        if report.get("files_processed") != len(STANDARD_FILES):
            fail("redact JSON output must include the file count")
        if report.get("replacements") != 9:
            fail("redact JSON output must include the replacement count")

        files = report.get("files")
        if not isinstance(files, list) or len(files) != len(STANDARD_FILES):
            fail("redact JSON output must include per-file details")
        for file in files:
            if not isinstance(file, dict):
                fail("redact JSON file details must be objects")
            if not isinstance(file.get("path"), str):
                fail("redact JSON file details must include path")
            if not isinstance(file.get("replacements"), int):
                fail("redact JSON file details must include replacements")
            if not isinstance(file.get("copied_binary"), bool):
                fail("redact JSON file details must include copied_binary")

        source_text = "\n".join(path.read_text() for path in source.iterdir())
        output_text = "\n".join(path.read_text() for path in output.iterdir())
        for original in [
            "test" + "-api-key",
            "test" + "-token",
            "test" + "-bearer-token",
            "developer" + "@" + "example.test",
            "/home" + "/example/private-project",
            "test" + "-password",
            "test" + "-secret",
            "test" + "-cookie",
            "sk-" + "testsecretvalue12345",
        ]:
            if original not in source_text:
                fail("redact must not modify the source bundle")
            if original in output_text:
                fail("redact must remove fake secret values from output")
        if "[REDACTED]" not in output_text:
            fail("redact output must contain the redaction placeholder")

        error_result = run_waybill(
            "redact",
            str(source),
            "--output",
            str(output),
            "--json",
        )
        if error_result.returncode == 0:
            fail("redact JSON error command must fail when output exists without --force")
        try:
            error_report = json.loads(error_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"redact JSON error output is invalid: {exc}")
        if error_report.get("success") is not False:
            fail("redact JSON error output must set success false")
        if "already exists" not in str(error_report.get("error", "")):
            fail("redact JSON error output must include the failure reason")


def validate_cli_pack() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-pack-") as parent:
        parent_path = Path(parent)
        output = parent_path / "waybill-example.zip"

        text_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"pack text command failed: {text_result.stderr.strip()}")
        if "Packed bundle:" not in text_result.stdout:
            fail("pack text output must report the output archive path")

        json_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"pack JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"pack JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("pack JSON output must set success true")
        if report.get("source") != "examples/claude-to-codex":
            fail("pack JSON output must include the source bundle path")
        if report.get("output") != str(output):
            fail("pack JSON output must include the output archive path")
        if report.get("archive_root") != "claude-to-codex":
            fail("pack JSON output must include the archive root")
        if report.get("file_count") != len(STANDARD_FILES):
            fail("pack JSON output must include the file count")
        if not isinstance(report.get("byte_count"), int) or report["byte_count"] <= 0:
            fail("pack JSON output must include the byte count")
        validation = report.get("validation")
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            fail("pack JSON output must include passing validation details")

        files = report.get("files")
        if not isinstance(files, list) or len(files) != len(STANDARD_FILES):
            fail("pack JSON output must include packed file details")
        for file in files:
            if not isinstance(file, dict):
                fail("pack JSON file details must be objects")
            if not isinstance(file.get("path"), str):
                fail("pack JSON file details must include path")
            if not file["path"].startswith("claude-to-codex/"):
                fail("pack JSON file paths must include the archive root")
            if not isinstance(file.get("size"), int):
                fail("pack JSON file details must include size")
        if not output.is_file():
            fail("pack must create the output zip archive")

        exists_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--json",
        )
        if exists_result.returncode == 0:
            fail("pack JSON error command must fail when output exists without --force")
        try:
            exists_report = json.loads(exists_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"pack JSON existing-output error is invalid: {exc}")
        if exists_report.get("success") is not False:
            fail("pack JSON existing-output error must set success false")
        if "already exists" not in str(exists_report.get("error", "")):
            fail("pack JSON existing-output error must include the failure reason")

        invalid = parent_path / "invalid"
        invalid_output = parent_path / "invalid.zip"
        write_redaction_fixture(invalid)
        invalid_result = run_waybill(
            "pack",
            str(invalid),
            "--output",
            str(invalid_output),
            "--json",
        )
        if invalid_result.returncode == 0:
            fail("pack JSON invalid-bundle command must fail")
        try:
            invalid_report = json.loads(invalid_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"pack JSON invalid-bundle output is invalid: {exc}")
        if invalid_report.get("success") is not False:
            fail("pack JSON invalid-bundle output must set success false")
        invalid_validation = invalid_report.get("validation")
        if not isinstance(invalid_validation, dict):
            fail("pack JSON invalid-bundle output must include validation details")
        if invalid_validation.get("valid") is not False:
            fail("pack JSON invalid-bundle validation must be invalid")
        if invalid_output.exists():
            fail("pack must not write an archive for invalid bundles")


def validate_cli_share() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-share-") as parent:
        parent_path = Path(parent)
        output = parent_path / "waybill-share.zip"

        text_result = run_waybill(
            "share",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"share text command failed: {text_result.stderr.strip()}")
        if "Archive:" not in text_result.stdout:
            fail("share text output must report the archive path")

        json_result = run_waybill(
            "share",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"share JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"share JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("share JSON output must set success true")
        if report.get("source") != "examples/claude-to-codex":
            fail("share JSON output must include the source bundle path")
        if report.get("archive") != str(output):
            fail("share JSON output must include the archive path")
        for section in ["redaction", "validation", "pack"]:
            if not isinstance(report.get(section), dict):
                fail(f"share JSON output must include {section} details")
        if report["validation"].get("valid") is not True:
            fail("share JSON validation details must be valid")
        if report["pack"].get("file_count") != len(STANDARD_FILES):
            fail("share JSON pack details must include file count")
        if not output.is_file():
            fail("share must create the output zip archive")
        redacted = Path(str(report.get("redacted")))
        if not redacted.is_dir():
            fail("share must create a redacted review bundle")

        exists_result = run_waybill(
            "share",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--json",
        )
        if exists_result.returncode == 0:
            fail("share JSON error command must fail when output exists without --force")
        try:
            exists_report = json.loads(exists_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"share JSON existing-output error is invalid: {exc}")
        if exists_report.get("success") is not False:
            fail("share JSON existing-output error must set success false")
        if "already exists" not in str(exists_report.get("error", "")):
            fail("share JSON existing-output error must include the failure reason")

        binary_source = parent_path / "binary-source"
        shutil.copytree(ROOT / "examples/claude-to-codex", binary_source)
        binary_name = "attachment.bin"
        (binary_source / binary_name).write_bytes(
            b"\xff\xfeunscannable test payload\n"
        )
        binary_source_before = snapshot_tree(binary_source)

        local_redacted = parent_path / "local-binary-redacted"
        redact_result = run_waybill(
            "redact",
            str(binary_source),
            "--output",
            str(local_redacted),
            "--json",
        )
        if redact_result.returncode != 0:
            fail(
                "redact must preserve its local binary behavior: "
                f"{redact_result.stderr.strip()}"
            )
        redact_report = parse_cli_json(redact_result, "binary redact")
        redacted_files = redact_report.get("files")
        if not isinstance(redacted_files, list) or not any(
            isinstance(file, dict)
            and file.get("path") == binary_name
            and file.get("copied_binary") is True
            for file in redacted_files
        ):
            fail("redact must report locally copied unscannable files")

        binary_text_archive = parent_path / "binary-text.zip"
        binary_text_redacted = parent_path / "binary-text-redacted"
        binary_text = run_waybill(
            "share",
            str(binary_source),
            "--output",
            str(binary_text_archive),
            "--redacted-output",
            str(binary_text_redacted),
        )
        if binary_text.returncode == 0:
            fail("share text command must reject unscannable files")
        binary_text_error = binary_text.stderr.lower()
        if (
            binary_name not in binary_text_error
            or "unscannable" not in binary_text_error
        ):
            fail("share text failure must identify the unscannable file")
        if binary_text_archive.exists() or binary_text_redacted.exists():
            fail("share must not create outputs for unscannable files")

        binary_json_archive = parent_path / "binary-json.zip"
        archive_sentinel = b"existing archive\n"
        binary_json_archive.write_bytes(archive_sentinel)
        binary_json_redacted = parent_path / "binary-json-redacted"
        binary_json_redacted.mkdir()
        redacted_sentinel = binary_json_redacted / "keep.txt"
        redacted_sentinel.write_text("existing redacted output\n")

        binary_json = run_waybill(
            "share",
            str(binary_source),
            "--output",
            str(binary_json_archive),
            "--redacted-output",
            str(binary_json_redacted),
            "--force",
            "--json",
        )
        if binary_json.returncode == 0:
            fail("share JSON command must reject unscannable files")
        binary_report = parse_cli_json(binary_json, "binary share")
        if binary_report.get("success") is not False:
            fail("share JSON binary failure must set success false")
        binary_error = str(binary_report.get("error", "")).lower()
        if binary_name not in binary_error or "unscannable" not in binary_error:
            fail("share JSON binary failure must identify the unscannable file")
        if binary_json_archive.read_bytes() != archive_sentinel:
            fail("share --force must not overwrite an archive after a safety failure")
        if redacted_sentinel.read_text() != "existing redacted output\n":
            fail("share --force must not replace redacted output after a safety failure")
        require_tree_unchanged(
            binary_source,
            binary_source_before,
            "binary share checks",
        )


def validate_cli_share_check() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-share-check-") as temporary:
        root = Path(temporary)
        bundle = root / "bundle"
        shutil.copytree(ROOT / "examples/claude-to-codex", bundle)
        secret = "validator-share-check-secret-12345"
        (bundle / "synthetic-secret.txt").write_text(f"api_key={secret}\n")
        before = snapshot_tree(root)

        result = run_waybill("share", str(bundle), "--check", "--json")
        report = parse_cli_json(result, "share --check")
        if report.get("shareable") is not True:
            fail("share --check must allow bundles that can be safely redacted")
        findings = report.get("findings")
        if not isinstance(findings, list) or not findings:
            fail("share --check must report planned redactions")
        for finding in findings:
            if not isinstance(finding, dict) or set(finding) != {
                "kind",
                "path",
                "count",
                "blocking",
            }:
                fail("share --check findings must use the value-free field set")
        if secret in result.stdout:
            fail("share --check JSON must not reveal matched secret content")
        require_tree_unchanged(root, before, "share --check")

        text_result = run_waybill("share", str(bundle), "--check")
        if text_result.returncode != 0 or "PASS bundle is shareable" not in text_result.stdout:
            fail("share --check text mode must report a shareable bundle")
        require_tree_unchanged(root, before, "share --check text")

        (bundle / "raw.bin").write_bytes(b"\xff\xfe")
        blocked_before = snapshot_tree(root)
        blocked_result = run_waybill("share", str(bundle), "--check", "--json")
        blocked_report = parse_cli_json(blocked_result, "blocked share --check")
        if blocked_report.get("shareable") is not False:
            fail("share --check must block unscannable bundle content")
        blocked_findings = blocked_report.get("findings")
        if not isinstance(blocked_findings, list) or not any(
            isinstance(finding, dict)
            and finding.get("kind") == "unscannable-file"
            and finding.get("blocking") is True
            for finding in blocked_findings
        ):
            fail("share --check must report an unscannable blocking finding")
        require_tree_unchanged(root, blocked_before, "blocked share --check")

        missing_output = run_waybill("share", str(bundle), "--json")
        missing_report = parse_cli_json(missing_output, "share missing output")
        if "--output" not in str(missing_report.get("error", "")):
            fail("ordinary share must still require --output")


def validate_cli_unpack() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-unpack-") as parent:
        parent_path = Path(parent)
        archive = parent_path / "waybill-example.zip"
        output = parent_path / "unpacked"

        pack_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(archive),
            "--force",
        )
        if pack_result.returncode != 0:
            fail(f"unpack setup pack command failed: {pack_result.stderr.strip()}")

        text_result = run_waybill(
            "unpack",
            str(archive),
            "--output",
            str(output),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"unpack text command failed: {text_result.stderr.strip()}")
        if "PASS valid Waybill Bundle:" not in text_result.stdout:
            fail("unpack text output must report valid bundle status")

        json_result = run_waybill(
            "unpack",
            str(archive),
            "--output",
            str(output),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"unpack JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"unpack JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("unpack JSON output must set success true")
        if report.get("source") != str(archive):
            fail("unpack JSON output must include the archive path")
        if report.get("output") != str(output):
            fail("unpack JSON output must include the output path")
        if report.get("archive_root") != "claude-to-codex":
            fail("unpack JSON output must include the archive root")
        if report.get("file_count") != len(STANDARD_FILES):
            fail("unpack JSON output must include file count")
        validation = report.get("validation")
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            fail("unpack JSON output must include passing validation details")
        files = report.get("files")
        if not isinstance(files, list) or len(files) != len(STANDARD_FILES):
            fail("unpack JSON output must include unpacked file details")
        if not (output / "claude-to-codex" / "WAYBILL.md").is_file():
            fail("unpack must extract the bundle files")

        exists_result = run_waybill(
            "unpack",
            str(archive),
            "--output",
            str(output),
            "--json",
        )
        if exists_result.returncode == 0:
            fail("unpack JSON error command must fail when output exists without --force")
        try:
            exists_report = json.loads(exists_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"unpack JSON existing-output error is invalid: {exc}")
        if exists_report.get("success") is not False:
            fail("unpack JSON existing-output error must set success false")


def validate_cli_render() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-render-") as parent:
        parent_path = Path(parent)
        output = parent_path / "waybill-report.md"

        text_result = run_waybill(
            "render",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
        )
        if text_result.returncode != 0:
            fail(f"render text command failed: {text_result.stderr.strip()}")
        if "Rendered bundle report:" not in text_result.stdout:
            fail("render text output must report the output report path")
        if "# Waybill Bundle Report" not in output.read_text():
            fail("render must write a Markdown report")

        json_result = run_waybill(
            "render",
            "examples/claude-to-codex",
            "--output",
            str(output),
            "--force",
            "--json",
        )
        if json_result.returncode != 0:
            fail(f"render JSON command failed: {json_result.stderr.strip()}")
        try:
            report = json.loads(json_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"render JSON output is invalid: {exc}")

        if report.get("success") is not True:
            fail("render JSON output must set success true")
        if report.get("bundle") != "examples/claude-to-codex":
            fail("render JSON output must include the bundle path")
        if report.get("output") != str(output):
            fail("render JSON output must include the output path")
        if not isinstance(report.get("bytes"), int) or report["bytes"] <= 0:
            fail("render JSON output must include byte count")
        validation = report.get("validation")
        if not isinstance(validation, dict) or validation.get("valid") is not True:
            fail("render JSON output must include passing validation details")

        stdout_result = run_waybill("render", "examples/claude-to-codex")
        if stdout_result.returncode != 0:
            fail(f"render stdout command failed: {stdout_result.stderr.strip()}")
        if "# Waybill Bundle Report" not in stdout_result.stdout:
            fail("render stdout output must include the report")

        json_stdout_result = run_waybill(
            "render",
            "examples/claude-to-codex",
            "--json",
        )
        if json_stdout_result.returncode == 0:
            fail("render JSON without --output must fail")
        json_stdout_report = parse_cli_json(
            json_stdout_result,
            "render JSON without output",
        )
        if json_stdout_report.get("success") is not False:
            fail("render JSON without output error must set success false")


def validate_cli_json_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            "tests.integration.test_cli_json_contract",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"CLI JSON contract tests failed: {detail}")


def validate_cli_end_to_end() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-e2e-") as parent:
        parent_path = Path(parent)
        draft = parent_path / "draft"
        redacted = parent_path / "redacted"
        archive = parent_path / "handoff.zip"
        unpacked = parent_path / "unpacked"
        report = parent_path / "report.md"

        new_result = run_waybill(
            "new",
            "--output",
            str(draft),
            "--repo",
            str(ROOT),
            "--force",
            "--json",
        )
        if new_result.returncode != 0:
            fail(f"end-to-end new command failed: {new_result.stderr.strip()}")

        redact_result = run_waybill(
            "redact",
            str(draft),
            "--output",
            str(redacted),
            "--force",
            "--json",
        )
        if redact_result.returncode != 0:
            fail(f"end-to-end redact command failed: {redact_result.stderr.strip()}")

        pack_result = run_waybill(
            "pack",
            str(redacted),
            "--output",
            str(archive),
            "--force",
            "--json",
        )
        if pack_result.returncode != 0:
            fail(f"end-to-end pack command failed: {pack_result.stderr.strip()}")

        unpack_result = run_waybill(
            "unpack",
            str(archive),
            "--output",
            str(unpacked),
            "--force",
            "--json",
        )
        if unpack_result.returncode != 0:
            fail(f"end-to-end unpack command failed: {unpack_result.stderr.strip()}")
        try:
            unpack_report = json.loads(unpack_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"end-to-end unpack JSON is invalid: {exc}")

        bundle = unpack_report.get("bundle")
        if not isinstance(bundle, str):
            fail("end-to-end unpack JSON must include bundle path")

        validate_result = run_waybill("validate", bundle, "--json")
        if validate_result.returncode != 0:
            fail(f"end-to-end validate command failed: {validate_result.stderr.strip()}")
        try:
            validate_report = json.loads(validate_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"end-to-end validate JSON is invalid: {exc}")
        if validate_report.get("valid") is not True:
            fail("end-to-end unpacked bundle must validate")

        render_result = run_waybill(
            "render",
            bundle,
            "--output",
            str(report),
            "--force",
            "--json",
        )
        if render_result.returncode != 0:
            fail(f"end-to-end render command failed: {render_result.stderr.strip()}")
        if not report.is_file():
            fail("end-to-end render must write a report")


def validate_resource_limits() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-limits-") as parent:
        parent_path = Path(parent)

        limited_bundle = parent_path / "limited"
        limited_bundle.mkdir()
        (limited_bundle / "large.txt").write_text("too large")
        try:
            list_bundle_files(limited_bundle, max_file_bytes=4)
        except BundleLimitError:
            pass
        else:
            fail("bundle file listing must enforce per-file limits")

        repo = parent_path / "repo"
        repo.mkdir()
        init_result = run_git(repo, "init")
        if init_result.returncode != 0:
            fail(f"resource limit git init failed: {init_result.stderr.strip()}")
        tracked = repo / "tracked.txt"
        tracked.write_text("base\n")
        add_result = run_git(repo, "add", "tracked.txt")
        if add_result.returncode != 0:
            fail(f"resource limit git add failed: {add_result.stderr.strip()}")
        commit_result = run_git(
            repo,
            "-c",
            "user.name=Waybill",
            "-c",
            "user.email=" + "waybill" + "@" + "example.invalid",
            "commit",
            "-m",
            "init",
        )
        if commit_result.returncode != 0:
            fail(f"resource limit git commit failed: {commit_result.stderr.strip()}")

        tracked.write_text("x" * 4096)
        draft = parent_path / "draft"
        new_result = run_waybill(
            "new",
            "--output",
            str(draft),
            "--repo",
            str(repo),
            "--force",
            "--max-diff-bytes",
            "128",
            "--json",
        )
        if new_result.returncode != 0:
            fail(f"resource limit new command failed: {new_result.stderr.strip()}")
        if "Diff omitted" not in (draft / "diff.patch").read_text():
            fail("new must omit diffs that exceed --max-diff-bytes")

        archive = parent_path / "large.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(
                "bundle/large.txt",
                "x" * (MAX_BUNDLE_FILE_BYTES + 1),
            )

        unpack_result = run_waybill(
            "unpack",
            str(archive),
            "--output",
            str(parent_path / "unpacked"),
            "--json",
        )
        if unpack_result.returncode == 0:
            fail("unpack must reject archives with oversized files")
        try:
            unpack_report = json.loads(unpack_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"oversized unpack JSON error is invalid: {exc}")
        if unpack_report.get("success") is not False:
            fail("oversized unpack JSON error must set success false")
        if "too large" not in str(unpack_report.get("error", "")):
            fail("oversized unpack JSON error must explain the size limit")


def validate_unsafe_bundle_paths() -> None:
    with tempfile.TemporaryDirectory(prefix="waybill-unsafe-paths-") as parent:
        parent_path = Path(parent)
        outside = parent_path / "outside.txt"
        outside.write_text("outside bundle data\n")

        symlink_bundle = parent_path / "symlink-bundle"
        shutil.copytree(ROOT / "examples/claude-to-codex", symlink_bundle)
        (symlink_bundle / "outside-link.txt").symlink_to(outside)

        commands = [
            ("validate", str(symlink_bundle), "--json"),
            (
                "redact",
                str(symlink_bundle),
                "--output",
                str(parent_path / "symlink-redacted"),
                "--json",
            ),
            (
                "pack",
                str(symlink_bundle),
                "--output",
                str(parent_path / "symlink.zip"),
                "--json",
            ),
            (
                "share",
                str(symlink_bundle),
                "--output",
                str(parent_path / "symlink-share.zip"),
                "--json",
            ),
        ]
        for command in commands:
            result = run_waybill(*command)
            if result.returncode == 0:
                fail(f"{command[0]} must reject bundle file symbolic links")
            combined = f"{result.stdout}\n{result.stderr}".lower()
            if "symbolic link" not in combined:
                fail(f"{command[0]} must explain bundle symbolic link rejection")

        internal_symlink_bundle = parent_path / "internal-symlink-bundle"
        shutil.copytree(
            ROOT / "examples/claude-to-codex",
            internal_symlink_bundle,
        )
        (internal_symlink_bundle / "waybill-link.md").symlink_to("WAYBILL.md")
        internal_result = run_waybill(
            "validate",
            str(internal_symlink_bundle),
            "--json",
        )
        if internal_result.returncode == 0:
            fail("validate must reject bundle-internal symbolic links")

        root_symlink = parent_path / "bundle-root-link"
        root_symlink.symlink_to(
            ROOT / "examples/claude-to-codex",
            target_is_directory=True,
        )
        root_result = run_waybill("validate", str(root_symlink), "--json")
        if root_result.returncode == 0:
            fail("validate must reject a symbolic link bundle root")

        if hasattr(os, "mkfifo"):
            special_bundle = parent_path / "special-bundle"
            shutil.copytree(ROOT / "examples/claude-to-codex", special_bundle)
            os.mkfifo(special_bundle / "command-pipe")
            special_result = run_waybill("validate", str(special_bundle), "--json")
            if special_result.returncode == 0:
                fail("validate must reject non-regular bundle files")
            if "unsupported file type" not in special_result.stdout.lower():
                fail("validate must explain non-regular bundle file rejection")

        redact_container = parent_path / "redact-container"
        redact_source = redact_container / "bundle"
        shutil.copytree(ROOT / "examples/claude-to-codex", redact_source)
        redact_result = run_waybill(
            "redact",
            str(redact_source),
            "--output",
            str(redact_container),
            "--force",
            "--json",
        )
        if redact_result.returncode == 0:
            fail("redact must reject an output path containing the source bundle")
        if not redact_source.is_dir():
            fail("redact must not delete the source bundle through an ancestor output")

        pack_container = parent_path / "pack-container.zip"
        pack_source = pack_container / "bundle"
        shutil.copytree(ROOT / "examples/claude-to-codex", pack_source)
        pack_result = run_waybill(
            "pack",
            str(pack_source),
            "--output",
            str(pack_container),
            "--force",
            "--json",
        )
        if pack_result.returncode == 0:
            fail("pack must reject an output path containing the source bundle")
        if not pack_source.is_dir():
            fail("pack must not delete the source bundle through an ancestor output")

        unpack_container = parent_path / "unpack-container"
        unpack_container.mkdir()
        unpack_archive = unpack_container / "source.zip"
        pack_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(unpack_archive),
            "--json",
        )
        if pack_result.returncode != 0:
            fail(f"unsafe unpack setup failed: {pack_result.stderr.strip()}")
        unpack_result = run_waybill(
            "unpack",
            str(unpack_archive),
            "--output",
            str(unpack_container),
            "--force",
            "--json",
        )
        if unpack_result.returncode == 0:
            fail("unpack must reject an output path containing the source archive")
        if not unpack_archive.is_file():
            fail("unpack must not delete the source archive through an ancestor output")

        output_target = parent_path / "existing-output.zip"
        output_target.write_text("keep this file\n")
        output_symlink = parent_path / "output-link.zip"
        output_symlink.symlink_to(output_target)
        output_symlink_result = run_waybill(
            "pack",
            "examples/claude-to-codex",
            "--output",
            str(output_symlink),
            "--force",
            "--json",
        )
        if output_symlink_result.returncode == 0:
            fail("pack must reject a symbolic link output path")
        if output_target.read_text() != "keep this file\n":
            fail("pack must not modify a symbolic link output target")

        share_source = parent_path / "share-source"
        share_redacted = parent_path / "share-redacted"
        shutil.copytree(ROOT / "examples/claude-to-codex", share_source)
        share_archive = share_source / "share.zip"
        share_result = run_waybill(
            "share",
            str(share_source),
            "--output",
            str(share_archive),
            "--redacted-output",
            str(share_redacted),
            "--json",
        )
        if share_result.returncode == 0:
            fail("share must reject an archive path inside the source bundle")
        if share_archive.exists():
            fail("share must not write an archive inside the source bundle")


def run_checks(checks: Sequence[tuple[str, Callable[[], None]]]) -> int:
    failures = 0
    for name, check in checks:
        try:
            check()
        except ValidationError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}", file=sys.stderr)
        except Exception as exc:
            failures += 1
            print(
                f"FAIL {name}: unexpected {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
        else:
            print(f"PASS {name}")

    if failures:
        print(
            f"FAIL Waybill repository validation: {failures} check(s) failed",
            file=sys.stderr,
        )
        return 1

    print("PASS Waybill repository validation")
    return 0


CHECKS: tuple[tuple[str, Callable[[], None]], ...] = (
    ("structure", validate_structure),
    ("metadata schema", validate_metadata_schema),
    ("schema version compatibility", validate_schema_version_compatibility),
    ("canonical handoff skill", validate_canonical_handoff_skill),
    ("Codex plugin", validate_codex_plugin),
    ("Codex marketplace", validate_codex_marketplace),
    ("Claude skills", validate_claude_skills),
    ("OpenCode adapter", validate_opencode_adapter),
    ("Cursor adapter", validate_cursor_adapter),
    ("Gemini CLI adapter", validate_gemini_cli_adapter),
    ("adapter synchronization", validate_adapter_synchronization),
    ("Python package", validate_python_package),
    ("packaging declarations", validate_packaging_declarations),
    ("wheel installation", validate_wheel_installation),
    ("CI workflow", validate_ci_workflow),
    ("PyPI publish workflow", validate_pypi_publish_workflow),
    ("examples", validate_examples),
    ("conformance scenarios", validate_conformance_scenarios),
    ("conformance runner dry-run", validate_conformance_runner_dry_run),
    ("export conformance scenarios", validate_export_conformance_scenarios),
    (
        "export conformance runner dry-run",
        validate_export_conformance_runner_dry_run,
    ),
    ("CLI validate", validate_cli_validate),
    ("CLI init", validate_cli_init),
    ("adapter installation lifecycle", validate_adapter_installation_lifecycle),
    ("CLI doctor", validate_cli_doctor),
    ("CLI new", validate_cli_new),
    ("CLI verify-repo", validate_cli_verify_repo),
    ("CLI verify-pair", validate_cli_verify_pair),
    ("CLI preflight", validate_cli_preflight),
    ("CLI ready", validate_cli_ready),
    ("CLI inspect", validate_cli_inspect),
    ("CLI redact", validate_cli_redact),
    ("CLI pack", validate_cli_pack),
    ("CLI share", validate_cli_share),
    ("CLI share --check", validate_cli_share_check),
    ("CLI unpack", validate_cli_unpack),
    ("CLI render", validate_cli_render),
    ("CLI JSON contract", validate_cli_json_contract),
    ("CLI end-to-end", validate_cli_end_to_end),
    ("resource limits", validate_resource_limits),
    ("unsafe bundle paths", validate_unsafe_bundle_paths),
)


def main() -> int:
    return run_checks(CHECKS)


if __name__ == "__main__":
    raise SystemExit(main())
