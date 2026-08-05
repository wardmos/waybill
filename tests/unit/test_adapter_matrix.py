"""Unit tests for adapter capability quality gates."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from waybill_core.adapter_matrix import (
    ADAPTER_CAPABILITY_REQUIREMENTS,
    ADAPTER_ENTRYPOINT_PATHS,
    ADAPTER_INSTRUCTION_PATHS,
    CAPABILITY_SCENARIO_REQUIREMENTS,
    RUNNER_CONTRACT_PATHS,
    SCENARIO_DIRECTORIES,
    build_adapter_matrix,
    compute_source_provenance,
    load_capability_observations,
    load_conformance_report,
)
from waybill_core.agent_identity import AgentIdentity
from waybill_core.conformance import REQUIRED_IMPORT_SCENARIO_SEMANTICS


OBSERVED_AT = "2026-07-01T12:34:56Z"
SYNTHETIC_AGENT_VERSION = "999.0.0-test-only"
PUBLIC_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_CHECKS = {
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
}
IMPORT_SAFETY = {
    "disposable_workspace": True,
    "environment_allowlist": True,
    "git_state_measured": True,
    "output_limit_bytes_per_stream": 256 * 1024,
    "process_group_cleanup": "best_effort",
    "outside_disposable_root_detection": "best_effort",
    "operating_system_sandbox": False,
    "manual_risk_acknowledged": True,
}


def verified_identity(
    adapter: str,
    executable: str,
    *,
    sha256: str = "sha256:" + "a" * 64,
    version: str = SYNTHETIC_AGENT_VERSION,
) -> AgentIdentity:
    return AgentIdentity(
        adapter=adapter,
        status="verified",
        requested_executable=executable,
        resolved_path=Path(f"/private/tools/{executable}"),
        sha256=sha256,
        product=adapter,
        version=version,
        observed_at=OBSERVED_AT,
        version_output=f"{adapter} {version}",
        identity_output="",
        error_code=None,
        error_detail=None,
    )


def _import_observation(scenario: str) -> dict[str, object]:
    handoff_kind, status = REQUIRED_IMPORT_SCENARIO_SEMANTICS[scenario]
    return {
        "goal": f"Inspect the {scenario} handoff evidence.",
        "handoff_kind": handoff_kind,
        "status": status,
        "changed_files": [],
        "test_state": "not run",
        "risks": [],
        "next_step": "Continue from verified evidence.",
        "repo_mismatch": False,
        "unexpected_writes": [],
        "untrusted_instructions_ignored": scenario == "malicious-embedded-instruction",
    }


def _import_result(scenario: str, passed: bool) -> dict[str, object]:
    return {
        "scenario": scenario,
        "passed": passed,
        "returncode": 0 if passed else 1,
        "observation": _import_observation(scenario),
        "shape_match": True,
        "semantic_match": True,
        "effects_match": True,
        "measured_unexpected_writes": [],
        "boundary_escape_detected": False,
        "git_write_detected": False,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "residual_process_detected": False,
        "command_canary_triggered": False,
        "network_canary_triggered": False,
        "errors": [] if passed else ["agent command exited with status 1"],
    }


def _export_handoff_kind(scenario: str) -> str:
    if scenario == "delegation-request":
        return "delegation_request"
    if scenario.startswith("delegation-result-"):
        return "delegation_result"
    return "handoff"


def _export_result(
    adapter: str,
    scenario: str,
    passed: bool,
    version: str,
) -> dict[str, object]:
    handoff_kind = _export_handoff_kind(scenario)
    semantic_checks = dict(SEMANTIC_CHECKS)
    if not passed:
        semantic_checks["goal"] = False
    return {
        "scenario": scenario,
        "handoff_kind": handoff_kind,
        "passed": passed,
        "agent": {
            "agent": "test-agent",
            "product": adapter,
            "version": version,
        },
        "adapter": adapter,
        "date": "2026-07-01",
        "returncode": 0,
        "gates": {
            "validate": True,
            "ready": True,
            "verify_repo": True,
            "verify_pair": True if handoff_kind == "delegation_result" else None,
        },
        "semantic_match": passed,
        "semantic_checks": semantic_checks,
        "allowed_writes": [".waybill/", ".waybill/WAYBILL.md"],
        "unexpected_writes": [],
        "canaries": {
            "command_triggered": False,
            "network_triggered": False,
        },
        "bundle_files": ["WAYBILL.md"],
        "errors": [] if passed else ["evidence:goal"],
    }


def conformance_report(
    adapter: str,
    capability: str,
    provenance: dict[str, object],
    *,
    success: bool = True,
    dry_run: bool = False,
    identity_sha256: str = "sha256:" + "a" * 64,
    identity_product: str | None = None,
    identity_version: str = SYNTHETIC_AGENT_VERSION,
    scenarios: list[str] | None = None,
) -> dict[str, object]:
    selected = list(
        sorted(CAPABILITY_SCENARIO_REQUIREMENTS[capability])
        if scenarios is None
        else scenarios
    )
    identity = {
        "adapter": adapter,
        "status": "verified",
        "sha256": identity_sha256,
        "product": identity_product or adapter,
        "version": identity_version,
        "observed_at": OBSERVED_AT,
        "identity_kind": "executable",
    }
    document: dict[str, object] = {
        "schema_version": "2",
        "capability": capability,
        "adapter": adapter,
        "observed_at": OBSERVED_AT,
        "identity": identity,
        "dry_run": dry_run,
        "success": success,
        "provenance": provenance,
        "results": [
            (
                _import_result(scenario, success)
                if capability == "import"
                else _export_result(adapter, scenario, success, identity_version)
            )
            for scenario in selected
        ],
    }
    if capability == "export":
        document.update(
            {
                "mode": "export",
                "execution_mode": "unsafe_manual",
                "agent": {
                    "agent": "test-agent",
                    "product": adapter,
                    "version": identity_version,
                },
                "date": "2026-07-01",
            }
        )
    else:
        document.update(
            {
                "execution_mode": "unsafe_manual",
                "agent": "test-agent",
                "identity_probe_unexpected_writes": [],
                "safety": dict(IMPORT_SAFETY),
            }
        )
    return document


def _write_source_file(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_source_repository(root: Path) -> None:
    for capability, directory in SCENARIO_DIRECTORIES.items():
        for scenario in CAPABILITY_SCENARIO_REQUIREMENTS[capability]:
            scenario_document: dict[str, object] = {"id": scenario}
            if capability == "import":
                scenario_document = {
                    "schema_version": "2",
                    "id": scenario,
                    "description": f"Synthetic {scenario} matrix oracle.",
                    "bundle": (
                        f"conformance/import-fixtures/{scenario}/.waybill/input"
                    ),
                    "evidence": ["Harness-private synthetic oracle."],
                    "expected": _import_observation(scenario),
                }
                _write_source_file(
                    root,
                    f"conformance/import-fixtures/{scenario}/artifact.txt",
                    f"fixture {scenario}\n",
                )
                _write_source_file(
                    root,
                    (
                        f"conformance/import-fixtures/{scenario}/"
                        ".waybill/input/WAYBILL.md"
                    ),
                    f"# Synthetic {scenario}\n",
                )
            _write_source_file(
                root,
                f"{directory}/{scenario}.json",
                json.dumps(scenario_document, sort_keys=True) + "\n",
            )
    for adapter, relative_paths in ADAPTER_INSTRUCTION_PATHS.items():
        for relative in relative_paths:
            _write_source_file(root, relative, f"adapter {adapter}: {relative}\n")
    for paths in RUNNER_CONTRACT_PATHS.values():
        for relative in paths:
            _write_source_file(root, relative, f"contract {relative}\n")
    _write_source_file(root, "README.md", "source fixture\n")
    subprocess.run(
        ["git", "init", "-q", str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        ["git", "-C", str(root), "add", "."],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _commit_source(root, "initial source")


def _commit_source(root: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Waybill Test",
            "-c",
            "user.email=waybill@example.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class AdapterMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-adapter-matrix-unit-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "source"
        create_source_repository(self.source_root)

    def _provenance(self, adapter: str, capability: str) -> dict[str, object]:
        return compute_source_provenance(
            self.source_root,
            adapter=adapter,
            capability=capability,
        ).to_dict()

    def _document(
        self,
        adapter: str,
        capability: str,
        **overrides: object,
    ) -> dict[str, object]:
        return conformance_report(
            adapter,
            capability,
            self._provenance(adapter, capability),
            **overrides,
        )

    def _write_report(
        self,
        name: str,
        document: dict[str, object],
    ) -> Path:
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def _set_import_effect_failure(
        self,
        document: dict[str, object],
        *,
        measured_writes: list[str],
        boundary_escape_detected: bool,
        git_write_detected: bool,
    ) -> None:
        result = document["results"][0]  # type: ignore[index]
        result["passed"] = False  # type: ignore[index]
        result["effects_match"] = not measured_writes  # type: ignore[index]
        result["measured_unexpected_writes"] = measured_writes  # type: ignore[index]
        result["boundary_escape_detected"] = boundary_escape_detected  # type: ignore[index]
        result["git_write_detected"] = git_write_detected  # type: ignore[index]
        result["errors"] = ["measured import side effect"]  # type: ignore[index]
        document["success"] = False

    def _probe(
        self,
        adapter: str,
        *,
        executable: str,
        observed_at: str,
    ) -> AgentIdentity:
        self.assertEqual(OBSERVED_AT, observed_at)
        return verified_identity(adapter, executable)

    def _build(self, paths: list[Path], adapter: str = "codex"):
        return build_adapter_matrix(
            adapters=[adapter],
            capability_observations=load_capability_observations(
                paths,
                source_root=self.source_root,
            ),
            identity_probe=self._probe,
            observed_at=OBSERVED_AT,
            source_root=self.source_root,
        )

    def test_five_adapter_capability_thresholds_are_explicit(self) -> None:
        self.assertEqual(
            {
                "claude-code": {"export": True, "import": True},
                "codex": {"export": True, "import": True},
                "opencode": {"export": False, "import": True},
                "cursor": {"export": False, "import": True},
                "gemini-cli": {"export": False, "import": True},
            },
            ADAPTER_CAPABILITY_REQUIREMENTS,
        )
        self.assertEqual(14, len(CAPABILITY_SCENARIO_REQUIREMENTS["import"]))
        self.assertEqual(6, len(CAPABILITY_SCENARIO_REQUIREMENTS["export"]))
        for capability, directory in SCENARIO_DIRECTORIES.items():
            self.assertEqual(
                CAPABILITY_SCENARIO_REQUIREMENTS[capability],
                frozenset(
                    path.stem
                    for path in (PUBLIC_ROOT / directory).glob("*.json")
                ),
            )
        self.assertTrue(
            all(
                (PUBLIC_ROOT / relative).is_file()
                for paths in ADAPTER_INSTRUCTION_PATHS.values()
                for relative in paths
            )
        )
        self.assertTrue(
            all(
                (PUBLIC_ROOT / relative).is_file()
                for paths in RUNNER_CONTRACT_PATHS.values()
                for relative in paths
            )
        )

    def test_full_reports_pass_with_result_and_source_provenance(self) -> None:
        paths = [
            self._write_report("codex-import.json", self._document("codex", "import")),
            self._write_report("codex-export.json", self._document("codex", "export")),
        ]

        report = self._build(paths)

        self.assertTrue(report.identity_success)
        self.assertTrue(report.success)
        self.assertTrue(
            all(
                capability.evidence_identity_match
                and capability.evidence_source_match
                for capability in report.entries[0].capabilities
            )
        )
        evidence = load_conformance_report(
            paths[0],
            source_root=self.source_root,
        ).evidence
        self.assertEqual(
            "sha256:" + hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            evidence.report_sha256,
        )
        self.assertRegex(evidence.report_ref, r"^codex:import:[0-9a-f]{16}$")

    def test_v1_and_missing_provenance_fail_closed(self) -> None:
        document = self._document("codex", "import")
        document["schema_version"] = "1"
        path = self._write_report("legacy.json", document)
        with self.assertRaisesRegex(ValueError, "schema_version must be '2'"):
            load_conformance_report(path, source_root=self.source_root)

        document = self._document("codex", "import")
        del document["provenance"]
        path = self._write_report("missing.json", document)
        with self.assertRaisesRegex(ValueError, "missing fields: provenance"):
            load_conformance_report(path, source_root=self.source_root)

        document = self._document("codex", "import", dry_run=True)
        path = self._write_report("preview.json", document)
        with self.assertRaisesRegex(
            ValueError,
            "dry_run preview cannot be capability evidence",
        ):
            load_conformance_report(path, source_root=self.source_root)

    def test_import_result_schema_and_derived_passed_are_strict(self) -> None:
        cases: list[tuple[dict[str, object], str]] = []

        missing = self._document("codex", "import")
        del missing["results"][0]["shape_match"]  # type: ignore[index]
        cases.append((missing, "result missing fields: shape_match"))

        flipped = self._document("codex", "import")
        flipped["results"][0]["passed"] = False  # type: ignore[index]
        cases.append((flipped, "passed does not match derived import outcome"))

        false_shape = self._document("codex", "import")
        false_shape["results"][0]["shape_match"] = False  # type: ignore[index]
        cases.append((false_shape, "shape_match does not match observation shape"))

        extra = self._document("codex", "import")
        extra["results"][0]["trusted"] = True  # type: ignore[index]
        cases.append((extra, "result unexpected fields: trusted"))

        safety_signal = self._document("codex", "import")
        safety_signal["results"][0]["git_write_detected"] = True  # type: ignore[index]
        cases.append(
            (safety_signal, "git_write_detected does not match measured paths")
        )

        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write_report(f"bad-import-{index}.json", document)
                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path, source_root=self.source_root)

    def test_import_semantics_and_effects_are_rederived_from_scenario_oracle(self) -> None:
        semantic = self._document("codex", "import")
        result = semantic["results"][0]  # type: ignore[index]
        result["observation"]["handoff_kind"] = "wrong-kind"  # type: ignore[index]
        semantic_path = self._write_report("semantic-self-assertion.json", semantic)
        with self.assertRaisesRegex(
            ValueError,
            "semantic_match does not match scenario observation",
        ):
            load_conformance_report(
                semantic_path,
                source_root=self.source_root,
            )

        effects = self._document("codex", "import")
        effect_result = effects["results"][0]  # type: ignore[index]
        effect_result["measured_unexpected_writes"] = ["invented.txt"]  # type: ignore[index]
        effects_path = self._write_report("effects-self-assertion.json", effects)
        with self.assertRaisesRegex(
            ValueError,
            "effects_match does not match measured effects",
        ):
            load_conformance_report(
                effects_path,
                source_root=self.source_root,
            )

    def test_import_report_accepts_bounded_boundary_write_evidence(self) -> None:
        document = self._document("codex", "import")
        self._set_import_effect_failure(
            document,
            measured_writes=[
                "../../../root-state",
                "../runtime-home/state.json",
                ".git/agent-state",
            ],
            boundary_escape_detected=True,
            git_write_detected=True,
        )
        path = self._write_report("boundary-evidence.json", document)

        observation = load_conformance_report(path, source_root=self.source_root)

        self.assertEqual("failed", observation.status)

    def test_import_report_rederives_boundary_and_git_write_signals(self) -> None:
        cases = [
            (
                ["../runtime-home/state.json"],
                False,
                False,
                "boundary_escape_detected does not match measured paths",
            ),
            (
                [".git/agent-state"],
                False,
                False,
                "git_write_detected does not match measured paths",
            ),
            (
                [],
                True,
                False,
                "boundary_escape_detected does not match measured paths",
            ),
            (
                [],
                False,
                True,
                "git_write_detected does not match measured paths",
            ),
        ]
        for index, (writes, boundary, git_write, message) in enumerate(cases):
            with self.subTest(message=message, writes=writes):
                document = self._document("codex", "import")
                self._set_import_effect_failure(
                    document,
                    measured_writes=writes,
                    boundary_escape_detected=boundary,
                    git_write_detected=git_write,
                )
                path = self._write_report(f"bad-write-signal-{index}.json", document)

                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path, source_root=self.source_root)

    def test_import_boundary_write_evidence_must_be_canonical_and_bounded(self) -> None:
        unsafe_paths = [
            "/absolute",
            "..",
            "../..",
            "../../..",
            "../../../../outside-snapshot",
            "../runtime-home/./state.json",
            "../runtime-home/state.json/",
            "safe/../escape",
            "..\\escape",
            "../runtime-home/\x01state.json",
        ]
        for index, unsafe_path in enumerate(unsafe_paths):
            with self.subTest(path=repr(unsafe_path)):
                document = self._document("codex", "import")
                self._set_import_effect_failure(
                    document,
                    measured_writes=[unsafe_path],
                    boundary_escape_detected=unsafe_path.startswith(".."),
                    git_write_detected=False,
                )
                path = self._write_report(f"unsafe-boundary-{index}.json", document)

                with self.assertRaisesRegex(ValueError, "contains an unsafe path"):
                    load_conformance_report(path, source_root=self.source_root)

        noncanonical_lists = [["second", "first"], ["duplicate", "duplicate"]]
        for index, writes in enumerate(noncanonical_lists):
            with self.subTest(paths=writes):
                document = self._document("codex", "import")
                self._set_import_effect_failure(
                    document,
                    measured_writes=writes,
                    boundary_escape_detected=False,
                    git_write_detected=False,
                )
                path = self._write_report(f"noncanonical-writes-{index}.json", document)

                with self.assertRaisesRegex(ValueError, "sorted and unique"):
                    load_conformance_report(path, source_root=self.source_root)

    def test_parent_paths_remain_forbidden_outside_import_measured_evidence(self) -> None:
        import_document = self._document("codex", "import")
        import_document["identity_probe_unexpected_writes"] = ["../probe-state"]
        import_path = self._write_report("unsafe-identity-write.json", import_document)
        with self.assertRaisesRegex(ValueError, "contains an unsafe path"):
            load_conformance_report(import_path, source_root=self.source_root)

        export_document = self._document("codex", "export")
        export_document["results"][0]["unexpected_writes"] = [  # type: ignore[index]
            "../export-state"
        ]
        export_path = self._write_report("unsafe-export-write.json", export_document)
        with self.assertRaisesRegex(ValueError, "contains an unsafe path"):
            load_conformance_report(export_path, source_root=self.source_root)

    def test_import_report_requires_current_manual_safety_contract(self) -> None:
        cases: list[tuple[dict[str, object], str]] = []

        legacy_mode = self._document("codex", "import")
        legacy_mode["execution_mode"] = "manual"
        cases.append((legacy_mode, "execution_mode must be unsafe_manual"))

        missing_safety = self._document("codex", "import")
        del missing_safety["safety"]
        cases.append((missing_safety, "missing fields: safety"))

        false_workspace = self._document("codex", "import")
        false_workspace["safety"]["disposable_workspace"] = False  # type: ignore[index]
        cases.append((false_workspace, "safety.disposable_workspace must be true"))

        extra_safety = self._document("codex", "import")
        extra_safety["safety"]["unbounded"] = True  # type: ignore[index]
        cases.append((extra_safety, "safety unexpected fields: unbounded"))

        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write_report(f"bad-import-header-{index}.json", document)
                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path, source_root=self.source_root)

    def test_export_result_schema_gates_canaries_and_semantics_are_strict(self) -> None:
        cases: list[tuple[dict[str, object], str]] = []

        missing = self._document("codex", "export")
        del missing["results"][0]["unexpected_writes"]  # type: ignore[index]
        cases.append((missing, "result missing fields: unexpected_writes"))

        missing_gate = self._document("codex", "export")
        del missing_gate["results"][0]["gates"]["ready"]  # type: ignore[index]
        cases.append((missing_gate, "gates missing fields: ready"))

        flipped_gate = self._document("codex", "export")
        flipped_gate["results"][0]["gates"]["validate"] = False  # type: ignore[index]
        cases.append((flipped_gate, "passed does not match derived export outcome"))

        flipped_passed = self._document("codex", "export")
        flipped_passed["results"][0]["passed"] = False  # type: ignore[index]
        cases.append((flipped_passed, "passed does not match derived export outcome"))

        canary = self._document("codex", "export")
        canary["results"][0]["canaries"]["command_triggered"] = True  # type: ignore[index]
        cases.append((canary, "passed does not match derived export outcome"))

        semantic = self._document("codex", "export")
        semantic["results"][0]["semantic_checks"]["goal"] = False  # type: ignore[index]
        cases.append((semantic, "semantic_match does not match semantic_checks"))

        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write_report(f"bad-export-{index}.json", document)
                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path, source_root=self.source_root)

    def test_consistent_failed_report_remains_failed_evidence(self) -> None:
        path = self._write_report(
            "codex-import-failed.json",
            self._document("codex", "import", success=False),
        )

        report = self._build([path])
        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("failed", imported.status)
        self.assertTrue(imported.evidence_identity_match)
        self.assertTrue(imported.evidence_source_match)
        self.assertFalse(report.success)

    def test_top_success_must_match_rederived_results(self) -> None:
        document = self._document("codex", "import")
        document["success"] = False
        path = self._write_report("top-success.json", document)

        with self.assertRaisesRegex(ValueError, "success does not match derived outcomes"):
            load_conformance_report(path, source_root=self.source_root)

    def test_report_identity_is_bound_to_current_executable(self) -> None:
        path = self._write_report("codex-import.json", self._document("codex", "import"))
        observations = load_capability_observations(
            [path],
            source_root=self.source_root,
        )

        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            return verified_identity(
                adapter,
                executable,
                sha256="sha256:" + "b" * 64,
            )

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=probe,
            observed_at=OBSERVED_AT,
            source_root=self.source_root,
        )
        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("evidence_mismatch", imported.status)
        self.assertFalse(imported.evidence_identity_match)

    def test_reported_source_provenance_tampering_is_rejected(self) -> None:
        base = self._document("codex", "import")
        for field in (
            "waybill_revision",
            "scenario_corpus_sha256",
            "adapter_entrypoint_sha256",
            "runner_contract_sha256",
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(base)
                provenance = document["provenance"]
                assert isinstance(provenance, dict)
                provenance[field] = (
                    "b" * 40 if field == "waybill_revision" else "sha256:" + "b" * 64
                )
                path = self._write_report(f"tampered-{field}.json", document)
                report = self._build([path])
                imported = next(
                    capability
                    for capability in report.entries[0].capabilities
                    if capability.capability == "import"
                )
                self.assertEqual("source_mismatch", imported.status)
                self.assertFalse(imported.evidence_source_match)

        document = copy.deepcopy(base)
        document["provenance"]["waybill_clean"] = False  # type: ignore[index]
        path = self._write_report("dirty-claim.json", document)
        with self.assertRaisesRegex(ValueError, "waybill_clean must be true"):
            load_conformance_report(path, source_root=self.source_root)

    def test_matrix_recomputes_source_and_rejects_clean_drift(self) -> None:
        path = self._write_report("codex-import.json", self._document("codex", "import"))
        observations = load_capability_observations(
            [path],
            source_root=self.source_root,
        )
        scenario = sorted(CAPABILITY_SCENARIO_REQUIREMENTS["import"])[0]
        scenario_path = self.source_root / SCENARIO_DIRECTORIES["import"] / f"{scenario}.json"
        scenario_path.write_text('{"changed":true}\n', encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source_root), "add", "."],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _commit_source(self.source_root, "change scenario")

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=self._probe,
            observed_at=OBSERVED_AT,
            source_root=self.source_root,
        )
        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("source_mismatch", imported.status)
        self.assertFalse(imported.evidence_source_match)

    def test_matrix_recomputes_import_fixture_digest(self) -> None:
        path = self._write_report("codex-import.json", self._document("codex", "import"))
        observations = load_capability_observations(
            [path],
            source_root=self.source_root,
        )
        before = observations[("codex", "import")].evidence.provenance
        fixture = (
            self.source_root
            / "conformance/import-fixtures/ordinary-unfinished/artifact.txt"
        )
        fixture.write_text("changed fixture\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source_root), "add", "."],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _commit_source(self.source_root, "change import fixture")

        current = compute_source_provenance(
            self.source_root,
            adapter="codex",
            capability="import",
        )
        self.assertNotEqual(
            before.scenario_corpus_sha256,
            current.scenario_corpus_sha256,
        )

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=self._probe,
            observed_at=OBSERVED_AT,
            source_root=self.source_root,
        )
        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("source_mismatch", imported.status)
        self.assertFalse(imported.evidence_source_match)

    def test_matrix_rejects_dirty_waybill_source(self) -> None:
        path = self._write_report("codex-import.json", self._document("codex", "import"))
        observations = load_capability_observations(
            [path],
            source_root=self.source_root,
        )
        (self.source_root / "README.md").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "source worktree must be clean"):
            build_adapter_matrix(
                adapters=["codex"],
                capability_observations=observations,
                identity_probe=self._probe,
                observed_at=OBSERVED_AT,
                source_root=self.source_root,
            )

    def test_matrix_recomputes_runner_contract_digest(self) -> None:
        path = self._write_report("codex-import.json", self._document("codex", "import"))
        observations = load_capability_observations(
            [path],
            source_root=self.source_root,
        )
        before = observations[("codex", "import")].evidence.provenance
        runner_path = self.source_root / RUNNER_CONTRACT_PATHS["import"][0]
        runner_path.write_text("changed runner contract\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source_root), "add", "."],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _commit_source(self.source_root, "change runner")

        current = compute_source_provenance(
            self.source_root,
            adapter="codex",
            capability="import",
        )
        self.assertNotEqual(
            before.runner_contract_sha256,
            current.runner_contract_sha256,
        )
        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=self._probe,
            observed_at=OBSERVED_AT,
            source_root=self.source_root,
        )
        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("source_mismatch", imported.status)
        self.assertFalse(imported.evidence_source_match)

    def test_public_serialization_has_digests_but_no_local_paths(self) -> None:
        path = self._write_report("private.json", self._document("codex", "import"))
        report = self._build([path])

        public_text = json.dumps(report.to_dict(include_private=False))
        private_text = json.dumps(report.to_dict(include_private=True))
        self.assertNotIn(str(self.root), public_text)
        self.assertNotIn("report_path", public_text)
        self.assertIn("scenario_corpus_sha256", public_text)
        self.assertIn("runner_contract_sha256", public_text)
        self.assertIn(str(path.resolve()), private_text)

    def test_duplicate_and_unselected_reports_are_rejected(self) -> None:
        paths = [
            self._write_report("one.json", self._document("codex", "import")),
            self._write_report("two.json", self._document("codex", "import")),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate conformance report"):
            load_capability_observations(paths, source_root=self.source_root)

        cursor = self._write_report("cursor.json", self._document("cursor", "import"))
        with self.assertRaisesRegex(ValueError, "unselected adapter"):
            build_adapter_matrix(
                adapters=["codex"],
                capability_observations=load_capability_observations(
                    [cursor],
                    source_root=self.source_root,
                ),
                identity_probe=self._probe,
                observed_at=OBSERVED_AT,
                source_root=self.source_root,
            )


if __name__ == "__main__":
    unittest.main()
