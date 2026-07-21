"""Unit tests for the isolated wheel-install verification script."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "test-wheel-install.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("waybill_wheel_install_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load wheel-install verification script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WheelInstallScriptTests(unittest.TestCase):
    def test_copy_uses_a_clean_temporary_source_tree(self) -> None:
        module = load_script()
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            source = root / "source"
            destination = root / "copy"
            source.mkdir()
            for name in ["LICENSE", "MANIFEST.in", "README.md", "pyproject.toml"]:
                (source / name).write_text(f"{name}\n", encoding="utf-8")
            package = source / "waybill_core"
            package.mkdir()
            (package / "__init__.py").write_text("package\n", encoding="utf-8")
            for ignored in [
                ".git",
                ".waybill",
                ".waybill-redacted",
                "build",
                "dist",
                "agent_waybill.egg-info",
                "__pycache__",
            ]:
                path = source / ignored
                path.mkdir()
                (path / "marker").write_text("private or generated\n", encoding="utf-8")
            node_modules = source / ".opencode" / "node_modules" / "package"
            node_modules.mkdir(parents=True)
            (node_modules / "index.js").write_text("generated\n", encoding="utf-8")
            (source / "unrelated-local-file.txt").write_text("private\n", encoding="utf-8")

            module.copy_source_tree(source, destination)

            self.assertEqual(
                {"LICENSE", "MANIFEST.in", "README.md", "pyproject.toml", "waybill_core"},
                {path.name for path in destination.iterdir()},
            )
            self.assertEqual("pyproject.toml\n", (destination / "pyproject.toml").read_text())
            self.assertEqual("package\n", (destination / "waybill_core/__init__.py").read_text())
            for ignored in [
                ".git",
                ".waybill",
                ".waybill-redacted",
                "build",
                "dist",
                "agent_waybill.egg-info",
                "__pycache__",
            ]:
                self.assertFalse((destination / ignored).exists(), ignored)
            self.assertFalse((destination / ".opencode/node_modules").exists())
            self.assertFalse((destination / "unrelated-local-file.txt").exists())

    def test_copy_rejects_symlinks_inside_packaged_sources(self) -> None:
        module = load_script()
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            source = root / "source"
            destination = root / "copy"
            package = source / "waybill_core"
            package.mkdir(parents=True)
            for name in ["LICENSE", "MANIFEST.in", "README.md", "pyproject.toml"]:
                (source / name).write_text(f"{name}\n", encoding="utf-8")
            outside = root / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            try:
                (package / "linked.py").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")

            with self.assertRaises(module.WheelVerificationError):
                module.copy_source_tree(source, destination)

    def test_subprocess_environment_cannot_import_from_source_overrides(self) -> None:
        module = load_script()
        environment = module.isolated_environment(
            {
                "PATH": os.defpath,
                "PYTHONPATH": "/untrusted/source",
                "PYTHONHOME": "/untrusted/runtime",
                "PYTHONSTARTUP": "/untrusted/startup.py",
            }
        )

        self.assertEqual(os.defpath, environment["PATH"])
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("PYTHONHOME", environment)
        self.assertNotIn("PYTHONSTARTUP", environment)
        self.assertEqual("1", environment["PYTHONNOUSERSITE"])
        self.assertEqual("1", environment["PYTHONSAFEPATH"])

    def test_cli_json_parser_is_strict(self) -> None:
        module = load_script()

        self.assertEqual({"success": True}, module.parse_json_object('{"success":true}'))
        for invalid in [
            "[]",
            '{"success":true,"success":false}',
            '{"success":NaN}',
            "not json",
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    module.parse_json_object(invalid)


if __name__ == "__main__":
    unittest.main()
