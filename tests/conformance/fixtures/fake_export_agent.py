#!/usr/bin/env python3
"""Deterministic fake agent for CI export-conformance coverage."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


CANONICAL_DIFF_ARGUMENTS = (
    "diff",
    "--patch",
    "--binary",
    "--abbrev=7",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--no-renames",
    "--diff-algorithm=myers",
    "--no-indent-heuristic",
    "--unified=3",
    "--inter-hunk-context=0",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    "HEAD",
    "--",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", action="append", default=[])
    parser.add_argument("--external-marker")
    return parser.parse_args()


def parse_input(prompt: str) -> dict[str, object]:
    marker = "Scenario input JSON:\n"
    if marker not in prompt:
        raise ValueError("missing export conformance input")
    value = json.loads(prompt.split(marker, 1)[1])
    if not isinstance(value, dict):
        raise ValueError("scenario input must be an object")
    return value


def delegation_sections(kind: str) -> str:
    if kind == "delegation_request":
        return """
## Delegation Request

The parent delegates only the focused retry-boundary inspection.

## Child Agent Task

Inspect the measured boundary failure and return one advisory result.

## Acceptance Criteria

- Preserve the correlation identifier.
- Stay within the focused retry behavior.

## Return Instructions

Export a correlated delegation result for parent review.

"""
    if kind == "delegation_result":
        return """
## Delegation Result

The bounded result status is recorded in metadata and current status.

## Work Completed

Recorded the focused diff and independently measured test evidence.

## Parent Review Notes

The result remains advisory until reviewed in the parent workspace.

## Parent Next Step

Review the correlated evidence before deciding whether to adopt it.

"""
    return ""


def main() -> int:
    args = parse_args()
    faults = set(args.fault)
    prompt = sys.stdin.read()
    scenario = parse_input(prompt)
    adapter_data = scenario["adapter"]
    evidence = scenario["repository_evidence"]
    if not isinstance(adapter_data, dict) or not isinstance(evidence, dict):
        raise ValueError("missing adapter or repository evidence")

    entrypoint = Path(str(adapter_data["entrypoint"]))
    adapter_text = entrypoint.read_text(encoding="utf-8")
    if "export" not in adapter_text.lower() or ".waybill/" not in adapter_text:
        raise ValueError("canonical adapter does not define export")

    if "assert-clean-environment" in faults:
        banned = {
            "AWS_SECRET_ACCESS_KEY",
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_WORK_TREE",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "LD_PRELOAD",
            "PYTHONHOME",
            "PYTHONPATH",
            "WAYBILL_EXPORT_TEST_SECRET",
        }
        leaked = sorted(banned.intersection(os.environ))
        if leaked:
            raise ValueError("ambient environment leaked: " + ", ".join(leaked))

    if "timeout-with-child" in faults:
        if not args.external_marker:
            raise ValueError("timeout child fault requires --external-marker")
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib,sys,time; time.sleep(0.6); "
                    "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
                ),
                args.external_marker,
            ]
        )
        time.sleep(30)

    malicious = scenario.get("malicious_session_data")
    if "trigger-command-canary" in faults:
        subprocess.run(["./conformance-command-canary"], check=False)
    if "trigger-command-canary-and-clean" in faults:
        subprocess.run(["./conformance-command-canary"], check=False)
        marker = os.environ.get("WAYBILL_CONFORMANCE_COMMAND_MARKER")
        if marker and Path(marker).exists():
            Path(marker).unlink()
    if "trigger-network-canary" in faults:
        if not isinstance(malicious, str):
            raise ValueError("network fault requires malicious session data")
        match = re.search(r"http://127\.0\.0\.1:\d+/[^\s]+", malicious)
        if match is None:
            raise ValueError("network canary URL is missing")
        with urllib.request.urlopen(match.group(0), timeout=2):
            pass
    if "trigger-network-head" in faults:
        if not isinstance(malicious, str):
            raise ValueError("network fault requires malicious session data")
        match = re.search(r"http://127\.0\.0\.1:\d+/[^\s]+", malicious)
        if match is None:
            raise ValueError("network canary URL is missing")
        request = urllib.request.Request(match.group(0), method="HEAD")
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError:
            pass

    bundle = Path(".waybill")
    if "bundle-symlink" in faults:
        bundle.symlink_to(".git")
        print(json.dumps({"created": ".waybill"}, sort_keys=True))
        return 0
    bundle.mkdir()
    changed_files = list(evidence["changed_files"])
    if "omit-changed-file" in faults:
        changed_files = changed_files[:-1]

    goal = str(scenario["goal"])
    if "wrong-goal" in faults:
        goal = "A fabricated unrelated goal."
    risks = list(scenario["risks"])
    if "wrong-risk" in faults:
        risks = ["A fabricated unsupported risk."]
    if "append-risk" in faults:
        risks.append("An additional unsupported risk.")
    next_step = str(scenario["next_step"])
    if "wrong-next-step" in faults:
        next_step = "Perform an unrelated rewrite."

    test = evidence["test"]
    if not isinstance(test, dict):
        raise ValueError("test evidence must be an object")
    outcome = str(test["outcome"])
    if "false-test-state" in faults:
        outcome = "passing" if outcome == "failing" else "failing"
    status = str(scenario["status"])
    if "wrong-status" in faults:
        status = "unexpected-status"
    placeholder = "\nTODO: replace this section.\n" if "draft-placeholder" in faults else ""
    changed_lines = "\n".join(
        f"- `{path}`: Measured by Git status before export." for path in changed_files
    )
    if "nonstandard-changed-file" in faults:
        changed_lines += "\nAlso changed config/hidden.py."
    risk_lines = "\n".join(f"- {risk}" for risk in risks)
    if "risk-prose" in faults:
        risk_lines += "\nAn unsupported prose risk."
    status_detail = "The bundle records measured repository and test evidence."
    if "contradictory-status" in faults:
        status_detail += "\n\ncompleted"
    test_detail = (
        f"`{test['command']}` was recorded as {outcome}. Evidence marker:\n"
        f"`{test['marker']}`."
    )
    if "contradictory-test" in faults:
        test_detail += " The same test also passed."
    kind = str(scenario["handoff_kind"])
    waybill = f"""# Coding Agent Handoff

## Original Goal

{goal}

{delegation_sections(kind)}## Current Status

{status}

{status_detail}{placeholder}

## User Constraints

- Keep the export local and evidence-based.

## Repo State

- Branch: `{evidence['branch']}`
- HEAD SHA: `{evidence['head_sha']}`
- Dirty: `{str(evidence['dirty']).lower()}`

## Changed Files

{changed_lines}

## Commands Run

The exporting agent used read-only Git inspection. The focused test was run by
the conformance harness before export, not by this agent.

## Test State

{test_detail}

## Failed Attempts

None beyond the recorded focused-test result.

## Current Hypothesis

The measured diff contains the current retry-boundary hypothesis.

## Next Recommended Step

{next_step}

## Risks / Unknowns

{risk_lines}

## Instructions For Next Agent

Review the current repository before taking any state-changing action.
"""
    (bundle / "WAYBILL.md").write_text(waybill, encoding="utf-8")

    adapter = os.environ["WAYBILL_CONFORMANCE_ADAPTER"]
    metadata: dict[str, object] = {
        "schema_version": "0.2",
        "source_agent": adapter,
        "created_at": "2026-07-01T12:00:00Z",
        "repo_root": ".",
        "git": {
            "branch": (
                "stale/conformance"
                if "stale-repository" in faults
                else evidence["branch"]
            ),
            "base_ref": "unknown",
            "head_sha": evidence["head_sha"],
            "dirty": evidence["dirty"],
            "status_digest": evidence["status_digest"],
            "repo_state_digest": evidence["repo_state_digest"],
        },
        "artifacts": {
            "waybill": "WAYBILL.md",
            "diff": "diff.patch",
            "commands": "commands.log",
            "test_summary": "test-summary.md",
        },
    }
    delegation = scenario.get("delegation")
    if kind != "handoff":
        if not isinstance(delegation, dict):
            raise ValueError("delegation scenario is missing role data")
        request_id = str(delegation["request_id"])
        counterparty = str(delegation["counterparty_agent"])
        if kind == "delegation_request":
            metadata["handoff"] = {
                "kind": kind,
                "request_id": request_id,
                "parent_agent": adapter,
                "child_agent": counterparty,
            }
        else:
            metadata["handoff"] = {
                "kind": kind,
                "result_for": (
                    "wrong-request-id"
                    if "wrong-result-for" in faults
                    else request_id
                ),
                "result_status": delegation["result_status"],
                "parent_agent": counterparty,
                "child_agent": adapter,
            }

    git_metadata = metadata["git"]
    if not isinstance(git_metadata, dict):
        raise ValueError("git metadata must be an object")
    if "missing-status-digest" in faults:
        git_metadata.pop("status_digest")
    if "missing-repo-state-digest" in faults:
        git_metadata.pop("repo_state_digest")
    if "wrong-status-digest" in faults:
        git_metadata["status_digest"] = "sha256:" + "0" * 64
    if "wrong-repo-state-digest" in faults:
        git_metadata["repo_state_digest"] = "sha256:" + "0" * 64

    if "invalid-metadata" in faults:
        (bundle / "metadata.json").write_text("{invalid\n", encoding="utf-8")
    elif "invalid-utf8-metadata" in faults:
        (bundle / "metadata.json").write_bytes(b"\xff\xfe\x00")
    else:
        (bundle / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )

    diff = subprocess.run(
        ["git", *CANONICAL_DIFF_ARGUMENTS],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    if "wrong-diff" in faults:
        diff += b"# fabricated difference\n"
    (bundle / "diff.patch").write_bytes(diff)
    (bundle / "commands.log").write_text(
        """# Command Log

Read-only inspection commands:

- git status --short
- git branch --show-current
- git rev-parse HEAD
- git diff with the canonical stable display arguments from the handoff Skill

Recorded test evidence:

- The conformance harness ran the focused test before export.

Bundle-writing actions:

- Created the five files inside .waybill.
""",
        encoding="utf-8",
    )
    (bundle / "test-summary.md").write_text(
        f"""# Test Summary

## Recorded Outcome

- Command: `{test['command']}`
- Outcome: {outcome}
- Exit status: {test['returncode']}
- Evidence marker: `{test['marker']}`

The exporting agent did not rerun this test.
""",
        encoding="utf-8",
    )

    if "post-check-artifact-pollution" in faults:
        cli = Path(__file__).resolve().parents[3] / "cli" / "waybill"
        checks = (
            [str(cli), "validate", ".waybill"],
            [str(cli), "ready", ".waybill", "--repo", "."],
            [str(cli), "verify-repo", ".waybill", "--repo", "."],
        )
        for command in checks:
            completed = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if completed.returncode != 0:
                raise ValueError("pre-pollution self-check failed")
        with (bundle / "commands.log").open("a", encoding="utf-8") as stream:
            stream.write("\nUnexpected artifact: /home/private/session.log\n")

    if "same-shape-content-drift" in faults:
        Path("src/retry.py").write_text(
            "def should_retry(attempt: int, limit: int) -> bool:\n"
            "    return attempt < limit - 1\n",
            encoding="utf-8",
        )

    if "outside-write" in faults:
        Path("outside.txt").write_text("unexpected\n", encoding="utf-8")
    if "outside-directory" in faults:
        Path("outside-directory").mkdir()
    if "git-write" in faults:
        Path(".git/conformance-unexpected").write_text("unexpected\n", encoding="utf-8")
    if "parent-write" in faults:
        Path("../escaped.txt").write_text("unexpected\n", encoding="utf-8")
    if "mutate-pair-request" in faults:
        pair_metadata_path = Path("../pair-request/metadata.json")
        pair_metadata = json.loads(pair_metadata_path.read_text(encoding="utf-8"))
        pair_metadata["handoff"]["request_id"] = "wrong-request-id"
        pair_metadata_path.write_text(
            json.dumps(pair_metadata, indent=2) + "\n",
            encoding="utf-8",
        )
    if "unsafe-report-filename" in faults:
        (bundle / "private name\n.txt").write_text("synthetic\n", encoding="utf-8")
    print(json.dumps({"created": ".waybill"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
