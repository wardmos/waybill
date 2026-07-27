#!/usr/bin/env python3
"""Run deterministic Waybill conformance scenarios against a custom command."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from waybill_core.conformance import (  # noqa: E402
    build_prompt,
    changed_snapshot_paths,
    load_scenarios,
    run_scenario,
    snapshot_workspace,
)
from waybill_core.agent_identity import (  # noqa: E402
    SUPPORTED_AGENT_PRODUCTS,
    current_observed_at,
    probe_agent_identity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run strict, read-only Waybill import scenarios. The custom command "
            "receives a fixed prompt on stdin and must write exactly one JSON "
            "object to stdout."
        )
    )
    parser.add_argument(
        "--agent-command",
        required=True,
        help=(
            "Quoted command line to run once per scenario. Shell syntax is not "
            "evaluated."
        ),
    )
    parser.add_argument(
        "--agent-name",
        default="custom",
        help="Stable label included in the JSON report. Defaults to custom.",
    )
    parser.add_argument(
        "--adapter",
        choices=SUPPORTED_AGENT_PRODUCTS,
        help=(
            "probe the actual executable product and version before a real run; "
            "the first --agent-command argument is the executable"
        ),
    )
    parser.add_argument(
        "--private-identity",
        action="store_true",
        help="include the resolved executable path and raw identity probe output",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        default=[],
        help="Scenario id to run. Repeat to preserve an explicit order.",
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=REPO_ROOT / "conformance" / "scenarios",
        help="Directory containing scenario JSON files.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace to snapshot and use as the command working directory.",
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
        help="Validate inputs and describe runs without executing the command.",
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


def _prompt_digest(prompt: str) -> str:
    return "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _parse_command(parser, args.agent_command)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not args.dry_run and args.adapter is None:
        parser.error("--adapter is required for a real run")

    try:
        scenarios = load_scenarios(args.scenario_dir, args.scenarios)
    except ValueError as exc:
        parser.error(str(exc))
    if not scenarios:
        parser.error(f"no scenario JSON files found in {args.scenario_dir}")

    if not args.workspace.is_dir():
        parser.error(f"workspace is not a directory: {args.workspace}")

    if args.dry_run:
        observed_at = current_observed_at()
        results = [
            {
                "scenario": scenario.id,
                "prompt_digest": _prompt_digest(build_prompt(scenario)),
            }
            for scenario in scenarios
        ]
        report = {
            "schema_version": "1",
            "capability": "import",
            "agent": args.agent_name,
            "adapter": args.adapter,
            "observed_at": observed_at,
            "identity": None,
            "identity_probe_unexpected_writes": [],
            "execution_mode": "dry_run",
            "dry_run": True,
            "success": True,
            "command": command,
            "results": results,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    observed_at = current_observed_at()
    identity_probe_before = snapshot_workspace(args.workspace)
    identity = probe_agent_identity(
        args.adapter,
        executable=command[0],
        observed_at=observed_at,
    )
    identity_probe_after = snapshot_workspace(args.workspace)
    identity_probe_writes = changed_snapshot_paths(
        identity_probe_before,
        identity_probe_after,
    )
    if not identity.verified or identity_probe_writes:
        report = {
            "schema_version": "1",
            "capability": "import",
            "agent": args.agent_name,
            "adapter": args.adapter,
            "observed_at": observed_at,
            "identity": identity.to_dict(include_private=args.private_identity),
            "identity_probe_unexpected_writes": identity_probe_writes,
            "execution_mode": "manual",
            "dry_run": False,
            "success": False,
            "results": [],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    results = [
        run_scenario(
            scenario,
            command,
            args.workspace,
            timeout_seconds=args.timeout,
        )
        for scenario in scenarios
    ]
    report = {
        "schema_version": "1",
        "capability": "import",
        "agent": args.agent_name,
        "adapter": args.adapter,
        "observed_at": observed_at,
        "identity": (
            identity.to_dict(include_private=args.private_identity)
            if identity is not None
            else None
        ),
        "identity_probe_unexpected_writes": identity_probe_writes,
        "execution_mode": "manual",
        "dry_run": False,
        "success": all(result.passed for result in results),
        "results": [result.to_dict() for result in results],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
