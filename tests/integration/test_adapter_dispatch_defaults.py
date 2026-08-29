"""Contract tests for optional handoff directions and export-by-default dispatch."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_EXPORT_RULE = (
    "When neither `export` nor `import` is supplied, default to `export`."
)

HANDOFF_ENTRYPOINTS = (
    "skills/handoff/SKILL.md",
    "adapters/claude-code/skills/handoff/SKILL.md",
    "adapters/codex/skills/handoff/SKILL.md",
    "adapters/cursor/rules/handoff.mdc",
    "adapters/gemini-cli/skills/handoff/SKILL.md",
    "adapters/opencode/skills/handoff/SKILL.md",
)

CLAUDE_SKILLS = (
    "adapters/claude-code/skills/handoff/SKILL.md",
    "adapters/claude-code/skills/waybill/SKILL.md",
)


class AdapterDispatchDefaultTests(unittest.TestCase):
    def test_every_handoff_entrypoint_defaults_an_omitted_direction_to_export(
        self,
    ) -> None:
        for relative_path in HANDOFF_ENTRYPOINTS:
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn(DEFAULT_EXPORT_RULE, text)
                self.assertIsNone(
                    re.search(
                        r"ask whether (?:the user wants to )?export or import",
                        " ".join(text.lower().split()),
                    )
                )

    def test_claude_argument_hints_mark_the_direction_as_optional(self) -> None:
        for relative_path in CLAUDE_SKILLS:
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn(
                    'argument-hint: "[export | import] [bundle-path]"',
                    text,
                )

    def test_primary_guides_show_the_short_default_export_form(self) -> None:
        for relative_path in ("README.md", "QUICKSTART.md"):
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn("```text\n/handoff\n```", text)
                self.assertIn("defaults to `export`", text)


if __name__ == "__main__":
    unittest.main()
