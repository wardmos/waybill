#!/usr/bin/env python3
"""Probe adapter identities and assemble a private capability quality matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from waybill_core.adapter_matrix import (  # noqa: E402
    ADAPTER_CAPABILITY_REQUIREMENTS,
    build_adapter_matrix,
    load_capability_observations,
)


ADAPTERS = tuple(ADAPTER_CAPABILITY_REQUIREMENTS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and fingerprint agent executables, verify product identity, "
            "and bind complete export/import conformance reports to the currently "
            "observed binaries. This command does not invoke a model."
        )
    )
    parser.add_argument(
        "--adapter",
        action="append",
        choices=ADAPTERS,
        default=[],
        help="adapter to include; repeat for a subset, defaults to all five",
    )
    parser.add_argument(
        "--executable",
        action="append",
        default=[],
        metavar="ADAPTER=PATH",
        help="override the executable used for one adapter identity probe",
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "non-dry-run conformance report JSON; repeat once per observed "
            "adapter capability"
        ),
    )
    parser.add_argument(
        "--identity-only",
        action="store_true",
        help="exit based only on executable identity, ignoring unrun capabilities",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="omit resolved paths, raw probe output, error detail, and evidence paths",
    )
    return parser


def _parse_executables(
    parser: argparse.ArgumentParser,
    values: list[str],
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        adapter, separator, executable = value.partition("=")
        if not separator or adapter not in ADAPTERS or not executable:
            parser.error(f"invalid --executable value: {value}")
        if adapter in overrides:
            parser.error(f"duplicate --executable adapter: {adapter}")
        overrides[adapter] = executable
    return overrides


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    adapters = args.adapter or list(ADAPTERS)
    executable_overrides = _parse_executables(parser, args.executable)
    try:
        capability_observations = load_capability_observations(args.report)
        report = build_adapter_matrix(
            adapters=adapters,
            executable_overrides=executable_overrides,
            capability_observations=capability_observations,
        )
    except ValueError as exc:
        detail = str(exc)
        if args.public:
            for report_path in args.report:
                candidates = {str(report_path), str(report_path.resolve())}
                for candidate in sorted(candidates, key=len, reverse=True):
                    detail = detail.replace(candidate, "<report>")
        parser.error(detail)

    print(
        json.dumps(
            report.to_dict(include_private=not args.public),
            indent=2,
            sort_keys=True,
        )
    )
    success = report.identity_success if args.identity_only else report.success
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
