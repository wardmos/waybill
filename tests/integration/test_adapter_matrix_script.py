"""Integration tests for the adapter quality-matrix CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_adapter_matrix import (
    conformance_report,
    create_source_repository,
    _commit_source,
)
from waybill_core.adapter_matrix import (
    ADAPTER_ENTRYPOINT_PATHS,
    CAPABILITY_SCENARIO_REQUIREMENTS,
    compute_source_provenance,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "adapter-matrix.py"
SYNTHETIC_AGENT_VERSION = "999.0.0-test-only"


class AdapterMatrixScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="waybill-adapter-matrix-script-"
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "source"
        create_source_repository(self.source_root)

    def _fake_executable(
        self,
        name: str,
        *,
        version_output: str,
        help_output: str = "",
    ) -> tuple[Path, Path]:
        executable = self.root / name
        model_marker = self.root / f"{name}-model-invoked"
        executable.write_text(
            f"""#!{sys.executable}
import pathlib
import sys

if "--version" in sys.argv:
    print({version_output!r})
    raise SystemExit(0)
if "--help" in sys.argv:
    print({help_output!r})
    raise SystemExit(0)
pathlib.Path({str(model_marker)!r}).touch()
raise SystemExit(0)
""",
            encoding="utf-8",
        )
        executable.chmod(0o755)
        return executable, model_marker

    def _report(
        self,
        adapter: str,
        capability: str,
        executable: Path,
        version: str,
        *,
        success: bool = True,
        scenarios: list[str] | None = None,
        identity_sha256: str | None = None,
        execution_mode: str | None = None,
    ) -> Path:
        executable_digest = (
            identity_sha256
            or "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
        )
        provenance = compute_source_provenance(
            self.source_root,
            adapter=adapter,
            capability=capability,
        ).to_dict()
        document = conformance_report(
            adapter,
            capability,
            provenance,
            success=success,
            scenarios=scenarios,
            identity_sha256=executable_digest,
            identity_version=version,
        )
        if execution_mode is not None:
            document["execution_mode"] = execution_mode
        report = self.root / f"{adapter}-{capability}.json"
        report.write_text(json.dumps(document), encoding="utf-8")
        return report

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--source-root",
                str(self.source_root),
                *arguments,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_public_full_matrix_uses_result_and_source_bound_reports(self) -> None:
        specifications = {
            "claude-code": (
                "claude",
                f"{SYNTHETIC_AGENT_VERSION} (Claude Code)",
                "",
                SYNTHETIC_AGENT_VERSION,
            ),
            "codex": (
                "codex",
                f"codex-cli {SYNTHETIC_AGENT_VERSION}",
                "",
                SYNTHETIC_AGENT_VERSION,
            ),
            "opencode": (
                "opencode",
                SYNTHETIC_AGENT_VERSION,
                "OpenCode help",
                SYNTHETIC_AGENT_VERSION,
            ),
            "cursor": (
                "agent",
                f"Cursor Agent {SYNTHETIC_AGENT_VERSION}",
                "",
                SYNTHETIC_AGENT_VERSION,
            ),
            "gemini-cli": (
                "gemini",
                SYNTHETIC_AGENT_VERSION,
                "Gemini CLI help",
                SYNTHETIC_AGENT_VERSION,
            ),
        }
        arguments: list[str] = ["--public"]
        markers: list[Path] = []
        for adapter, (name, version_output, help_text, version) in specifications.items():
            executable, marker = self._fake_executable(
                name,
                version_output=version_output,
                help_output=help_text,
            )
            arguments.extend(["--executable", f"{adapter}={executable}"])
            markers.append(marker)
            for capability, required in (
                ("export", adapter in {"claude-code", "codex"}),
                ("import", True),
            ):
                if required:
                    report = self._report(adapter, capability, executable, version)
                    arguments.extend(["--report", str(report)])

        completed = self._run(*arguments)

        self.assertEqual(0, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["identity_success"])
        self.assertTrue(report["success"])
        self.assertNotIn(str(self.root), completed.stdout)
        self.assertNotIn("report_path", completed.stdout)
        self.assertIn("runner_contract_sha256", completed.stdout)
        self.assertTrue(all(not marker.exists() for marker in markers))

    def test_cli_rejects_deleted_result_field_before_identity_probe(self) -> None:
        codex, marker = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        report = self._report(
            "codex", "import", codex, SYNTHETIC_AGENT_VERSION
        )
        document = json.loads(report.read_text(encoding="utf-8"))
        del document["results"][0]["effects_match"]
        report.write_text(json.dumps(document), encoding="utf-8")

        completed = self._run(
            "--adapter",
            "codex",
            "--executable",
            f"codex={codex}",
            "--report",
            str(report),
            "--public",
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("result missing fields: effects_match", completed.stderr)
        self.assertNotIn(str(self.root), completed.stderr)
        self.assertFalse(marker.exists())

    def test_cli_rejects_flipped_export_gate(self) -> None:
        codex, marker = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        report = self._report(
            "codex", "export", codex, SYNTHETIC_AGENT_VERSION
        )
        document = json.loads(report.read_text(encoding="utf-8"))
        document["results"][0]["gates"]["ready"] = False
        report.write_text(json.dumps(document), encoding="utf-8")

        completed = self._run(
            "--adapter",
            "codex",
            "--executable",
            f"codex={codex}",
            "--report",
            str(report),
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("passed does not match derived export outcome", completed.stderr)
        self.assertFalse(marker.exists())

    def test_clean_source_drift_fails_matrix_without_model_call(self) -> None:
        codex, marker = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        report = self._report(
            "codex", "import", codex, SYNTHETIC_AGENT_VERSION
        )
        entrypoint = self.source_root / ADAPTER_ENTRYPOINT_PATHS["codex"]
        entrypoint.write_text("changed adapter\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.source_root), "add", "."],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _commit_source(self.source_root, "change adapter")

        completed = self._run(
            "--adapter",
            "codex",
            "--executable",
            f"codex={codex}",
            "--report",
            str(report),
            "--public",
        )

        self.assertEqual(1, completed.returncode, completed.stderr)
        matrix = json.loads(completed.stdout)
        imported = next(
            item
            for item in matrix["entries"][0]["capabilities"]
            if item["capability"] == "import"
        )
        self.assertEqual("source_mismatch", imported["status"])
        self.assertFalse(imported["evidence_source_match"])
        self.assertFalse(marker.exists())

    def test_partial_and_v1_reports_are_rejected_fail_closed(self) -> None:
        codex, marker = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        partial = self._report(
            "codex",
            "import",
            codex,
            SYNTHETIC_AGENT_VERSION,
            scenarios=["ordinary-unfinished"],
        )
        completed = self._run("--report", str(partial), "--public")
        self.assertEqual(2, completed.returncode)
        self.assertIn("scenario coverage mismatch", completed.stderr)

        legacy = self._report(
            "codex", "import", codex, SYNTHETIC_AGENT_VERSION
        )
        document = json.loads(legacy.read_text(encoding="utf-8"))
        document["schema_version"] = "1"
        legacy.write_text(json.dumps(document), encoding="utf-8")
        completed = self._run("--report", str(legacy), "--public")
        self.assertEqual(2, completed.returncode)
        self.assertIn("schema_version must be '2'", completed.stderr)
        self.assertFalse(marker.exists())

    def test_identity_only_rejects_grok_without_source_provenance(self) -> None:
        agent, marker = self._fake_executable(
            "agent",
            version_output=f"grok {SYNTHETIC_AGENT_VERSION} [test]",
        )

        completed = self._run(
            "--adapter",
            "cursor",
            "--executable",
            f"cursor={agent}",
            "--identity-only",
            "--public",
        )

        self.assertEqual(1, completed.returncode)
        identity = json.loads(completed.stdout)["entries"][0]["identity"]
        self.assertEqual("identity_mismatch", identity["status"])
        self.assertEqual("grok", identity["product"])
        self.assertFalse(marker.exists())

    def test_private_output_only_adds_report_path_not_source_path(self) -> None:
        codex, _ = self._fake_executable(
            "codex",
            version_output=f"codex-cli {SYNTHETIC_AGENT_VERSION}",
        )
        report_path = self._report(
            "codex", "import", codex, SYNTHETIC_AGENT_VERSION
        )

        completed = self._run(
            "--adapter",
            "codex",
            "--executable",
            f"codex={codex}",
            "--report",
            str(report_path),
        )

        self.assertEqual(1, completed.returncode, completed.stderr)
        report = json.loads(completed.stdout)
        imported = next(
            item
            for item in report["entries"][0]["capabilities"]
            if item["capability"] == "import"
        )
        self.assertEqual(
            str(report_path.resolve()),
            imported["evidence"]["report_path"],
        )
        self.assertNotIn("source_root", completed.stdout)
        self.assertNotIn(str(self.source_root), completed.stdout)

    def test_naked_result_flag_is_rejected(self) -> None:
        completed = self._run("--result", "codex:import=passed")
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments: --result", completed.stderr)

    def test_smoke_dry_run_still_uses_identity_only_without_model_call(self) -> None:
        agent, marker = self._fake_executable(
            "agent",
            version_output=f"Cursor Agent {SYNTHETIC_AGENT_VERSION}",
        )
        environment = dict(os.environ)
        environment["WAYBILL_CURSOR_BINARY"] = str(agent)

        completed = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "smoke-agents.sh"),
                "--tool",
                "cursor",
                "--dry-run",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("adapter-matrix.py", completed.stdout)
        self.assertIn("--identity-only", completed.stdout)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
