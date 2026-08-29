"""Tests for bidirectional export-to-import conformance."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from waybill_core.conformance import build_prompt
from waybill_core.export_conformance import (
    ExportAgentIdentity,
    load_export_scenarios,
    prepare_synthetic_repository,
)
from waybill_core.roundtrip_conformance import (
    _import_scenario,
    run_bidirectional_roundtrip,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "conformance" / "export-scenarios"
FAKE_AGENT = REPO_ROOT / "tests" / "conformance" / "fixtures" / "fake_roundtrip_agent.py"
RUNNER = REPO_ROOT / "scripts" / "conformance-roundtrip.py"


class BidirectionalRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = {
            scenario.id: scenario for scenario in load_export_scenarios(SCENARIO_DIR)
        }["ordinary-unfinished"]
        cls.left_identity = ExportAgentIdentity(
            agent="deterministic-left",
            product="deterministic-fake",
            version="999.0.0-test-only",
        )
        cls.right_identity = ExportAgentIdentity(
            agent="deterministic-right",
            product="deterministic-fake",
            version="999.0.0-test-only",
        )

    def _run(
        self,
        *,
        left_adapter: str = "codex",
        right_adapter: str = "claude-code",
        left_fault: str | None = None,
        right_fault: str | None = None,
    ):
        left = [sys.executable, str(FAKE_AGENT)]
        right = [sys.executable, str(FAKE_AGENT)]
        if left_fault is not None:
            left.extend(["--fault", left_fault])
        if right_fault is not None:
            right.extend(["--fault", right_fault])
        return run_bidirectional_roundtrip(
            self.scenario,
            left,
            right,
            self.left_identity,
            self.right_identity,
            left_adapter=left_adapter,
            right_adapter=right_adapter,
            source_root=REPO_ROOT,
            timeout_seconds=20,
        )

    def test_import_prompt_withholds_the_controller_semantic_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prepared = prepare_synthetic_repository(
                Path(temporary),
                self.scenario,
                adapter="codex",
                source_root=REPO_ROOT,
            )
            import_scenario = _import_scenario(
                self.scenario,
                prepared,
                exporter_adapter="codex",
                importer_adapter="claude-code",
            )

        prompt = build_prompt(import_scenario)
        prompt_input = json.loads(prompt.split("Scenario input JSON:\n", 1)[1])
        self.assertNotIn("expected", prompt_input)
        self.assertFalse(
            any(
                item.startswith("ROUNDTRIP_OBSERVATION_CONTRACT=")
                for item in prompt_input["evidence"]
            )
        )
        self.assertNotIn("Copy every semantic field exactly", prompt)
        self.assertNotIn(
            json.dumps(import_scenario.expected, sort_keys=True),
            prompt,
        )
        self.assertIn(
            "The normalized value must end with a period immediately after MARKER.",
            prompt,
        )

    def test_role_specific_import_commands_override_export_permissions(self) -> None:
        clean = [sys.executable, str(FAKE_AGENT)]
        export_with_import_fault = [
            sys.executable,
            str(FAKE_AGENT),
            "--fault",
            "import-write",
        ]

        result = run_bidirectional_roundtrip(
            self.scenario,
            export_with_import_fault,
            export_with_import_fault,
            self.left_identity,
            self.right_identity,
            left_adapter="codex",
            right_adapter="claude-code",
            left_import_command=clean,
            right_import_command=clean,
            source_root=REPO_ROOT,
            timeout_seconds=20,
        )

        self.assertTrue(result.passed, result.errors)

    def test_both_directions_pass_export_gates_and_zero_write_import(self) -> None:
        result = self._run()

        self.assertTrue(result.passed, result.errors)
        self.assertFalse(result.environment_blocked)
        self.assertEqual(
            ["codex-to-claude-code", "claude-code-to-codex"],
            [direction.direction for direction in result.directions],
        )
        for direction in result.directions:
            with self.subTest(direction=direction.direction):
                self.assertTrue(direction.export_result.passed)
                self.assertTrue(direction.export_result.validation_ok)
                self.assertTrue(direction.export_result.readiness_ok)
                self.assertTrue(direction.export_result.repo_verification_ok)
                self.assertIsNotNone(direction.import_result)
                assert direction.import_result is not None
                self.assertTrue(direction.import_result.passed)
                self.assertTrue(direction.import_result.effects_match)
                self.assertEqual(
                    [], direction.import_result.measured_unexpected_writes
                )

    def test_route_matrix_covers_all_four_ordered_adapter_pairs(self) -> None:
        results = (
            self._run(),
            self._run(left_adapter="codex", right_adapter="codex"),
            self._run(left_adapter="claude-code", right_adapter="claude-code"),
        )

        self.assertTrue(all(result.passed for result in results))
        self.assertEqual([2, 1, 1], [len(result.directions) for result in results])
        self.assertEqual(
            {
                "codex-to-claude-code",
                "claude-code-to-codex",
                "codex-to-codex",
                "claude-code-to-claude-code",
            },
            {
                direction.direction
                for result in results
                for direction in result.directions
            },
        )

    def test_import_workspace_write_fails_only_the_affected_direction(self) -> None:
        result = self._run(right_fault="import-write")
        directions = {direction.direction: direction for direction in result.directions}

        self.assertFalse(result.passed)
        affected = directions["codex-to-claude-code"]
        self.assertIsNotNone(affected.import_result)
        assert affected.import_result is not None
        self.assertEqual(
            ["roundtrip-import-write.txt"],
            affected.import_result.measured_unexpected_writes,
        )
        self.assertFalse(affected.passed)
        self.assertTrue(directions["claude-code-to-codex"].passed)

    def test_environment_block_is_reported_without_an_unsandboxed_retry(self) -> None:
        result = self._run(right_fault="environment-blocked")
        report = result.to_dict()

        self.assertFalse(result.passed)
        self.assertTrue(result.environment_blocked)
        self.assertEqual(0, report["automatic_retries"])
        self.assertNotIn("Failed RTM_NEWADDR", json.dumps(report))


class RoundtripRunnerCliTests(unittest.TestCase):
    def test_deterministic_fake_cli_runs_both_directions(self) -> None:
        relative_fixture = FAKE_AGENT.relative_to(REPO_ROOT)
        command = f"{sys.executable} {relative_fixture}"
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--deterministic-fake",
                "--left-adapter",
                "codex",
                "--right-adapter",
                "claude-code",
                "--left-agent-command",
                command,
                "--right-agent-command",
                command,
                "--timeout",
                "20",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["success"])
        self.assertEqual("roundtrip", report["capability"])
        self.assertEqual("deterministic_fake", report["execution_mode"])
        self.assertEqual(2, len(report["directions"]))

    def test_deterministic_fake_cli_runs_each_same_adapter_route_once(self) -> None:
        relative_fixture = FAKE_AGENT.relative_to(REPO_ROOT)
        command = f"{sys.executable} {relative_fixture}"

        for adapter in ("codex", "claude-code"):
            with self.subTest(adapter=adapter):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER),
                        "--deterministic-fake",
                        "--left-adapter",
                        adapter,
                        "--right-adapter",
                        adapter,
                        "--left-agent-command",
                        command,
                        "--right-agent-command",
                        command,
                        "--timeout",
                        "20",
                    ],
                    cwd=REPO_ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                report = json.loads(completed.stdout)
                self.assertTrue(report["success"])
                self.assertEqual(
                    [f"{adapter}-to-{adapter}"],
                    [direction["direction"] for direction in report["directions"]],
                )

    def test_cli_accepts_role_specific_import_commands(self) -> None:
        clean = f"{sys.executable} {FAKE_AGENT}"
        export_with_import_fault = clean + " --fault import-write"
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--deterministic-fake",
                "--left-adapter",
                "codex",
                "--right-adapter",
                "claude-code",
                "--left-agent-command",
                export_with_import_fault,
                "--right-agent-command",
                export_with_import_fault,
                "--left-import-command",
                clean,
                "--right-import-command",
                clean,
                "--timeout",
                "20",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["success"])

    def test_cli_requires_an_explicit_execution_mode(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--left-adapter",
                "codex",
                "--right-adapter",
                "claude-code",
                "--left-agent-command",
                "unused-left",
                "--right-agent-command",
                "unused-right",
                "--dry-run",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("--deterministic-fake", completed.stderr)
        self.assertIn("--unsafe-manual", completed.stderr)

    def test_manual_dry_run_records_launcher_scoped_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            launcher = Path(temporary) / "codex-wrapper"
            launcher.write_text(
                "#!/bin/sh\nprintf 'codex-cli 999.0.0-test-only\\n'\n",
                encoding="utf-8",
            )
            launcher.chmod(0o755)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--unsafe-manual",
                    "--dry-run",
                    "--left-adapter",
                    "codex",
                    "--right-adapter",
                    "codex",
                    "--left-identity-kind",
                    "launcher",
                    "--right-identity-kind",
                    "launcher",
                    "--left-agent-command",
                    str(launcher),
                    "--right-agent-command",
                    str(launcher),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        for side in ("left", "right"):
            identity = report[side]["identity"]
            self.assertEqual("launcher", identity["identity_kind"])
            self.assertEqual("codex", identity["reported_product"])
            self.assertNotIn("product", identity)

    def test_manual_evidence_rejects_custom_scenario_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scenario_dir = Path(temporary) / "scenarios"
            scenario_dir.mkdir()
            (scenario_dir / "ordinary-unfinished.json").write_bytes(
                (SCENARIO_DIR / "ordinary-unfinished.json").read_bytes()
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--unsafe-manual",
                    "--left-adapter",
                    "codex",
                    "--right-adapter",
                    "claude-code",
                    "--left-agent-command",
                    sys.executable,
                    "--right-agent-command",
                    sys.executable,
                    "--scenario-dir",
                    str(scenario_dir),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn(
            "manual evidence requires the canonical --scenario-dir",
            completed.stderr,
        )


class ConformanceDocumentationTests(unittest.TestCase):
    def test_roundtrip_documentation_keeps_the_oracle_controller_side(self) -> None:
        documentation = (REPO_ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")

        self.assertIn(
            "The expected roundtrip observation remains controller-side",
            documentation,
        )
        self.assertNotIn("The importer copies those values exactly", documentation)

    def test_runtime_scratch_exception_remains_narrow(self) -> None:
        documentation = (REPO_ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
        normalized = " ".join(documentation.split())

        self.assertIn(
            "The controller-assigned `runtime-home/tmp` subtree is disposable CLI "
            "scratch.",
            normalized,
        )
        self.assertIn(
            "Replacing that temporary directory itself, writing anywhere else in "
            "runtime-home, or changing the workspace still fails.",
            normalized,
        )

    def test_live_commands_allow_safe_noninteractive_bundle_writes(self) -> None:
        documentation = (REPO_ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")

        self.assertIn(
            "--agent-command 'codex exec --ephemeral --approve-for-me -C . "
            "--color never -'",
            documentation,
        )
        self.assertIn(
            "--left-agent-command 'codex exec --ephemeral --approve-for-me "
            "-C . --color never -'",
            documentation,
        )
        self.assertIn(
            "--right-agent-command 'claude -p --safe-mode --permission-mode auto "
            "--no-session-persistence'",
            documentation,
        )
        self.assertIn(
            "--left-import-command 'codex exec --ephemeral -s read-only -C . "
            "--color never -'",
            documentation,
        )
        self.assertIn(
            "--right-import-command 'claude -p --safe-mode --permission-mode plan "
            "--no-session-persistence'",
            documentation,
        )
        self.assertIn(
            "--right-import-command 'claude -p --safe-mode --permission-mode plan "
            "--no-session-persistence' \\\n  --timeout 360",
            documentation,
        )
        self.assertNotIn(
            "--agent-command 'codex exec --ephemeral -C . -'",
            documentation,
        )


if __name__ == "__main__":
    unittest.main()
