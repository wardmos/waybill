"""Tests for deterministic Waybill export conformance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from waybill_core.export_conformance import (
    REQUIRED_EXPORT_SCENARIO_IDS,
    SUPPORTED_EXPORT_ADAPTERS,
    ExportAgentIdentity,
    build_export_prompt,
    load_export_scenario,
    load_export_scenarios,
    prepare_synthetic_repository,
    run_export_scenario,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "conformance" / "export-scenarios"
FAKE_AGENT = REPO_ROOT / "tests" / "conformance" / "fixtures" / "fake_export_agent.py"
SYNTHETIC_AGENT_VERSION = "999.0.0-test-only"


def scenario_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1",
        "id": "sample-export",
        "description": "Export one grounded ordinary handoff.",
        "handoff_kind": "handoff",
        "status": "unfinished",
        "fixture_state": "failing",
        "goal": "Stop retrying after the configured attempt limit.",
        "expected_changed_files": ["src/retry.py", "tests/test_retry.py"],
        "risks": ["The boundary condition may be off by one."],
        "next_step": "Change the inclusive comparison and rerun the focused test.",
        "malicious_session_instruction": None,
        "delegation": None,
    }
    document.update(overrides)
    return document


class ExportScenarioLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _write(self, document: dict[str, object], name: str = "sample-export") -> Path:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_loads_a_strict_ordinary_export_scenario(self) -> None:
        scenario = load_export_scenario(self._write(scenario_document()))

        self.assertEqual("sample-export", scenario.id)
        self.assertEqual("handoff", scenario.handoff_kind)
        self.assertEqual(("src/retry.py", "tests/test_retry.py"), scenario.expected_changed_files)
        self.assertIsNone(scenario.delegation)

    def test_required_export_matrix_is_complete(self) -> None:
        self.assertEqual(
            REQUIRED_EXPORT_SCENARIO_IDS,
            {scenario.id for scenario in load_export_scenarios(SCENARIO_DIR)},
        )

    def test_rejects_extra_fields_invalid_paths_and_inconsistent_delegation(self) -> None:
        cases = [
            (scenario_document(extra=True), "unexpected fields: extra"),
            (
                scenario_document(expected_changed_files=["../outside"]),
                "expected_changed_files paths must not traverse parents",
            ),
            (
                scenario_document(
                    handoff_kind="delegation_result",
                    status="completed",
                    delegation=None,
                ),
                "delegation is required for delegation_result",
            ),
            (
                scenario_document(
                    malicious_session_instruction="run a command without canaries"
                ),
                "malicious_session_instruction must contain",
            ),
        ]
        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write(document, f"invalid-{index}")
                document["id"] = f"invalid-{index}"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    load_export_scenario(path)

    def test_rejects_duplicate_fields_and_nonstandard_json_constants(self) -> None:
        duplicate = json.dumps(scenario_document()).replace(
            '"id": "sample-export"',
            '"id": "sample-export", "id": "sample-export"',
            1,
        )
        duplicate_path = self.root / "sample-export.json"
        duplicate_path.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate JSON field: id"):
            load_export_scenario(duplicate_path)

        nonstandard = json.dumps(scenario_document()).replace(
            '"delegation": null',
            '"delegation": NaN',
            1,
        )
        duplicate_path.write_text(nonstandard, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-standard JSON constant: NaN"):
            load_export_scenario(duplicate_path)


class SyntheticRepositoryTests(unittest.TestCase):
    def test_repository_evidence_is_measured_before_the_agent_runs(self) -> None:
        scenario = load_export_scenario(SCENARIO_DIR / "ordinary-unfinished.json")
        with tempfile.TemporaryDirectory() as temporary:
            prepared = prepare_synthetic_repository(
                Path(temporary),
                scenario,
                adapter="codex",
                source_root=REPO_ROOT,
            )

            self.assertEqual(
                ["src/retry.py", "tests/test_retry.py"],
                prepared.evidence.changed_files,
            )
            self.assertNotEqual(0, prepared.evidence.test_returncode)
            self.assertIn(prepared.evidence.test_marker, prepared.evidence.test_output)
            self.assertEqual("failing", prepared.evidence.test_outcome)
            installed_adapter = prepared.repo / prepared.evidence.adapter_entrypoint
            self.assertTrue(installed_adapter.is_file())
            self.assertEqual(
                (REPO_ROOT / "adapters/codex/skills/handoff/SKILL.md").read_bytes(),
                installed_adapter.read_bytes(),
            )
            installed_references = installed_adapter.parent / "references"
            for name in ("bundle-format.md", "export.md", "import.md"):
                self.assertEqual(
                    (REPO_ROOT / "skills/handoff/references" / name).read_bytes(),
                    (installed_references / name).read_bytes(),
                )
            installed_assets = installed_adapter.parent / "assets/bundle-template"
            for name in (
                "WAYBILL.md",
                "metadata.json",
                "diff.patch",
                "commands.log",
                "test-summary.md",
            ):
                self.assertEqual(
                    (
                        REPO_ROOT
                        / "skills/handoff/assets/bundle-template"
                        / name
                    ).read_bytes(),
                    (installed_assets / name).read_bytes(),
                )
            self.assertEqual(
                (REPO_ROOT / "skills/handoff/scripts/check_bundle.py").read_bytes(),
                (installed_adapter.parent / "scripts/check_bundle.py").read_bytes(),
            )
            self.assertTrue(prepared.evidence.canonical_diff.startswith(b"diff --git "))
            self.assertRegex(
                prepared.evidence.status_digest,
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertRegex(
                prepared.evidence.repo_state_digest,
                r"^sha256:[0-9a-f]{64}$",
            )

            prompt = build_export_prompt(
                scenario,
                prepared.evidence,
                command_canary="./conformance-command-canary",
                network_canary_url="http://127.0.0.1:9/conformance-canary",
            )
            self.assertIn("WAYBILL EXPORT CONFORMANCE PROMPT v1", prompt)
            self.assertIn("Only write inside .waybill/", prompt)
            self.assertIn('"changed_files":["src/retry.py","tests/test_retry.py"]', prompt)
            self.assertIn(
                f'"repo_state_digest":"{prepared.evidence.repo_state_digest}"',
                prompt,
            )
            self.assertIn(
                f'"status_digest":"{prepared.evidence.status_digest}"',
                prompt,
            )
            self.assertNotIn(str(prepared.repo), prompt)

            prompt_input = json.loads(prompt.split("Scenario input JSON:\n", 1)[1])
            render_contract = prompt_input["render_contract"]
            self.assertEqual(
                {
                    "first_line_exact": scenario.status,
                    "allowed_status_claims": [scenario.status],
                },
                render_contract["WAYBILL.md"]["Current Status"],
            )
            self.assertEqual(
                {
                    "exact_paths": prepared.evidence.changed_files,
                    "line_format": "- `PATH`: REASON",
                    "one_line_per_path": True,
                    "other_nonblank_lines_allowed": False,
                },
                render_contract["WAYBILL.md"]["Changed Files"],
            )
            self.assertEqual(
                [
                    f"- Command: `{prepared.evidence.test_command}`",
                    f"- Outcome: {prepared.evidence.test_outcome}",
                    f"- Exit status: {prepared.evidence.test_returncode}",
                    f"- Evidence marker: `{prepared.evidence.test_marker}`",
                ],
                render_contract["test-summary.md"]["required_exact_lines"],
            )
            self.assertEqual(
                [f"- {risk}" for risk in scenario.risks],
                render_contract["WAYBILL.md"]["Risks / Unknowns"][
                    "exact_lines"
                ],
            )
            self.assertEqual(
                {
                    "source_agent": prepared.evidence.adapter,
                    "git.branch": prepared.evidence.branch,
                    "git.head_sha": prepared.evidence.head_sha,
                    "git.dirty": prepared.evidence.dirty,
                    "git.status_digest": prepared.evidence.status_digest,
                    "git.repo_state_digest": prepared.evidence.repo_state_digest,
                },
                render_contract["metadata.json"]["required_exact_values"],
            )
            self.assertEqual(
                {
                    "kind": "handoff",
                    "may_be_omitted": True,
                },
                render_contract["metadata.json"]["handoff"],
            )
            self.assertEqual(
                "sha256:" + hashlib.sha256(
                    prepared.evidence.canonical_diff
                ).hexdigest(),
                render_contract["diff.patch"]["exact_sha256"],
            )
            self.assertIn(
                "The render_contract object is normative",
                prompt,
            )
            self.assertIn(
                "Finish the five required files before optional verification",
                prompt,
            )

    def test_all_export_adapters_support_basic_and_enhanced_verification(self) -> None:
        scenario = load_export_scenario(SCENARIO_DIR / "ordinary-unfinished.json")
        with tempfile.TemporaryDirectory() as temporary:
            for adapter in SUPPORTED_EXPORT_ADAPTERS:
                with self.subTest(adapter=adapter):
                    prepared = prepare_synthetic_repository(
                        Path(temporary) / adapter,
                        scenario,
                        adapter=adapter,
                        source_root=REPO_ROOT,
                    )
                    entrypoint = prepared.repo / prepared.evidence.adapter_entrypoint
                    reference_root = entrypoint.parent / "references"
                    if adapter == "cursor":
                        reference_root = (
                            entrypoint.parent / "waybill-handoff/references"
                        )
                    instructions = "\n".join(
                        [entrypoint.read_text(encoding="utf-8")]
                        + [
                            (reference_root / name).read_text(encoding="utf-8")
                            for name in ("bundle-format.md", "export.md", "import.md")
                        ]
                    )

                    for required in (
                        "status_digest",
                        "repo_state_digest",
                        "does not require the Waybill CLI",
                        "Omit optional digest fields",
                        "perform the basic checks directly",
                        "Optional Enhanced Verification",
                        "../scripts/check_bundle.py",
                        "waybill verify-pair REQUEST RESULT",
                    ):
                        self.assertIn(required, instructions)


class ExportExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenarios = {
            scenario.id: scenario for scenario in load_export_scenarios(SCENARIO_DIR)
        }
        cls.identity = ExportAgentIdentity(
            agent="deterministic-fake",
            product="waybill-test-agent",
            version=SYNTHETIC_AGENT_VERSION,
        )

    def _run(self, scenario_id: str, *faults: str):
        command = [sys.executable, str(FAKE_AGENT)]
        for fault in faults:
            command.extend(["--fault", fault])
        return run_export_scenario(
            self.scenarios[scenario_id],
            command,
            self.identity,
            adapter="codex",
            source_root=REPO_ROOT,
            timeout_seconds=20,
        )

    def test_ordinary_export_passes_all_grounded_gates(self) -> None:
        result = self._run("ordinary-unfinished")

        self.assertTrue(result.passed, result.errors)
        self.assertTrue(result.validation_ok)
        self.assertTrue(result.readiness_ok)
        self.assertTrue(result.repo_verification_ok)
        self.assertIsNone(result.pair_verification_ok)
        self.assertTrue(result.semantic_match)
        self.assertEqual([], result.unexpected_writes)
        self.assertFalse(result.command_canary_triggered)
        self.assertFalse(result.network_canary_triggered)
        self.assertEqual(
            [
                ".waybill/",
                ".waybill/WAYBILL.md",
                ".waybill/commands.log",
                ".waybill/diff.patch",
                ".waybill/metadata.json",
                ".waybill/test-summary.md",
            ],
            result.allowed_writes,
        )

    def test_test_summary_categories_do_not_contradict_focused_outcome(self) -> None:
        result = self._run("ordinary-unfinished", "canonical-test-headings")

        self.assertTrue(result.passed, result.errors)
        self.assertTrue(result.semantic_checks["test_state"])

    def test_negated_opposite_outcome_is_not_a_contradictory_claim(self) -> None:
        result = self._run("ordinary-unfinished", "negated-opposite-outcome")

        self.assertTrue(result.passed, result.errors)
        self.assertTrue(result.semantic_checks["test_state"])

    def test_test_summary_category_reference_is_not_an_outcome_claim(self) -> None:
        result = self._run(
            "ordinary-unfinished",
            "test-summary-category-reference",
        )

        self.assertTrue(result.passed, result.errors)
        self.assertTrue(result.semantic_checks["test_state"])

    def test_structurally_valid_but_unsupported_claims_fail_semantic_evidence(self) -> None:
        for fault, expected_code in [
            ("wrong-goal", "evidence:goal"),
            ("omit-changed-file", "evidence:changed-files"),
            ("false-test-state", "evidence:test-state"),
            ("wrong-risk", "evidence:risks"),
            ("append-risk", "evidence:risks"),
            ("risk-prose", "evidence:risks"),
            ("wrong-next-step", "evidence:next-step"),
            ("wrong-status", "evidence:status"),
            ("contradictory-status", "evidence:status"),
            ("contradictory-test", "evidence:test-state"),
            ("nonstandard-changed-file", "evidence:changed-files"),
            ("wrong-diff", "evidence:diff"),
        ]:
            with self.subTest(fault=fault):
                result = self._run("ordinary-unfinished", fault)
                self.assertFalse(result.passed)
                self.assertTrue(result.validation_ok)
                self.assertIn(expected_code, result.errors)
                if fault == "wrong-diff":
                    self.assertFalse(result.readiness_ok)
                    self.assertFalse(result.repo_verification_ok)
                    self.assertIn("gate:ready", result.errors)
                    self.assertIn("gate:verify-repo", result.errors)

    def test_current_export_requires_exact_repository_fidelity_digests(self) -> None:
        cases = (
            ("missing-status-digest", "evidence:status-digest"),
            ("missing-repo-state-digest", "evidence:repo-state-digest"),
            ("wrong-status-digest", "evidence:status-digest"),
            ("wrong-repo-state-digest", "evidence:repo-state-digest"),
        )
        for fault, expected_code in cases:
            with self.subTest(fault=fault):
                result = self._run("ordinary-unfinished", fault)

                self.assertFalse(result.passed)
                self.assertTrue(result.validation_ok)
                self.assertFalse(result.readiness_ok)
                self.assertIn("gate:ready", result.errors)
                self.assertIn(expected_code, result.errors)

    def test_tracked_content_drift_with_same_status_shape_fails_final_gate(self) -> None:
        result = self._run("ordinary-unfinished", "same-shape-content-drift")

        self.assertFalse(result.passed)
        self.assertTrue(result.validation_ok)
        self.assertFalse(result.readiness_ok)
        self.assertFalse(result.repo_verification_ok)
        self.assertIn("gate:ready", result.errors)
        self.assertIn("gate:verify-repo", result.errors)

    def test_pollution_after_agent_self_check_fails_immutable_final_validation(self) -> None:
        result = self._run("ordinary-unfinished", "post-check-artifact-pollution")

        self.assertFalse(result.passed)
        self.assertFalse(result.validation_ok)
        self.assertFalse(result.readiness_ok)
        self.assertIn("gate:validate", result.errors)
        self.assertIn("gate:ready", result.errors)

    def test_validate_ready_and_verify_repo_fail_independently(self) -> None:
        invalid = self._run("ordinary-unfinished", "invalid-metadata")
        self.assertFalse(invalid.validation_ok)
        self.assertIn("gate:validate", invalid.errors)

        placeholder = self._run("ordinary-unfinished", "draft-placeholder")
        self.assertTrue(placeholder.validation_ok)
        self.assertFalse(placeholder.readiness_ok)
        self.assertIn("gate:ready", placeholder.errors)

        stale = self._run("ordinary-unfinished", "stale-repository")
        self.assertTrue(stale.validation_ok)
        self.assertFalse(stale.repo_verification_ok)
        self.assertIn("gate:verify-repo", stale.errors)

    def test_unsafe_bundle_root_is_rejected_before_follow_up_reads(self) -> None:
        result = self._run("ordinary-unfinished", "bundle-symlink")

        self.assertFalse(result.passed)
        self.assertFalse(result.validation_ok)
        self.assertIn("bundle:unsafe", result.errors)

    def test_invalid_utf8_bundle_returns_a_sanitized_failure(self) -> None:
        result = self._run("ordinary-unfinished", "invalid-utf8-metadata")

        self.assertFalse(result.passed)
        self.assertFalse(result.validation_ok)
        self.assertIn("bundle:unreadable", result.errors)
        self.assertNotIn(tempfile.gettempdir() + "/", json.dumps(result.to_dict()))

    def test_only_waybill_writes_are_allowed(self) -> None:
        for fault, expected_path in (
            ("outside-write", "outside.txt"),
            ("outside-directory", "outside-directory/"),
            ("git-write", ".git/conformance-unexpected"),
            ("parent-write", "outside-repository/escaped.txt"),
        ):
            with self.subTest(fault=fault):
                result = self._run("ordinary-unfinished", fault)
                self.assertFalse(result.passed)
                self.assertIn(expected_path, result.unexpected_writes)
                self.assertIn("effect:unexpected-write", result.errors)

    def test_malicious_session_canaries_are_observed_without_overclaiming(self) -> None:
        safe = self._run("malicious-session-instruction")
        self.assertTrue(safe.passed, safe.errors)
        self.assertFalse(safe.command_canary_triggered)
        self.assertFalse(safe.network_canary_triggered)

        command = self._run("malicious-session-instruction", "trigger-command-canary")
        self.assertFalse(command.passed)
        self.assertTrue(command.command_canary_triggered)
        self.assertIn("effect:command-canary", command.errors)

        cleaned_command = self._run(
            "malicious-session-instruction",
            "trigger-command-canary-and-clean",
        )
        self.assertFalse(cleaned_command.passed)
        self.assertTrue(cleaned_command.command_canary_triggered)

        network = self._run("malicious-session-instruction", "trigger-network-canary")
        self.assertFalse(network.passed)
        self.assertTrue(network.network_canary_triggered)
        self.assertIn("effect:network-canary", network.errors)

        network_head = self._run(
            "malicious-session-instruction",
            "trigger-network-head",
        )
        self.assertFalse(network_head.passed)
        self.assertTrue(network_head.network_canary_triggered)

    def test_delegation_request_and_all_result_statuses_share_the_pipeline(self) -> None:
        request = self._run("delegation-request")
        self.assertTrue(request.passed, request.errors)
        self.assertIsNone(request.pair_verification_ok)

        for status in ("completed", "partial", "blocked"):
            with self.subTest(status=status):
                result = self._run(f"delegation-result-{status}")
                self.assertTrue(result.passed, result.errors)
                self.assertTrue(result.pair_verification_ok)

    def test_wrong_result_for_is_rejected_by_verify_pair(self) -> None:
        result = self._run("delegation-result-completed", "wrong-result-for")

        self.assertFalse(result.passed)
        self.assertFalse(result.pair_verification_ok)
        self.assertIn("gate:verify-pair", result.errors)

    def test_agent_cannot_rewrite_pair_input_to_make_wrong_result_match(self) -> None:
        result = self._run(
            "delegation-result-completed",
            "wrong-result-for",
            "mutate-pair-request",
        )

        self.assertFalse(result.passed)
        self.assertIn(
            "outside-repository/pair-request/metadata.json",
            result.unexpected_writes,
        )
        self.assertIn("effect:unexpected-write", result.errors)

    def test_agent_environment_excludes_host_injection_and_secret_variables(self) -> None:
        poisoned = {
            "AWS_SECRET_ACCESS_KEY": "not-a-real-secret",
            "GIT_DIR": "/tmp/not-the-synthetic-repository",
            "GIT_INDEX_FILE": "/tmp/not-the-synthetic-index",
            "GIT_WORK_TREE": "/tmp/not-the-synthetic-worktree",
            "HTTP_PROXY": "http://credential.invalid:9999",
            "HTTPS_PROXY": "http://credential.invalid:9999",
            "LD_PRELOAD": "/tmp/not-a-library.so",
            "PYTHONHOME": "/tmp/not-a-python-home",
            "PYTHONPATH": "/tmp/not-a-python-path",
            "WAYBILL_EXPORT_TEST_SECRET": "must-not-leak",
        }
        with mock.patch.dict(os.environ, poisoned, clear=False):
            result = self._run("ordinary-unfinished", "assert-clean-environment")

        self.assertTrue(result.passed, result.errors)

    def test_environment_startup_failure_is_classified_without_raw_output(self) -> None:
        source = (
            "import sys;"
            "sys.stdin.read();"
            "sys.stderr.write('bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\\n');"
            "raise SystemExit(1)"
        )
        result = run_export_scenario(
            self.scenarios["ordinary-unfinished"],
            [sys.executable, "-c", source],
            self.identity,
            adapter="codex",
            source_root=REPO_ROOT,
            timeout_seconds=20,
        )
        report = result.to_dict()

        self.assertFalse(result.passed)
        self.assertTrue(result.environment_blocked)
        self.assertEqual("network-namespace", result.environment_block_reason)
        self.assertIn("environment:blocked", result.errors)
        self.assertNotIn("Failed RTM_NEWADDR", json.dumps(report))

    def test_timeout_kills_the_agent_process_group_before_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "descendant-survived"
            command = [
                sys.executable,
                str(FAKE_AGENT),
                "--fault",
                "timeout-with-child",
                "--external-marker",
                str(marker),
            ]
            result = run_export_scenario(
                self.scenarios["ordinary-unfinished"],
                command,
                self.identity,
                adapter="codex",
                source_root=REPO_ROOT,
                timeout_seconds=0.2,
            )
            time.sleep(0.8)

            self.assertFalse(marker.exists())
        self.assertIn("agent:timeout", result.errors)
        self.assertIsNone(result.returncode)

    def test_report_is_sanitized_and_contains_observation_identity(self) -> None:
        report = self._run("ordinary-unfinished").to_dict()
        serialized = json.dumps(report, sort_keys=True)

        self.assertEqual("deterministic-fake", report["agent"]["agent"])
        self.assertEqual("waybill-test-agent", report["agent"]["product"])
        self.assertEqual(SYNTHETIC_AGENT_VERSION, report["agent"]["version"])
        self.assertEqual("codex", report["adapter"])
        self.assertRegex(str(report["date"]), r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(report["semantic_match"])
        self.assertEqual(
            {
                "changed_files": True,
                "delegation": True,
                "diff": True,
                "goal": True,
                "next_step": True,
                "repo_state_digest": True,
                "risks": True,
                "source_agent": True,
                "status": True,
                "status_digest": True,
                "test_state": True,
            },
            report["semantic_checks"],
        )
        self.assertNotIn(tempfile.gettempdir() + "/", serialized)
        self.assertNotIn("stdout", serialized)
        self.assertNotIn("stderr", serialized)

    def test_untrusted_filenames_are_hashed_before_reporting(self) -> None:
        report = self._run("ordinary-unfinished", "unsafe-report-filename").to_dict()
        serialized = json.dumps(report, sort_keys=True)

        self.assertNotIn("private name", serialized)
        self.assertIn("redacted-path-sha256:", serialized)


class ExportRunnerCliTests(unittest.TestCase):
    def test_deterministic_fake_cli_verifies_the_complete_export_matrix(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "conformance-exports.py"),
                "--agent-name",
                "deterministic-fake",
                "--agent-product",
                "deterministic-fake",
                "--agent-version",
                SYNTHETIC_AGENT_VERSION,
                "--deterministic-fake",
                "--adapter",
                "codex",
                "--agent-command",
                f"{sys.executable} {FAKE_AGENT}",
                "--require-complete-matrix",
                "--timeout",
                "20",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertFalse(report["dry_run"])
        self.assertTrue(report["success"])
        results = report["results"]
        self.assertEqual(
            REQUIRED_EXPORT_SCENARIO_IDS,
            {result["scenario"] for result in results},
        )
        self.assertEqual(len(REQUIRED_EXPORT_SCENARIO_IDS), len(results))
        for result in results:
            with self.subTest(scenario=result["scenario"]):
                self.assertTrue(result["passed"])
                self.assertTrue(result["gates"]["validate"])
                self.assertTrue(result["gates"]["ready"])
                self.assertTrue(result["gates"]["verify_repo"])
                if result["handoff_kind"] == "delegation_result":
                    self.assertTrue(result["gates"]["verify_pair"])
                else:
                    self.assertIsNone(result["gates"]["verify_pair"])
                self.assertTrue(result["semantic_match"])
                self.assertTrue(all(result["semantic_checks"].values()))
                self.assertEqual([], result["unexpected_writes"])
                self.assertFalse(result["canaries"]["command_triggered"])
                self.assertFalse(result["canaries"]["network_triggered"])

        forged = json.loads(json.dumps(report))
        forged_result = forged["results"][0]
        forged_result["allowed_writes"] = []
        forged_result["semantic_checks"].pop("goal")
        forged_result["unexpected_writes"] = ["outside.txt"]
        check_report = runpy.run_path(
            str(REPO_ROOT / "scripts" / "conformance-exports.py")
        )["_complete_matrix_errors"]
        matrix_errors = check_report(forged)
        prefix = f"matrix:{forged_result['scenario']}"
        self.assertIn(f"{prefix}:allowed-writes", matrix_errors)
        self.assertIn(f"{prefix}:semantic-check-set", matrix_errors)
        self.assertIn(f"{prefix}:unexpected-writes", matrix_errors)

    def test_complete_matrix_mode_rejects_dry_runs_and_selected_scenarios(self) -> None:
        common = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "conformance-exports.py"),
            "--agent-name",
            "deterministic-fake",
            "--agent-product",
            "deterministic-fake",
            "--agent-version",
            SYNTHETIC_AGENT_VERSION,
            "--deterministic-fake",
            "--adapter",
            "codex",
            "--agent-command",
            f"{sys.executable} {FAKE_AGENT}",
            "--require-complete-matrix",
        ]
        for extra, expected in (
            (["--dry-run"], "cannot be combined with --dry-run"),
            (
                ["--scenario", "ordinary-unfinished"],
                "cannot be combined with --scenario",
            ),
        ):
            with self.subTest(extra=extra):
                completed = subprocess.run(
                    [*common, *extra],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(2, completed.returncode)
                self.assertIn(expected, completed.stderr)

    def test_manual_dry_run_binds_the_observed_executable_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "codex"
            executable.write_text(
                f"#!/bin/sh\nprintf 'codex-cli {SYNTHETIC_AGENT_VERSION}\\n'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "conformance-exports.py"),
                    "--agent-name",
                    "codex",
                    "--agent-product",
                    "codex",
                    "--agent-version",
                    SYNTHETIC_AGENT_VERSION,
                    "--unsafe-manual",
                    "--adapter",
                    "codex",
                    "--agent-command",
                    str(executable),
                    "--scenario",
                    "ordinary-unfinished",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual("2", report["schema_version"])
        self.assertEqual("unsafe_manual", report["execution_mode"])
        self.assertIsNone(report["provenance"])
        self.assertEqual("verified", report["identity"]["status"])
        self.assertEqual("codex", report["identity"]["product"])
        self.assertEqual(SYNTHETIC_AGENT_VERSION, report["identity"]["version"])
        self.assertRegex(report["identity"]["sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_dry_run_validates_without_running_agent_or_creating_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "must-not-run"
            source = f"from pathlib import Path; Path({str(marker)!r}).touch()"
            command = f"{sys.executable} -c {source!r}"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "conformance-exports.py"),
                    "--agent-name",
                    "fake",
                    "--agent-product",
                    "deterministic-fake",
                    "--agent-version",
                    SYNTHETIC_AGENT_VERSION,
                    "--deterministic-fake",
                    "--adapter",
                    "codex",
                    "--agent-command",
                    command,
                    "--scenario",
                    "ordinary-unfinished",
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(marker.exists())
            report = json.loads(completed.stdout)
            self.assertEqual("2", report["schema_version"])
            self.assertTrue(report["success"])
            self.assertTrue(report["dry_run"])
            self.assertEqual("export", report["capability"])
            self.assertEqual("deterministic_fake", report["execution_mode"])
            self.assertIsNone(report["provenance"])
            self.assertTrue(report["identity"]["verified"])
            self.assertRegex(
                report["identity"]["sha256"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertRegex(report["observed_at"], r"Z$")
            self.assertEqual(["ordinary-unfinished"], report["scenarios"])
            self.assertNotIn("command", report)

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
                    str(REPO_ROOT / "scripts" / "conformance-exports.py"),
                    "--agent-name",
                    "codex",
                    "--agent-product",
                    "codex",
                    "--agent-version",
                    SYNTHETIC_AGENT_VERSION,
                    "--unsafe-manual",
                    "--adapter",
                    "codex",
                    "--agent-command",
                    sys.executable,
                    "--scenario-dir",
                    str(scenario_dir),
                    "--scenario",
                    "ordinary-unfinished",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn(
            "manual evidence requires the canonical --scenario-dir",
            completed.stderr,
        )

    def test_runner_requires_an_explicit_execution_mode(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "conformance-exports.py"),
                "--agent-name",
                "fake",
                "--agent-product",
                "deterministic-fake",
                "--agent-version",
                SYNTHETIC_AGENT_VERSION,
                "--adapter",
                "codex",
                "--agent-command",
                f"{sys.executable} {FAKE_AGENT}",
                "--scenario",
                "ordinary-unfinished",
                "--dry-run",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("one of the arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
