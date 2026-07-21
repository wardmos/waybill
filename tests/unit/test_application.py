"""Unit tests for the transport-neutral Waybill application facade."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from waybill_core.application import (
    InspectBundleReport,
    OperationResult,
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
        self.assertEqual("inspect", result.access.operation)
        self.assertEqual("read", result.access.intent)

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


if __name__ == "__main__":
    unittest.main()
