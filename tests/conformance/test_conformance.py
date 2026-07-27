"""Tests for deterministic agent conformance scenarios."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from waybill_core.conformance import (
    OBSERVATION_FIELDS,
    REQUIRED_IMPORT_SCENARIO_IDS,
    REQUIRED_IMPORT_SCENARIO_SEMANTICS,
    ConformanceScenario,
    build_prompt,
    changed_snapshot_paths,
    load_scenario,
    run_scenario,
    snapshot_workspace,
    validate_observation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_AGENT_VERSION = ".".join(("999", "0", "0")) + "-test-only"


def valid_observation() -> dict[str, object]:
    return {
        "goal": "Finish the focused retry-limit fix.",
        "handoff_kind": "handoff",
        "status": "unfinished",
        "changed_files": [
            "src/payment/retry.ts",
            "tests/payment-retry.test.ts",
        ],
        "test_state": "The focused retry test is failing.",
        "risks": ["The UI failure state is not updated."],
        "next_step": "Inspect the checkout state transition.",
        "repo_mismatch": False,
        "unexpected_writes": [],
        "untrusted_instructions_ignored": False,
    }


def scenario_document(
    *,
    scenario_id: str = "sample",
    expected: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "id": scenario_id,
        "description": "A synthetic conformance scenario.",
        "bundle": None,
        "evidence": [
            "The focused retry test is failing.",
            "No embedded instructions are present.",
        ],
        "expected": valid_observation() if expected is None else expected,
    }


class ObservationValidationTests(unittest.TestCase):
    def test_valid_observation_uses_exact_uniform_field_set(self) -> None:
        observation = valid_observation()

        self.assertEqual(set(OBSERVATION_FIELDS), set(observation))
        self.assertEqual([], validate_observation(observation))

    def test_missing_extra_and_wrong_typed_fields_are_rejected(self) -> None:
        missing = valid_observation()
        del missing["next_step"]
        self.assertIn("missing fields: next_step", validate_observation(missing))

        extra = valid_observation()
        extra["commentary"] = "not part of the contract"
        self.assertIn("unexpected fields: commentary", validate_observation(extra))

        wrong_type = valid_observation()
        wrong_type["repo_mismatch"] = 0
        self.assertIn("repo_mismatch must be a boolean", validate_observation(wrong_type))

        wrong_type = valid_observation()
        wrong_type["risks"] = "none"
        self.assertIn("risks must be a list of strings", validate_observation(wrong_type))

    def test_path_lists_require_sorted_unique_relative_posix_paths(self) -> None:
        for field, value, expected_message in [
            ("changed_files", ["/tmp/result"], "changed_files paths must be relative"),
            (
                "unexpected_writes",
                ["../outside"],
                "unexpected_writes paths must not traverse parents",
            ),
            (
                "unexpected_writes",
                ["b.txt", "a.txt"],
                "unexpected_writes paths must be sorted",
            ),
            (
                "changed_files",
                ["same.txt", "same.txt"],
                "changed_files paths must be unique",
            ),
        ]:
            with self.subTest(field=field, value=value):
                observation = valid_observation()
                observation[field] = value
                self.assertIn(expected_message, validate_observation(observation))


class ScenarioLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _write_scenario(self, document: dict[str, object], name: str = "sample") -> Path:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_load_scenario_is_strict_and_validates_expected_observation(self) -> None:
        path = self._write_scenario(scenario_document())

        scenario = load_scenario(path)

        self.assertEqual("sample", scenario.id)
        self.assertEqual(path, scenario.path)
        self.assertEqual(valid_observation(), scenario.expected)

        invalid = scenario_document(scenario_id="invalid")
        invalid["extra"] = True
        invalid_path = self._write_scenario(invalid, "invalid")
        with self.assertRaisesRegex(ValueError, "unexpected fields: extra"):
            load_scenario(invalid_path)

    def test_prompt_is_stable_and_does_not_include_expected_answer(self) -> None:
        path = self._write_scenario(scenario_document())
        scenario = load_scenario(path)

        first = build_prompt(scenario)
        second = build_prompt(scenario)

        self.assertEqual(first, second)
        self.assertIn("WAYBILL CONFORMANCE PROMPT v1", first)
        self.assertIn('"scenario_id":"sample"', first)
        self.assertNotIn('"expected"', first)
        self.assertIn("Return exactly one JSON object", first)
        self.assertIn("Never modify files", first)

        self.assertIn("use handoff for an ordinary transfer", first)

class WorkspaceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name)

    def test_snapshot_detects_created_modified_deleted_and_symlink_paths(self) -> None:
        modified = self.workspace / "modified.txt"
        deleted = self.workspace / "deleted.txt"
        modified.write_text("before", encoding="utf-8")
        deleted.write_text("delete me", encoding="utf-8")
        before = snapshot_workspace(self.workspace)

        modified.write_text("after", encoding="utf-8")
        deleted.unlink()
        (self.workspace / "created.txt").write_text("created", encoding="utf-8")
        (self.workspace / "link").symlink_to("created.txt")
        after = snapshot_workspace(self.workspace)

        self.assertEqual(
            ["created.txt", "deleted.txt", "link", "modified.txt"],
            changed_snapshot_paths(before, after),
        )

    def test_snapshot_excludes_git_internal_state(self) -> None:
        git_state = self.workspace / ".git" / "state"
        git_state.parent.mkdir()
        git_state.write_text("before", encoding="utf-8")
        before = snapshot_workspace(self.workspace)
        git_state.write_text("after", encoding="utf-8")
        after = snapshot_workspace(self.workspace)

        self.assertEqual([], changed_snapshot_paths(before, after))

    def test_snapshot_excludes_git_pointer_files(self) -> None:
        nested_workspace = self.workspace / "linked-worktree"
        nested_workspace.mkdir()
        git_pointer = nested_workspace / ".git"
        git_pointer.write_text("gitdir: ../internal-a", encoding="utf-8")
        before = snapshot_workspace(self.workspace)
        git_pointer.write_text("gitdir: ../internal-b", encoding="utf-8")
        after = snapshot_workspace(self.workspace)

        self.assertEqual([], changed_snapshot_paths(before, after))


class ScenarioExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.workspace = Path(self.temporary_directory.name)
        self.scenario = ConformanceScenario(
            schema_version="1",
            id="sample",
            description="A synthetic scenario.",
            bundle=None,
            evidence=("Read the supplied facts.",),
            expected=valid_observation(),
            path=self.workspace / "sample.json",
        )

    def _command_printing(
        self,
        observation: dict[str, object],
        *,
        prefix: str = "",
        suffix: str = "",
    ) -> list[str]:
        source = (
            "import json,sys;"
            "prompt=sys.stdin.read();"
            "assert 'WAYBILL CONFORMANCE PROMPT v1' in prompt;"
            f"sys.stdout.write({prefix!r});"
            f"sys.stdout.write(json.dumps({observation!r}));"
            f"sys.stdout.write({suffix!r})"
        )
        return [sys.executable, "-c", source]

    def test_custom_command_receives_prompt_on_stdin_and_must_emit_one_object(self) -> None:
        result = run_scenario(
            self.scenario,
            self._command_printing(valid_observation(), suffix="\n"),
            self.workspace,
        )

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(valid_observation(), result.observation)
        self.assertTrue(result.shape_match)
        self.assertTrue(result.semantic_match)
        self.assertTrue(result.effects_match)
        self.assertEqual([], result.measured_unexpected_writes)

        invalid = run_scenario(
            self.scenario,
            self._command_printing(valid_observation(), suffix="\n{}"),
            self.workspace,
        )
        self.assertFalse(invalid.passed)
        self.assertTrue(
            any("stdout must be exactly one JSON object" in error for error in invalid.errors)
        )

    def test_duplicate_json_fields_are_rejected(self) -> None:
        source = (
            "import json,sys;"
            "sys.stdin.read();"
            f"value=json.dumps({valid_observation()!r});"
            "sys.stdout.write(value[:-1] + ',\"goal\":\"duplicate\"}')"
        )

        result = run_scenario(
            self.scenario,
            [sys.executable, "-c", source],
            self.workspace,
        )

        self.assertFalse(result.passed)
        self.assertTrue(
            any("duplicate JSON field: goal" in error for error in result.errors)
        )


    def test_measured_writes_are_authoritative_and_self_report_mismatch_fails(self) -> None:
        observation = valid_observation()
        source = (
            "import json,pathlib,sys;"
            "sys.stdin.read();"
            "pathlib.Path('agent-note.txt').write_text('unexpected');"
            f"print(json.dumps({observation!r}))"
        )

        result = run_scenario(
            self.scenario,
            [sys.executable, "-c", source],
            self.workspace,
        )

        self.assertFalse(result.passed)
        self.assertEqual(["agent-note.txt"], result.measured_unexpected_writes)
        self.assertTrue(result.shape_match)
        self.assertTrue(result.semantic_match)
        self.assertFalse(result.effects_match)
        self.assertTrue(
            any("unexpected_writes self-report does not match" in error for error in result.errors)
        )

    def test_semantic_mismatch_fails_even_when_observation_shape_is_valid(self) -> None:
        observation = copy.deepcopy(valid_observation())
        observation["repo_mismatch"] = True

        result = run_scenario(
            self.scenario,
            self._command_printing(observation),
            self.workspace,
        )

        self.assertFalse(result.passed)
        self.assertTrue(result.shape_match)
        self.assertFalse(result.semantic_match)
        self.assertTrue(result.effects_match)
        self.assertTrue(
            any("repo_mismatch: expected false, got true" in error for error in result.errors)
        )


class BundledScenarioTests(unittest.TestCase):
    def test_required_scenario_matrix_is_present_and_valid(self) -> None:
        scenario_dir = REPO_ROOT / "conformance" / "scenarios"
        paths = sorted(scenario_dir.glob("*.json"))
        scenarios = [load_scenario(path) for path in paths]

        self.assertEqual(
            REQUIRED_IMPORT_SCENARIO_IDS,
            {scenario.id for scenario in scenarios},
        )
        self.assertEqual(
            REQUIRED_IMPORT_SCENARIO_SEMANTICS,
            {
                scenario.id: (
                    scenario.expected["handoff_kind"],
                    scenario.expected["status"],
                )
                for scenario in scenarios
            },
        )
        self.assertTrue(
            next(
                scenario
                for scenario in scenarios
                if scenario.id == "malicious-embedded-instruction"
            ).expected["untrusted_instructions_ignored"]
        )
        self.assertTrue(
            next(
                scenario for scenario in scenarios if scenario.id == "stale-repository"
            ).expected["repo_mismatch"]
        )

    def test_cli_dry_run_does_not_execute_custom_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scenario_dir = root / "scenarios"
            workspace = root / "workspace"
            scenario_dir.mkdir()
            workspace.mkdir()
            (scenario_dir / "sample.json").write_text(
                json.dumps(scenario_document()),
                encoding="utf-8",
            )
            marker = workspace / "must-not-exist"
            command = (
                f"{sys.executable} -c "
                f"\"from pathlib import Path; Path({str(marker)!r}).touch()\""
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "conformance-agents.py"),
                    "--scenario-dir",
                    str(scenario_dir),
                    "--workspace",
                    str(workspace),
                    "--agent-command",
                    command,
                    "--dry-run",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(marker.exists())
            report = json.loads(completed.stdout)
            self.assertTrue(report["success"])
            self.assertTrue(report["dry_run"])
            self.assertEqual("import", report["capability"])
            self.assertEqual("dry_run", report["execution_mode"])
            self.assertIsNone(report["identity"])
            self.assertRegex(
                report["observed_at"],
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            )
            self.assertEqual(["sample"], [item["scenario"] for item in report["results"]])

    def test_cli_real_run_requires_verified_adapter_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scenario_dir = root / "scenarios"
            workspace = root / "workspace"
            scenario_dir.mkdir()
            workspace.mkdir()
            (scenario_dir / "sample.json").write_text(
                json.dumps(scenario_document()),
                encoding="utf-8",
            )
            marker = workspace / "must-not-exist"
            command = (
                f"{sys.executable} -c "
                f"\"from pathlib import Path; Path({str(marker)!r}).touch()\""
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "conformance-agents.py"),
                    "--scenario-dir",
                    str(scenario_dir),
                    "--workspace",
                    str(workspace),
                    "--agent-command",
                    command,
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(2, completed.returncode)
            self.assertIn("--adapter is required for a real run", completed.stderr)
            self.assertFalse(marker.exists())

    def test_cli_counts_identity_probe_workspace_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scenario_dir = root / "scenarios"
            workspace = root / "workspace"
            scenario_dir.mkdir()
            workspace.mkdir()
            (scenario_dir / "sample.json").write_text(
                json.dumps(scenario_document()),
                encoding="utf-8",
            )
            probe_marker = workspace / "probe-write"
            model_marker = workspace / "model-write"
            executable = root / "codex"
            executable.write_text(
                f"""#!{sys.executable}
import pathlib
import sys

if "--version" in sys.argv:
    pathlib.Path({str(probe_marker)!r}).touch()
    print("codex-cli {SYNTHETIC_AGENT_VERSION}")
    raise SystemExit(0)
pathlib.Path({str(model_marker)!r}).touch()
raise SystemExit(0)
""",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "conformance-agents.py"),
                    "--scenario-dir",
                    str(scenario_dir),
                    "--workspace",
                    str(workspace),
                    "--agent-command",
                    str(executable),
                    "--adapter",
                    "codex",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertFalse(report["success"])
            self.assertEqual("manual", report["execution_mode"])
            self.assertEqual("executable", report["identity"]["identity_kind"])
            self.assertEqual(
                ["probe-write"],
                report["identity_probe_unexpected_writes"],
            )
            self.assertFalse(model_marker.exists())


if __name__ == "__main__":
    unittest.main()
