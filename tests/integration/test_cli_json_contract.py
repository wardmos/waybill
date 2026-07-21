"""Integration tests for the Waybill CLI JSON envelope."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from waybill_core.cli import main
from waybill_core.scaffold import create_draft_bundle


ROOT = Path(__file__).resolve().parents[2]
ORDINARY = ROOT / "examples" / "claude-to-codex"
REQUEST = ROOT / "examples" / "claude-parent-codex-child-request"
RESULT = ROOT / "examples" / "claude-parent-codex-child-result"


class CliJsonContractTests(unittest.TestCase):
    def _run_json(self, arguments: list[str]) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)
        self.assertEqual("", stderr.getvalue(), arguments)
        report = json.loads(stdout.getvalue())
        self.assertIsInstance(report.get("success"), bool, arguments)
        self.assertEqual(exit_code == 0, report["success"], arguments)
        if "valid" in report:
            self.assertEqual(report["success"], report["valid"], arguments)
        return exit_code, report

    def _git(self, repo: Path, *arguments: str) -> None:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

    def _matching_bundle(self, root: Path) -> tuple[Path, Path]:
        repo = root / "repo"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "config", "user.name", "Waybill Test")
        self._git(repo, "config", "user.email", "waybill@example.invalid")
        (repo / "tracked.txt").write_text("synthetic repository content\n")
        self._git(repo, "add", "tracked.txt")
        self._git(repo, "commit", "-m", "initial fixture")

        draft = root / "metadata-source"
        create_draft_bundle(draft, repo)
        recorded_git = json.loads((draft / "metadata.json").read_text())["git"]

        bundle = root / "matching-bundle"
        shutil.copytree(ORDINARY, bundle)
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["git"] = recorded_git
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        return repo, bundle

    def test_all_json_commands_have_successful_common_envelopes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-json-success-") as temporary:
            root = Path(temporary)
            repo, bundle = self._matching_bundle(root)
            install_target = root / "install-target"
            install_target.mkdir()
            packed = root / "packed.zip"

            cases = [
                ["validate", str(bundle), "--json"],
                [
                    "init",
                    "--target",
                    str(install_target),
                    "--adapter",
                    "claude-code",
                    "--json",
                ],
                [
                    "doctor",
                    "--target",
                    str(install_target),
                    "--adapter",
                    "claude-code",
                    "--json",
                ],
                ["verify-repo", str(bundle), "--repo", str(repo), "--json"],
                ["verify-pair", str(REQUEST), str(RESULT), "--json"],
                [
                    "new",
                    "--output",
                    str(root / "new-bundle"),
                    "--repo",
                    str(repo),
                    "--json",
                ],
                ["preflight", str(bundle), "--repo", str(repo), "--json"],
                ["ready", str(bundle), "--repo", str(repo), "--json"],
                ["inspect", str(bundle), "--json"],
                [
                    "redact",
                    str(bundle),
                    "--output",
                    str(root / "redacted"),
                    "--json",
                ],
                [
                    "pack",
                    str(bundle),
                    "--output",
                    str(packed),
                    "--json",
                ],
                ["share", str(bundle), "--check", "--json"],
                [
                    "share",
                    str(bundle),
                    "--output",
                    str(root / "shared.zip"),
                    "--json",
                ],
                [
                    "unpack",
                    str(packed),
                    "--output",
                    str(root / "unpacked"),
                    "--json",
                ],
                [
                    "render",
                    str(bundle),
                    "--output",
                    str(root / "report.md"),
                    "--json",
                ],
            ]

            observed: set[str] = set()
            for arguments in cases:
                with self.subTest(command=arguments[0], arguments=arguments):
                    exit_code, report = self._run_json(arguments)
                    self.assertEqual(0, exit_code, report)
                    observed.add(arguments[0])

            self.assertEqual(
                {
                    "validate",
                    "init",
                    "doctor",
                    "verify-repo",
                    "verify-pair",
                    "new",
                    "preflight",
                    "ready",
                    "inspect",
                    "redact",
                    "pack",
                    "share",
                    "unpack",
                    "render",
                },
                observed,
            )

    def test_all_json_commands_have_machine_readable_failure_envelopes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-json-failure-") as temporary:
            root = Path(temporary)
            repo, bundle = self._matching_bundle(root)
            missing = root / "missing"
            conflicting_draft = root / "existing-draft"
            create_draft_bundle(conflicting_draft, repo)
            existing_report = root / "existing-report.md"
            existing_report.write_text("keep existing report\n")

            cases = [
                ["validate", str(missing), "--json"],
                ["init", "--target", str(missing), "--json"],
                ["doctor", "--target", str(missing), "--json"],
                ["verify-repo", str(missing), "--repo", str(repo), "--json"],
                ["verify-pair", str(missing), str(missing), "--json"],
                [
                    "new",
                    "--output",
                    str(conflicting_draft),
                    "--repo",
                    str(repo),
                    "--json",
                ],
                ["preflight", str(missing), "--repo", str(repo), "--json"],
                ["ready", str(missing), "--repo", str(repo), "--json"],
                ["inspect", str(missing), "--json"],
                [
                    "redact",
                    str(missing),
                    "--output",
                    str(root / "redacted"),
                    "--json",
                ],
                [
                    "pack",
                    str(missing),
                    "--output",
                    str(root / "packed.zip"),
                    "--json",
                ],
                ["share", str(bundle), "--json"],
                [
                    "unpack",
                    str(missing),
                    "--output",
                    str(root / "unpacked"),
                    "--json",
                ],
                [
                    "render",
                    str(bundle),
                    "--output",
                    str(existing_report),
                    "--json",
                ],
            ]

            observed: set[str] = set()
            for arguments in cases:
                with self.subTest(command=arguments[0], arguments=arguments):
                    exit_code, report = self._run_json(arguments)
                    self.assertNotEqual(0, exit_code, report)
                    observed.add(arguments[0])

            self.assertEqual(
                {
                    "validate",
                    "init",
                    "doctor",
                    "verify-repo",
                    "verify-pair",
                    "new",
                    "preflight",
                    "ready",
                    "inspect",
                    "redact",
                    "pack",
                    "share",
                    "unpack",
                    "render",
                },
                observed,
            )

    def test_json_usage_errors_do_not_emit_argparse_text(self) -> None:
        cases = [
            (
                ["share", str(ORDINARY), "--not-a-waybill-option", "--json"],
                "unrecognized arguments",
            ),
            (["pack", "--json"], "required"),
        ]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                exit_code, report = self._run_json(arguments)

                self.assertEqual(2, exit_code)
                self.assertIn(expected, report["error"])

    def test_unexpected_json_error_is_caught_without_a_traceback(self) -> None:
        with mock.patch(
            "waybill_core.application.validate_bundle",
            side_effect=RuntimeError("synthetic unexpected failure"),
        ):
            exit_code, report = self._run_json(
                ["validate", str(ORDINARY), "--json"]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("synthetic unexpected failure", report["error"])


if __name__ == "__main__":
    unittest.main()
