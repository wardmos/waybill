"""Tests for shared bounded agent execution helpers."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

from pathlib import Path

from waybill_core.agent_execution import classify_environment_block, execute_agent


class EnvironmentBlockClassificationTests(unittest.TestCase):
    def test_classifies_known_namespace_startup_failures(self) -> None:
        cases = (
            (
                b"",
                b"bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\n",
                "network-namespace",
            ),
            (
                b"",
                b"bwrap: cannot create user namespace: Operation not permitted\n",
                "user-namespace",
            ),
            (
                b"",
                (
                    b"bwrap: No permissions to create a new namespace, likely "
                    b"because the kernel does not allow non-privileged user "
                    b"namespaces.\n"
                ),
                "user-namespace",
            ),
        )
        for stdout, stderr, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    expected,
                    classify_environment_block(stdout=stdout, stderr=stderr),
                )

    def test_does_not_classify_an_ordinary_agent_failure(self) -> None:
        self.assertIsNone(
            classify_environment_block(
                stdout=b"",
                stderr=b"project validation failed: missing metadata.json\n",
            )
        )

    def test_does_not_trust_namespace_text_from_agent_stdout(self) -> None:
        self.assertIsNone(
            classify_environment_block(
                stdout=(
                    b"analysis: kernel does not allow non-privileged user namespaces\n"
                ),
                stderr=b"",
            )
        )

    def test_does_not_classify_unprefixed_namespace_diagnostic(self) -> None:
        self.assertIsNone(
            classify_environment_block(
                stdout=b"",
                stderr=b"no permissions to create a new namespace\n",
            )
        )

    def test_executor_rejects_invalid_limits_before_starting_a_process(self) -> None:
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            execute_agent(
                ["unused"],
                cwd=Path.cwd(),
                prompt="",
                timeout_seconds=0,
                environment={},
                output_limit_bytes=1,
            )

    def test_timeout_covers_blocked_prompt_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            execution = execute_agent(
                [sys.executable, "-c", "import time; time.sleep(0.6)"],
                cwd=Path(temporary),
                prompt="x" * (2 * 1024 * 1024),
                timeout_seconds=0.05,
                environment=os.environ.copy(),
                output_limit_bytes=1024,
            )

        self.assertTrue(execution.timed_out)

    def test_timeout_terminates_a_descendant_before_it_can_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "late-descendant-write.txt"
            child = (
                "import time; from pathlib import Path; "
                f"time.sleep(0.8); Path({str(marker)!r}).write_text('late')"
            )
            parent = (
                "import subprocess, time; "
                f"subprocess.Popen([{sys.executable!r}, '-c', {child!r}]); "
                "time.sleep(5)"
            )

            execution = execute_agent(
                [sys.executable, "-c", parent],
                cwd=root,
                prompt="",
                timeout_seconds=0.1,
                environment=os.environ.copy(),
                output_limit_bytes=1024,
            )
            time.sleep(1.0)

            self.assertTrue(execution.timed_out)
            self.assertFalse(marker.exists())

    def test_completed_parent_reports_and_terminates_a_live_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "residual-descendant-write.txt"
            child = (
                "import time; from pathlib import Path; "
                f"time.sleep(0.8); Path({str(marker)!r}).write_text('late')"
            )
            parent = (
                "import subprocess; "
                f"subprocess.Popen([{sys.executable!r}, '-c', {child!r}])"
            )

            execution = execute_agent(
                [sys.executable, "-c", parent],
                cwd=root,
                prompt="",
                timeout_seconds=2,
                environment=os.environ.copy(),
                output_limit_bytes=1024,
            )
            time.sleep(1.0)

            self.assertTrue(execution.residual_process_detected)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
