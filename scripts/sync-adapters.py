#!/usr/bin/env python3
"""Check or rewrite generated adapter mirrors from canonical sources."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from waybill_core.adapter_sources import (  # noqa: E402
    find_adapter_drift,
    sync_adapter_mirrors,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize generated adapter and package files from the "
            "canonical Skill and thin wrappers."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="report mirror drift without changing files",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="rewrite missing or different mirrors",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root (defaults to the script's repository)",
    )
    return parser


def check(root: Path) -> int:
    issues = find_adapter_drift(root)
    if not issues:
        print("PASS adapter mirrors are in sync")
        return 0

    for issue in issues:
        print(
            f"DRIFT {issue.mirror}: {issue.reason} "
            f"(canonical: {issue.canonical})",
            file=sys.stderr,
        )
    return 1


def write(root: Path) -> int:
    try:
        updated = sync_adapter_mirrors(root)
    except FileNotFoundError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    for relative_path in updated:
        print(f"UPDATED {relative_path}")
    if not updated:
        print("PASS adapter mirrors are already in sync")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.check:
        return check(root)
    return write(root)


if __name__ == "__main__":
    raise SystemExit(main())
