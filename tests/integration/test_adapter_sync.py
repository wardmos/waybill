"""Tests for canonical adapter sources and generated mirrors."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from waybill_core.adapter_sources import (
    ADAPTER_SOURCES,
    MIRROR_SOURCES,
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
        ".claude/skills/handoff/references/bundle-format.md",
        ".claude/skills/handoff/references/export.md",
        ".claude/skills/handoff/references/import.md",
        ".claude/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".claude/skills/handoff/assets/bundle-template/metadata.json",
        ".claude/skills/handoff/assets/bundle-template/diff.patch",
        ".claude/skills/handoff/assets/bundle-template/commands.log",
        ".claude/skills/handoff/assets/bundle-template/test-summary.md",
        ".claude/skills/handoff/scripts/check_bundle.py",
        ".claude/skills/waybill/SKILL.md",
    ),
    "opencode": (
        ".opencode/commands/handoff.md",
        ".opencode/commands/waybill.md",
        ".opencode/skills/handoff/SKILL.md",
        ".opencode/skills/handoff/references/bundle-format.md",
        ".opencode/skills/handoff/references/export.md",
        ".opencode/skills/handoff/references/import.md",
        ".opencode/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".opencode/skills/handoff/assets/bundle-template/metadata.json",
        ".opencode/skills/handoff/assets/bundle-template/diff.patch",
        ".opencode/skills/handoff/assets/bundle-template/commands.log",
        ".opencode/skills/handoff/assets/bundle-template/test-summary.md",
        ".opencode/skills/handoff/scripts/check_bundle.py",
        ".opencode/skills/waybill/SKILL.md",
    ),
    "cursor": (
        ".cursor/rules/handoff.mdc",
        ".cursor/rules/waybill-handoff/references/bundle-format.md",
        ".cursor/rules/waybill-handoff/references/export.md",
        ".cursor/rules/waybill-handoff/references/import.md",
        ".cursor/rules/waybill-handoff/assets/bundle-template/WAYBILL.md",
        ".cursor/rules/waybill-handoff/assets/bundle-template/metadata.json",
        ".cursor/rules/waybill-handoff/assets/bundle-template/diff.patch",
        ".cursor/rules/waybill-handoff/assets/bundle-template/commands.log",
        ".cursor/rules/waybill-handoff/assets/bundle-template/test-summary.md",
        ".cursor/rules/waybill-handoff/scripts/check_bundle.py",
        ".cursor/rules/waybill.mdc",
    ),
    "gemini-cli": (
        ".gemini/skills/handoff/SKILL.md",
        ".gemini/skills/handoff/references/bundle-format.md",
        ".gemini/skills/handoff/references/export.md",
        ".gemini/skills/handoff/references/import.md",
        ".gemini/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".gemini/skills/handoff/assets/bundle-template/metadata.json",
        ".gemini/skills/handoff/assets/bundle-template/diff.patch",
        ".gemini/skills/handoff/assets/bundle-template/commands.log",
        ".gemini/skills/handoff/assets/bundle-template/test-summary.md",
        ".gemini/skills/handoff/scripts/check_bundle.py",
        ".gemini/skills/waybill/SKILL.md",
    ),
}


class AdapterSourceManifestTests(unittest.TestCase):
    def test_manifest_maps_shared_references_and_thin_wrappers(self) -> None:
        actual_targets = {
            adapter: tuple(source.install_target for source in sources_for_adapter(adapter))
            for adapter in EXPECTED_TARGETS
        }
        self.assertEqual(EXPECTED_TARGETS, actual_targets)

        seen_mirrors: set[str] = set()
        for source in ADAPTER_SOURCES:
            with self.subTest(canonical=source.canonical):
                self.assertEqual(
                    f"waybill_core/template-files/{source.install_target}",
                    source.packaged_mirror,
                )
                if source.canonical.startswith("skills/handoff/"):
                    self.assertIsNotNone(source.repository_mirror)
                    assert source.repository_mirror is not None
                    self.assertTrue(
                        source.repository_mirror.startswith(
                            f"adapters/{source.adapter}/"
                        )
                    )
                    self.assertEqual(
                        (source.repository_mirror, source.packaged_mirror),
                        source.mirrors,
                    )
                else:
                    self.assertTrue(
                        source.canonical.startswith(f"adapters/{source.adapter}/")
                    )
                    self.assertIsNone(source.repository_mirror)
                    self.assertEqual((source.packaged_mirror,), source.mirrors)
                self.assertTrue(seen_mirrors.isdisjoint(source.mirrors))
                seen_mirrors.update(source.mirrors)

        self.assertTrue(
            all(
                not mirror.startswith((".claude/", ".cursor/", ".gemini/", ".opencode/"))
                for mirror in seen_mirrors
            )
        )

    def test_codex_resources_are_generated_from_the_shared_skill(self) -> None:
        codex_mirrors = [
            source
            for source in MIRROR_SOURCES
            if any(path.startswith("adapters/codex/") for path in source.mirrors)
        ]
        self.assertEqual(9, len(codex_mirrors))
        self.assertTrue(
            all(
                source.canonical.startswith("skills/handoff/")
                for source in codex_mirrors
            )
        )

    def test_repository_mirrors_are_byte_for_byte_in_sync(self) -> None:
        self.assertEqual([], find_adapter_drift(ROOT))


class AdapterSyncTests(unittest.TestCase):
    def populate_adapter_tree(self, root: Path) -> None:
        contents: dict[str, bytes] = {}
        for source in MIRROR_SOURCES:
            content = contents.setdefault(
                source.canonical,
                f"canonical adapter content {len(contents)}\n".encode(),
            )
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
            changed_source = next(
                source for source in ADAPTER_SOURCES if source.repository_mirror
            )
            missing_source = ADAPTER_SOURCES[0]
            assert changed_source.repository_mirror is not None
            (root / changed_source.repository_mirror).write_bytes(b"drift\n")
            (root / missing_source.packaged_mirror).unlink()

            drift = find_adapter_drift(root)
            self.assertEqual(
                {
                    (changed_source.repository_mirror, "different"),
                    (missing_source.packaged_mirror, "missing"),
                },
                {(issue.mirror, issue.reason) for issue in drift},
            )

            repaired = sync_adapter_mirrors(root)

            self.assertEqual(
                {
                    changed_source.repository_mirror,
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
            canonical_contents: dict[str, bytes] = {}
            for source in ADAPTER_SOURCES:
                canonical_content = canonical_contents.setdefault(
                    source.canonical,
                    f"canonical adapter file {len(canonical_contents)}\n".encode(),
                )
                canonical = source_root / source.canonical
                canonical.parent.mkdir(parents=True, exist_ok=True)
                canonical.write_bytes(canonical_content)
                if source.repository_mirror is not None:
                    stale_mirror = source_root / source.repository_mirror
                    stale_mirror.parent.mkdir(parents=True, exist_ok=True)
                    stale_mirror.write_bytes(b"stale repository mirror\n")
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
