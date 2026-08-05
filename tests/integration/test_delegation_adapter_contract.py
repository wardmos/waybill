"""Contract tests for delegation guidance in the canonical handoff skill."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_EXPORT = ROOT / "skills/handoff/references/export.md"
CANONICAL_FORMAT = ROOT / "skills/handoff/references/bundle-format.md"
CANONICAL_IMPORT = ROOT / "skills/handoff/references/import.md"


class DelegationAdapterContractTests(unittest.TestCase):
    def test_export_guidance_requires_correlation_roles_and_result_status(self) -> None:
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (CANONICAL_FORMAT, CANONICAL_EXPORT)
        )
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

    def test_import_guidance_uses_read_only_pair_verification(self) -> None:
        text = CANONICAL_IMPORT.read_text(encoding="utf-8")
        self.assertIn("waybill verify-pair REQUEST RESULT", text)
        self.assertIn("mismatch", text)


if __name__ == "__main__":
    unittest.main()
