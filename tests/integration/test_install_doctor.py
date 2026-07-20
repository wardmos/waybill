"""Tests for adapter installation planning, manifests, and doctor states."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from waybill_core import __version__
from waybill_core.adapter_installation import (
    MANIFEST_FILENAME,
    AdapterFileRecord,
    AdapterInstallationManifest,
    InstallationManifestError,
    load_installation_manifest,
    write_installation_manifest,
)
from waybill_core.adapter_sources import sources_for_adapter
from waybill_core.cli import main
from waybill_core.doctor import doctor_repository
from waybill_core.install import InstallConflictError, install_adapters


def snapshot_tree(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[f"{relative}@"] = os.readlink(path).encode()
        elif path.is_dir():
            snapshot[f"{relative}/"] = b""
        elif path.is_file():
            snapshot[relative] = path.read_bytes()
    return snapshot


def populate_source(root: Path, adapter: str, prefix: str = "v1") -> None:
    for index, source in enumerate(sources_for_adapter(adapter)):
        path = root / source.canonical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{prefix} {adapter} {index}\n")


def checks_by_name(report: object) -> dict[str, object]:
    return {check.name: check for check in report.checks}


class InstallPlanningTests(unittest.TestCase):
    def test_dry_run_is_read_only_and_reports_planned_actions(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            populate_source(source, "claude-code")
            before = snapshot_tree(target)

            report = install_adapters(
                source,
                target,
                ["claude-code"],
                dry_run=True,
            )

            self.assertTrue(report.dry_run)
            self.assertFalse(report.has_conflicts)
            self.assertEqual(before, snapshot_tree(target))
            self.assertEqual(
                {
                    ".claude/skills/handoff/SKILL.md": "would-create",
                    ".claude/skills/waybill/SKILL.md": "would-create",
                    ".gitignore": "would-create",
                    MANIFEST_FILENAME: "would-create",
                },
                {action.path: action.action for action in report.actions},
            )

            applied = install_adapters(source, target, ["claude-code"])
            self.assertFalse(applied.dry_run)
            self.assertEqual(
                {"created"},
                {action.action for action in applied.actions},
            )

            second_preview = install_adapters(
                source,
                target,
                ["claude-code"],
                dry_run=True,
            )
            self.assertEqual(
                {"unchanged"},
                {action.action for action in second_preview.actions},
            )

    def test_all_conflicts_are_found_before_any_file_is_written(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            populate_source(source, "claude-code")
            for adapter_source in sources_for_adapter("claude-code"):
                path = target / adapter_source.install_target
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local customization\n")
            before = snapshot_tree(target)

            preview = install_adapters(
                source,
                target,
                ["claude-code"],
                dry_run=True,
            )
            self.assertEqual(
                {
                    item.install_target
                    for item in sources_for_adapter("claude-code")
                },
                {
                    action.path
                    for action in preview.actions
                    if action.action == "would-conflict"
                },
            )
            self.assertTrue(preview.has_conflicts)
            self.assertEqual(before, snapshot_tree(target))

            with self.assertRaises(InstallConflictError) as raised:
                install_adapters(source, target, ["claude-code"])

            self.assertEqual(2, len(raised.exception.conflicts))
            self.assertEqual(before, snapshot_tree(target))
            self.assertFalse((target / ".gitignore").exists())
            self.assertFalse((target / MANIFEST_FILENAME).exists())

    def test_force_updates_regular_files_but_never_follows_symlinks(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-outside-") as outside_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            outside = Path(outside_tmp) / "outside.md"
            outside.write_text("outside\n")
            populate_source(source, "claude-code")
            adapter_sources = sources_for_adapter("claude-code")

            regular = target / adapter_sources[0].install_target
            regular.parent.mkdir(parents=True, exist_ok=True)
            regular.write_text("old\n")
            linked = target / adapter_sources[1].install_target
            linked.parent.mkdir(parents=True, exist_ok=True)
            linked.symlink_to(outside)

            preview = install_adapters(
                source,
                target,
                ["claude-code"],
                force=True,
                dry_run=True,
            )
            actions = {action.path: action.action for action in preview.actions}
            self.assertEqual(
                "would-update",
                actions[adapter_sources[0].install_target],
            )
            self.assertEqual(
                "would-conflict",
                actions[adapter_sources[1].install_target],
            )

            with self.assertRaises(InstallConflictError):
                install_adapters(source, target, ["claude-code"], force=True)
            self.assertEqual("old\n", regular.read_text())
            self.assertEqual("outside\n", outside.read_text())


class InstallationManifestTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_selective_init_merges_records(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            populate_source(source, "claude-code")
            populate_source(source, "cursor")

            install_adapters(source, target, ["claude-code"])
            manifest_path = target / MANIFEST_FILENAME
            claude_bytes = manifest_path.read_bytes()
            raw = json.loads(claude_bytes)
            self.assertEqual(
                {"format_version", "waybill_version", "files"},
                set(raw),
            )
            self.assertEqual(1, raw["format_version"])
            self.assertEqual(__version__, raw["waybill_version"])
            self.assertNotIn("timestamp", raw)
            self.assertEqual(
                {
                    item.install_target
                    for item in sources_for_adapter("claude-code")
                },
                set(raw["files"]),
            )
            for target_path, record in raw["files"].items():
                self.assertEqual("claude-code", record["adapter"])
                self.assertEqual(
                    hashlib.sha256(
                        (target / target_path).read_bytes()
                    ).hexdigest(),
                    record["sha256"],
                )

            install_adapters(source, target, ["claude-code"])
            self.assertEqual(claude_bytes, manifest_path.read_bytes())

            install_adapters(source, target, ["cursor"])
            merged = load_installation_manifest(target)
            self.assertIsNotNone(merged)
            assert merged is not None
            self.assertEqual(
                set(raw["files"])
                | {
                    item.install_target
                    for item in sources_for_adapter("cursor")
                },
                set(merged.files),
            )
            for path, record in raw["files"].items():
                self.assertEqual(record["sha256"], merged.files[path].sha256)

    def test_manifest_write_is_atomic_and_preserves_old_file_on_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-manifest-") as target_tmp:
            target = Path(target_tmp)
            first = AdapterInstallationManifest(
                format_version=1,
                waybill_version="0.1",
                files={
                    ".claude/skills/handoff/SKILL.md": AdapterFileRecord(
                        adapter="claude-code",
                        sha256="0" * 64,
                    )
                },
            )
            write_installation_manifest(target, first)
            manifest = target / MANIFEST_FILENAME
            before = manifest.read_bytes()
            second = AdapterInstallationManifest(
                format_version=1,
                waybill_version="0.2",
                files=first.files,
            )

            with mock.patch(
                "waybill_core.adapter_installation.os.replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaises(OSError):
                    write_installation_manifest(target, second)

            self.assertEqual(before, manifest.read_bytes())
            self.assertEqual(
                [MANIFEST_FILENAME],
                sorted(path.name for path in target.iterdir()),
            )

    def test_manifest_paths_format_and_symlinks_fail_closed(self) -> None:
        valid_record = {"adapter": "claude-code", "sha256": "0" * 64}
        invalid_documents = (
            "{not json",
            json.dumps(
                {
                    "format_version": 1,
                    "waybill_version": "0.1",
                    "files": {"../escape": valid_record},
                }
            ),
            json.dumps(
                {
                    "format_version": 1,
                    "waybill_version": "0.1",
                    "timestamp": "forbidden",
                    "files": {},
                }
            ),
            json.dumps(
                {
                    "format_version": 1,
                    "waybill_version": "0.1",
                    "files": {
                        ".claude/skills/handoff/SKILL.md": {
                            "adapter": "cursor",
                            "sha256": "0" * 64,
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "format_version": True,
                    "waybill_version": "0.1",
                    "files": {},
                }
            ),
        )
        for document in invalid_documents:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory(
                    prefix="waybill-invalid-manifest-"
                ) as target_tmp:
                    target = Path(target_tmp)
                    (target / MANIFEST_FILENAME).write_text(document)
                    with self.assertRaises(InstallationManifestError):
                        load_installation_manifest(target)

        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-outside-") as outside_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            populate_source(source, "claude-code")
            outside = Path(outside_tmp) / "manifest.json"
            outside.write_text("{}")
            (target / MANIFEST_FILENAME).symlink_to(outside)
            before = snapshot_tree(target)

            preview = install_adapters(
                source,
                target,
                ["claude-code"],
                dry_run=True,
            )
            actions = {action.path: action.action for action in preview.actions}
            self.assertEqual("would-conflict", actions[MANIFEST_FILENAME])
            self.assertEqual(before, snapshot_tree(target))
            with self.assertRaises(InstallConflictError):
                install_adapters(source, target, ["claude-code"], force=True)
            self.assertEqual(before, snapshot_tree(target))
            self.assertEqual("{}", outside.read_text())


class DoctorStateTests(unittest.TestCase):
    def install_claude(self, source: Path, target: Path) -> None:
        populate_source(source, "claude-code")
        install_adapters(source, target, ["claude-code"])

    def adapter_checks(self, report: object) -> dict[str, object]:
        names = {
            item.install_target
            for item in sources_for_adapter("claude-code")
        }
        return {
            check.name: check for check in report.checks if check.name in names
        }

    def test_doctor_distinguishes_current_missing_stale_and_modified(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            self.install_claude(source, target)
            adapter_sources = sources_for_adapter("claude-code")

            current = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            self.assertFalse(current.has_errors)
            self.assertEqual(
                {("current", "ok")},
                {
                    (check.state, check.status)
                    for check in self.adapter_checks(current).values()
                },
            )

            installed = target / adapter_sources[0].install_target
            old_content = installed.read_bytes()
            installed.unlink()
            missing = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            check = checks_by_name(missing)[adapter_sources[0].install_target]
            self.assertEqual(("missing", "error"), (check.state, check.status))

            installed.write_bytes(old_content)
            canonical = source / adapter_sources[0].canonical
            canonical.write_text("v2 canonical content\n")
            stale = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            check = checks_by_name(stale)[adapter_sources[0].install_target]
            self.assertEqual(("stale", "error"), (check.state, check.status))

            canonical.write_bytes(old_content)
            installed.write_text("local modification\n")
            modified = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            check = checks_by_name(modified)[adapter_sources[0].install_target]
            self.assertEqual(
                ("modified", "warning"),
                (check.state, check.status),
            )
            self.assertFalse(modified.has_errors)

    def test_legacy_and_invalid_manifests_are_handled_explicitly(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-target-") as target_tmp,
        ):
            source = Path(source_tmp)
            target = Path(target_tmp)
            populate_source(source, "claude-code")
            for adapter_source in sources_for_adapter("claude-code"):
                installed = target / adapter_source.install_target
                installed.parent.mkdir(parents=True, exist_ok=True)
                installed.write_bytes(
                    (source / adapter_source.canonical).read_bytes()
                )
            (target / ".gitignore").write_text(".waybill/\n")

            legacy = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            self.assertEqual(
                {"current"},
                {
                    check.state
                    for check in self.adapter_checks(legacy).values()
                },
            )
            manifest_check = checks_by_name(legacy)[MANIFEST_FILENAME]
            self.assertEqual(
                ("legacy", "ok"),
                (manifest_check.state, manifest_check.status),
            )

            (target / MANIFEST_FILENAME).write_text("{broken")
            before = snapshot_tree(target)
            invalid = doctor_repository(
                target,
                ["claude-code"],
                source_root=source,
            )
            manifest_check = checks_by_name(invalid)[MANIFEST_FILENAME]
            self.assertEqual(
                ("invalid", "error"),
                (manifest_check.state, manifest_check.status),
            )
            self.assertTrue(invalid.has_errors)
            self.assertEqual(before, snapshot_tree(target))

    def test_report_states_codex_plugin_is_not_managed_by_init(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-doctor-") as target_tmp:
            report = doctor_repository(Path(target_tmp), ["claude-code"])

            self.assertFalse(report.codex_plugin_managed_by_init)
            self.assertIn("not managed", report.codex_plugin_message.lower())


class InstallDoctorCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(arguments)
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_init_dry_run_json_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-init-cli-") as target_tmp:
            target = Path(target_tmp)
            before = snapshot_tree(target)

            exit_code, report, stderr = self.run_cli(
                [
                    "init",
                    "--target",
                    str(target),
                    "--adapter",
                    "claude-code",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(0, exit_code)
            self.assertEqual("", stderr)
            self.assertEqual(before, snapshot_tree(target))
            self.assertIs(True, report["success"])
            self.assertIs(True, report["dry_run"])
            self.assertIs(False, report["has_conflicts"])
            self.assertEqual(
                {
                    "would-create",
                },
                {action["action"] for action in report["actions"]},
            )

    def test_init_conflict_dry_run_reports_failure_without_writes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-init-cli-") as target_tmp:
            target = Path(target_tmp)
            conflict = target / ".claude" / "skills" / "handoff" / "SKILL.md"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("local customization\n")
            before = snapshot_tree(target)

            exit_code, report, stderr = self.run_cli(
                [
                    "init",
                    "--target",
                    str(target),
                    "--adapter",
                    "claude-code",
                    "--dry-run",
                    "--json",
                ]
            )

            self.assertEqual(1, exit_code)
            self.assertEqual("", stderr)
            self.assertEqual(before, snapshot_tree(target))
            self.assertIs(False, report["success"])
            self.assertIs(True, report["dry_run"])
            self.assertIs(True, report["has_conflicts"])
            self.assertIn(
                {
                    "path": ".claude/skills/handoff/SKILL.md",
                    "action": "would-conflict",
                },
                report["actions"],
            )

    def test_doctor_json_exposes_states_and_codex_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-doctor-cli-") as target_tmp:
            target = Path(target_tmp)
            install_exit, _report, _stderr = self.run_cli(
                [
                    "init",
                    "--target",
                    str(target),
                    "--adapter",
                    "claude-code",
                    "--json",
                ]
            )
            self.assertEqual(0, install_exit)
            before = snapshot_tree(target)

            exit_code, report, stderr = self.run_cli(
                [
                    "doctor",
                    "--target",
                    str(target),
                    "--adapter",
                    "claude-code",
                    "--json",
                ]
            )

            self.assertEqual(0, exit_code)
            self.assertEqual("", stderr)
            self.assertEqual(before, snapshot_tree(target))
            self.assertIs(False, report["codex_plugin_managed_by_init"])
            self.assertIn("not managed", report["codex_plugin_message"].lower())
            self.assertTrue(
                all(isinstance(check["state"], str) for check in report["checks"])
            )


if __name__ == "__main__":
    unittest.main()
