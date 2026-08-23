"""Tests for aggregate repository validation execution."""

from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]

EXPECTED_NEW_REQUIRED_FILES = {
    "CONFORMANCE.md",
    ".codex-plugin/plugin.json",
    "scripts/adapter-matrix.py",
    "scripts/build-adapters.py",
    "scripts/conformance-agents.py",
    "scripts/conformance-exports.py",
    "scripts/conformance-roundtrip.py",
    "scripts/test-wheel-install.py",
    "skills/handoff/SKILL.md",
    "skills/handoff/__init__.py",
    "skills/handoff/references/bundle-format.md",
    "skills/handoff/references/export.md",
    "skills/handoff/references/import.md",
    "skills/handoff/assets/bundle-template/WAYBILL.md",
    "skills/handoff/assets/bundle-template/metadata.json",
    "skills/handoff/assets/bundle-template/diff.patch",
    "skills/handoff/assets/bundle-template/commands.log",
    "skills/handoff/assets/bundle-template/test-summary.md",
    "skills/handoff/scripts/check_bundle.py",
    "waybill_core/adapter_matrix.py",
    "waybill_core/adapter_bundles.py",
    "waybill_core/adapter_installation.py",
    "waybill_core/adapter_sources.py",
    "waybill_core/agent_identity.py",
    "waybill_core/agent_execution.py",
    "waybill_core/application.py",
    "waybill_core/conformance.py",
    "waybill_core/export_conformance.py",
    "waybill_core/roundtrip_conformance.py",
    "waybill_core/delegation.py",
    "conformance/scenarios/cross-agent-divergence-recovery.json",
    "conformance/scenarios/delegation-blocked.json",
    "conformance/scenarios/delegation-partial.json",
    "conformance/scenarios/delegation-request.json",
    "conformance/scenarios/delegation-result.json",
    "conformance/scenarios/failed-test.json",
    "conformance/scenarios/legacy-unknown-schema.json",
    "conformance/scenarios/malicious-embedded-instruction.json",
    "conformance/scenarios/missing-recommended-artifact.json",
    "conformance/scenarios/multi-request-mismatch.json",
    "conformance/scenarios/ordinary-unfinished.json",
    "conformance/scenarios/patch-verification.json",
    "conformance/scenarios/read-only-code-review.json",
    "conformance/scenarios/stale-repository.json",
    "conformance/export-scenarios/delegation-request.json",
    "conformance/export-scenarios/delegation-result-blocked.json",
    "conformance/export-scenarios/delegation-result-completed.json",
    "conformance/export-scenarios/delegation-result-partial.json",
    "conformance/export-scenarios/malicious-session-instruction.json",
    "conformance/export-scenarios/ordinary-unfinished.json",
}

EXPECTED_CHECK_NAMES = (
    "structure",
    "metadata schema",
    "schema version compatibility",
    "canonical handoff skill",
    "Codex plugin",
    "Codex marketplace",
    "Claude skills",
    "OpenCode adapter",
    "Cursor adapter",
    "Gemini CLI adapter",
    "adapter distribution build",
    "Python package",
    "packaging declarations",
    "wheel installation",
    "CI workflow",
    "PyPI publish workflow",
    "examples",
    "conformance scenarios",
    "conformance runner dry-run",
    "export conformance scenarios",
    "export conformance runner dry-run",
    "roundtrip conformance runner dry-run",
    "CLI validate",
    "CLI init",
    "adapter installation lifecycle",
    "CLI doctor",
    "CLI new",
    "CLI verify-repo",
    "CLI verify-pair",
    "CLI preflight",
    "CLI ready",
    "CLI inspect",
    "CLI redact",
    "CLI pack",
    "CLI share",
    "CLI share --check",
    "CLI unpack",
    "CLI render",
    "CLI JSON contract",
    "CLI end-to-end",
    "resource limits",
    "unsafe bundle paths",
)


def load_validator() -> ModuleType:
    path = ROOT / "scripts" / "validate-waybill.py"
    spec = importlib.util.spec_from_file_location("waybill_repository_validator", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load repository validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValidationRunnerTests(unittest.TestCase):
    def test_required_files_cover_new_modules_and_scenarios(self) -> None:
        validator = load_validator()

        self.assertTrue(EXPECTED_NEW_REQUIRED_FILES.issubset(validator.REQUIRED_FILES))

    def test_check_inventory_is_stable_complete_and_unique(self) -> None:
        validator = load_validator()

        self.assertIsInstance(validator.CHECKS, tuple)
        names = tuple(name for name, _check in validator.CHECKS)
        self.assertEqual(EXPECTED_CHECK_NAMES, names)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(callable(check) for _name, check in validator.CHECKS))

    def test_main_runs_the_stable_check_inventory(self) -> None:
        validator = load_validator()

        with mock.patch.object(validator, "run_checks", return_value=7) as runner:
            self.assertEqual(7, validator.main())

        runner.assert_called_once_with(validator.CHECKS)

    def test_runner_reports_every_failure_and_continues(self) -> None:
        validator = load_validator()
        calls: list[str] = []

        def expected_failure() -> None:
            calls.append("expected")
            validator.fail("first problem")

        def unexpected_failure() -> None:
            calls.append("unexpected")
            raise RuntimeError("second problem")

        def final_success() -> None:
            calls.append("success")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = validator.run_checks(
                [
                    ("expected check", expected_failure),
                    ("unexpected check", unexpected_failure),
                    ("final check", final_success),
                ]
            )

        self.assertEqual(1, exit_code)
        self.assertEqual(["expected", "unexpected", "success"], calls)
        self.assertIn("PASS final check", stdout.getvalue())
        self.assertIn("FAIL expected check: first problem", stderr.getvalue())
        self.assertIn(
            "FAIL unexpected check: unexpected RuntimeError: second problem",
            stderr.getvalue(),
        )
        self.assertIn("2 check(s) failed", stderr.getvalue())

    def test_runner_preserves_the_success_summary(self) -> None:
        validator = load_validator()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = validator.run_checks((("one", lambda: None),))

        self.assertEqual(0, exit_code)
        self.assertIn("PASS one", stdout.getvalue())
        self.assertIn("PASS Waybill repository validation", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
