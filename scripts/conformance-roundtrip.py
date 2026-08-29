#!/usr/bin/env python3
"""Run live generated Waybill handoffs across selected adapter routes."""

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
FAKE_AGENT = REPO_ROOT / "tests/conformance/fixtures/fake_roundtrip_agent.py"
FAKE_AGENT_DEPENDENCIES = (
    FAKE_AGENT,
    REPO_ROOT / "tests/conformance/fixtures/fake_export_agent.py",
)
SCENARIO_ID = "ordinary-unfinished"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from waybill_core.adapter_matrix import (  # noqa: E402
    compute_source_provenance,
    require_canonical_manual_scenario_directory,
)
from waybill_core.agent_identity import IDENTITY_KINDS, probe_agent_identity  # noqa: E402
from waybill_core.export_conformance import (  # noqa: E402
    SUPPORTED_EXPORT_ADAPTERS,
    ExportAgentIdentity,
    load_export_scenarios,
)
from waybill_core.roundtrip_conformance import run_bidirectional_roundtrip  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export a live synthetic .waybill bundle, then import it with the "
            "selected adapter under zero-write observation. Cross-adapter pairs "
            "run both directions; same-adapter pairs run once."
        )
    )
    parser.add_argument("--left-agent-command", required=True)
    parser.add_argument("--right-agent-command", required=True)
    parser.add_argument(
        "--left-import-command",
        help=(
            "Optional read-only command for the left adapter when it imports; "
            "defaults to --left-agent-command."
        ),
    )
    parser.add_argument(
        "--right-import-command",
        help=(
            "Optional read-only command for the right adapter when it imports; "
            "defaults to --right-agent-command."
        ),
    )
    parser.add_argument(
        "--left-adapter",
        required=True,
        choices=SUPPORTED_EXPORT_ADAPTERS,
    )
    parser.add_argument(
        "--right-adapter",
        required=True,
        choices=SUPPORTED_EXPORT_ADAPTERS,
    )
    parser.add_argument(
        "--left-identity-kind",
        choices=IDENTITY_KINDS,
        help="Required for --unsafe-manual; scopes the left command identity.",
    )
    parser.add_argument(
        "--right-identity-kind",
        choices=IDENTITY_KINDS,
        help="Required for --unsafe-manual; scopes the right command identity.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--deterministic-fake",
        action="store_true",
        help="Run the repository-owned deterministic coding-agent fixture.",
    )
    mode.add_argument(
        "--unsafe-manual",
        action="store_true",
        help=(
            "Acknowledge that real agents use best-effort observation rather than "
            "an operating-system sandbox. Environment failures are reported and "
            "are never retried with weaker controls."
        ),
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=REPO_ROOT / "conformance/export-scenarios",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate commands, adapters, identities, and scenario without "
            "handoff execution."
        ),
    )
    return parser


def _parse_command(
    parser: argparse.ArgumentParser,
    option: str,
    value: str,
) -> list[str]:
    try:
        command = shlex.split(value, posix=True)
    except ValueError as exc:
        parser.error(f"invalid {option}: {exc}")
    if not command:
        parser.error(f"{option} must not be empty")
    if any("\x00" in argument for argument in command):
        parser.error(f"{option} must not contain NUL bytes")
    return command


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


def _fixture_identity(
    parser: argparse.ArgumentParser,
    command: list[str],
    *,
    side: str,
    dry_run: bool,
) -> tuple[ExportAgentIdentity, dict[str, object]]:
    if not dry_run:
        matches = [
            index
            for index, argument in enumerate(command)
            if argument
            and not argument.startswith("-")
            and Path(argument).exists()
            and Path(argument).resolve() == FAKE_AGENT.resolve()
        ]
        if not matches:
            parser.error(
                f"--deterministic-fake requires {side} command to execute the "
                "repository fake roundtrip agent"
            )
        command[matches[0]] = str(FAKE_AGENT.resolve())
    digest = hashlib.sha256()
    for dependency in FAKE_AGENT_DEPENDENCIES:
        relative = dependency.relative_to(REPO_ROOT).as_posix().encode("utf-8")
        content = dependency.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    identity = ExportAgentIdentity(
        agent=f"deterministic-{side}",
        product="deterministic-fake",
        version="deterministic-fixture",
    )
    return identity, {
        "verified": True,
        "identity_kind": "deterministic_fixture",
        "product": identity.product,
        "version": identity.version,
        "sha256": "sha256:" + digest.hexdigest(),
    }


def _manual_identity(
    parser: argparse.ArgumentParser,
    command: list[str],
    *,
    adapter: str,
    identity_kind: str,
) -> tuple[ExportAgentIdentity, dict[str, object]]:
    probe = probe_agent_identity(
        adapter,
        executable=command[0],
        environment=_probe_environment(),
    )
    if not probe.verified or probe.product is None or probe.version is None:
        parser.error(
            f"{adapter} identity verification failed: "
            + str(probe.error_code or probe.status)
        )
    return (
        ExportAgentIdentity(
            agent=adapter,
            product=probe.product,
            version=probe.version,
        ),
        probe.to_dict(
            include_private=False,
            identity_kind=identity_kind,
        ),
    )


def _require_matching_role_identity(
    parser: argparse.ArgumentParser,
    *,
    side: str,
    export_report: dict[str, object],
    import_report: dict[str, object],
) -> None:
    identity_kind = export_report.get("identity_kind")
    fields = (
        ("reported_product", "reported_version", "sha256")
        if identity_kind == "launcher"
        else ("product", "version", "sha256")
    )
    if import_report.get("identity_kind") != identity_kind:
        parser.error(f"{side} export and import identity kinds must match")
    if any(export_report.get(field) != import_report.get(field) for field in fields):
        parser.error(
            f"{side} export and import commands must resolve to the same "
            "verified product, version, and executable"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    left_command = _parse_command(
        parser, "--left-agent-command", args.left_agent_command
    )
    right_command = _parse_command(
        parser, "--right-agent-command", args.right_agent_command
    )
    left_import_command = (
        list(left_command)
        if args.left_import_command is None
        else _parse_command(
            parser,
            "--left-import-command",
            args.left_import_command,
        )
    )
    right_import_command = (
        list(right_command)
        if args.right_import_command is None
        else _parse_command(
            parser,
            "--right-import-command",
            args.right_import_command,
        )
    )
    try:
        scenarios = load_export_scenarios(args.scenario_dir, [SCENARIO_ID])
    except ValueError as exc:
        parser.error(str(exc))
    scenario = scenarios[0]
    if args.unsafe_manual and not args.dry_run:
        try:
            require_canonical_manual_scenario_directory(
                args.scenario_dir,
                REPO_ROOT / "conformance" / "export-scenarios",
            )
        except ValueError as exc:
            parser.error(str(exc))
    if args.unsafe_manual and (
        args.left_identity_kind is None or args.right_identity_kind is None
    ):
        parser.error(
            "--left-identity-kind and --right-identity-kind are required "
            "for --unsafe-manual"
        )

    if args.deterministic_fake:
        left_identity, left_report = _fixture_identity(
            parser, left_command, side="left", dry_run=args.dry_run
        )
        right_identity, right_report = _fixture_identity(
            parser, right_command, side="right", dry_run=args.dry_run
        )
        if args.left_import_command is None:
            left_import_command = list(left_command)
            left_import_report = left_report
        else:
            _, left_import_report = _fixture_identity(
                parser,
                left_import_command,
                side="left import",
                dry_run=args.dry_run,
            )
        if args.right_import_command is None:
            right_import_command = list(right_command)
            right_import_report = right_report
        else:
            _, right_import_report = _fixture_identity(
                parser,
                right_import_command,
                side="right import",
                dry_run=args.dry_run,
            )
        execution_mode = "deterministic_fake"
        provenance = None
    else:
        left_identity, left_report = _manual_identity(
            parser,
            left_command,
            adapter=args.left_adapter,
            identity_kind=args.left_identity_kind,
        )
        right_identity, right_report = _manual_identity(
            parser,
            right_command,
            adapter=args.right_adapter,
            identity_kind=args.right_identity_kind,
        )
        if args.left_import_command is None:
            left_import_report = left_report
        else:
            _, left_import_report = _manual_identity(
                parser,
                left_import_command,
                adapter=args.left_adapter,
                identity_kind=args.left_identity_kind,
            )
            _require_matching_role_identity(
                parser,
                side="left",
                export_report=left_report,
                import_report=left_import_report,
            )
        if args.right_import_command is None:
            right_import_report = right_report
        else:
            _, right_import_report = _manual_identity(
                parser,
                right_import_command,
                adapter=args.right_adapter,
                identity_kind=args.right_identity_kind,
            )
            _require_matching_role_identity(
                parser,
                side="right",
                export_report=right_report,
                import_report=right_import_report,
            )
        execution_mode = "unsafe_manual"
        provenance = None

    common: dict[str, object] = {
        "schema_version": "1",
        "capability": "roundtrip",
        "execution_mode": execution_mode,
        "dry_run": args.dry_run,
        "left": {
            "adapter": args.left_adapter,
            "agent": left_identity.to_dict(),
            "identity": left_report,
            "import_identity": left_import_report,
        },
        "right": {
            "adapter": args.right_adapter,
            "agent": right_identity.to_dict(),
            "identity": right_report,
            "import_identity": right_import_report,
        },
        "scenario": SCENARIO_ID,
        "provenance": provenance,
    }
    if args.dry_run:
        common.update({"success": True, "directions": []})
        print(json.dumps(common, indent=2, sort_keys=True))
        return 0

    if args.unsafe_manual:
        try:
            provenance = {
                side: {
                    capability: compute_source_provenance(
                        REPO_ROOT,
                        adapter=adapter,
                        capability=capability,
                    ).to_dict()
                    for capability in ("export", "import")
                }
                for side, adapter in (
                    ("left", args.left_adapter),
                    ("right", args.right_adapter),
                )
            }
        except ValueError as exc:
            parser.error(f"could not bind clean source provenance: {exc}")
        common["provenance"] = provenance

    result = run_bidirectional_roundtrip(
        scenario,
        left_command,
        right_command,
        left_identity,
        right_identity,
        left_adapter=args.left_adapter,
        right_adapter=args.right_adapter,
        left_import_command=left_import_command,
        right_import_command=right_import_command,
        source_root=REPO_ROOT,
        timeout_seconds=args.timeout,
        inherit_user_config=args.unsafe_manual,
    )
    result_report = result.to_dict()
    common.update(
        {
            "success": result.passed,
            "environment_blocked": result.environment_blocked,
            "automatic_retries": result_report["automatic_retries"],
            "directions": result_report["directions"],
            "errors": result_report["errors"],
        }
    )
    print(json.dumps(common, indent=2, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
