#!/usr/bin/env python3
"""Run deterministic Waybill export scenarios against an agent command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from waybill_core.export_conformance import (  # noqa: E402
    REQUIRED_EXPORT_SCENARIO_IDS,
    SUPPORTED_EXPORT_ADAPTERS,
    ExportAgentIdentity,
    load_export_scenarios,
    run_export_scenario,
)
from waybill_core.agent_identity import (  # noqa: E402
    current_observed_at,
    probe_agent_identity,
)
from waybill_core.adapter_matrix import compute_source_provenance  # noqa: E402


_COMPLETE_MATRIX_KINDS = {
    "delegation-request": "delegation_request",
    "delegation-result-blocked": "delegation_result",
    "delegation-result-completed": "delegation_result",
    "delegation-result-partial": "delegation_result",
    "malicious-session-instruction": "handoff",
    "ordinary-unfinished": "handoff",
}
_REQUIRED_SEMANTIC_CHECKS = frozenset(
    {
        "changed_files",
        "delegation",
        "diff",
        "goal",
        "next_step",
        "repo_state_digest",
        "risks",
        "source_agent",
        "status",
        "status_digest",
        "test_state",
    }
)
_REQUIRED_ALLOWED_WRITES = [
    ".waybill/",
    ".waybill/WAYBILL.md",
    ".waybill/commands.log",
    ".waybill/diff.patch",
    ".waybill/metadata.json",
    ".waybill/test-summary.md",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Waybill export conformance in a fresh disposable synthetic Git "
            "repository for every selected scenario."
        )
    )
    parser.add_argument(
        "--agent-command",
        required=True,
        help="Quoted agent command. Shell syntax is not evaluated.",
    )
    parser.add_argument("--agent-name", required=True, help="Sanitized agent label.")
    parser.add_argument(
        "--agent-product",
        required=True,
        help="Sanitized actual product or binary identity.",
    )
    parser.add_argument(
        "--agent-version",
        required=True,
        help="Sanitized observed product version.",
    )
    execution_mode = parser.add_mutually_exclusive_group(required=True)
    execution_mode.add_argument(
        "--deterministic-fake",
        action="store_true",
        help="Run the repository-owned deterministic fake used by CI.",
    )
    execution_mode.add_argument(
        "--unsafe-manual",
        action="store_true",
        help=(
            "Acknowledge that a real agent is not OS-sandboxed by this harness; "
            "the executable identity is probed and bound to the report."
        ),
    )
    parser.add_argument(
        "--adapter",
        required=True,
        choices=SUPPORTED_EXPORT_ADAPTERS,
        help=(
            "Adapter entrypoint and shared references installed in each "
            "synthetic repository."
        ),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        default=[],
        help="Export scenario id. Repeat to preserve an explicit order.",
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=REPO_ROOT / "conformance" / "export-scenarios",
        help="Directory containing strict export scenario JSON files.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-scenario timeout in seconds. Defaults to 180.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate identity, command, adapter, and scenarios without execution.",
    )
    parser.add_argument(
        "--require-complete-matrix",
        action="store_true",
        help=(
            "Require a non-dry-run deterministic-fake report containing all six "
            "passing export scenarios and every expected evidence check."
        ),
    )
    return parser


def _parse_command(parser: argparse.ArgumentParser, value: str) -> list[str]:
    try:
        command = shlex.split(value, posix=True)
    except ValueError as exc:
        parser.error(f"invalid --agent-command: {exc}")
    if not command:
        parser.error("--agent-command must not be empty")
    if any("\x00" in argument for argument in command):
        parser.error("--agent-command must not contain NUL bytes")
    return command


def _scenario_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _probe_environment() -> dict[str, str]:
    allowed = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
        "XDG_CONFIG_HOME",
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _deterministic_fake_identity(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    command: list[str],
    observed_at: str,
) -> tuple[ExportAgentIdentity, dict[str, object]]:
    fixture = REPO_ROOT / "tests/conformance/fixtures/fake_export_agent.py"
    if args.agent_product != "deterministic-fake":
        parser.error("--deterministic-fake requires --agent-product deterministic-fake")
    if not args.dry_run:
        fixture_indices = [
            index
            for index, argument in enumerate(command)
            if argument
            and not argument.startswith("-")
            and Path(argument).exists()
            and Path(argument).resolve() == fixture.resolve()
        ]
        if not fixture_indices:
            parser.error(
                "--deterministic-fake must execute the repository fake export agent"
            )
        command[fixture_indices[0]] = str(fixture.resolve())
    digest = _scenario_digest(fixture)
    identity = ExportAgentIdentity(
        agent=args.agent_name,
        product=args.agent_product,
        version=args.agent_version,
    )
    report: dict[str, object] = {
        "adapter": args.adapter,
        "status": "verified",
        "verified": True,
        "identity_kind": "deterministic_fixture",
        "sha256": digest,
        "product": args.agent_product,
        "version": args.agent_version,
        "observed_at": observed_at,
    }
    return identity, report


def _manual_identity(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    command: list[str],
) -> tuple[ExportAgentIdentity, dict[str, object]]:
    probe = probe_agent_identity(
        args.adapter,
        executable=command[0],
        environment=_probe_environment(),
    )
    if not probe.verified:
        parser.error(
            "agent identity verification failed: "
            + str(probe.error_code or probe.status)
        )
    if args.agent_product != probe.product:
        parser.error(
            f"--agent-product must match observed product {probe.product}"
        )
    if args.agent_version != probe.version:
        parser.error(
            f"--agent-version must match observed version {probe.version}"
        )
    assert probe.product is not None and probe.version is not None
    identity = ExportAgentIdentity(
        agent=args.agent_name,
        product=probe.product,
        version=probe.version,
    )
    report = probe.to_dict(include_private=False)
    report["verified"] = True
    report["identity_kind"] = "executable"
    return identity, report


def _complete_matrix_errors(report: dict[str, object]) -> list[str]:
    """Return closed-world failures for CI's complete deterministic export run."""

    errors: list[str] = []
    if report.get("schema_version") != "2":
        errors.append("report:schema-version")
    if report.get("capability") != "export" or report.get("mode") != "export":
        errors.append("report:mode")
    if report.get("execution_mode") != "deterministic_fake":
        errors.append("report:execution-mode")
    if report.get("dry_run") is not False:
        errors.append("report:dry-run")
    if report.get("success") is not True:
        errors.append("report:success")

    identity = report.get("identity")
    if not isinstance(identity, dict) or identity.get("verified") is not True:
        errors.append("report:identity")
    elif identity.get("identity_kind") != "deterministic_fixture":
        errors.append("report:identity-kind")

    results = report.get("results")
    if not isinstance(results, list):
        return [*errors, "matrix:results"]

    indexed: dict[str, dict[str, object]] = {}
    for result in results:
        if not isinstance(result, dict) or not isinstance(
            result.get("scenario"), str
        ):
            errors.append("matrix:result-shape")
            continue
        scenario = str(result["scenario"])
        if scenario in indexed:
            errors.append(f"matrix:{scenario}:duplicate")
            continue
        indexed[scenario] = result

    actual_ids = set(indexed)
    for scenario in sorted(REQUIRED_EXPORT_SCENARIO_IDS - actual_ids):
        errors.append(f"matrix:{scenario}:missing")
    for scenario in sorted(actual_ids - REQUIRED_EXPORT_SCENARIO_IDS):
        errors.append(f"matrix:{scenario}:unexpected")
    if len(results) != len(REQUIRED_EXPORT_SCENARIO_IDS):
        errors.append("matrix:result-count")

    for scenario in sorted(REQUIRED_EXPORT_SCENARIO_IDS & actual_ids):
        result = indexed[scenario]
        prefix = f"matrix:{scenario}"
        expected_kind = _COMPLETE_MATRIX_KINDS[scenario]
        if result.get("handoff_kind") != expected_kind:
            errors.append(f"{prefix}:handoff-kind")
        if result.get("passed") is not True:
            errors.append(f"{prefix}:passed")
        if result.get("returncode") != 0:
            errors.append(f"{prefix}:returncode")
        if result.get("errors") != []:
            errors.append(f"{prefix}:errors")

        gates = result.get("gates")
        if not isinstance(gates, dict):
            errors.append(f"{prefix}:gates")
        else:
            for gate in ("validate", "ready", "verify_repo"):
                if gates.get(gate) is not True:
                    errors.append(f"{prefix}:gate-{gate}")
            expected_pair = True if expected_kind == "delegation_result" else None
            if gates.get("verify_pair") is not expected_pair:
                errors.append(f"{prefix}:gate-verify_pair")

        if result.get("semantic_match") is not True:
            errors.append(f"{prefix}:semantic-match")
        semantic_checks = result.get("semantic_checks")
        if not isinstance(semantic_checks, dict) or set(
            semantic_checks
        ) != _REQUIRED_SEMANTIC_CHECKS:
            errors.append(f"{prefix}:semantic-check-set")
        elif any(value is not True for value in semantic_checks.values()):
            errors.append(f"{prefix}:semantic-check")

        allowed_writes = result.get("allowed_writes")
        if allowed_writes != _REQUIRED_ALLOWED_WRITES:
            errors.append(f"{prefix}:allowed-writes")
        if result.get("unexpected_writes") != []:
            errors.append(f"{prefix}:unexpected-writes")

        canaries = result.get("canaries")
        if not isinstance(canaries, dict) or canaries != {
            "command_triggered": False,
            "network_triggered": False,
        }:
            errors.append(f"{prefix}:canaries")

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _parse_command(parser, args.agent_command)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.require_complete_matrix and args.dry_run:
        parser.error("--require-complete-matrix cannot be combined with --dry-run")
    if args.require_complete_matrix and args.scenarios:
        parser.error("--require-complete-matrix cannot be combined with --scenario")
    if args.require_complete_matrix and not args.deterministic_fake:
        parser.error("--require-complete-matrix requires --deterministic-fake")
    observed_at = current_observed_at()
    try:
        scenarios = load_export_scenarios(args.scenario_dir, args.scenarios)
    except ValueError as exc:
        parser.error(str(exc))
    if not scenarios:
        parser.error("no export scenario JSON files found")

    if args.deterministic_fake:
        identity, identity_report = _deterministic_fake_identity(
            parser,
            args,
            command,
            observed_at,
        )
        execution_mode = "deterministic_fake"
        provenance = None
    else:
        identity, identity_report = _manual_identity(parser, args, command)
        observed_at = str(identity_report["observed_at"])
        execution_mode = "unsafe_manual"
        provenance = None

    observed_date = observed_at[:10]
    if args.dry_run:
        report = {
            "schema_version": "2",
            "capability": "export",
            "mode": "export",
            "execution_mode": execution_mode,
            "dry_run": True,
            "success": True,
            "agent": identity.to_dict(),
            "identity": identity_report,
            "adapter": args.adapter,
            "date": observed_date,
            "observed_at": observed_at,
            "provenance": provenance,
            "scenarios": [scenario.id for scenario in scenarios],
            "scenario_digests": {
                scenario.id: _scenario_digest(scenario.path) for scenario in scenarios
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.unsafe_manual:
        try:
            provenance = compute_source_provenance(
                REPO_ROOT,
                adapter=args.adapter,
                capability="export",
            ).to_dict()
        except ValueError as exc:
            parser.error(f"could not bind clean source provenance: {exc}")

    results = [
        run_export_scenario(
            scenario,
            command,
            identity,
            adapter=args.adapter,
            source_root=REPO_ROOT,
            timeout_seconds=args.timeout,
        )
        for scenario in scenarios
    ]
    report = {
        "schema_version": "2",
        "capability": "export",
        "mode": "export",
        "execution_mode": execution_mode,
        "dry_run": False,
        "success": all(result.passed for result in results),
        "agent": identity.to_dict(),
        "identity": identity_report,
        "adapter": args.adapter,
        "date": observed_date,
        "observed_at": observed_at,
        "provenance": provenance,
        "results": [result.to_dict() for result in results],
    }
    if args.require_complete_matrix:
        matrix_errors = _complete_matrix_errors(report)
        if matrix_errors:
            report["success"] = False
            print(
                "complete export matrix failed: " + ", ".join(matrix_errors),
                file=sys.stderr,
            )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
