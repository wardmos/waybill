"""Tests for the canonical Skill and agent-specific adapter layout."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills/handoff"
REFERENCE_NAMES = ("bundle-format.md", "export.md", "import.md")


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
            "waybill ready",
            (references / "export.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "read-only",
            (references / "import.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
