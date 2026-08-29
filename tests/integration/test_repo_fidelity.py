from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from waybill_core import repo as repo_module
from waybill_core.repo import RepoVerificationReport, verify_repo_state
from waybill_core.readiness import check_export_readiness
from waybill_core.scaffold import create_draft_bundle
from waybill_core.validation import has_errors, validate_bundle


ROOT = Path(__file__).resolve().parents[2]
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class RepoFidelityTests(unittest.TestCase):
    def test_git_environment_isolates_user_config_and_repo_routing(self) -> None:
        configured = {
            "GIT_CONFIG_GLOBAL": "/tmp/synthetic-global-config",
            "GIT_DIR": "/tmp/wrong-git-dir",
            "GIT_WORK_TREE": "/tmp/wrong-work-tree",
            "GIT_INDEX_FILE": "/tmp/wrong-index",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_PARAMETERS": "'core.bare'='true'",
            "GIT_CONFIG_KEY_0": "core.bare",
            "GIT_CONFIG_VALUE_0": "true",
            "GIT_NAMESPACE": "wrong-namespace",
            "GIT_SHALLOW_FILE": "/tmp/wrong-shallow-file",
        }
        with mock.patch.dict(os.environ, configured, clear=True):
            environment = repo_module._git_environment()

        self.assertEqual(os.devnull, environment["GIT_CONFIG_GLOBAL"])
        self.assertEqual("1", environment["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual("1", environment["GIT_ATTR_NOSYSTEM"])
        for name in configured.keys() - {"GIT_CONFIG_GLOBAL"}:
            self.assertNotIn(name, environment)

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

    def test_new_preserves_non_utf8_diff_bytes_exactly(self) -> None:
        (self.repo / "unstaged.txt").write_bytes(b"\xffchanged\n")
        expected = repo_module.read_repo_diff(self.repo).content

        bundle = self.create_bundle()

        self.assertEqual(expected, (bundle / "diff.patch").read_bytes())
        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))
        self.assertEqual("ok", checks["diff_patch"].status)

    def test_new_records_the_canonical_tracked_diff_command(self) -> None:
        commands = (self.create_bundle() / "commands.log").read_text()
        expected = " ".join(repo_module.canonical_diff_commands(self.repo)[0])

        self.assertIn(expected + " -> captured in diff.patch", commands)
        self.assertNotIn(" diff --binary HEAD -- -> captured", commands)

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
        self.assertIn("diff_max_bytes", git_schema["properties"])
        self.assertNotIn("diff_max_bytes", git_schema["required"])
        self.assertEqual(1, git_schema["properties"]["diff_max_bytes"]["minimum"])
        self.assertEqual(
            5_000_000,
            git_schema["properties"]["diff_max_bytes"]["maximum"],
        )

    def test_custom_diff_limit_roundtrips_through_metadata_and_verification(self) -> None:
        (self.repo / "unstaged.txt").write_text("x" * 4096)
        bundle = self.parent / "custom-limit-bundle"

        create_draft_bundle(bundle, self.repo, max_diff_bytes=128)

        metadata = json.loads((bundle / "metadata.json").read_text())
        self.assertEqual(128, metadata["git"]["diff_max_bytes"])
        self.assertEqual(
            repo_module.diff_omission_note(128),
            (bundle / "diff.patch").read_bytes(),
        )
        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)
        self.assertFalse(report.has_errors)
        self.assertEqual("warning", checks["diff_patch"].status)

    def test_new_rejects_a_diff_limit_larger_than_a_bundle_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "bundle file limit"):
            create_draft_bundle(
                self.parent / "oversized-limit-bundle",
                self.repo,
                max_diff_bytes=5_000_001,
            )

    def test_new_and_verify_support_an_unborn_repository(self) -> None:
        unborn = self.parent / "unborn"
        unborn.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(unborn)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tracked = unborn / "tracked.txt"
        tracked.write_text("staged content\n")
        subprocess.run(
            ["git", "-C", str(unborn), "add", "tracked.txt"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tracked.write_text("worktree content\n")
        (unborn / "untracked.txt").write_text("private untracked content\n")
        bundle = self.parent / "unborn-bundle"

        create_draft_bundle(bundle, unborn)

        metadata = json.loads((bundle / "metadata.json").read_text())
        patch = (bundle / "diff.patch").read_text()
        self.assertEqual("unknown", metadata["git"]["head_sha"])
        self.assertIn("+staged content", patch)
        self.assertIn("-staged content", patch)
        self.assertIn("+worktree content", patch)
        self.assertNotIn("private untracked content", patch)
        self.assertEqual(
            2,
            (bundle / "commands.log").read_text().count(
                "-> captured in diff.patch"
            ),
        )
        report = verify_repo_state(bundle, unborn)
        checks = self.checks_by_name(report)
        self.assertFalse(report.has_errors)
        self.assertEqual("warning", checks["head_sha"].status)
        self.assertEqual("ok", checks["diff_patch"].status)

    def test_user_level_attributes_do_not_change_repo_fidelity(self) -> None:
        (self.repo / "unstaged.txt").write_text("stable changed content\n")
        (self.repo / "visible-untracked.txt").write_text("private content\n")
        expected = repo_module.read_repo_diff(self.repo).content
        bundle = self.parent / "isolated-config-bundle"
        create_draft_bundle(bundle, self.repo)
        attributes = self.parent / "global-attributes"
        attributes.write_text("*.txt binary\n")
        excludes = self.parent / "global-excludes"
        excludes.write_text("visible-untracked.txt\n")
        global_config = self.parent / "global-gitconfig"
        subprocess.run(
            [
                "git",
                "config",
                "--file",
                str(global_config),
                "core.attributesFile",
                str(attributes),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            [
                "git",
                "config",
                "--file",
                str(global_config),
                "core.excludesFile",
                str(excludes),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        with mock.patch.dict(
            os.environ,
            {"GIT_CONFIG_GLOBAL": str(global_config)},
            clear=False,
        ):
            actual = repo_module.read_repo_diff(self.repo).content
            report = verify_repo_state(bundle, self.repo)

        self.assertEqual(expected, actual)
        self.assertNotIn(b"GIT binary patch", actual)
        self.assertFalse(report.has_errors)

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

    def test_verify_rejects_diff_patch_that_does_not_match_live_repo(self) -> None:
        (self.repo / "unstaged.txt").write_text("captured unstaged content\n")
        bundle = self.create_bundle()
        patch_path = bundle / "diff.patch"
        patch_path.write_text(
            patch_path.read_text().replace(
                "+captured unstaged content",
                "+tampered unstaged content",
            )
        )

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertTrue(report.has_errors)
        self.assertEqual("error", checks["diff_patch"].status)
        self.assertEqual("does not match", checks["diff_patch"].message)
        readiness = check_export_readiness(bundle, self.repo)
        readiness_checks = {
            check.name: check for check in readiness.repo_report.checks
        }
        self.assertTrue(readiness.has_errors)
        self.assertEqual("error", readiness_checks["diff_patch"].status)

    def test_verify_rejects_content_appended_to_no_diff_note(self) -> None:
        (self.repo / "private-untracked.txt").write_text(
            "private content\n",
            encoding="utf-8",
        )
        bundle = self.create_bundle()
        patch_path = bundle / "diff.patch"
        patch_path.write_bytes(
            patch_path.read_bytes()
            + b"diff --git a/fabricated.txt b/fabricated.txt\n+fabricated\n"
        )

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual("error", checks["diff_patch"].status)
        self.assertEqual("does not match", checks["diff_patch"].message)

    def test_verify_rejects_content_appended_to_truncated_diff_note(self) -> None:
        (self.repo / "unstaged.txt").write_bytes(
            b"x" * (repo_module.MAX_DIFF_BYTES + 1)
        )
        bundle = self.create_bundle()
        patch_path = bundle / "diff.patch"
        patch_path.write_bytes(patch_path.read_bytes() + b"fabricated trailing patch\n")

        checks = self.checks_by_name(verify_repo_state(bundle, self.repo))

        self.assertEqual("error", checks["diff_patch"].status)
        self.assertEqual("does not match", checks["diff_patch"].message)

    def test_verify_rejects_invalid_dirty_instead_of_skipping_diff_patch(self) -> None:
        (self.repo / "unstaged.txt").write_text("captured unstaged content\n")
        bundle = self.create_bundle()
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["git"]["dirty"] = "true"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        (bundle / "diff.patch").write_text("tampered diff\n")

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertTrue(report.has_errors)
        self.assertEqual("error", checks["dirty"].status)
        self.assertEqual("error", checks["diff_patch"].status)

    def test_verify_accepts_captured_diff_patch(self) -> None:
        (self.repo / "unstaged.txt").write_text("captured unstaged content\n")
        bundle = self.create_bundle()

        report = verify_repo_state(bundle, self.repo)
        checks = self.checks_by_name(report)

        self.assertFalse(report.has_errors)
        self.assertEqual("ok", checks["diff_patch"].status)
        self.assertEqual("matches", checks["diff_patch"].message)

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
        self.assertEqual(checks["diff_patch"].status, "ok")

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

    def test_legacy_bundle_still_validates_but_is_not_current_export_ready(self) -> None:
        bundle = self.create_bundle()
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["git"].pop("status_digest")
        metadata["git"].pop("repo_state_digest")
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

        self.assertFalse(has_errors(validate_bundle(bundle)))
        readiness = check_export_readiness(bundle, self.repo)
        checks = {check.name: check for check in readiness.content_checks}

        self.assertTrue(readiness.has_errors)
        self.assertEqual("error", checks["status_digest"].status)
        self.assertEqual("error", checks["repo_state_digest"].status)
        for name in ("status_digest", "repo_state_digest"):
            check = checks[name]
            self.assertIn("strict readiness", check.message)
            self.assertIn("repository_digests", check.message)
            self.assertEqual("metadata.json", check.path)


if __name__ == "__main__":
    unittest.main()
