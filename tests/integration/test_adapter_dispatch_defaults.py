"""Contract tests for optional handoff directions and export-by-default dispatch."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from waybill_core.adapter_bundles import bundle_sources_for_adapter
from waybill_core.adapter_sources import AGENT_ADAPTER_ENTRYPOINTS


ROOT = Path(__file__).resolve().parents[2]
DISPATCH = ROOT / "skills/handoff/references/dispatch.md"

DEFAULT_EXPORT_RULE = (
    "When neither `export` nor `import` is supplied, default to `export`."
)

HANDOFF_ENTRYPOINTS = {
    "skills/handoff/SKILL.md": "references/dispatch.md",
    "adapters/claude-code/skills/handoff/SKILL.md": "references/dispatch.md",
    "adapters/cursor/rules/handoff.mdc": (
        "waybill-handoff/references/dispatch.md"
    ),
    "adapters/gemini-cli/skills/handoff/SKILL.md": "references/dispatch.md",
    "adapters/opencode/skills/handoff/SKILL.md": "references/dispatch.md",
}

CLAUDE_SKILLS = (
    "adapters/claude-code/skills/handoff/SKILL.md",
    "adapters/claude-code/skills/waybill/SKILL.md",
)


class AdapterDispatchDefaultTests(unittest.TestCase):
    def test_shared_dispatch_owns_direction_and_path_selection(self) -> None:
        text = DISPATCH.read_text(encoding="utf-8")

        self.assertIn(DEFAULT_EXPORT_RULE, text)
        self.assertIn("bundle-format.md", text)
        self.assertIn("export.md", text)
        self.assertIn("import.md", text)
        self.assertIn("path without a direction", text)
        self.assertNotIn("source_agent", text)
        self.assertIsNone(
            re.search(
                r"ask whether (?:the user wants to )?export or import",
                " ".join(text.lower().split()),
            )
        )

    def test_every_handoff_entrypoint_is_a_thin_dispatch_wrapper(self) -> None:
        for relative_path, dispatch_path in HANDOFF_ENTRYPOINTS.items():
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            with self.subTest(path=relative_path):
                self.assertIn(dispatch_path, text)
                self.assertNotIn(DEFAULT_EXPORT_RULE, text)
                for operation_reference in (
                    "bundle-format.md",
                    "export.md",
                    "import.md",
                ):
                    self.assertNotIn(operation_reference, text)

    def test_codex_standalone_reuses_the_repository_skill(self) -> None:
        canonical = "skills/handoff/SKILL.md"

        self.assertEqual(canonical, AGENT_ADAPTER_ENTRYPOINTS["codex"])
        self.assertFalse(
            (ROOT / "adapters/codex/skills/handoff/SKILL.md").exists()
        )
        codex_entrypoints = [
            source.canonical
            for source in bundle_sources_for_adapter("codex")
            if source.target == canonical
        ]
        self.assertEqual([canonical], codex_entrypoints)

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
