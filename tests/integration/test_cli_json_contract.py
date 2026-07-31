"""Integration tests for the Waybill CLI JSON envelope."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from waybill_core.cli import APPLICATION, main
from waybill_core.scaffold import create_draft_bundle


ROOT = Path(__file__).resolve().parents[2]
ORDINARY = ROOT / "examples" / "claude-to-codex"
REQUEST = ROOT / "examples" / "claude-parent-codex-child-request"
RESULT = ROOT / "examples" / "claude-parent-codex-child-result"


class CliJsonContractTests(unittest.TestCase):
    def _run_raw(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)
        return exit_code, stdout.getvalue(), stderr.getvalue()

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

    def test_facade_result_is_the_single_source_for_json_success_and_exit(self) -> None:
        contradictory = mock.Mock(
            payload=[],
            success=False,
            valid=False,
            problems=(),
        )
        with mock.patch(
            "waybill_core.cli.APPLICATION.validate",
            return_value=contradictory,
        ):
            exit_code, report = self._run_json(
                ["validate", str(ORDINARY), "--json"]
            )

        self.assertEqual(1, exit_code)
        self.assertFalse(report["success"])
        self.assertFalse(report["valid"])

    def test_operational_facade_failure_is_rendered_without_payload_access(self) -> None:
        failed = mock.Mock(
            payload=None,
            success=False,
            valid=None,
            problems=(mock.Mock(message="synthetic operational failure"),),
        )
        with mock.patch(
            "waybill_core.cli.APPLICATION.verify_repo",
            return_value=failed,
        ):
            exit_code, report = self._run_json(
                [
                    "verify-repo",
                    str(ORDINARY),
                    "--repo",
                    str(ROOT),
                    "--json",
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertFalse(report["success"])
        self.assertEqual("synthetic operational failure", report["error"])

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

    def test_inspect_renderers_use_only_controller_captured_evidence(self) -> None:
        operation = APPLICATION.inspect(ORDINARY)
        self.assertTrue(operation.success, operation.problems)

        for output_mode in ([], ["--json"]):
            arguments = ["inspect", str(ORDINARY), *output_mode]
            with self.subTest(arguments=arguments):
                with ExitStack() as stack:
                    stack.enter_context(
                        mock.patch(
                            "waybill_core.cli.APPLICATION.inspect",
                            return_value=operation,
                        )
                    )
                    for method in (
                        "absolute",
                        "exists",
                        "is_dir",
                        "is_file",
                        "is_symlink",
                        "lstat",
                        "open",
                        "read_bytes",
                        "read_text",
                        "resolve",
                        "stat",
                    ):
                        stack.enter_context(
                            mock.patch.object(
                                Path,
                                method,
                                side_effect=AssertionError(
                                    f"renderer attempted Path.{method}"
                                ),
                            )
                        )
                    exit_code, _, stderr = self._run_raw(arguments)

                self.assertEqual(0, exit_code)
                self.assertEqual("", stderr)

    def test_inspect_text_output_is_exactly_compatible(self) -> None:
        exit_code, stdout, stderr = self._run_raw(["inspect", str(ORDINARY)])

        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        self.assertEqual(
            """Bundle: <BUNDLE>
Schema version status: current
Schema version: 0.2
Source agent: claude-code
Created at: 2026-07-01T12:00:00Z
Repo root: .
Git branch: fix/payment-retry-limit
Git base ref: main
Git head SHA: unknown
Git dirty: True
Handoff kind: handoff
Parent agent: unknown
Child agent: unknown
Artifacts:
  - waybill: WAYBILL.md (present)
  - diff: diff.patch (present)
  - commands: commands.log (present)
  - test_summary: test-summary.md (present)
Validation: 0 error(s), 0 warning(s)
""",
            stdout.replace(str(ORDINARY), "<BUNDLE>"),
        )

    def test_inspect_json_output_is_exactly_compatible(self) -> None:
        exit_code, stdout, stderr = self._run_raw(
            ["inspect", str(ORDINARY), "--json"]
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("", stderr)
        self.assertEqual(
            """{
  "bundle": "<BUNDLE>",
  "success": true,
  "valid": true,
  "schema_version_status": "current",
  "handoff": {
    "kind": "handoff"
  },
  "metadata": {
    "schema_version": "0.2",
    "source_agent": "claude-code",
    "created_at": "2026-07-01T12:00:00Z",
    "repo_root": ".",
    "git": {
      "branch": "fix/payment-retry-limit",
      "base_ref": "main",
      "head_sha": "unknown",
      "dirty": true
    },
    "artifacts": {
      "waybill": "WAYBILL.md",
      "diff": "diff.patch",
      "commands": "commands.log",
      "test_summary": "test-summary.md"
    }
  },
  "metadata_error": null,
  "artifacts": [
    {
      "name": "waybill",
      "path": "WAYBILL.md",
      "status": "present",
      "bytes": 2310
    },
    {
      "name": "diff",
      "path": "diff.patch",
      "status": "present",
      "bytes": 698
    },
    {
      "name": "commands",
      "path": "commands.log",
      "status": "present",
      "bytes": 416
    },
    {
      "name": "test_summary",
      "path": "test-summary.md",
      "status": "present",
      "bytes": 209
    }
  ],
  "validation": {
    "errors": 0,
    "warnings": 0,
    "issues": []
  }
}
""",
            stdout.replace(str(ORDINARY), "<BUNDLE>"),
        )


if __name__ == "__main__":
    unittest.main()
