"""Integration tests for public CLI lifecycle and JSON help."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "cli" / "waybill"


class CliHelpTests(unittest.TestCase):
    def _help(self, *arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments, "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, arguments)
        self.assertEqual("", result.stderr, arguments)
        return " ".join(result.stdout.split())

    def test_top_level_help_documents_json_exit_contract(self) -> None:
        text = self._help()

        self.assertIn("top-level boolean success", text)
        self.assertIn("true exactly when the exit status is zero", text)

    def test_init_help_documents_managed_lifecycle_boundaries(self) -> None:
        text = self._help("init")

        self.assertIn(".waybill-adapters.json", text)
        self.assertIn(
            "would-create, would-update, unchanged, or would-conflict",
            text,
        )
        self.assertIn("never follows symbolic links", text)
        self.assertIn("Codex plugin is not managed by init", text)

    def test_doctor_help_documents_manifest_states(self) -> None:
        text = self._help("doctor")

        self.assertIn("current, missing, stale, or modified", text)
        self.assertIn(
            "Without a manifest, changed files are modified rather than stale",
            text,
        )

    def test_share_help_documents_read_only_check(self) -> None:
        text = self._help("share")

        self.assertIn("--check performs no writes and does not require --output", text)
        self.assertIn("never include matched secret values", text)


if __name__ == "__main__":
    unittest.main()
