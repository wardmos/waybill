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
    def test_entrypoint_inventory_excludes_domain_owned_files(self) -> None:
        validator = load_validator()
        inventory = set(validator.REPOSITORY_ENTRYPOINT_FILES)
        adapter_sources = {
            source.canonical for source in validator.ADAPTER_BUNDLE_SOURCES
        }

        self.assertFalse(hasattr(validator, "REQUIRED_PRODUCT_FILES"))
        self.assertFalse(hasattr(validator, "CORE_REPOSITORY_FILES"))
        self.assertEqual(
            len(validator.REPOSITORY_ENTRYPOINT_FILES),
            len(inventory),
        )
        self.assertTrue(
            {".gitignore", "LICENSE", "MANIFEST.in", "pyproject.toml"}
            <= inventory
        )
        self.assertTrue(inventory.isdisjoint(adapter_sources))
        self.assertFalse(
            any(
                path.startswith(
                    ("conformance/scenarios/", "conformance/export-scenarios/")
                )
                for path in inventory
            )
        )
        self.assertFalse(
            any(
                path.startswith("waybill_core/")
                and path not in {"waybill_core/__init__.py", "waybill_core/cli.py"}
                for path in inventory
            )
        )

    def test_adapter_distribution_checks_manifest_owned_sources(self) -> None:
        validator = load_validator()
        expected = sorted(
            {source.canonical for source in validator.ADAPTER_BUNDLE_SOURCES}
        )
        checked: list[str] = []

        def record_required_file(path: str) -> Path:
            checked.append(path)
            return ROOT / path

        with (
            mock.patch.object(
                validator,
                "require_file",
                side_effect=record_required_file,
            ),
            mock.patch.object(
                validator,
                "build_adapter_bundles",
                side_effect=validator.ValidationError("stop after source checks"),
            ),
            self.assertRaisesRegex(
                validator.ValidationError,
                "stop after source checks",
            ),
        ):
            validator.validate_adapter_distribution_build()

        self.assertEqual(expected, checked)

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
