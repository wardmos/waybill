"""Unit tests for the transport-neutral Waybill application facade."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import waybill_core

from waybill_core.application import (
    AccessIntent,
    AccessIntentName,
    InspectArtifactReport,
    InspectBundleReport,
    OperationResult,
    PackBundleReport,
    Problem,
    RenderBundleReport,
    RootAccess,
    RootIntentName,
    UnpackBundleReport,
    WaybillApplication,
)
from waybill_core.delegation import DelegationPairReport
from waybill_core.preflight import ImportPreflightReport
from waybill_core.readiness import ExportReadinessReport
from waybill_core.repo import RepoVerificationReport
from waybill_core.validation import ValidationIssue


ROOT = Path(__file__).resolve().parents[2]
ORDINARY = ROOT / "examples" / "claude-to-codex"
REQUEST = ROOT / "examples" / "claude-parent-codex-child-request"
RESULT = ROOT / "examples" / "claude-parent-codex-child-result"


class ApplicationFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = WaybillApplication()

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
        (repo / ".gitignore").write_text(".waybill/\n")
        (repo / "tracked.txt").write_text("synthetic content\n")
        self._git(repo, "add", ".gitignore", "tracked.txt")
        self._git(repo, "commit", "-m", "initial fixture")

        bundle = root / "bundle"
        shutil.copytree(ORDINARY, bundle)
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text())

        from waybill_core.repo import read_repo_fidelity

        fidelity = read_repo_fidelity(repo)
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        metadata["git"] = {
            "branch": branch,
            "base_ref": "unknown",
            "head_sha": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            ).stdout.strip(),
            "dirty": False,
            "status_digest": fidelity.status_digest,
            "repo_state_digest": fidelity.repo_state_digest,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        return repo, bundle

    def test_validate_returns_stable_result_without_transport_dependencies(self) -> None:
        result = self.application.validate(ORDINARY)

        self.assertIsInstance(result, OperationResult)
        self.assertTrue(result.success)
        self.assertTrue(result.valid)
        self.assertEqual((), result.problems)
        self.assertEqual("validate", result.access.operation)
        self.assertEqual("read", result.access.intent)
        self.assertEqual((ORDINARY.resolve(),), result.access.roots)
        self.assertTrue(all(isinstance(issue, ValidationIssue) for issue in result.payload))

    def test_validation_failure_has_a_stable_code_and_read_intent(self) -> None:
        result = self.application.validate(ROOT / "missing-bundle")

        self.assertFalse(result.success)
        self.assertFalse(result.valid)
        self.assertEqual(["bundle_invalid"], [problem.code for problem in result.problems])
        self.assertEqual("read", result.access.intent)

    def test_repository_pair_preflight_and_readiness_results_are_typed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-") as temporary:
            repo, bundle = self._matching_bundle(Path(temporary))

            repo_result = self.application.verify_repo(bundle, repo)
            pair_result = self.application.verify_pair(REQUEST, RESULT)
            preflight_result = self.application.preflight(bundle, repo)
            readiness_result = self.application.ready(bundle, repo)

        cases = [
            (repo_result, RepoVerificationReport, "verify-repo"),
            (pair_result, DelegationPairReport, "verify-pair"),
            (preflight_result, ImportPreflightReport, "preflight"),
            (readiness_result, ExportReadinessReport, "ready"),
        ]
        for result, payload_type, operation in cases:
            with self.subTest(operation=operation):
                self.assertTrue(result.success, result.problems)
                self.assertTrue(result.valid)
                self.assertIsInstance(result.payload, payload_type)
                self.assertEqual(operation, result.access.operation)
                self.assertEqual("read", result.access.intent)

    def test_pair_mismatch_uses_a_stable_problem_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-pair-") as temporary:
            mismatched = Path(temporary) / "result"
            shutil.copytree(RESULT, mismatched)
            metadata_path = mismatched / "metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["handoff"]["result_for"] = "wrong-request"
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

            result = self.application.verify_pair(REQUEST, mismatched)

        self.assertFalse(result.success)
        self.assertFalse(result.valid)
        self.assertEqual(
            ["delegation_pair_mismatch"],
            [problem.code for problem in result.problems],
        )

    def test_inspect_returns_metadata_and_validation_as_data(self) -> None:
        result = self.application.inspect(ORDINARY)

        self.assertTrue(result.success)
        self.assertTrue(result.valid)
        self.assertIsInstance(result.payload, InspectBundleReport)
        self.assertEqual("0.2", result.payload.metadata["schema_version"])
        self.assertIsNone(result.payload.metadata_error)
        self.assertEqual(
            (
                InspectArtifactReport("waybill", "WAYBILL.md", "present", 2310),
                InspectArtifactReport("diff", "diff.patch", "present", 698),
                InspectArtifactReport("commands", "commands.log", "present", 416),
                InspectArtifactReport(
                    "test_summary",
                    "test-summary.md",
                    "present",
                    209,
                ),
            ),
            result.payload.artifacts,
        )
        self.assertEqual("inspect", result.access.operation)
        self.assertEqual("read", result.access.intent)

    def test_inspect_captures_missing_and_invalid_artifacts_inside_controller(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-artifacts-") as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            shutil.copytree(ORDINARY, bundle)
            outside = root / "outside.txt"
            outside.write_text("must not be inspected\n")
            symlink = bundle / "outside-link.txt"
            try:
                symlink.symlink_to(outside)
            except (NotImplementedError, OSError):
                symlink_supported = False
            else:
                symlink_supported = True
            metadata_path = bundle / "metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["artifacts"] = {
                "waybill": "WAYBILL.md",
                "missing": "missing.txt",
                "invalid_type": 42,
                "blank": " ",
                "traversal": "../outside.txt",
                "absolute": str(outside),
                "backslash": "folder\\outside.txt",
                "dot_segment": "./WAYBILL.md",
                "control": "bad\u0001name",
            }
            if symlink_supported:
                metadata["artifacts"]["symlink"] = "outside-link.txt"
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

            result = self.application.inspect(bundle)

        self.assertFalse(result.success)
        self.assertFalse(result.valid)
        expected_artifacts = [
            InspectArtifactReport("waybill", "WAYBILL.md", "present", 2310),
            InspectArtifactReport("missing", "missing.txt", "missing", 0),
            InspectArtifactReport("invalid_type", None, "invalid", 0),
            InspectArtifactReport("blank", " ", "invalid", 0),
            InspectArtifactReport("traversal", "../outside.txt", "invalid", 0),
            InspectArtifactReport("absolute", str(outside), "invalid", 0),
            InspectArtifactReport(
                "backslash",
                "folder\\outside.txt",
                "invalid",
                0,
            ),
            InspectArtifactReport("dot_segment", "./WAYBILL.md", "invalid", 0),
            InspectArtifactReport("control", "bad\u0001name", "invalid", 0),
        ]
        if symlink_supported:
            expected_artifacts.append(
                InspectArtifactReport("symlink", "outside-link.txt", "invalid", 0)
            )
        self.assertEqual(
            tuple(expected_artifacts),
            result.payload.artifacts,
        )

    def test_inspect_reports_unreadable_metadata_without_transport_exception(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-inspect-") as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(ORDINARY, bundle)
            (bundle / "metadata.json").write_bytes(b"\xff\xfe")

            result = self.application.inspect(bundle)

        self.assertFalse(result.success)
        self.assertFalse(result.valid)
        self.assertIsNone(result.payload.metadata)
        self.assertEqual(
            "metadata.json must be UTF-8 text",
            result.payload.metadata_error,
        )

    def test_draft_creation_exposes_mixed_root_intents_and_stable_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-draft-") as temporary:
            repo, _ = self._matching_bundle(Path(temporary))
            output = Path(temporary) / "draft"

            result = self.application.create_draft(
                output,
                repo,
                source_agent="test-agent",
                goal="Create a transport-neutral draft.",
            )
            duplicate = self.application.create_draft(output, repo)

        self.assertTrue(result.success)
        self.assertEqual("mixed", result.access.intent)
        self.assertEqual(
            [(repo.resolve(), "read"), (output.resolve(), "write")],
            [(entry.root, entry.intent) for entry in result.access.root_intents],
        )
        self.assertFalse(duplicate.success)
        self.assertIsNone(duplicate.payload)
        self.assertEqual(
            ["draft_creation_failed"],
            [problem.code for problem in duplicate.problems],
        )

    def test_install_and_doctor_use_transport_neutral_results(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-install-") as temporary:
            target = Path(temporary) / "target"
            target.mkdir()
            install = self.application.install_adapters(
                ROOT,
                target,
                ["claude-code"],
            )
            doctor = self.application.doctor(
                target,
                ["claude-code"],
                source_root=ROOT,
            )

        self.assertTrue(install.success, install.problems)
        self.assertEqual("mixed", install.access.intent)
        self.assertTrue(doctor.success, doctor.problems)
        self.assertEqual("read", doctor.access.intent)

    def test_bundle_write_use_cases_return_typed_reports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-write-") as temporary:
            root = Path(temporary)
            redacted_path = root / "redacted"
            redacted = self.application.redact(ORDINARY, redacted_path)
            packed = self.application.pack(redacted_path, root / "bundle.zip")
            unpacked = self.application.unpack(root / "bundle.zip", root / "unpacked")
            rendered = self.application.render(
                unpacked.payload.unpack.bundle,
                output=root / "report.md",
            )
            share_check = self.application.share_check(ORDINARY)
            shared = self.application.share(
                ORDINARY,
                root / "shared.zip",
                redacted_output=root / "shared-redacted",
            )
            rendered_file_exists = (root / "report.md").is_file()

        self.assertTrue(redacted.success, redacted.problems)
        self.assertTrue(packed.success, packed.problems)
        self.assertIsInstance(packed.payload, PackBundleReport)
        self.assertTrue(unpacked.success, unpacked.problems)
        self.assertIsInstance(unpacked.payload, UnpackBundleReport)
        self.assertTrue(rendered.success, rendered.problems)
        self.assertIsInstance(rendered.payload, RenderBundleReport)
        self.assertTrue(share_check.success, share_check.problems)
        self.assertTrue(shared.success, shared.problems)
        self.assertTrue(rendered_file_exists)

    def test_invalid_pack_returns_validation_evidence_without_writing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-pack-") as temporary:
            root = Path(temporary)
            output = root / "missing.zip"

            result = self.application.pack(root / "missing-bundle", output)

        self.assertFalse(result.success)
        self.assertFalse(result.valid)
        self.assertIsInstance(result.payload, PackBundleReport)
        self.assertIsNone(result.payload.pack)
        self.assertTrue(result.payload.validation_issues)
        self.assertEqual(
            ["bundle_invalid"],
            [problem.code for problem in result.problems],
        )
        self.assertFalse(output.exists())

    def test_operational_failures_are_stable_results_for_every_use_case(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-boundary-") as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            repo = root / "repo"
            request = root / "request"
            result_bundle = root / "result"
            source = root / "source"
            target = root / "target"
            archive = root / "bundle.zip"
            output = root / "output"

            cases = [
                (
                    "validate",
                    "waybill_core.application.validate_bundle",
                    lambda: self.application.validate(bundle),
                    "bundle_validation_failed",
                    "validate",
                    [(bundle.resolve(), "read")],
                ),
                (
                    "verify-repo",
                    "waybill_core.application.verify_repo_state",
                    lambda: self.application.verify_repo(bundle, repo),
                    "repository_verification_failed",
                    "verify-repo",
                    [(bundle.resolve(), "read"), (repo.resolve(), "read")],
                ),
                (
                    "verify-pair",
                    "waybill_core.application.verify_delegation_pair",
                    lambda: self.application.verify_pair(request, result_bundle),
                    "delegation_pair_verification_failed",
                    "verify-pair",
                    [(request.resolve(), "read"), (result_bundle.resolve(), "read")],
                ),
                (
                    "preflight",
                    "waybill_core.application.run_import_preflight",
                    lambda: self.application.preflight(bundle, repo),
                    "import_preflight_execution_failed",
                    "preflight",
                    [(bundle.resolve(), "read"), (repo.resolve(), "read")],
                ),
                (
                    "ready",
                    "waybill_core.application.check_export_readiness",
                    lambda: self.application.ready(bundle, repo),
                    "export_readiness_check_failed",
                    "ready",
                    [(bundle.resolve(), "read"), (repo.resolve(), "read")],
                ),
                (
                    "inspect",
                    "waybill_core.application.validate_bundle",
                    lambda: self.application.inspect(bundle),
                    "bundle_inspection_failed",
                    "inspect",
                    [(bundle.resolve(), "read")],
                ),
                (
                    "init",
                    "waybill_core.application.install_adapters",
                    lambda: self.application.install_adapters(source, target, ["codex"]),
                    "adapter_installation_failed",
                    "init",
                    [(source.resolve(), "read"), (target.resolve(), "write")],
                ),
                (
                    "doctor",
                    "waybill_core.application.doctor_repository",
                    lambda: self.application.doctor(target, ["codex"], source_root=source),
                    "doctor_failed",
                    "doctor",
                    [(target.resolve(), "read"), (source.resolve(), "read")],
                ),
                (
                    "new",
                    "waybill_core.application.create_draft_bundle",
                    lambda: self.application.create_draft(output, repo),
                    "draft_creation_failed",
                    "new",
                    [(repo.resolve(), "read"), (output.resolve(), "write")],
                ),
                (
                    "redact",
                    "waybill_core.application.redact_bundle",
                    lambda: self.application.redact(bundle, output),
                    "redaction_failed",
                    "redact",
                    [(bundle.resolve(), "read"), (output.resolve(), "write")],
                ),
                (
                    "pack-validation",
                    "waybill_core.application.validate_bundle",
                    lambda: self.application.pack(bundle, archive),
                    "bundle_validation_failed",
                    "pack",
                    [(bundle.resolve(), "read"), (archive.resolve(), "write")],
                ),
                (
                    "share-check",
                    "waybill_core.application.check_shareability",
                    lambda: self.application.share_check(bundle),
                    "share_check_failed",
                    "share-check",
                    [(bundle.resolve(), "read")],
                ),
                (
                    "share",
                    "waybill_core.application.share_bundle",
                    lambda: self.application.share(bundle, archive, redacted_output=output),
                    "share_failed",
                    "share",
                    [
                        (bundle.resolve(), "read"),
                        (archive.resolve(), "write"),
                        (output.resolve(), "write"),
                    ],
                ),
                (
                    "unpack",
                    "waybill_core.application.unpack_bundle",
                    lambda: self.application.unpack(archive, output),
                    "unpack_failed",
                    "unpack",
                    [(archive.resolve(), "read"), (output.resolve(), "write")],
                ),
                (
                    "render",
                    "waybill_core.application.validate_bundle",
                    lambda: self.application.render(bundle, output=output),
                    "render_failed",
                    "render",
                    [(bundle.resolve(), "read"), (output.resolve(), "write")],
                ),
            ]

            for exception_type in (OSError, RuntimeError):
                for (
                    name,
                    patch_target,
                    invoke,
                    problem_code,
                    operation,
                    root_intents,
                ) in cases:
                    with self.subTest(name=name, exception=exception_type.__name__):
                        with patch(
                            patch_target,
                            side_effect=exception_type("synthetic operational failure"),
                        ):
                            operation_result = invoke()

                        self.assertFalse(operation_result.success)
                        self.assertIsNone(operation_result.valid)
                        self.assertIsNone(operation_result.payload)
                        self.assertEqual(
                            [problem_code],
                            [problem.code for problem in operation_result.problems],
                        )
                        self.assertEqual(operation, operation_result.access.operation)
                        intents = {intent for _, intent in root_intents}
                        expected_intent = (
                            "read"
                            if intents == {"read"}
                            else "write"
                            if intents == {"write"}
                            else "mixed"
                        )
                        self.assertEqual(expected_intent, operation_result.access.intent)
                        self.assertEqual(
                            root_intents,
                            [
                                (entry.root, entry.intent)
                                for entry in operation_result.access.root_intents
                            ],
                        )

    def test_pack_failure_preserves_successful_bundle_validation_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-application-pack-boundary-") as temporary:
            output = Path(temporary) / "bundle.zip"
            with patch(
                "waybill_core.application.pack_bundle",
                side_effect=RuntimeError("synthetic pack runtime failure"),
            ):
                result = self.application.pack(ORDINARY, output)

        self.assertFalse(result.success)
        self.assertTrue(result.valid)
        self.assertIsInstance(result.payload, PackBundleReport)
        self.assertIsNone(result.payload.pack)
        self.assertEqual(["pack_failed"], [problem.code for problem in result.problems])

    def test_access_intent_survives_root_resolution_failure(self) -> None:
        with patch.object(Path, "resolve", side_effect=OSError("synthetic resolve failure")):
            result = self.application.validate(ORDINARY)

        self.assertFalse(result.success)
        self.assertIsNone(result.valid)
        self.assertEqual("validate", result.access.operation)
        self.assertEqual((ORDINARY.absolute(),), result.access.roots)
        self.assertEqual(
            ["bundle_validation_failed"],
            [problem.code for problem in result.problems],
        )

    def test_access_intent_survives_resolution_and_absolute_fallback_failures(self) -> None:
        bundle = Path("synthetic-relative-bundle")
        for resolve_error in (OSError, RuntimeError):
            for absolute_error in (OSError, RuntimeError):
                with self.subTest(
                    resolve_error=resolve_error.__name__,
                    absolute_error=absolute_error.__name__,
                ):
                    with (
                        patch.object(
                            Path,
                            "resolve",
                            side_effect=resolve_error("synthetic resolve failure"),
                        ),
                        patch.object(
                            Path,
                            "absolute",
                            side_effect=absolute_error("synthetic absolute failure"),
                        ),
                        patch(
                            "waybill_core.application.validate_bundle",
                            return_value=[],
                        ),
                    ):
                        result = self.application.validate(bundle)

                    self.assertTrue(result.success)
                    self.assertTrue(result.valid)
                    self.assertEqual((bundle,), result.access.roots)
                    self.assertEqual(
                        (RootAccess(bundle, "read"),),
                        result.access.root_intents,
                    )

    def test_facade_contract_types_are_exported_from_the_package(self) -> None:
        expected = {
            "AccessIntent": AccessIntent,
            "AccessIntentName": AccessIntentName,
            "InspectArtifactReport": InspectArtifactReport,
            "InspectBundleReport": InspectBundleReport,
            "OperationResult": OperationResult,
            "PackBundleReport": PackBundleReport,
            "Problem": Problem,
            "RenderBundleReport": RenderBundleReport,
            "RootAccess": RootAccess,
            "RootIntentName": RootIntentName,
            "UnpackBundleReport": UnpackBundleReport,
            "WaybillApplication": WaybillApplication,
        }

        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertIs(value, getattr(waybill_core, name))
                self.assertIn(name, waybill_core.__all__)


if __name__ == "__main__":
    unittest.main()
