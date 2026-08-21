#!/usr/bin/env python3
"""Build self-contained agent adapter bundles from canonical sources."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from waybill_core.adapter_bundles import build_adapter_bundles  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build standalone adapters without tracking generated copies."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist/adapters",
        help="new output directory (defaults to dist/adapters)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing regular output directory",
    )
    return parser


def _remove_existing_output(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"adapter output is not a regular directory: {path}")
    try:
        path.parent.resolve().relative_to(DIST_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"refusing to replace output outside {DIST_ROOT}: {path}"
        ) from exc
    shutil.rmtree(path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Keep the final path component unresolved so a symlink cannot hide from
    # the replacement preflight performed with lstat().
    output = Path(os.path.abspath(args.output))
    try:
        output.lstat()
    except FileNotFoundError:
        pass
    else:
        if not args.replace:
            print(f"ERROR adapter output already exists: {output}", file=sys.stderr)
            return 1
        try:
            _remove_existing_output(output)
        except ValueError as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            return 1

    try:
        report = build_adapter_bundles(ROOT, output)
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(f"PASS built {len(report.files)} adapter files in {report.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
