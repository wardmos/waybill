"""Unit tests for Waybill Bundle validation."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from waybill_core.validation import WAYBILL_SECTIONS, ValidationIssue, validate_bundle


class BundleValidationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.bundle = Path(self.temporary_directory.name) / "bundle"
        self.bundle.mkdir()
        self.metadata: dict[str, Any] = {
            "schema_version": "0.2",
            "source_agent": "codex",
            "created_at": "2026-06-29T12:34:56Z",
            "repo_root": ".",
            "git": {
                "branch": "main",
                "base_ref": "origin/main",
                "head_sha": "0123456789abcdef",
                "dirty": False,
            },
            "artifacts": {
                "waybill": "WAYBILL.md",
                "diff": "diff.patch",
                "commands": "commands.log",
                "test_summary": "test-summary.md",
            },
        }
        self._write_bundle()

    def _write_bundle(self, metadata: dict[str, Any] | None = None) -> None:
        current_metadata = self.metadata if metadata is None else metadata
        (self.bundle / "metadata.json").write_text(
            json.dumps(current_metadata),
            encoding="utf-8",
        )
        sections = "\n\n".join(f"## {section}\n\nRecorded." for section in WAYBILL_SECTIONS)
        (self.bundle / "WAYBILL.md").write_text(sections, encoding="utf-8")
        (self.bundle / "diff.patch").write_text("No tracked diff.\n", encoding="utf-8")
        (self.bundle / "commands.log").write_text(
            "read-only: inspected repository\n"
            "bundle-writing: wrote bundle files\n",
            encoding="utf-8",
        )
        (self.bundle / "test-summary.md").write_text("Tests passed.\n", encoding="utf-8")

    def _issues_for(self, metadata: dict[str, Any]) -> list[ValidationIssue]:
        self._write_bundle(metadata)
        return validate_bundle(self.bundle)

    @staticmethod
    def _error_messages(issues: list[ValidationIssue]) -> list[str]:
        return [issue.message for issue in issues if issue.severity == "error"]

    @staticmethod
    def _set_nested(metadata: dict[str, Any], field: str, value: Any) -> None:
        parts = field.split(".")
        target = metadata
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value

    def test_valid_metadata_accepts_rfc3339_offsets(self) -> None:
        for created_at in [
            "2026-06-29T12:34:56Z",
            "2026-06-29t12:34:56.123456+05:30",
            "2026-06-29T12:34:56-04:00",
        ]:
            with self.subTest(created_at=created_at):
                metadata = copy.deepcopy(self.metadata)
                metadata["created_at"] = created_at
                self.assertEqual([], self._error_messages(self._issues_for(metadata)))

    def test_invalid_utf8_metadata_returns_a_validation_error(self) -> None:
        (self.bundle / "metadata.json").write_bytes(b"\xff\xfe\x00")

        issues = validate_bundle(self.bundle)

        self.assertIn(
            "metadata.json must be UTF-8 text",
            self._error_messages(issues),
        )

    def test_required_metadata_strings_reject_wrong_types_and_empty_values(self) -> None:
        cases = [
            ("source_agent", 1, "metadata source_agent must be a non-empty string"),
            ("source_agent", "", "metadata source_agent must be a non-empty string"),
            ("source_agent", "   ", "metadata source_agent must be a non-empty string"),
            ("created_at", [], "metadata created_at must be an RFC 3339 date-time"),
            ("created_at", "", "metadata created_at must be an RFC 3339 date-time"),
            ("repo_root", None, "metadata repo_root must be a non-empty string"),
            ("repo_root", "", "metadata repo_root must be a non-empty string"),
            ("repo_root", "   ", "metadata repo_root must be a non-empty string"),
            ("git.branch", False, "metadata git.branch must be a non-empty string"),
            ("git.branch", "", "metadata git.branch must be a non-empty string"),
            ("git.base_ref", [], "metadata git.base_ref must be a non-empty string"),
            ("git.base_ref", "", "metadata git.base_ref must be a non-empty string"),
            ("git.head_sha", 123, "metadata git.head_sha must be a non-empty string"),
            ("git.head_sha", "", "metadata git.head_sha must be a non-empty string"),
        ]

        for field, value, expected_message in cases:
            with self.subTest(field=field, value=value):
                metadata = copy.deepcopy(self.metadata)
                self._set_nested(metadata, field, value)
                self.assertIn(
                    expected_message,
                    self._error_messages(self._issues_for(metadata)),
                )

    def test_created_at_rejects_non_rfc3339_or_timezone_naive_values(self) -> None:
        for created_at in [
            "2026-06-29",
            "2026-06-29 12:34:56Z",
            "2026-06-29T12:34:56",
            "2026-02-30T12:34:56Z",
            "not-a-date",
        ]:
            with self.subTest(created_at=created_at):
                metadata = copy.deepcopy(self.metadata)
                metadata["created_at"] = created_at
                self.assertIn(
                    "metadata created_at must be an RFC 3339 date-time",
                    self._error_messages(self._issues_for(metadata)),
                )

    def test_git_requires_object_fields_with_schema_types(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["git"] = "main"
        self.assertIn(
            "metadata git must be an object",
            self._error_messages(self._issues_for(metadata)),
        )

        for field in ["branch", "base_ref", "head_sha", "dirty"]:
            with self.subTest(missing=field):
                metadata = copy.deepcopy(self.metadata)
                del metadata["git"][field]
                self.assertIn(
                    f"metadata git missing {field}",
                    self._error_messages(self._issues_for(metadata)),
                )

        metadata = copy.deepcopy(self.metadata)
        metadata["git"]["dirty"] = 1
        self.assertIn(
            "metadata git.dirty must be boolean",
            self._error_messages(self._issues_for(metadata)),
        )

    def test_optional_repo_digests_must_match_sha256_format(self) -> None:
        valid_digest = f"sha256:{'a' * 64}"
        metadata = copy.deepcopy(self.metadata)
        metadata["git"]["status_digest"] = valid_digest
        metadata["git"]["repo_state_digest"] = valid_digest
        self.assertEqual([], self._error_messages(self._issues_for(metadata)))

        for field, value in [
            ("status_digest", 1),
            ("status_digest", ""),
            ("status_digest", "sha256:not-a-digest"),
            ("repo_state_digest", None),
            ("repo_state_digest", f"sha256:{'A' * 64}"),
        ]:
            with self.subTest(field=field, value=value):
                metadata = copy.deepcopy(self.metadata)
                metadata["git"][field] = value
                self.assertIn(
                    f"metadata git.{field} must be a sha256 digest",
                    self._error_messages(self._issues_for(metadata)),
                )

    def test_artifact_paths_must_be_non_empty_strings(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        del metadata["artifacts"]["waybill"]
        self.assertIn(
            "metadata artifacts missing waybill",
            self._error_messages(self._issues_for(metadata)),
        )

        for name, value in [
            ("diff", 42),
            ("commands", None),
            ("test_summary", []),
            ("custom", {}),
            ("diff", ""),
            ("diff", "   "),
        ]:
            with self.subTest(name=name, value=value):
                metadata = copy.deepcopy(self.metadata)
                metadata["artifacts"][name] = value
                self.assertIn(
                    f"metadata artifacts.{name} must be a non-empty string",
                    self._error_messages(self._issues_for(metadata)),
                )

    def test_handoff_fields_follow_schema_types_and_non_empty_constraints(self) -> None:
        metadata = copy.deepcopy(self.metadata)
        metadata["handoff"] = []
        self.assertIn(
            "metadata handoff must be an object",
            self._error_messages(self._issues_for(metadata)),
        )

        for field, value, expected_message in [
            ("kind", 1, "metadata handoff.kind must be a string"),
            ("kind", "", "metadata handoff.kind must be one of: "),
            ("parent_agent", 1, "metadata handoff.parent_agent must be a non-empty string"),
            ("parent_agent", "", "metadata handoff.parent_agent must be a non-empty string"),
            ("parent_agent", "   ", "metadata handoff.parent_agent must be a non-empty string"),
            ("child_agent", [], "metadata handoff.child_agent must be a non-empty string"),
            ("child_agent", "", "metadata handoff.child_agent must be a non-empty string"),
        ]:
            with self.subTest(field=field, value=value):
                metadata = copy.deepcopy(self.metadata)
                metadata["handoff"] = {"kind": "handoff", field: value}
                self.assertTrue(
                    any(
                        message.startswith(expected_message)
                        for message in self._error_messages(self._issues_for(metadata))
                    )
                )

    def test_sensitive_content_scan_covers_nested_regular_files(self) -> None:
        sensitive_path = self.bundle / "attachments" / "logs" / "debug.txt"
        sensitive_path.parent.mkdir(parents=True)
        sensitive_path.write_text(
            "Authorization: Bearer synthetic-test-token-value",
            encoding="utf-8",
        )

        matching = [
            issue
            for issue in validate_bundle(self.bundle)
            if issue.severity == "error"
            and issue.message.startswith("possible secret matching")
        ]

        self.assertEqual(1, len(matching))
        self.assertEqual("attachments/logs/debug.txt", matching[0].path)

    def test_unscannable_nested_file_is_a_relative_path_warning(self) -> None:
        binary_path = self.bundle / "attachments" / "payload.bin"
        binary_path.parent.mkdir(parents=True)
        binary_path.write_bytes(b"\xff\xfeunscannable")

        matching = [
            issue
            for issue in validate_bundle(self.bundle)
            if issue.message == "could not scan binary or non-UTF-8 file"
        ]

        self.assertEqual(1, len(matching))
        self.assertEqual("warning", matching[0].severity)
        self.assertEqual("attachments/payload.bin", matching[0].path)

    def test_commands_log_accepts_equivalent_section_labels(self) -> None:
        (self.bundle / "commands.log").write_text(
            "# Read only inspection\n\n- git status: clean\n"
            "\n# Bundle writes\n\n- created the bundle files\n",
            encoding="utf-8",
        )

        issues = validate_bundle(self.bundle)

        self.assertFalse(
            any(issue.message.startswith("commands.log should") for issue in issues)
        )

    def test_validation_issue_paths_are_bundle_relative(self) -> None:
        (self.bundle / "commands.log").write_text(
            "Inspected the repository and created files.\n",
            encoding="utf-8",
        )
        (self.bundle / "WAYBILL.md").unlink()

        issues = validate_bundle(self.bundle)

        self.assertIn("WAYBILL.md", {issue.path for issue in issues})
        self.assertIn("commands.log", {issue.path for issue in issues})
        self.assertTrue(
            all(
                issue.path is None or not Path(issue.path).is_absolute()
                for issue in issues
            )
        )


if __name__ == "__main__":
    unittest.main()
