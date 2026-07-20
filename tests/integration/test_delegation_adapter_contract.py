"""Contract tests for delegation correlation in canonical adapters."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FULL_HANDOFF_ADAPTERS = (
    "adapters/claude-code/skills/handoff/SKILL.md",
    "adapters/codex/skills/handoff/SKILL.md",
    "adapters/opencode/skills/handoff/SKILL.md",
    "adapters/cursor/rules/handoff.mdc",
    "adapters/gemini-cli/skills/handoff/SKILL.md",
)
PAIR_AWARE_IMPORTS = FULL_HANDOFF_ADAPTERS + (
    "adapters/claude-code/commands/handoff-import.md",
)


class DelegationAdapterContractTests(unittest.TestCase):
    def test_export_guidance_requires_correlation_roles_and_result_status(self) -> None:
        for relative in FULL_HANDOFF_ADAPTERS:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(adapter=relative):
                for required in [
                    "request_id",
                    "result_for",
                    "result_status",
                    "parent_agent",
                    "child_agent",
                    "completed",
                    "partial",
                    "blocked",
                ]:
                    self.assertIn(required, text)

        command = (
            ROOT / "adapters/claude-code/commands/handoff-export.md"
        ).read_text(encoding="utf-8")
        for required in ["request_id", "result_for", "result_status"]:
            self.assertIn(required, command)

    def test_import_guidance_uses_read_only_pair_verification(self) -> None:
        for relative in PAIR_AWARE_IMPORTS:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(adapter=relative):
                self.assertIn("waybill verify-pair REQUEST RESULT", text)
                self.assertIn("mismatch", text)


if __name__ == "__main__":
    unittest.main()
