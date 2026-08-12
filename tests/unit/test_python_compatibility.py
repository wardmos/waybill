from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PythonCompatibilityTests(unittest.TestCase):
    def test_package_import_does_not_require_datetime_utc(self) -> None:
        script = """
import datetime

if hasattr(datetime, "UTC"):
    del datetime.UTC

import waybill_core
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
