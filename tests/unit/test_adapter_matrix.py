"""Unit tests for adapter capability quality gates."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from waybill_core.adapter_matrix import (
    ADAPTER_CAPABILITY_REQUIREMENTS,
    CAPABILITY_SCENARIO_REQUIREMENTS,
    build_adapter_matrix,
    load_capability_observations,
    load_conformance_report,
)
from waybill_core.agent_identity import AgentIdentity


OBSERVED_AT = "2026-07-01T12:34:56Z"
REPO_ROOT = Path(__file__).resolve().parents[2]


def verified_identity(
    adapter: str,
    executable: str,
    *,
    sha256: str = "sha256:" + "a" * 64,
    version: str = "1.2.3",
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


def conformance_report(
    adapter: str,
    capability: str,
    *,
    success: bool = True,
    dry_run: bool = False,
    identity_sha256: str = "sha256:" + "a" * 64,
    identity_product: str | None = None,
    identity_version: str = "1.2.3",
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
    }
    document: dict[str, object] = {
        "schema_version": "1",
        "capability": capability,
        "adapter": adapter,
        "observed_at": OBSERVED_AT,
        "identity": identity,
        "dry_run": dry_run,
        "success": success,
        "results": [
            {"scenario": scenario, "passed": success} for scenario in selected
        ],
    }
    if capability == "export":
        document["execution_mode"] = "unsafe_manual"
        identity["identity_kind"] = "executable"
    else:
        document["execution_mode"] = "manual"
        identity["identity_kind"] = "executable"
    return document


class AdapterMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-adapter-matrix-unit-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _write_report(
        self,
        name: str,
        document: dict[str, object],
    ) -> Path:
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

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
        self.assertEqual(
            CAPABILITY_SCENARIO_REQUIREMENTS["import"],
            frozenset(
                path.stem
                for path in (REPO_ROOT / "conformance/scenarios").glob("*.json")
            ),
        )
        self.assertEqual(
            CAPABILITY_SCENARIO_REQUIREMENTS["export"],
            frozenset(
                path.stem
                for path in (REPO_ROOT / "conformance/export-scenarios").glob("*.json")
            ),
        )

    def test_full_real_reports_pass_when_current_identity_matches(self) -> None:
        paths = [
            self._write_report(
                "codex-import.json", conformance_report("codex", "import")
            ),
            self._write_report(
                "codex-export.json", conformance_report("codex", "export")
            ),
        ]
        observations = load_capability_observations(paths)

        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            self.assertEqual(OBSERVED_AT, observed_at)
            return verified_identity(adapter, executable)

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )

        self.assertTrue(report.identity_success)
        self.assertTrue(report.success)
        self.assertEqual(
            ["passed", "passed"],
            [capability.status for capability in report.entries[0].capabilities],
        )
        self.assertTrue(
            all(
                capability.evidence_identity_match
                for capability in report.entries[0].capabilities
            )
        )
        evidence = observations[("codex", "import")].evidence
        self.assertEqual(
            "sha256:" + hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            evidence.report_sha256,
        )
        self.assertRegex(evidence.report_ref, r"^codex:import:[0-9a-f]{16}$")

    def test_report_identity_is_bound_to_current_executable(self) -> None:
        path = self._write_report(
            "codex-import.json", conformance_report("codex", "import")
        )
        observations = load_capability_observations([path])

        for identity_overrides in (
            {"sha256": "sha256:" + "b" * 64},
            {"version": "9.9.9"},
        ):
            with self.subTest(identity_overrides=identity_overrides):
                def probe(
                    adapter: str,
                    *,
                    executable: str,
                    observed_at: str,
                ) -> AgentIdentity:
                    return verified_identity(adapter, executable, **identity_overrides)

                report = build_adapter_matrix(
                    adapters=["codex"],
                    capability_observations=observations,
                    identity_probe=probe,
                    observed_at=OBSERVED_AT,
                )

                imported = next(
                    capability
                    for capability in report.entries[0].capabilities
                    if capability.capability == "import"
                )
                self.assertFalse(report.success)
                self.assertEqual("evidence_mismatch", imported.status)
                self.assertFalse(imported.evidence_identity_match)

    def test_failed_full_report_is_recorded_as_failed(self) -> None:
        path = self._write_report(
            "codex-import.json",
            conformance_report("codex", "import", success=False),
        )
        observations = load_capability_observations([path])

        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            return verified_identity(adapter, executable)

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=observations,
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )

        imported = next(
            capability
            for capability in report.entries[0].capabilities
            if capability.capability == "import"
        )
        self.assertEqual("failed", imported.status)
        self.assertTrue(imported.evidence_identity_match)
        self.assertFalse(report.success)

    def test_report_requires_real_verified_provenance(self) -> None:
        cases = [
            (
                conformance_report("codex", "import", dry_run=True),
                "dry_run must be false",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "observed_at": "2026-07-01",
                },
                "observed_at must be an RFC 3339 timestamp",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "identity": {
                        "adapter": "codex",
                        "status": "identity_mismatch",
                        "sha256": "sha256:" + "a" * 64,
                        "product": "grok",
                        "version": "1.2.3",
                        "observed_at": OBSERVED_AT,
                        "identity_kind": "executable",
                    },
                },
                "identity.status must be verified",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "identity": {
                        "adapter": "codex",
                        "status": "verified",
                        "sha256": None,
                        "product": "codex",
                        "version": "1.2.3",
                        "observed_at": OBSERVED_AT,
                        "identity_kind": "executable",
                    },
                },
                "identity.sha256",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "capability": ["import"],
                },
                "capability must be export or import",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "identity": {
                        "adapter": "codex",
                        "status": "verified",
                        "sha256": "sha256:" + "a" * 64,
                        "product": "codex",
                        "version": "/private/tool/version",
                        "observed_at": OBSERVED_AT,
                        "identity_kind": "executable",
                    },
                },
                "identity.version must be a normalized version",
            ),
        ]

        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write_report(f"bad-{index}.json", document)
                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path)

    def test_deterministic_export_fixture_cannot_count_as_capability(self) -> None:
        document = conformance_report("codex", "export")
        document["execution_mode"] = "deterministic_fake"
        identity = document["identity"]
        assert isinstance(identity, dict)
        identity["identity_kind"] = "deterministic_fixture"

        path = self._write_report("fake-export.json", document)
        with self.assertRaisesRegex(
            ValueError,
            "export execution_mode must be unsafe_manual",
        ):
            load_conformance_report(path)

    def test_non_manual_import_cannot_count_as_capability(self) -> None:
        document = conformance_report("codex", "import")
        document["execution_mode"] = "deterministic_fake"

        path = self._write_report("fake-import.json", document)
        with self.assertRaisesRegex(
            ValueError,
            "import execution_mode must be manual",
        ):
            load_conformance_report(path)

    def test_export_requires_executable_identity_kind(self) -> None:
        document = conformance_report("codex", "export")
        identity = document["identity"]
        assert isinstance(identity, dict)
        identity["identity_kind"] = "self_reported"

        path = self._write_report("self-reported-export.json", document)
        with self.assertRaisesRegex(
            ValueError,
            "identity.identity_kind must be executable",
        ):
            load_conformance_report(path)

    def test_report_requires_exact_scenario_coverage_and_consistent_success(self) -> None:
        required = sorted(CAPABILITY_SCENARIO_REQUIREMENTS["import"])
        cases = [
            (
                conformance_report("codex", "import", scenarios=required[:-1]),
                "scenario coverage mismatch",
            ),
            (
                conformance_report(
                    "codex", "import", scenarios=required + [required[0]]
                ),
                "duplicate result scenarios",
            ),
            (
                {
                    **conformance_report("codex", "import"),
                    "results": [
                        {"scenario": scenario, "passed": scenario != required[0]}
                        for scenario in required
                    ],
                },
                "success does not match result outcomes",
            ),
        ]

        for index, (document, message) in enumerate(cases):
            with self.subTest(message=message):
                path = self._write_report(f"coverage-{index}.json", document)
                with self.assertRaisesRegex(ValueError, message):
                    load_conformance_report(path)

    def test_duplicate_capability_reports_are_rejected(self) -> None:
        paths = [
            self._write_report(
                "one.json", conformance_report("codex", "import")
            ),
            self._write_report(
                "two.json", conformance_report("codex", "import")
            ),
        ]

        with self.assertRaisesRegex(ValueError, "duplicate conformance report"):
            load_capability_observations(paths)

    def test_public_serialization_keeps_hash_but_omits_evidence_path(self) -> None:
        path = self._write_report(
            "private-codex-import.json", conformance_report("codex", "import")
        )

        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            return verified_identity(adapter, executable)

        report = build_adapter_matrix(
            adapters=["codex"],
            capability_observations=load_capability_observations([path]),
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )

        public = report.to_dict(include_private=False)
        private = report.to_dict(include_private=True)
        public_text = json.dumps(public)
        self.assertNotIn(str(self.root), public_text)
        self.assertNotIn("report_path", public_text)
        self.assertIn("report_sha256", public_text)
        self.assertIn(str(path), json.dumps(private))

    def test_missing_evidence_and_identity_mismatch_fail_closed(self) -> None:
        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            identity = verified_identity(adapter, executable)
            if adapter != "cursor":
                return identity
            return AgentIdentity(
                **{
                    **identity.__dict__,
                    "status": "identity_mismatch",
                    "product": "grok",
                    "error_code": "unexpected_product",
                }
            )

        no_evidence = build_adapter_matrix(
            adapters=["codex"],
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )
        self.assertFalse(no_evidence.success)
        self.assertEqual(
            ["not_run", "not_run"],
            [capability.status for capability in no_evidence.entries[0].capabilities],
        )

        cursor_path = self._write_report(
            "cursor-import.json", conformance_report("cursor", "import")
        )
        mismatched = build_adapter_matrix(
            adapters=["cursor"],
            capability_observations=load_capability_observations([cursor_path]),
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )
        self.assertFalse(mismatched.identity_success)
        self.assertEqual(
            "identity_mismatch",
            next(
                capability
                for capability in mismatched.entries[0].capabilities
                if capability.capability == "import"
            ).status,
        )

    def test_optional_failure_does_not_fail_required_gate(self) -> None:
        paths = [
            self._write_report(
                "opencode-export.json",
                conformance_report("opencode", "export", success=False),
            ),
            self._write_report(
                "opencode-import.json", conformance_report("opencode", "import")
            ),
        ]

        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            return verified_identity(adapter, executable)

        report = build_adapter_matrix(
            adapters=["opencode"],
            capability_observations=load_capability_observations(paths),
            identity_probe=probe,
            observed_at=OBSERVED_AT,
        )
        self.assertTrue(report.success)

    def test_empty_selection_and_unselected_reports_are_rejected(self) -> None:
        def probe(adapter: str, *, executable: str, observed_at: str) -> AgentIdentity:
            return verified_identity(adapter, executable)

        with self.assertRaisesRegex(ValueError, "at least one adapter"):
            build_adapter_matrix(
                adapters=[],
                identity_probe=probe,
                observed_at=OBSERVED_AT,
            )

        path = self._write_report(
            "cursor-import.json", conformance_report("cursor", "import")
        )
        with self.assertRaisesRegex(ValueError, "unselected adapter"):
            build_adapter_matrix(
                adapters=["codex"],
                capability_observations=load_capability_observations([path]),
                identity_probe=probe,
                observed_at=OBSERVED_AT,
            )


if __name__ == "__main__":
    unittest.main()
