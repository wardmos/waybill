"""Tests for the canonical Skill and agent-specific adapter layout."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills/handoff"
REFERENCE_NAMES = ("bundle-format.md", "export.md", "import.md")
BUNDLE_ASSET_NAMES = (
    "WAYBILL.md",
    "metadata.json",
    "diff.patch",
    "commands.log",
    "test-summary.md",
)


class CanonicalSkillLayoutTests(unittest.TestCase):
    def test_handoff_skill_has_one_canonical_entrypoint(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        self.assertIn("name: handoff", skill)
        self.assertIn("description:", skill)
        for reference in REFERENCE_NAMES:
            self.assertIn(f"references/{reference}", skill)

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
        delegation_spec = " ".join(
            (ROOT / "spec/delegation.md").read_text(encoding="utf-8").split()
        ).lower()

        self.assertIn("result_status is a claim, not proof", import_workflow)
        self.assertIn("conditionally reviewable", import_workflow)
        self.assertIn("do not say a result is safe to accept", import_workflow)
        self.assertIn("does not establish semantic correctness or test truth", delegation_spec)

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

    def test_user_docs_make_the_waybill_cli_an_optional_enhancement(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        quickstart = (ROOT / "QUICKSTART.md").read_text(encoding="utf-8")
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        claude = (ROOT / "adapters/claude-code/README.md").read_text(
            encoding="utf-8"
        )
        codex = (ROOT / "adapters/codex/README.md").read_text(encoding="utf-8")

        self.assertIn("## Optional Support CLI", readme)
        self.assertIn(
            "does not require the Waybill CLI",
            " ".join(quickstart.split()),
        )
        self.assertIn("## Optional Managed Adapter Lifecycle", install)
        self.assertIn("without the Waybill CLI", claude)
        self.assertIn("without the Waybill CLI", codex)


if __name__ == "__main__":
    unittest.main()
