"""Unit tests for fail-closed agent executable identity probes."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from waybill_core.agent_identity import probe_agent_identity


SYNTHETIC_AGENT_VERSION = ".".join(("999", "0", "0")) + "-test-only"


class AgentIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-agent-identity-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def _fake_executable(
        self,
        name: str,
        *,
        version_output: str,
        help_output: str = "",
        version_exit: int = 0,
    ) -> Path:
        path = self.root / name
        path.write_text(
            f"""#!{sys.executable}
import sys

if "--version" in sys.argv:
    print({version_output!r})
    raise SystemExit({version_exit})
if "--help" in sys.argv:
    print({help_output!r})
    raise SystemExit(0)
raise SystemExit(97)
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def test_probe_resolves_realpath_hash_product_version_and_time(self) -> None:
        target = self._fake_executable(
            "codex-real",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        link = self.root / "codex"
        try:
            link.symlink_to(target.name)
        except OSError as exc:
            self.skipTest(f"symbolic links are unavailable: {exc}")

        identity = probe_agent_identity(
            "codex",
            executable=str(link),
            observed_at="2026-07-01T12:34:56Z",
        )

        expected_hash = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertEqual("verified", identity.status)
        self.assertEqual(target.resolve(), identity.resolved_path)
        self.assertEqual(expected_hash, identity.sha256)
        self.assertEqual("codex", identity.product)
        self.assertEqual(SYNTHETIC_AGENT_VERSION, identity.version)
        self.assertEqual("2026-07-01T12:34:56Z", identity.observed_at)

        public = identity.to_dict(include_private=False)
        private = identity.to_dict(include_private=True)
        self.assertEqual("executable", public["identity_kind"])
        self.assertNotIn("resolved_path", public)
        self.assertNotIn("requested_executable", public)
        self.assertNotIn("executable_name", public)
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertEqual(str(target.resolve()), private["resolved_path"])
        self.assertEqual(str(link), private["requested_executable"])
        self.assertIn("codex-cli", private["version_output"])

    def test_cursor_probe_rejects_grok_even_when_binary_is_named_agent(self) -> None:
        agent = self._fake_executable(
            "agent",
            version_output=f"grok {SYNTHETIC_AGENT_VERSION} [test]",
        )

        identity = probe_agent_identity(
            "cursor",
            executable=str(agent),
            observed_at="2026-07-01T12:34:56Z",
        )

        self.assertEqual("identity_mismatch", identity.status)
        self.assertEqual("grok", identity.product)
        self.assertEqual(SYNTHETIC_AGENT_VERSION, identity.version)
        self.assertEqual("unexpected_product", identity.error_code)

    def test_numeric_version_uses_branded_help_to_verify_opencode(self) -> None:
        opencode = self._fake_executable(
            "opencode",
            version_output=SYNTHETIC_AGENT_VERSION,
            help_output="OpenCode - terminal coding agent",
        )

        identity = probe_agent_identity(
            "opencode",
            executable=str(opencode),
            observed_at="2026-07-01T12:34:56Z",
        )

        self.assertEqual("verified", identity.status)
        self.assertEqual("opencode", identity.product)
        self.assertEqual(SYNTHETIC_AGENT_VERSION, identity.version)
        self.assertIn("OpenCode", identity.identity_output)

    def test_all_supported_products_are_recognized_from_fake_executables(self) -> None:
        cases = {
            "claude-code": (
                "claude",
                f"{SYNTHETIC_AGENT_VERSION} (Claude Code)",
                "",
            ),
            "codex": (
                "codex",
                f"codex-cli {SYNTHETIC_AGENT_VERSION}",
                "",
            ),
            "opencode": (
                "opencode",
                SYNTHETIC_AGENT_VERSION,
                "OpenCode help",
            ),
            "cursor": (
                "agent",
                f"Cursor Agent {SYNTHETIC_AGENT_VERSION}",
                "",
            ),
            "gemini-cli": (
                "gemini",
                SYNTHETIC_AGENT_VERSION,
                "Gemini CLI help",
            ),
        }

        for adapter, (name, version, help_text) in cases.items():
            with self.subTest(adapter=adapter):
                executable = self._fake_executable(
                    f"{name}-{adapter}",
                    version_output=version,
                    help_output=help_text,
                )
                identity = probe_agent_identity(
                    adapter,
                    executable=str(executable),
                    observed_at="2026-07-01T12:34:56Z",
                )
                self.assertEqual("verified", identity.status, identity)
                self.assertEqual(adapter, identity.product)

    def test_missing_and_failed_probes_do_not_guess_identity(self) -> None:
        missing = probe_agent_identity(
            "gemini-cli",
            executable=str(self.root / "missing"),
            observed_at="2026-07-01T12:34:56Z",
        )
        self.assertEqual("missing", missing.status)
        self.assertIsNone(missing.product)
        self.assertIsNone(missing.sha256)

        failed_executable = self._fake_executable(
            "claude",
            version_output="Claude Code unavailable",
            version_exit=3,
        )
        failed = probe_agent_identity(
            "claude-code",
            executable=str(failed_executable),
            observed_at="2026-07-01T12:34:56Z",
        )
        self.assertEqual("probe_failed", failed.status)
        self.assertIsNone(failed.product)
        self.assertEqual("version_probe_failed", failed.error_code)

    def test_path_lookup_uses_supplied_environment(self) -> None:
        codex = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        environment = dict(os.environ)
        environment["PATH"] = str(self.root)

        identity = probe_agent_identity(
            "codex",
            executable="codex",
            environment=environment,
            observed_at="2026-07-01T12:34:56Z",
        )

        self.assertEqual("verified", identity.status)
        self.assertEqual(codex.resolve(), identity.resolved_path)


if __name__ == "__main__":
    unittest.main()
