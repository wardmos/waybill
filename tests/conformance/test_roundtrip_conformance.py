"""Tests for bidirectional export-to-import conformance."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from waybill_core.export_conformance import ExportAgentIdentity, load_export_scenarios
from waybill_core.roundtrip_conformance import run_bidirectional_roundtrip


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

    def _run(self, *, left_fault: str | None = None, right_fault: str | None = None):
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
            left_adapter="codex",
            right_adapter="claude-code",
            source_root=REPO_ROOT,
            timeout_seconds=20,
        )

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
        command = f"{sys.executable} {FAKE_AGENT}"
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


if __name__ == "__main__":
    unittest.main()
