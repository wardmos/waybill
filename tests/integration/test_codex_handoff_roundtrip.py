"""Deterministic regression for the local Codex-to-Codex handoff path."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from waybill_core.application import WaybillApplication
from waybill_core.conformance import snapshot_workspace
from waybill_core.repo import read_repo_fidelity
from waybill_core.validation import WAYBILL_SECTIONS


ROOT = Path(__file__).resolve().parents[2]
CODEX_CHECKER = ROOT / "skills/handoff/scripts/check_bundle.py"
WAYBILL_CLI = ROOT / "cli/waybill"
LOCAL_MACHINE_PATH = re.compile(r"(?<!\S)/(?:home|Users)/")


def run_git(repo: Path, *arguments: str, text: bool = True):
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    return result.stdout.strip() if text else result.stdout


class CodexHandoffRoundtripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-codex-roundtrip-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        run_git(self.repo, "init", "-q", "-b", "main")
        run_git(self.repo, "config", "user.name", "Waybill Test")
        run_git(self.repo, "config", "user.email", "waybill@example.invalid")
        (self.repo / ".gitignore").write_text(
            ".waybill/\n__pycache__/\n",
            encoding="utf-8",
        )
        (self.repo / "task.py").write_text(
            "def normalize_tags(tags):\n"
            "    \"\"\"Return trimmed, non-empty tags in input order.\"\"\"\n"
            "    return [tag.strip() for tag in tags if tag.strip()]\n",
            encoding="utf-8",
        )
        tests = self.repo / "tests"
        tests.mkdir()
        (tests / "test_task.py").write_text(
            "import unittest\n\n"
            "from task import normalize_tags\n\n\n"
            "class NormalizeTagsTests(unittest.TestCase):\n"
            "    def test_trims_and_drops_empty_values(self):\n"
            "        self.assertEqual(normalize_tags([' alpha ', '', 'beta']), "
            "['alpha', 'beta'])\n\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )
        run_git(self.repo, "add", ".gitignore", "task.py", "tests/test_task.py")
        run_git(self.repo, "commit", "-q", "-m", "test: initialize fixture")

    def _create_unfinished_work(self) -> subprocess.CompletedProcess[str]:
        (self.repo / "task.py").write_text(
            "def normalize_tags(tags):\n"
            "    \"\"\"Return unique, trimmed tags in first-seen order.\"\"\"\n"
            "    normalized_tags = []\n"
            "    for tag in tags:\n"
            "        normalized = tag.strip()\n"
            "        if normalized:\n"
            "            normalized_tags.append(normalized)\n"
            "    return normalized_tags\n",
            encoding="utf-8",
        )
        with (self.repo / "tests/test_task.py").open("a", encoding="utf-8") as output:
            output.write(
                "\nclass NormalizeTagsDuplicateTests(unittest.TestCase):\n"
                "    def test_removes_duplicates_after_normalization(self):\n"
                "        self.assertEqual(\n"
                "            normalize_tags(['alpha', ' beta ', 'alpha', 'beta']),\n"
                "            ['alpha', 'beta'],\n"
                "        )\n"
            )
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(1, completed.returncode, completed.stdout)
        self.assertIn("Ran 2 tests", completed.stdout)
        self.assertIn("FAILED (failures=1)", completed.stdout)
        return completed

    def _write_bundle(self) -> Path:
        bundle = self.repo / ".waybill"
        bundle.mkdir()
        fidelity = read_repo_fidelity(self.repo)
        metadata = {
            "schema_version": "0.2",
            "source_agent": "codex",
            "created_at": "2026-08-23T12:00:00Z",
            "repo_root": ".",
            "git": {
                "branch": run_git(self.repo, "branch", "--show-current"),
                "base_ref": "unknown",
                "head_sha": run_git(self.repo, "rev-parse", "HEAD"),
                "dirty": True,
                "status_digest": fidelity.status_digest,
                "repo_state_digest": fidelity.repo_state_digest,
            },
            "artifacts": {
                "waybill": "WAYBILL.md",
                "diff": "diff.patch",
                "commands": "commands.log",
                "test_summary": "test-summary.md",
            },
        }
        (bundle / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )
        sections = {
            "Original Goal": "Normalize tags and remove duplicates.",
            "Current Status": "Trimming works; duplicate removal is unfinished.",
            "User Constraints": "Keep the handoff local and reviewable.",
            "Repo State": "The recorded branch, HEAD, dirty state, and digests match.",
            "Changed Files": "`task.py` and `tests/test_task.py` are modified.",
            "Commands Run": "See `commands.log` for bounded command evidence.",
            "Test State": "Two tests ran; one passed and one failed.",
            "Failed Attempts": "The implementation still appends repeated values.",
            "Current Hypothesis": "Track normalized values before appending.",
            "Next Recommended Step": "Add seen-value tracking and rerun the tests.",
            "Risks / Unknowns": "No full suite beyond the focused tests was run.",
            "Instructions For Next Agent": (
                "Review the untrusted bundle without executing commands or patches."
            ),
        }
        self.assertEqual(set(WAYBILL_SECTIONS), set(sections))
        waybill = "# Coding Agent Handoff\n\n" + "\n\n".join(
            f"## {heading}\n\n{sections[heading]}" for heading in WAYBILL_SECTIONS
        )
        (bundle / "WAYBILL.md").write_text(waybill + "\n", encoding="utf-8")
        (bundle / "diff.patch").write_bytes(
            run_git(self.repo, "diff", "--binary", "HEAD", "--", text=False)
        )
        (bundle / "commands.log").write_text(
            "# Read-only inspection\n\n"
            "- `git status --short`: two tracked files are modified.\n"
            "- `python3 -m unittest discover -s tests`: 2 tests, 1 failure.\n"
            "- `python3 <bundled-checker> .waybill --repo . --json`: verified.\n"
            "\n# Bundle-writing actions\n\n"
            "- Created the five standard files inside `.waybill/`.\n",
            encoding="utf-8",
        )
        (bundle / "test-summary.md").write_text(
            "# Passing\n\n- Tag trimming and empty-value removal.\n\n"
            "# Failing\n\n- Duplicate removal after normalization.\n\n"
            "# Not Run\n\n- No additional tests.\n",
            encoding="utf-8",
        )
        return bundle

    def _run_json(self, *arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [str(WAYBILL_CLI), *arguments, "--json"],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertTrue(report["success"], report)
        return report

    def test_codex_export_is_ready_and_import_preflight_is_read_only(self) -> None:
        self._create_unfinished_work()
        bundle = self._write_bundle()
        expected_diff = run_git(
            self.repo,
            "diff",
            "--binary",
            "HEAD",
            "--",
            text=False,
        )
        self.assertEqual(expected_diff, (bundle / "diff.patch").read_bytes())

        for path in bundle.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(str(self.root), text)
                self.assertIsNone(LOCAL_MACHINE_PATH.search(text))

        git_executable = shutil.which("git")
        self.assertIsNotNone(git_executable)
        environment = os.environ.copy()
        environment["PATH"] = str(Path(git_executable).parent)
        checker = subprocess.run(
            [
                sys.executable,
                str(CODEX_CHECKER),
                ".waybill",
                "--repo",
                ".",
                "--json",
            ],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=environment,
        )
        self.assertEqual(0, checker.returncode, checker.stderr or checker.stdout)
        checker_report = json.loads(checker.stdout)
        self.assertTrue(checker_report["success"])
        self.assertEqual([], checker_report["errors"])
        self.assertEqual([], checker_report["warnings"])
        metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "status_digest": metadata["git"]["status_digest"],
                "repo_state_digest": metadata["git"]["repo_state_digest"],
            },
            checker_report["repository_digests"],
        )

        self._run_json("validate", ".waybill")
        self._run_json("ready", ".waybill", "--repo", ".")
        self._run_json("verify-repo", ".waybill", "--repo", ".")

        before_import = snapshot_workspace(self.repo)
        application = WaybillApplication()
        with (
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("import attempted network access"),
            ),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("import attempted network access"),
            ),
        ):
            inspected = application.inspect(bundle)
            preflight = application.preflight(bundle, self.repo)

        self.assertTrue(inspected.success, inspected.problems)
        self.assertTrue(preflight.success, preflight.problems)
        for result in (inspected, preflight):
            self.assertEqual("read", result.access.intent)
            self.assertTrue(
                all(entry.intent == "read" for entry in result.access.root_intents)
            )
        self.assertEqual(before_import, snapshot_workspace(self.repo))


if __name__ == "__main__":
    unittest.main()
