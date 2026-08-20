"""Behavior tests for the optional read-only bundled Skill checker."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import ModuleType
from unittest import mock

from waybill_core.repo import read_repo_fidelity
from waybill_core.validation import WAYBILL_SECTIONS, validate_bundle


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "skills/handoff/scripts/check_bundle.py"


def load_checker_module() -> ModuleType:
    module_name = "waybill_test_bundled_checker"
    spec = importlib.util.spec_from_file_location(module_name, CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load bundled checker module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CHECKER_MODULE = load_checker_module()


def run_git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def write_waybill(path: Path) -> None:
    sections = "\n\n".join(
        f"## {heading}\n\nSynthetic {heading.lower()} evidence."
        for heading in WAYBILL_SECTIONS
    )
    path.write_text(f"# Coding Agent Handoff\n\n{sections}\n", encoding="utf-8")


class BundledSkillCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-skill-checker-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.name", "Waybill Test")
        run_git(self.repo, "config", "user.email", "waybill@example.invalid")
        (self.repo / ".gitignore").write_text(".waybill/\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        run_git(self.repo, "add", ".gitignore", "tracked.txt")
        run_git(self.repo, "commit", "-q", "-m", "initial")

        self.bundle = self.repo / ".waybill"
        self.bundle.mkdir()
        write_waybill(self.bundle / "WAYBILL.md")
        (self.bundle / "diff.patch").write_text(
            "# No tracked diff captured.\n", encoding="utf-8"
        )
        (self.bundle / "commands.log").write_text(
            "# Read-only inspection\n\n- git status --short: clean\n"
            "\n# Bundle writes\n\n- Wrote the bundle files.\n",
            encoding="utf-8",
        )
        (self.bundle / "test-summary.md").write_text(
            "# Passing\n\nNone.\n\n# Failing\n\nNone.\n"
            "\n# Not Run\n\nTests were not requested.\n",
            encoding="utf-8",
        )
        self.metadata = {
            "schema_version": "0.2",
            "source_agent": "codex",
            "created_at": "2026-08-05T12:00:00Z",
            "repo_root": ".",
            "git": {
                "branch": run_git(self.repo, "branch", "--show-current"),
                "base_ref": "unknown",
                "head_sha": run_git(self.repo, "rev-parse", "HEAD"),
                "dirty": False,
            },
            "artifacts": {
                "waybill": "WAYBILL.md",
                "diff": "diff.patch",
                "commands": "commands.log",
                "test_summary": "test-summary.md",
            },
        }
        self.write_metadata()

    def write_metadata(self) -> None:
        (self.bundle / "metadata.json").write_text(
            json.dumps(self.metadata, indent=2) + "\n", encoding="utf-8"
        )

    def run_checker(
        self,
        bundle: Path | None = None,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        git_executable = shutil.which("git")
        self.assertIsNotNone(git_executable)
        environment = os.environ.copy()
        environment["PATH"] = str(Path(git_executable).parent)
        self.assertIsNone(shutil.which("waybill", path=environment["PATH"]))
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                str(self.bundle if bundle is None else bundle),
                "--repo",
                str(self.repo),
                "--json",
                *extra,
            ],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )

    def bundle_snapshot(self) -> dict[str, str]:
        return {
            path.relative_to(self.bundle).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in self.bundle.rglob("*")
            if path.is_file() and not path.is_symlink()
        }

    def test_basic_bundle_without_digests_passes_without_writes(self) -> None:
        before = self.bundle_snapshot()

        result = self.run_checker()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["success"])
        self.assertEqual([], report["errors"])
        self.assertEqual(
            {"status-digest-missing", "repo-state-digest-missing"},
            {warning["code"] for warning in report["warnings"]},
        )
        fidelity = read_repo_fidelity(self.repo)
        self.assertEqual(
            {
                "status_digest": fidelity.status_digest,
                "repo_state_digest": fidelity.repo_state_digest,
            },
            report["repository_digests"],
        )
        self.assertEqual(before, self.bundle_snapshot())
        self.assertEqual("", run_git(self.repo, "status", "--short"))

    def test_reads_each_bundle_file_once(self) -> None:
        opened: list[str] = []
        original_open = CHECKER_MODULE.os.open

        def tracked_open(
            path: str | Path,
            flags: int,
            *arguments: object,
            **keywords: object,
        ) -> int:
            candidate = Path(path)
            try:
                relative = candidate.relative_to(self.bundle)
            except ValueError:
                pass
            else:
                opened.append(relative.as_posix())
            return original_open(path, flags, *arguments, **keywords)

        with mock.patch.object(CHECKER_MODULE.os, "open", side_effect=tracked_open):
            checker = CHECKER_MODULE.check_bundle(self.bundle, self.repo, None)

        self.assertEqual([], checker.errors)
        self.assertEqual(
            Counter({relative: 1 for relative in self.bundle_snapshot()}),
            Counter(opened),
        )
        self.assertEqual({}, checker._file_snapshots)

    def test_rejects_bundle_file_changed_during_check(self) -> None:
        original_read = CHECKER_MODULE._read_regular_bytes
        changed = False

        def change_after_first_read(
            path: Path,
            relative: str,
            checker: object,
        ) -> bytes | None:
            nonlocal changed
            content = original_read(path, relative, checker)
            if relative == "WAYBILL.md" and not changed:
                with path.open("a", encoding="utf-8") as output:
                    output.write("\nConcurrent synthetic change.\n")
                changed = True
            return content

        with mock.patch.object(
            CHECKER_MODULE,
            "_read_regular_bytes",
            side_effect=change_after_first_read,
        ):
            checker = CHECKER_MODULE.check_bundle(self.bundle, self.repo, None)

        self.assertTrue(changed)
        changed_errors = [
            error for error in checker.errors if error.code == "file-changed"
        ]
        self.assertEqual(["WAYBILL.md"], [error.path for error in changed_errors])

    def test_exact_repository_digests_match_the_full_checker_contract(self) -> None:
        fidelity = read_repo_fidelity(self.repo)
        self.metadata["git"]["status_digest"] = fidelity.status_digest
        self.metadata["git"]["repo_state_digest"] = fidelity.repo_state_digest
        self.write_metadata()

        result = self.run_checker()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["success"])
        self.assertEqual([], report["warnings"])

    def test_rejects_unresolved_placeholders_and_escaping_artifacts(self) -> None:
        self.metadata["artifacts"]["diff"] = "../outside.patch"
        self.write_metadata()
        with (self.bundle / "WAYBILL.md").open("a", encoding="utf-8") as output:
            output.write("\n{{UNRESOLVED_VALUE}}\n")

        result = self.run_checker()

        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["success"])
        self.assertTrue(
            {"artifact-path", "unresolved-placeholder"}.issubset(
                {error["code"] for error in report["errors"]}
            )
        )

    def test_rejects_sensitive_content_with_bundle_relative_findings(self) -> None:
        nested = self.bundle / "attachments" / "debug.txt"
        nested.parent.mkdir()
        nested.write_text(
            "Authorization: Bearer synthetic-test-token-value\n",
            encoding="utf-8",
        )
        with (self.bundle / "commands.log").open("a", encoding="utf-8") as output:
            output.write(
                "python3 /home/synthetic/.codex/plugins/waybill/check_bundle.py "
                ".waybill --repo . --json\n"
            )

        result = self.run_checker()

        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        findings = [
            finding
            for finding in report["errors"]
            if finding["code"] == "sensitive-content"
        ]
        self.assertEqual(
            {"attachments/debug.txt", "commands.log"},
            {finding["path"] for finding in findings},
        )
        core_paths = {
            issue.path
            for issue in validate_bundle(self.bundle)
            if issue.severity == "error"
            and issue.message.startswith("possible secret matching")
        }
        self.assertEqual(core_paths, {finding["path"] for finding in findings})
        self.assertNotIn("synthetic-test-token-value", result.stdout)
        self.assertNotIn("/home/synthetic", result.stdout)

    def test_warns_for_unscannable_content_with_a_relative_path(self) -> None:
        binary = self.bundle / "attachments" / "payload.bin"
        binary.parent.mkdir()
        binary.write_bytes(b"\xff\xfeunscannable")

        result = self.run_checker()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        matching = [
            warning
            for warning in report["warnings"]
            if warning["code"] == "content-encoding"
        ]
        self.assertEqual(
            ["attachments/payload.bin"],
            [warning["path"] for warning in matching],
        )

    def test_commands_log_section_warnings_are_structured_and_relative(self) -> None:
        (self.bundle / "commands.log").write_text(
            "Inspected the repository and created files.\n",
            encoding="utf-8",
        )

        result = self.run_checker()

        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        matching = [
            warning
            for warning in report["warnings"]
            if warning["code"] == "commands-log-section"
        ]
        self.assertEqual(
            {
                "commands.log should identify bundle-writing commands/actions",
                "commands.log should identify read-only commands/actions",
            },
            {warning["message"] for warning in matching},
        )
        self.assertEqual(
            {"commands.log"},
            {warning["path"] for warning in matching},
        )

    def test_rejects_symlinks_without_disclosing_the_target(self) -> None:
        outside = self.root / "outside-secret.txt"
        outside.write_text("synthetic secret value\n", encoding="utf-8")
        linked = self.bundle / "linked.txt"
        try:
            linked.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symbolic links are unavailable: {exc}")

        result = self.run_checker()

        self.assertEqual(1, result.returncode)
        self.assertNotIn("synthetic secret value", result.stdout)
        report = json.loads(result.stdout)
        self.assertIn("unsafe-entry", {error["code"] for error in report["errors"]})

    def test_request_result_correlation_is_checked_read_only(self) -> None:
        request = self.root / "request"
        request.mkdir()
        write_waybill(request / "WAYBILL.md")
        request_metadata = dict(self.metadata)
        request_metadata["source_agent"] = "claude-code"
        request_metadata["handoff"] = {
            "kind": "delegation_request",
            "request_id": "req-1",
            "parent_agent": "claude-code",
            "child_agent": "codex",
        }
        request_metadata["artifacts"] = {"waybill": "WAYBILL.md"}
        (request / "metadata.json").write_text(
            json.dumps(request_metadata, indent=2) + "\n", encoding="utf-8"
        )
        self.metadata["handoff"] = {
            "kind": "delegation_result",
            "result_for": "wrong-request",
            "result_status": "completed",
            "parent_agent": "claude-code",
            "child_agent": "codex",
        }
        self.write_metadata()

        result = self.run_checker(None, "--request", str(request))

        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertIn(
            "delegation-result-for",
            {error["code"] for error in report["errors"]},
        )


if __name__ == "__main__":
    unittest.main()
