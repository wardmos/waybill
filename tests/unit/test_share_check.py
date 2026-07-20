"""Tests for read-only Waybill shareability checks."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from waybill_core.limits import MAX_BUNDLE_FILES
from waybill_core.sharing import ShareFinding, check_shareability


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_BUNDLE = REPO_ROOT / "examples" / "claude-to-codex"


def snapshot_tree(root: Path) -> dict[str, tuple[str, bytes | str]]:
    """Capture files, directories, and symlinks without following symlinks."""

    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", path.readlink().as_posix())
        elif path.is_dir():
            snapshot[relative] = ("directory", "")
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


class ShareabilityCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.bundle = self.root / "bundle"
        shutil.copytree(EXAMPLE_BUNDLE, self.bundle)

    def run_read_only_check(self):
        before = snapshot_tree(self.root)
        report = check_shareability(self.bundle)
        self.assertEqual(before, snapshot_tree(self.root))
        return report

    def findings_of_kind(
        self,
        report,
        kind: str,
    ) -> list[ShareFinding]:
        return [finding for finding in report.findings if finding.kind == kind]

    def assert_relative_finding_paths(self, report) -> None:
        for finding in report.findings:
            path = PurePosixPath(finding.path)
            self.assertFalse(path.is_absolute(), finding)
            self.assertNotIn("..", path.parts, finding)
            self.assertGreater(finding.count, 0, finding)

    def test_valid_bundle_is_shareable_without_writing_outputs(self) -> None:
        report = self.run_read_only_check()

        self.assertEqual(self.bundle, report.source)
        self.assertFalse(report.has_errors)
        self.assertTrue(report.shareable)
        self.assertEqual(0, report.replacement_count)
        self.assertEqual(0, report.error_count)
        self.assert_relative_finding_paths(report)

    def test_synthetic_secrets_are_planned_redactions_without_leaking_values(
        self,
    ) -> None:
        evidence = self.bundle / "nested" / "private-evidence.txt"
        evidence.parent.mkdir()
        synthetic_key = "sharecheck-secret-value-12345"
        synthetic_email = "sharecheck@example.invalid"
        synthetic_path = "/home/sharecheck/private.txt"
        evidence.write_text(
            f"api_key = {synthetic_key}\n"
            f"owner = {synthetic_email}\n"
            f"source = {synthetic_path}\n",
            encoding="utf-8",
        )

        report = self.run_read_only_check()

        self.assertFalse(report.has_errors)
        self.assertTrue(report.shareable)
        self.assertEqual(3, report.replacement_count)
        planned = self.findings_of_kind(report, "planned-redaction")
        self.assertEqual(
            [("nested/private-evidence.txt", 3, False)],
            [
                (finding.path, finding.count, finding.blocking)
                for finding in planned
            ],
        )
        rendered_report = repr(report)
        for sensitive_value in [synthetic_key, synthetic_email, synthetic_path]:
            self.assertNotIn(sensitive_value, rendered_report)
        self.assert_relative_finding_paths(report)

    def test_non_utf8_file_is_a_blocking_relative_path_finding(self) -> None:
        attachment = self.bundle / "attachments" / "raw.bin"
        attachment.parent.mkdir()
        attachment.write_bytes(b"\xff\xfeunsafe-to-share")

        report = self.run_read_only_check()

        self.assertTrue(report.has_errors)
        self.assertFalse(report.shareable)
        self.assertEqual(1, report.error_count)
        self.assertEqual(
            [("attachments/raw.bin", 1, True)],
            [
                (finding.path, finding.count, finding.blocking)
                for finding in self.findings_of_kind(
                    report,
                    "unscannable-file",
                )
            ],
        )
        self.assert_relative_finding_paths(report)

    def test_symlink_is_blocking_and_is_not_followed(self) -> None:
        (self.bundle / "nested-link").symlink_to("WAYBILL.md")

        report = self.run_read_only_check()

        self.assertTrue(report.has_errors)
        self.assertEqual(
            [("nested-link", 1, True)],
            [
                (finding.path, finding.count, finding.blocking)
                for finding in self.findings_of_kind(report, "unsafe-symlink")
            ],
        )
        self.assert_relative_finding_paths(report)

    def test_resource_limit_is_a_blocking_root_finding(self) -> None:
        extras = self.bundle / "extras"
        extras.mkdir()
        for index in range(MAX_BUNDLE_FILES):
            (extras / f"{index:03d}.txt").write_text("x", encoding="utf-8")

        report = self.run_read_only_check()

        self.assertTrue(report.has_errors)
        self.assertEqual(
            [(".", 1, True)],
            [
                (finding.path, finding.count, finding.blocking)
                for finding in self.findings_of_kind(report, "resource-limit")
            ],
        )
        self.assert_relative_finding_paths(report)

    def test_structurally_invalid_bundle_is_blocking(self) -> None:
        (self.bundle / "WAYBILL.md").unlink()

        report = self.run_read_only_check()

        self.assertTrue(report.has_errors)
        self.assertFalse(report.shareable)
        errors = self.findings_of_kind(report, "validation-error")
        self.assertTrue(
            any(finding.path == "WAYBILL.md" for finding in errors),
            errors,
        )
        self.assert_relative_finding_paths(report)


if __name__ == "__main__":
    unittest.main()
