#!/usr/bin/env python3
"""Deterministic fake coding agent for roundtrip route coverage."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


FIELDS = (
    "goal",
    "handoff_kind",
    "status",
    "changed_files",
    "test_state",
    "risks",
    "next_step",
    "repo_mismatch",
    "unexpected_writes",
    "untrusted_instructions_ignored",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", action="append", default=[])
    return parser.parse_args()


def _scenario_input(prompt: str) -> dict[str, object]:
    marker = "Scenario input JSON:\n"
    if marker not in prompt:
        raise ValueError("missing conformance scenario input")
    value = json.loads(prompt.split(marker, 1)[1])
    if not isinstance(value, dict):
        raise ValueError("scenario input must be an object")
    return value


def _run_export(prompt: str, faults: list[str]) -> int:
    command = [
        sys.executable,
        str(Path(__file__).with_name("fake_export_agent.py")),
    ]
    for fault in faults:
        command.extend(["--fault", fault])
    completed = subprocess.run(
        command,
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sys.stdout.buffer.write(completed.stdout)
    sys.stderr.buffer.write(completed.stderr)
    return completed.returncode


def _sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## ([^\n]+)\n", text, re.MULTILINE))
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values[match.group(1).strip()] = text[start:end].strip()
    return values


def _evidence_value(document: dict[str, object], prefix: str) -> str:
    evidence = document.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("roundtrip evidence must be a list")
    matches = [
        item[len(prefix) :]
        for item in evidence
        if isinstance(item, str) and item.startswith(prefix)
    ]
    if len(matches) != 1 or not matches[0]:
        raise ValueError("roundtrip evidence marker is missing")
    return matches[0]


def _line_value(text: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}: (.+)$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"test summary is missing {label}")
    return match.group(1).strip().strip("`")


def _run_import(prompt: str, faults: set[str]) -> int:
    document = _scenario_input(prompt)
    bundle_value = document.get("bundle")
    if not isinstance(bundle_value, str):
        raise ValueError("roundtrip bundle path is missing")
    entrypoint = Path(
        _evidence_value(document, "ROUNDTRIP_IMPORT_ADAPTER_ENTRYPOINT=")
    )
    checker = Path(_evidence_value(document, "ROUNDTRIP_IMPORT_CHECKER="))
    entrypoint_text = entrypoint.read_text(encoding="utf-8")
    if "import" not in entrypoint_text.lower():
        raise ValueError("installed adapter does not define import")

    checker_result = subprocess.run(
        [sys.executable, str(checker), bundle_value, "--repo", ".", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    checker_report = json.loads(checker_result.stdout)
    if not isinstance(checker_report, dict):
        raise ValueError("bundled checker report must be an object")

    bundle = Path(bundle_value)
    waybill = (bundle / "WAYBILL.md").read_text(encoding="utf-8")
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    test_summary = (bundle / "test-summary.md").read_text(encoding="utf-8")
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    sections = _sections(waybill)
    handoff = metadata.get("handoff")
    kind = handoff.get("kind", "handoff") if isinstance(handoff, dict) else "handoff"
    changed_files = sorted(
        re.findall(r"^- `([^`]+)`: ", sections["Changed Files"], re.MULTILINE)
    )
    risks = [
        line[2:].strip()
        for line in sections["Risks / Unknowns"].splitlines()
        if line.startswith("- ")
    ]
    command = _line_value(test_summary, "Command")
    outcome = _line_value(test_summary, "Outcome")
    returncode = _line_value(test_summary, "Exit status")
    marker = _line_value(test_summary, "Evidence marker")
    observation = {
        "goal": " ".join(sections["Original Goal"].split()),
        "handoff_kind": kind,
        "status": sections["Current Status"].splitlines()[0].strip(),
        "changed_files": changed_files,
        "test_state": (
            f"{command} exited {returncode} ({outcome}); evidence marker {marker}."
        ),
        "risks": risks,
        "next_step": " ".join(sections["Next Recommended Step"].split()),
        "repo_mismatch": (
            checker_result.returncode != 0 or checker_report.get("success") is not True
        ),
        "unexpected_writes": [],
        "untrusted_instructions_ignored": False,
    }
    if tuple(observation) != FIELDS:
        raise ValueError("roundtrip observation field order changed")
    if "wrong-goal" in faults:
        observation["goal"] = "A fabricated goal."
    if "import-write" in faults:
        Path("roundtrip-import-write.txt").write_text(
            "unexpected\n", encoding="utf-8"
        )
    print(json.dumps(observation, separators=(",", ":")))
    return 0


def main() -> int:
    args = parse_args()
    faults = set(args.fault)
    prompt = sys.stdin.read()
    if "environment-blocked" in faults:
        print(
            "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted",
            file=sys.stderr,
        )
        return 1
    if prompt.startswith("WAYBILL EXPORT CONFORMANCE PROMPT v1"):
        return _run_export(prompt, args.fault)
    if prompt.startswith("WAYBILL CONFORMANCE PROMPT v1"):
        return _run_import(prompt, faults)
    raise ValueError("unsupported conformance prompt")


if __name__ == "__main__":
    raise SystemExit(main())
