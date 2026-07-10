from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from waybill_core.repo import RepoVerificationReport, verify_repo_state
from waybill_core.scaffold import create_draft_bundle


ROOT = Path(__file__).resolve().parents[1]
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class RepoFidelityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-repo-fidelity-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.parent = Path(self.temporary_directory.name)
        self.repo = self.parent / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.name", "Waybill Test")
        self.git("config", "user.email", "waybill@example.invalid")
        (self.repo / "staged.txt").write_text("base staged\n")
        (self.repo / "unstaged.txt").write_text("base unstaged\n")
        self.git("add", "staged.txt", "unstaged.txt")
        self.git("commit", "-m", "initial commit")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            self.fail(
                f"git {' '.join(args)} failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout

    def create_bundle(self, name: str = "bundle") -> Path:
        bundle = self.parent / name
        create_draft_bundle(bundle, self.repo)
        return bundle

    @staticmethod
    def checks_by_name(report: RepoVerificationReport) -> dict[str, object]:
        return {check.name: check for check in report.checks}

    def test_new_captures_staged_and_unstaged_tracked_content_only(self) -> None:
        (self.repo / "staged.txt").write_text("captured staged content\n")
        self.git("add", "staged.txt")
        (self.repo / "unstaged.txt").write_text("captured unstaged content\n")
        (self.repo / "private-untracked.txt").write_text(
            "UNTRACKED-CONTENT-MUST-NOT-BE-CAPTURED\n"
        )

        patch = (self.create_bundle() / "diff.patch").read_text()

        self.assertIn("+captured staged content", patch)
        self.assertIn("+captured unstaged content", patch)
        self.assertNotIn("UNTRACKED-CONTENT-MUST-NOT-BE-CAPTURED", patch)

    def test_new_stores_only_sha256_repo_fidelity_values_in_metadata(self) -> None:
        (self.repo / "private-untracked-name.txt").write_text("private content\n")

        metadata_path = self.create_bundle() / "metadata.json"
        metadata_text = metadata_path.read_text()
        git_metadata = json.loads(metadata_text)["git"]

        for name in ("status_digest", "repo_state_digest"):
            self.assertRegex(git_metadata[name], DIGEST_PATTERN)
        self.assertNotIn(str(self.repo), metadata_text)
        self.assertNotIn("private-untracked-name.txt", metadata_text)

    def test_digest_schema_fields_are_defined_but_optional(self) -> None:
        schema = json.loads((ROOT / "spec/metadata.schema.json").read_text())
        git_schema = schema["properties"]["git"]

        for name in ("status_digest", "repo_state_digest"):
            self.assertIn(name, git_schema["properties"])
            self.assertNotIn(name, git_schema["required"])

    def test_verify_detects_changed_unstaged_content_with_same_basic_state(self) -> None:
        (self.repo / "unstaged.txt").write_text("first unstaged content\n")
        bundle = self.create_bundle()
        (self.repo / "unstaged.txt").write_text("second unstaged content\n")

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual(checks["branch"].status, "ok")
        self.assertEqual(checks["head_sha"].status, "ok")
        self.assertEqual(checks["dirty"].status, "ok")
        self.assertEqual(checks["status_digest"].status, "ok")
        self.assertEqual(checks["repo_state_digest"].status, "error")

    def test_verify_detects_changed_staged_content_with_same_basic_state(self) -> None:
        (self.repo / "staged.txt").write_text("first staged content\n")
        self.git("add", "staged.txt")
        bundle = self.create_bundle()
        (self.repo / "staged.txt").write_text("second staged content\n")
        self.git("add", "staged.txt")

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual(checks["branch"].status, "ok")
        self.assertEqual(checks["head_sha"].status, "ok")
        self.assertEqual(checks["dirty"].status, "ok")
        self.assertEqual(checks["status_digest"].status, "ok")
        self.assertEqual(checks["repo_state_digest"].status, "error")

    def test_verify_detects_changed_status_with_same_dirty_flag(self) -> None:
        (self.repo / "staged.txt").write_text("modified staged path\n")
        bundle = self.create_bundle()
        (self.repo / "staged.txt").write_text("base staged\n")
        (self.repo / "unstaged.txt").write_text("modified unstaged path\n")

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual(checks["dirty"].status, "ok")
        self.assertEqual(checks["status_digest"].status, "error")
        self.assertEqual(checks["repo_state_digest"].status, "error")

    def test_verify_detects_changed_untracked_path_set_without_reading_content(
        self,
    ) -> None:
        first = self.repo / "first-untracked.txt"
        first.write_text("same private content\n")
        bundle = self.create_bundle()
        first.unlink()
        (self.repo / "second-untracked.txt").write_text("same private content\n")

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual(checks["dirty"].status, "ok")
        self.assertEqual(checks["status_digest"].status, "error")
        self.assertEqual(checks["repo_state_digest"].status, "error")

    def test_verify_ignores_untracked_content_changes_at_the_same_path(self) -> None:
        untracked = self.repo / "untracked.txt"
        untracked.write_text("first private content\n")
        bundle = self.create_bundle()
        untracked.write_text("second private content\n")

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertFalse(report.has_errors)
        self.assertEqual(checks["status_digest"].status, "ok")
        self.assertEqual(checks["repo_state_digest"].status, "ok")

    def test_repo_state_digest_is_independent_of_diff_display_config(self) -> None:
        (self.repo / "unstaged.txt").write_text("stable changed content\n")
        bundle = self.create_bundle()
        self.git("config", "diff.noprefix", "true")
        self.git("config", "diff.mnemonicPrefix", "true")
        self.git("config", "diff.algorithm", "patience")
        self.git("config", "diff.indentHeuristic", "true")
        self.git("config", "diff.context", "8")
        self.git("config", "diff.interHunkContext", "8")
        self.git("config", "color.ui", "always")

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertFalse(report.has_errors)
        self.assertEqual(checks["repo_state_digest"].status, "ok")

    def test_verify_legacy_bundle_without_digests_warns_but_still_matches(self) -> None:
        bundle = self.create_bundle()
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["git"].pop("status_digest")
        metadata["git"].pop("repo_state_digest")
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertFalse(report.has_errors)
        self.assertEqual(checks["status_digest"].status, "warning")
        self.assertEqual(checks["repo_state_digest"].status, "warning")


if __name__ == "__main__":
    unittest.main()
