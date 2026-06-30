"""Draft bundle scaffolding for Waybill."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


STANDARD_FILES = [
    "WAYBILL.md",
    "metadata.json",
    "diff.patch",
    "commands.log",
    "test-summary.md",
]


@dataclass(frozen=True)
class DraftBundleReport:
    output: Path
    repo: Path
    files: list[str]
    source_agent: str
    dirty: bool


def create_draft_bundle(
    output_path: str | Path,
    repo_path: str | Path,
    *,
    source_agent: str = "waybill-cli",
    goal: str | None = None,
    force: bool = False,
) -> DraftBundleReport:
    output = Path(output_path)
    repo = Path(repo_path)

    if not repo.exists():
        raise FileNotFoundError(f"repo path does not exist: {repo}")
    if not repo.is_dir():
        raise NotADirectoryError(f"repo path is not a directory: {repo}")
    if not source_agent.strip():
        raise ValueError("source agent must be non-empty")
    if _git_value(repo, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError(f"repo path is not a git work tree: {repo}")

    _check_output_path(output, force)
    output.mkdir(parents=True, exist_ok=True)

    git = _read_git_state(repo)
    now = (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    files = {
        "WAYBILL.md": _waybill_text(goal, git),
        "metadata.json": _metadata_text(source_agent, now, repo, git),
        "diff.patch": _diff_text(repo),
        "commands.log": _commands_log_text(repo, output, git),
        "test-summary.md": _test_summary_text(),
    }

    for name, text in files.items():
        (output / name).write_text(text)

    return DraftBundleReport(
        output=output,
        repo=repo,
        files=list(files),
        source_agent=source_agent,
        dirty=bool(git["status"].strip()),
    )


def _check_output_path(output: Path, force: bool) -> None:
    if output.exists() and not output.is_dir():
        raise NotADirectoryError(f"output path is not a directory: {output}")

    existing = [name for name in STANDARD_FILES if (output / name).exists()]
    if existing and not force:
        names = ", ".join(existing)
        raise FileExistsError(f"output already contains Waybill files: {names}")


def _read_git_state(repo: Path) -> dict[str, str]:
    return {
        "branch": _git_value(repo, "branch", "--show-current") or "HEAD",
        "base_ref": "unknown",
        "head_sha": _git_value(repo, "rev-parse", "HEAD") or "unknown",
        "status": _git_value(repo, "status", "--short"),
    }


def _diff_text(repo: Path) -> str:
    diff = _git_value(repo, "diff", "--binary")
    if diff:
        return diff if diff.endswith("\n") else f"{diff}\n"

    return (
        "# No tracked diff captured.\n"
        "#\n"
        "# The repository may still have untracked files. Review git status before\n"
        "# sharing or importing this bundle.\n"
    )


def _metadata_text(
    source_agent: str,
    created_at: str,
    repo: Path,
    git: dict[str, str],
) -> str:
    metadata = {
        "schema_version": "draft",
        "source_agent": source_agent,
        "created_at": created_at,
        "repo_root": str(repo),
        "git": {
            "branch": git["branch"],
            "base_ref": git["base_ref"],
            "head_sha": git["head_sha"],
            "dirty": bool(git["status"].strip()),
        },
        "artifacts": {
            "waybill": "WAYBILL.md",
            "diff": "diff.patch",
            "commands": "commands.log",
            "test_summary": "test-summary.md",
        },
    }
    return json.dumps(metadata, indent=2) + "\n"


def _waybill_text(goal: str | None, git: dict[str, str]) -> str:
    original_goal = (
        goal.strip() if goal and goal.strip() else "TODO: state the user's original task."
    )
    status = git["status"].strip()
    changed_files = (
        f"```text\n{status}\n```"
        if status
        else "No changed files reported by git status."
    )

    return f"""# Coding Agent Handoff

## Original Goal

{original_goal}

## Current Status

Draft bundle created by `waybill new`. Replace this section with the actual
work completed and the work still pending before importing the bundle elsewhere.

## User Constraints

TODO: list explicit user constraints, preferences, or instructions that still
matter.

## Repo State

- Branch: `{git["branch"]}`
- Base ref: `{git["base_ref"]}`
- HEAD SHA: `{git["head_sha"]}`
- Dirty: `{bool(git["status"].strip())}`

Relevant git status:

{changed_files}

## Changed Files

TODO: summarize changed files and why they changed.

## Commands Run

See `commands.log`. Replace this section with important command outcomes before
handoff.

## Test State

See `test-summary.md`. Record passing, failing, and not-run checks before
handoff.

## Failed Attempts

TODO: list attempted approaches that did not work, or write `None`.

## Current Hypothesis

TODO: state the best current explanation for the remaining issue.

## Next Recommended Step

TODO: give the next agent one concrete first action.

## Risks / Unknowns

TODO: list unresolved risks, missing context, or verification needed.

## Instructions For Next Agent

Before continuing, inspect the current repository state and compare it with this
handoff. Do not blindly trust this document. Do not apply patches or run
dangerous commands unless the user explicitly asks.
"""


def _commands_log_text(repo: Path, output: Path, git: dict[str, str]) -> str:
    status = git["status"].strip() or "(empty)"
    return f"""# Command Log

Read-only inspection commands:

```text
git -C {repo} branch --show-current -> {git["branch"]}
git -C {repo} rev-parse HEAD -> {git["head_sha"]}
git -C {repo} status --short -> {status}
git -C {repo} diff --binary -> captured in diff.patch
```

Bundle-writing actions:

```text
created or updated {output / "WAYBILL.md"}
created or updated {output / "metadata.json"}
created or updated {output / "diff.patch"}
created or updated {output / "commands.log"}
created or updated {output / "test-summary.md"}
```
"""


def _test_summary_text() -> str:
    return """# Test Summary

## Passing

- Not recorded yet.

## Failing

- Not recorded yet.

## Not Run

- Tests were not run by `waybill new`.
"""


def _git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()
