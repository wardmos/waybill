"""Tests for canonical adapter sources and generated mirrors."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from waybill_core.adapter_sources import (
    ADAPTER_SOURCES,
    find_adapter_drift,
    sources_for_adapter,
    sync_adapter_mirrors,
)
from waybill_core.install import install_adapters


ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = ROOT / "scripts" / "sync-adapters.py"

EXPECTED_TARGETS = {
    "claude-code": (
        ".claude/skills/handoff/SKILL.md",
        ".claude/skills/waybill/SKILL.md",
    ),
    "opencode": (
        ".opencode/commands/handoff.md",
        ".opencode/commands/waybill.md",
        ".opencode/skills/handoff/SKILL.md",
        ".opencode/skills/waybill/SKILL.md",
    ),
    "cursor": (
        ".cursor/rules/handoff.mdc",
        ".cursor/rules/waybill.mdc",
    ),
    "gemini-cli": (
        ".gemini/skills/handoff/SKILL.md",
        ".gemini/skills/waybill/SKILL.md",
    ),
}


class AdapterSourceManifestTests(unittest.TestCase):
    def test_manifest_maps_canonical_files_to_both_mirror_kinds(self) -> None:
        actual_targets = {
            adapter: tuple(source.install_target for source in sources_for_adapter(adapter))
            for adapter in EXPECTED_TARGETS
        }
        self.assertEqual(EXPECTED_TARGETS, actual_targets)

        seen_mirrors: set[str] = set()
        for source in ADAPTER_SOURCES:
            with self.subTest(canonical=source.canonical):
                self.assertTrue(
                    source.canonical.startswith(f"adapters/{source.adapter}/")
                )
                self.assertEqual(source.install_target, source.workspace_mirror)
                self.assertEqual(
                    f"waybill_core/template-files/{source.install_target}",
                    source.packaged_mirror,
                )
                self.assertEqual(
                    (source.workspace_mirror, source.packaged_mirror),
                    source.mirrors,
                )
                self.assertTrue(seen_mirrors.isdisjoint(source.mirrors))
                seen_mirrors.update(source.mirrors)

    def test_repository_mirrors_are_byte_for_byte_in_sync(self) -> None:
        self.assertEqual([], find_adapter_drift(ROOT))


class AdapterSyncTests(unittest.TestCase):
    def populate_adapter_tree(self, root: Path) -> None:
        for index, source in enumerate(ADAPTER_SOURCES):
            content = f"canonical adapter content {index}\n".encode()
            canonical = root / source.canonical
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_bytes(content)
            for mirror_path in source.mirrors:
                mirror = root / mirror_path
                mirror.parent.mkdir(parents=True, exist_ok=True)
                mirror.write_bytes(content)

    def test_drift_detection_and_repair_cover_changed_and_missing_mirrors(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-adapter-sync-") as tmp:
            root = Path(tmp)
            self.populate_adapter_tree(root)
            changed_source = ADAPTER_SOURCES[0]
            missing_source = ADAPTER_SOURCES[1]
            (root / changed_source.workspace_mirror).write_bytes(b"drift\n")
            (root / missing_source.packaged_mirror).unlink()

            drift = find_adapter_drift(root)
            self.assertEqual(
                {
                    (changed_source.workspace_mirror, "different"),
                    (missing_source.packaged_mirror, "missing"),
                },
                {(issue.mirror, issue.reason) for issue in drift},
            )

            repaired = sync_adapter_mirrors(root)

            self.assertEqual(
                {
                    changed_source.workspace_mirror,
                    missing_source.packaged_mirror,
                },
                set(repaired),
            )
            self.assertEqual([], find_adapter_drift(root))

    def test_sync_script_check_reports_drift_and_write_repairs_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-adapter-script-") as tmp:
            root = Path(tmp)
            self.populate_adapter_tree(root)
            drifted = ADAPTER_SOURCES[-1].packaged_mirror
            (root / drifted).write_bytes(b"out of date\n")

            check = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), "--check", "--root", str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(1, check.returncode)
            self.assertIn(f"DRIFT {drifted}", check.stderr)

            write = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), "--write", "--root", str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, write.returncode, write.stderr)
            self.assertIn(f"UPDATED {drifted}", write.stdout)

            recheck = subprocess.run(
                [sys.executable, str(SYNC_SCRIPT), "--check", "--root", str(root)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, recheck.returncode, recheck.stderr)
            self.assertIn("PASS adapter mirrors are in sync", recheck.stdout)


class AdapterInstallSourceTests(unittest.TestCase):
    def test_source_checkout_install_reads_canonical_adapter_files(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-adapter-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-adapter-target-") as target_tmp,
        ):
            source_root = Path(source_tmp)
            target_root = Path(target_tmp)
            expected: dict[str, bytes] = {}
            for index, source in enumerate(ADAPTER_SOURCES):
                canonical_content = f"canonical adapter file {index}\n".encode()
                canonical = source_root / source.canonical
                canonical.parent.mkdir(parents=True, exist_ok=True)
                canonical.write_bytes(canonical_content)
                stale_mirror = source_root / source.workspace_mirror
                stale_mirror.parent.mkdir(parents=True, exist_ok=True)
                stale_mirror.write_bytes(b"stale workspace mirror\n")
                expected[source.install_target] = canonical_content

            report = install_adapters(
                source_root,
                target_root,
                ["all"],
            )

            self.assertEqual(list(EXPECTED_TARGETS), report.adapters)
            for target, content in expected.items():
                self.assertEqual(content, (target_root / target).read_bytes())

    def test_packaged_templates_remain_the_install_fallback(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-empty-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-adapter-target-") as target_tmp,
        ):
            source_root = Path(source_tmp)
            target_root = Path(target_tmp)

            install_adapters(source_root, target_root, ["all"])

            for source in ADAPTER_SOURCES:
                with self.subTest(target=source.install_target):
                    self.assertEqual(
                        (ROOT / source.packaged_mirror).read_bytes(),
                        (target_root / source.install_target).read_bytes(),
                    )


if __name__ == "__main__":
    unittest.main()
