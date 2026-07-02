#!/usr/bin/env python3
"""Validate the Waybill repository shape without third-party packages."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from waybill_core.scaffold import STANDARD_FILES  # noqa: E402
from waybill_core.validation import validate_bundle  # noqa: E402

REQUIRED_FILES = [
    "README.md",
    ".gitignore",
    "INSTALL.md",
    "TESTING.md",
    "spec/waybill-bundle.md",
    "spec/waybill-template.md",
    "spec/metadata.schema.json",
    "cli/waybill",
    "waybill_core/__init__.py",
    "waybill_core/doctor.py",
    "waybill_core/install.py",
    "waybill_core/packing.py",
    "waybill_core/preflight.py",
    "waybill_core/readiness.py",
    "waybill_core/redaction.py",
    "waybill_core/repo.py",
    "waybill_core/rendering.py",
    "waybill_core/scaffold.py",
    "waybill_core/sharing.py",
    "waybill_core/validation.py",
    ".agents/plugins/marketplace.json",
    ".claude/skills/handoff/SKILL.md",
    ".claude/skills/waybill/SKILL.md",
    ".opencode/commands/handoff.md",
    ".opencode/commands/waybill.md",
    ".opencode/skills/handoff/SKILL.md",
    ".opencode/skills/waybill/SKILL.md",
    "adapters/claude-code/README.md",
    "adapters/claude-code/commands/handoff-export.md",
    "adapters/claude-code/commands/handoff-import.md",
    "adapters/codex/README.md",
    "adapters/codex/.codex-plugin/plugin.json",
    "adapters/codex/skills/handoff/SKILL.md",
    "adapters/opencode/README.md",
    "adapters/opencode/commands/handoff.md",
    "adapters/opencode/commands/waybill.md",
    "adapters/opencode/skills/handoff/SKILL.md",
    "adapters/opencode/skills/waybill/SKILL.md",
]

EXAMPLES = [
    "examples/claude-to-codex",
    "examples/codex-to-claude",
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


def run_waybill(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "cli/waybill"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


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


def validate_opencode_adapter() -> None:
    command_paths = {
        "handoff": ROOT / ".opencode/commands/handoff.md",
        "waybill": ROOT / ".opencode/commands/waybill.md",
        "adapter handoff": ROOT / "adapters/opencode/commands/handoff.md",
        "adapter waybill": ROOT / "adapters/opencode/commands/waybill.md",
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
        "handoff": ROOT / ".opencode/skills/handoff/SKILL.md",
        "waybill": ROOT / ".opencode/skills/waybill/SKILL.md",
        "adapter handoff": ROOT / "adapters/opencode/skills/handoff/SKILL.md",
        "adapter waybill": ROOT / "adapters/opencode/skills/waybill/SKILL.md",
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
        if "export" not in text or "import" not in text:
            fail(f"OpenCode skill {name} must cover export and import")
        if "Do not automatically apply `diff.patch`" not in text:
            fail(f"OpenCode skill {name} must forbid automatic patch application")
        if ".waybill/" not in text:
            fail(f"OpenCode skill {name} must mention .waybill/")
        if name.endswith("handoff") and not has_command_classification_rule(text):
            fail("OpenCode handoff skill must require command log action classification")
        if "source_agent" in text and "opencode" not in text:
            fail(f"OpenCode skill {name} must use source_agent opencode")


def validate_example(example_dir: Path) -> None:
    issues = validate_bundle(example_dir)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        formatted = "; ".join(issue.format() for issue in errors)
        fail(f"{example_dir.relative_to(ROOT)} invalid bundle: {formatted}")


def validate_examples() -> None:
    for example in EXAMPLES:
        validate_example(ROOT / example)


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
        if report.get("adapters") != ["claude-code", "opencode"]:
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


def write_redaction_fixture(source: Path) -> None:
    source.mkdir()
    (source / "WAYBILL.md").write_text(
        "\n".join(
            [
                "# Fixture",
                "api_key: fixture-value",
                "token=fixture-value",
                "Bearer fixture-value",
            ]
        )
    )
    (source / "metadata.json").write_text('{"password": "fixture-value"}\n')
    (source / "diff.patch").write_text("secret: fixture-value\n")
    (source / "commands.log").write_text("cookie=fixture-value\n")
    (source / "test-summary.md").write_text("fixture-value\n")


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
        if report.get("replacements") != 7:
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
            "fixture-value",
            "fixture-value",
            "fixture-value",
            "fixture-value",
            "fixture-value",
            "fixture-value",
            "fixture-value",
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
        try:
            json_stdout_report = json.loads(json_stdout_result.stdout)
        except json.JSONDecodeError as exc:
            fail(f"render JSON without output error is invalid: {exc}")
        if json_stdout_report.get("success") is not False:
            fail("render JSON without output error must set success false")


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


def main() -> int:
    checks = [
        ("structure", validate_structure),
        ("metadata schema", validate_metadata_schema),
        ("Codex plugin", validate_codex_plugin),
        ("Codex marketplace", validate_codex_marketplace),
        ("Claude skills", validate_claude_skills),
        ("OpenCode adapter", validate_opencode_adapter),
        ("examples", validate_examples),
        ("CLI init", validate_cli_init),
        ("CLI new", validate_cli_new),
        ("CLI redact", validate_cli_redact),
        ("CLI pack", validate_cli_pack),
        ("CLI share", validate_cli_share),
        ("CLI unpack", validate_cli_unpack),
        ("CLI render", validate_cli_render),
        ("CLI end-to-end", validate_cli_end_to_end),
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
