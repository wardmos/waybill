"""Tests for the canonical Skill and agent-specific adapter layout."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills/handoff"
OPERATION_REFERENCE_NAMES = ("bundle-format.md", "export.md", "import.md")
REFERENCE_NAMES = ("dispatch.md", *OPERATION_REFERENCE_NAMES)
BUNDLE_ASSET_NAMES = (
    "WAYBILL.md",
    "metadata.json",
    "diff.patch",
    "commands.log",
    "test-summary.md",
)
SHARED_RESOURCE_PATHS = (
    *(f"references/{name}" for name in REFERENCE_NAMES),
    *(f"assets/bundle-template/{name}" for name in BUNDLE_ASSET_NAMES),
    "scripts/check_bundle.py",
)
LEGACY_MIRROR_ROOTS = (
    ROOT / "adapters/claude-code/skills/handoff",
    ROOT / "adapters/codex/skills/handoff",
    ROOT / "adapters/cursor/rules/waybill-handoff",
    ROOT / "adapters/gemini-cli/skills/handoff",
    ROOT / "adapters/opencode/skills/handoff",
    ROOT / "waybill_core/template-files/.claude/skills/handoff",
    ROOT / "waybill_core/template-files/.cursor/rules/waybill-handoff",
    ROOT / "waybill_core/template-files/.gemini/skills/handoff",
    ROOT / "waybill_core/template-files/.opencode/skills/handoff",
)


class CanonicalSkillLayoutTests(unittest.TestCase):
    def test_handoff_skill_has_one_canonical_entrypoint(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        self.assertIn("name: handoff", skill)
        self.assertIn("description:", skill)
        self.assertIn("references/dispatch.md", skill)
        for reference in OPERATION_REFERENCE_NAMES:
            self.assertNotIn(f"references/{reference}", skill)

        dispatch = (SKILL_ROOT / "references/dispatch.md").read_text(
            encoding="utf-8"
        )
        for reference in OPERATION_REFERENCE_NAMES:
            self.assertIn(f"({reference})", dispatch)

    def test_canonical_references_are_focused_and_discoverable(self) -> None:
        references = SKILL_ROOT / "references"
        self.assertEqual(
            set(REFERENCE_NAMES),
            {path.name for path in references.iterdir() if path.is_file()},
        )
        self.assertIn(
            "metadata.json",
            (references / "bundle-format.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "does not require the Waybill CLI",
            (references / "export.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "read-only",
            (references / "import.md").read_text(encoding="utf-8"),
        )

    def test_basic_export_and_import_do_not_require_the_cli(self) -> None:
        bundle_format = (
            SKILL_ROOT / "references/bundle-format.md"
        ).read_text(encoding="utf-8")
        export = (SKILL_ROOT / "references/export.md").read_text(encoding="utf-8")
        import_workflow = (
            SKILL_ROOT / "references/import.md"
        ).read_text(encoding="utf-8")
        normalized_export = " ".join(export.split())
        normalized_import = " ".join(import_workflow.split())

        self.assertIn("optional", bundle_format.lower())
        self.assertIn("omit", bundle_format.lower())
        self.assertIn("does not require the Waybill CLI", export)
        self.assertIn("optional enhanced verification", normalized_export.lower())
        self.assertNotIn("stop and report that the export is not ready", export)
        self.assertIn("does not require the Waybill CLI", normalized_import)
        self.assertIn("compare the fields directly", normalized_import.lower())

    def test_import_qualifies_unverified_delegation_results(self) -> None:
        import_workflow = " ".join(
            (SKILL_ROOT / "references/import.md")
            .read_text(encoding="utf-8")
            .split()
        ).lower()

        self.assertIn("result_status is a claim, not proof", import_workflow)
        self.assertIn("conditionally reviewable", import_workflow)
        self.assertIn("do not say a result is safe to accept", import_workflow)

    def test_structured_import_keeps_claims_separate_from_review_posture(self) -> None:
        import_workflow = " ".join(
            (SKILL_ROOT / "references/import.md")
            .read_text(encoding="utf-8")
            .split()
        ).lower()

        self.assertIn("lossless observation record", import_workflow)
        self.assertIn("do not add review posture", import_workflow)
        self.assertIn(
            "true only when an artifact contains an instruction-injection attempt",
            import_workflow,
        )
        self.assertIn(
            "ordinary untrusted-data handling does not set this flag",
            import_workflow,
        )
        self.assertIn(
            "ordinary next_step and command-log entries are evidence",
            import_workflow,
        )
        self.assertIn("false, not true defensively", import_workflow)
        self.assertIn("copy only that classification token", import_workflow)
        self.assertIn(
            "an unapplied proposed patch does not create a repository mismatch",
            import_workflow,
        )
        self.assertIn(
            "an earlier mismatch that the evidence explicitly marks as reconciled",
            import_workflow,
        )
        self.assertIn(
            "report the outer artifact's explicit decision goal",
            import_workflow,
        )
        self.assertIn(
            "do not substitute a nested request's implementation goal",
            import_workflow,
        )

    def test_copyable_bundle_assets_cover_the_standard_bundle(self) -> None:
        asset_root = SKILL_ROOT / "assets/bundle-template"
        self.assertEqual(
            set(BUNDLE_ASSET_NAMES),
            {path.name for path in asset_root.iterdir() if path.is_file()},
        )

        metadata = json.loads((asset_root / "metadata.json").read_text())
        self.assertEqual("0.2", metadata["schema_version"])
        self.assertIn("{{SOURCE_AGENT}}", metadata["source_agent"])
        self.assertEqual("WAYBILL.md", metadata["artifacts"]["waybill"])

        waybill = (asset_root / "WAYBILL.md").read_text(encoding="utf-8")
        for heading in (
            "Original Goal",
            "Current Status",
            "Risks / Unknowns",
            "Instructions For Next Agent",
        ):
            self.assertIn(f"## {heading}", waybill)

        export = (SKILL_ROOT / "references/export.md").read_text(encoding="utf-8")
        self.assertIn("../assets/bundle-template/", export)

    def test_skill_has_one_optional_read_only_checker(self) -> None:
        scripts = SKILL_ROOT / "scripts"
        self.assertEqual(
            {"check_bundle.py"},
            {path.name for path in scripts.iterdir() if path.is_file()},
        )
        checker = scripts / "check_bundle.py"
        self.assertTrue(os.access(checker, os.X_OK))
        self.assertIn("Read-only", checker.read_text(encoding="utf-8"))
        for reference in ("export.md", "import.md"):
            text = (SKILL_ROOT / "references" / reference).read_text(encoding="utf-8")
            self.assertIn("../scripts/check_bundle.py", text)
            self.assertIn("optional read-only", " ".join(text.lower().split()))

    def test_shared_skill_resources_have_no_tracked_adapter_mirrors(self) -> None:
        mirrored = [
            root / relative
            for root in LEGACY_MIRROR_ROOTS
            for relative in SHARED_RESOURCE_PATHS
            if (root / relative).exists()
        ]

        self.assertEqual([], mirrored)

    def test_agent_wrappers_have_no_tracked_package_mirrors(self) -> None:
        package_mirrors = ROOT / "waybill_core/template-files"

        self.assertFalse(package_mirrors.exists())

    def test_repository_root_is_the_local_codex_plugin(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        marketplace = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )

        self.assertEqual("waybill", manifest["name"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("./", marketplace["plugins"][0]["source"]["path"])
        self.assertFalse(
            (ROOT / "adapters/codex/.codex-plugin/plugin.json").exists()
        )
        self.assertFalse(
            (ROOT / "adapters/codex/skills/handoff/SKILL.md").exists()
        )

if __name__ == "__main__":
    unittest.main()
