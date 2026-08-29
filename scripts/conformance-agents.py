#!/usr/bin/env python3
"""Run deterministic Waybill conformance scenarios against a custom command."""

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
AGENT_OUTPUT_LIMIT_BYTES = 256 * 1024
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
    IDENTITY_KINDS,
    SUPPORTED_AGENT_PRODUCTS,
    current_observed_at,
    probe_agent_identity,
)
from waybill_core.adapter_matrix import (  # noqa: E402
    compute_source_provenance,
    require_canonical_manual_scenario_directory,
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
        "--identity-kind",
        choices=IDENTITY_KINDS,
        help=(
            "Required for a real run: executable for a direct agent binary or "
            "launcher for a command that forwards to an agent."
        ),
    )
    parser.add_argument(
        "--unsafe-manual",
        action="store_true",
        help=(
            "Acknowledge that a real agent uses best-effort process and filesystem "
            "observation, not an operating-system sandbox."
        ),
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
        help=(
            "Identity-probe observation root and legacy v1 workspace. V2 scenarios "
            "run only in their scenario-owned disposable fixtures."
        ),
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


def _sanitized_error(message: str, *roots: Path) -> str:
    sanitized = message
    labels = ("<repository>", "<scenario-directory>", "<workspace>")
    candidates = (REPO_ROOT, *roots)
    for path, label in zip(candidates, labels):
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        sanitized = sanitized.replace(resolved, label)
    return sanitized


def _safety_report(*, manual_acknowledged: bool) -> dict[str, object]:
    return {
        "disposable_workspace": True,
        "environment_allowlist": True,
        "git_state_measured": True,
        "output_limit_bytes_per_stream": AGENT_OUTPUT_LIMIT_BYTES,
        "process_group_cleanup": "best_effort",
        "outside_disposable_root_detection": "best_effort",
        "operating_system_sandbox": False,
        "manual_risk_acknowledged": manual_acknowledged,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _parse_command(parser, args.agent_command)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not args.dry_run and args.adapter is None:
        parser.error("--adapter is required for a real run")
    if not args.dry_run and not args.unsafe_manual:
        parser.error("--unsafe-manual is required for a real run")

    try:
        scenarios = load_scenarios(args.scenario_dir, args.scenarios)
    except ValueError as exc:
        parser.error(_sanitized_error(str(exc), args.scenario_dir, args.workspace))
    if not scenarios:
        parser.error("no scenario JSON files found")
    if args.unsafe_manual and not args.dry_run:
        try:
            require_canonical_manual_scenario_directory(
                args.scenario_dir,
                REPO_ROOT / "conformance" / "scenarios",
            )
        except ValueError as exc:
            parser.error(str(exc))
    if not args.dry_run and args.identity_kind is None:
        parser.error("--identity-kind is required for a real run")

    if not args.workspace.is_dir():
        parser.error("workspace is not a directory")

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
            "schema_version": "2",
            "capability": "import",
            "agent": args.agent_name,
            "adapter": args.adapter,
            "observed_at": observed_at,
            "identity": None,
            "identity_probe_unexpected_writes": [],
            "execution_mode": "dry_run",
            "safety": _safety_report(manual_acknowledged=False),
            "dry_run": True,
            "success": True,
            "provenance": None,
            "results": results,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    observed_at = current_observed_at()
    identity_probe_before = snapshot_workspace(args.workspace, include_git=True)
    original_working_directory = Path.cwd()
    try:
        os.chdir(args.workspace)
        identity = probe_agent_identity(
            args.adapter,
            executable=command[0],
            environment=_probe_environment(),
            observed_at=observed_at,
        )
    finally:
        os.chdir(original_working_directory)
    identity_probe_after = snapshot_workspace(args.workspace, include_git=True)
    identity_probe_writes = changed_snapshot_paths(
        identity_probe_before,
        identity_probe_after,
    )
    if not identity.verified or identity_probe_writes:
        report = {
            "schema_version": "2",
            "capability": "import",
            "agent": args.agent_name,
            "adapter": args.adapter,
            "observed_at": observed_at,
            "identity": identity.to_dict(
                include_private=args.private_identity,
                identity_kind=args.identity_kind,
            ),
            "identity_probe_unexpected_writes": identity_probe_writes,
            "execution_mode": "unsafe_manual",
            "safety": _safety_report(manual_acknowledged=True),
            "dry_run": False,
            "success": False,
            "provenance": None,
            "results": [],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    try:
        provenance = compute_source_provenance(
            REPO_ROOT,
            adapter=args.adapter,
            capability="import",
        )
        results = [
            run_scenario(
                scenario,
                command,
                args.workspace,
                timeout_seconds=args.timeout,
                output_limit_bytes=AGENT_OUTPUT_LIMIT_BYTES,
                inherit_user_config=True,
            )
            for scenario in scenarios
        ]
    except (OSError, ValueError) as exc:
        parser.error(_sanitized_error(str(exc), args.scenario_dir, args.workspace))
    report = {
        "schema_version": "2",
        "capability": "import",
        "agent": args.agent_name,
        "adapter": args.adapter,
        "observed_at": observed_at,
        "identity": (
            identity.to_dict(
                include_private=args.private_identity,
                identity_kind=args.identity_kind,
            )
            if identity is not None
            else None
        ),
        "identity_probe_unexpected_writes": identity_probe_writes,
        "execution_mode": "unsafe_manual",
        "safety": _safety_report(manual_acknowledged=True),
        "dry_run": False,
        "success": all(result.passed for result in results),
        "provenance": provenance.to_dict(),
        "results": [result.to_dict() for result in results],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
