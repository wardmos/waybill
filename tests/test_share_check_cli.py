"""CLI integration tests for read-only share checks."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests.test_share_check import snapshot_tree
from waybill_core.cli import main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "claude-to-codex"


class ShareCheckCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.bundle = self.root / "bundle"
        shutil.copytree(EXAMPLE, self.bundle)

    def _run(self) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["share", str(self.bundle), "--check", "--json"])
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_json_check_is_read_only_and_reports_value_free_redactions(self) -> None:
        secret = "share-cli-synthetic-secret-12345"
        (self.bundle / "notes.txt").write_text(
            f"api_key={secret}\n",
            encoding="utf-8",
        )
        before = snapshot_tree(self.root)

        exit_code, report, stderr = self._run()

        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        self.assertEqual(before, snapshot_tree(self.root))
        self.assertIs(True, report["success"])
        self.assertIs(True, report["shareable"])
        self.assertEqual(1, report["replacement_count"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertEqual(
            "planned-redaction",
            report["findings"][0]["kind"],
        )
        self.assertEqual(
            {"kind", "path", "count", "blocking"},
            set(report["findings"][0]),
        )

    def test_unscannable_check_fails_without_writing_outputs(self) -> None:
        (self.bundle / "raw.bin").write_bytes(b"\xff\xfe")
        before = snapshot_tree(self.root)

        exit_code, report, stderr = self._run()

        self.assertEqual(1, exit_code)
        self.assertEqual("", stderr)
        self.assertEqual(before, snapshot_tree(self.root))
        self.assertIs(False, report["success"])
        self.assertIs(False, report["shareable"])
        self.assertEqual("unscannable-file", report["findings"][0]["kind"])

    def test_regular_share_still_requires_output_without_writing(self) -> None:
        before = snapshot_tree(self.root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["share", str(self.bundle), "--json"])

        self.assertEqual(1, exit_code)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(before, snapshot_tree(self.root))
        report = json.loads(stdout.getvalue())
        self.assertIs(False, report["success"])
        self.assertIn("--output", report["error"])


if __name__ == "__main__":
    unittest.main()
