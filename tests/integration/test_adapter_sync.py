"""Tests for canonical adapter sources and generated distributions."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from waybill_core import adapter_sources
from waybill_core.adapter_bundles import (
    ADAPTER_BUNDLE_SOURCES,
    BUNDLE_ADAPTERS,
    build_adapter_bundles,
    bundle_sources_for_adapter,
)
from waybill_core.adapter_sources import (
    ADAPTER_SOURCES,
    CANONICAL_SKILL_ROOT,
    SHARED_RESOURCE_PATHS,
    sources_for_adapter,
)
from waybill_core.install import install_adapters


ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build-adapters.py"

EXPECTED_TARGETS = {
    "claude-code": (
        ".claude/skills/handoff/SKILL.md",
        ".claude/skills/handoff/references/dispatch.md",
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
        ".opencode/skills/handoff/references/dispatch.md",
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
        ".cursor/rules/waybill-handoff/references/dispatch.md",
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
        ".gemini/skills/handoff/references/dispatch.md",
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
    def test_retired_sync_entrypoint_is_absent(self) -> None:
        self.assertFalse((ROOT / "scripts" / "sync-adapters.py").exists())

    def test_manifest_maps_canonical_resources_and_thin_wrappers(self) -> None:
        actual_targets = {
            adapter: tuple(source.install_target for source in sources_for_adapter(adapter))
            for adapter in EXPECTED_TARGETS
        }
        self.assertEqual(EXPECTED_TARGETS, actual_targets)

        for source in ADAPTER_SOURCES:
            with self.subTest(canonical=source.canonical):
                self.assertTrue(
                    source.canonical.startswith("skills/handoff/")
                    or source.canonical.startswith(f"adapters/{source.adapter}/")
                )
                self.assertFalse(Path(source.bundle_target).is_absolute())

    def test_shared_resources_are_packaged_once_from_the_canonical_skill(self) -> None:
        shared = [
            source
            for source in ADAPTER_SOURCES
            if source.canonical.startswith(f"{CANONICAL_SKILL_ROOT}/")
        ]

        self.assertEqual(len(SHARED_RESOURCE_PATHS) * 4, len(shared))
        self.assertEqual(
            set(SHARED_RESOURCE_PATHS),
            {
                source.canonical.removeprefix(f"{CANONICAL_SKILL_ROOT}/")
                for source in shared
            },
        )


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
                expected[source.install_target] = canonical_content

            report = install_adapters(
                source_root,
                target_root,
                ["all"],
            )

            self.assertEqual(list(EXPECTED_TARGETS), report.adapters)
            for target, content in expected.items():
                self.assertEqual(content, (target_root / target).read_bytes())

    def test_canonical_packages_remain_the_install_fallback(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="waybill-empty-source-") as source_tmp,
            tempfile.TemporaryDirectory(prefix="waybill-adapter-target-") as target_tmp,
        ):
            source_root = Path(source_tmp)
            target_root = Path(target_tmp)

            with (
                mock.patch.object(
                    adapter_sources,
                    "PACKAGE_SKILL_ROOT",
                    ROOT / CANONICAL_SKILL_ROOT,
                ),
                mock.patch.object(
                    adapter_sources,
                    "PACKAGE_ADAPTER_ROOT",
                    ROOT / "adapters",
                ),
            ):
                install_adapters(source_root, target_root, ["all"])

            for source in ADAPTER_SOURCES:
                with self.subTest(target=source.install_target):
                    expected = ROOT / source.canonical
                    self.assertEqual(
                        expected.read_bytes(),
                        (target_root / source.install_target).read_bytes(),
                    )


class AdapterBundleBuildTests(unittest.TestCase):
    def test_builds_complete_standalone_adapters_from_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-adapter-build-") as tmp:
            output = Path(tmp) / "adapters"

            report = build_adapter_bundles(ROOT, output)

            expected_files = {
                f"{source.adapter}/{source.target}"
                for source in ADAPTER_BUNDLE_SOURCES
            }
            self.assertEqual(expected_files, set(report.files))
            self.assertEqual(set(BUNDLE_ADAPTERS), {path.name for path in output.iterdir()})
            for adapter in BUNDLE_ADAPTERS:
                sources = bundle_sources_for_adapter(adapter)
                self.assertTrue(sources)
                for source in sources:
                    with self.subTest(adapter=adapter, target=source.target):
                        generated = output / adapter / source.target
                        self.assertFalse(generated.is_symlink())
                        self.assertEqual(
                            (ROOT / source.canonical).read_bytes(),
                            generated.read_bytes(),
                        )

            with self.assertRaises(FileExistsError):
                build_adapter_bundles(ROOT, output)

    def test_build_script_replaces_only_generated_dist_directories(self) -> None:
        (ROOT / "dist").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="waybill-adapter-cli-", dir=ROOT / "dist"
        ) as tmp:
            output = Path(tmp) / "adapters"
            first = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, first.returncode, first.stderr)

            without_replace = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(1, without_replace.returncode)
            self.assertIn("already exists", without_replace.stderr)

            with_replace = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--output",
                    str(output),
                    "--replace",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, with_replace.returncode, with_replace.stderr)
            self.assertTrue((output / "codex/skills/handoff/SKILL.md").is_file())

    def test_build_script_does_not_follow_output_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="waybill-adapter-symlink-") as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            output = root / "output"
            try:
                output.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--output",
                    str(output),
                    "--replace",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("not a regular directory", result.stderr)
            self.assertEqual("keep\n", sentinel.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
