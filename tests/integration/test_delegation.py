"""Tests for correlated delegation request and result bundles."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from waybill_core.cli import main
from waybill_core.delegation import verify_delegation_pair
from waybill_core.rendering import render_bundle
from waybill_core.validation import validate_bundle


ROOT = Path(__file__).resolve().parents[2]
REQUEST_EXAMPLE = ROOT / "examples" / "claude-parent-codex-child-request"
RESULT_EXAMPLE = ROOT / "examples" / "claude-parent-codex-child-result"


class DelegationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _copy_example(self, source: Path, name: str) -> Path:
        destination = self.root / name
        destination.mkdir()
        for path in source.iterdir():
            if path.is_file():
                (destination / path.name).write_bytes(path.read_bytes())
        return destination

    @staticmethod
    def _metadata(bundle: Path) -> dict[str, Any]:
        return json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))

    @staticmethod
    def _write_metadata(bundle: Path, metadata: dict[str, Any]) -> None:
        (bundle / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _errors(bundle: Path) -> list[str]:
        return [
            issue.message
            for issue in validate_bundle(bundle)
            if issue.severity == "error"
        ]

    def test_delegation_request_requires_correlation_roles_and_parent_source(self) -> None:
        valid = self._copy_example(REQUEST_EXAMPLE, "valid-request")
        self.assertEqual([], self._errors(valid))

        for field in ["request_id", "parent_agent", "child_agent"]:
            with self.subTest(missing=field):
                bundle = self._copy_example(REQUEST_EXAMPLE, f"request-missing-{field}")
                metadata = self._metadata(bundle)
                del metadata["handoff"][field]
                self._write_metadata(bundle, metadata)
                self.assertIn(
                    f"metadata handoff.{field} is required for delegation_request",
                    self._errors(bundle),
                )

        source_mismatch = self._copy_example(REQUEST_EXAMPLE, "request-source-mismatch")
        metadata = self._metadata(source_mismatch)
        metadata["source_agent"] = "codex"
        self._write_metadata(source_mismatch, metadata)
        self.assertIn(
            "metadata source_agent must match handoff.parent_agent for delegation_request",
            self._errors(source_mismatch),
        )

    def test_delegation_result_requires_reference_status_roles_and_child_source(self) -> None:
        valid = self._copy_example(RESULT_EXAMPLE, "valid-result")
        self.assertEqual([], self._errors(valid))

        for field in ["result_for", "result_status", "parent_agent", "child_agent"]:
            with self.subTest(missing=field):
                bundle = self._copy_example(RESULT_EXAMPLE, f"result-missing-{field}")
                metadata = self._metadata(bundle)
                del metadata["handoff"][field]
                self._write_metadata(bundle, metadata)
                self.assertIn(
                    f"metadata handoff.{field} is required for delegation_result",
                    self._errors(bundle),
                )

        invalid_status = self._copy_example(RESULT_EXAMPLE, "invalid-status")
        metadata = self._metadata(invalid_status)
        metadata["handoff"]["result_status"] = "done"
        self._write_metadata(invalid_status, metadata)
        self.assertIn(
            "metadata handoff.result_status must be one of: completed, partial, blocked",
            self._errors(invalid_status),
        )

        source_mismatch = self._copy_example(RESULT_EXAMPLE, "result-source-mismatch")
        metadata = self._metadata(source_mismatch)
        metadata["source_agent"] = "claude-code"
        self._write_metadata(source_mismatch, metadata)
        self.assertIn(
            "metadata source_agent must match handoff.child_agent for delegation_result",
            self._errors(source_mismatch),
        )

    def test_ordinary_handoff_does_not_require_delegation_correlation(self) -> None:
        bundle = self._copy_example(REQUEST_EXAMPLE, "ordinary")
        metadata = self._metadata(bundle)
        metadata["handoff"] = {"kind": "handoff"}
        self._write_metadata(bundle, metadata)

        errors = self._errors(bundle)

        self.assertFalse(
            any("request_id" in message or "result_for" in message for message in errors)
        )


class DelegationPairTests(DelegationValidationTests):
    def test_verify_pair_accepts_matching_request_and_result(self) -> None:
        request = self._copy_example(REQUEST_EXAMPLE, "request")
        result = self._copy_example(RESULT_EXAMPLE, "result")

        report = verify_delegation_pair(request, result)

        self.assertFalse(report.has_errors)
        self.assertTrue(all(check.status == "ok" for check in report.checks))

    def test_verify_pair_rejects_reference_and_role_mismatches(self) -> None:
        request = self._copy_example(REQUEST_EXAMPLE, "request")
        result = self._copy_example(RESULT_EXAMPLE, "result")
        metadata = self._metadata(result)
        metadata["handoff"]["result_for"] = "another-request"
        metadata["handoff"]["parent_agent"] = "another-parent"
        self._write_metadata(result, metadata)

        report = verify_delegation_pair(request, result)

        self.assertTrue(report.has_errors)
        failed = {check.name for check in report.checks if check.status == "error"}
        self.assertIn("correlation", failed)
        self.assertIn("parent_agent", failed)

    def test_verify_pair_json_and_review_surfaces_show_correlation(self) -> None:
        request = self._copy_example(REQUEST_EXAMPLE, "request")
        result = self._copy_example(RESULT_EXAMPLE, "result")
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(
                ["verify-pair", str(request), str(result), "--json"]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(report["success"])
        self.assertEqual("queue-retry-limit-inspection-001", report["request_id"])
        self.assertEqual(report["request_id"], report["result_for"])
        self.assertEqual("completed", report["result_status"])

        output = io.StringIO()
        with redirect_stdout(output):
            inspect_exit = main(["inspect", str(result)])
        self.assertEqual(0, inspect_exit)
        self.assertIn("Delegation result for: queue-retry-limit-inspection-001", output.getvalue())
        self.assertIn("Delegation result status: completed", output.getvalue())

        rendered = render_bundle(result)
        self.assertIn("| Handoff kind | delegation_result |", rendered)
        self.assertIn(
            "| Delegation result for | queue-retry-limit-inspection-001 |",
            rendered,
        )
        self.assertIn("| Delegation result status | completed |", rendered)


if __name__ == "__main__":
    unittest.main()
