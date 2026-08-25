"""Tests for shared bounded agent execution helpers."""

from __future__ import annotations

import os
import sys
import tempfile
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
                b"cannot create user namespace: Operation not permitted\n",
                b"",
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


if __name__ == "__main__":
    unittest.main()
