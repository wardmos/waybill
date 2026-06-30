"""Repository state verification for Waybill Bundles."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RepoCheck:
    name: str
    status: str
    expected: object
    actual: object
    message: str


@dataclass(frozen=True)
class RepoVerificationReport:
    bundle: Path
    repo: Path
    checks: list[RepoCheck]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)


def verify_repo_state(
    bundle_path: str | Path,
    repo_path: str | Path,
) -> RepoVerificationReport:
    bundle = Path(bundle_path)
    repo = Path(repo_path)
    checks: list[RepoCheck] = []

    metadata = _read_metadata(bundle, checks)
    current = _read_repo_state(repo, checks)
    if metadata is None or current is None:
        return RepoVerificationReport(bundle, repo, checks)

    git = metadata.get("git") if isinstance(metadata.get("git"), dict) else {}
    _compare_value("branch", git.get("branch"), current.get("branch"), checks)
    _compare_value("head_sha", git.get("head_sha"), current.get("head_sha"), checks)
    _compare_dirty(git.get("dirty"), current.get("dirty"), checks)

    return RepoVerificationReport(bundle, repo, checks)


def _read_metadata(bundle: Path, checks: list[RepoCheck]) -> dict[str, Any] | None:
    path = bundle / "metadata.json"
    if not path.is_file():
        checks.append(_error("metadata", "present", "missing", "metadata.json is missing"))
        return None

    try:
        metadata = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        checks.append(_error("metadata", "valid JSON", "invalid JSON", str(exc)))
        return None

    if not isinstance(metadata, dict):
        checks.append(
            _error("metadata", "object", type(metadata).__name__, "metadata must be an object")
        )
        return None

    checks.append(RepoCheck("metadata", "ok", "metadata.json", str(path), "read"))
    return metadata


def _read_repo_state(repo: Path, checks: list[RepoCheck]) -> dict[str, object] | None:
    if not repo.exists():
        checks.append(
            _error("repo", "existing directory", str(repo), "repo path does not exist")
        )
        return None
    if not repo.is_dir():
        checks.append(_error("repo", "directory", str(repo), "repo path is not a directory"))
        return None

    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--short")

    failed = [result for result in [branch, head, status] if result.returncode != 0]
    if failed:
        message = (
            failed[0].stderr.strip()
            or failed[0].stdout.strip()
            or "git command failed"
        )
        checks.append(_error("repo", "git repository", str(repo), message))
        return None

    checks.append(RepoCheck("repo", "ok", "git repository", str(repo), "read"))
    return {
        "branch": branch.stdout.strip() or "HEAD",
        "head_sha": head.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
    }


def _compare_value(
    name: str,
    expected: object,
    actual: object,
    checks: list[RepoCheck],
) -> None:
    if expected in [None, "", "unknown"]:
        checks.append(RepoCheck(name, "warning", expected, actual, "expected value unknown"))
        return

    if expected == actual:
        checks.append(RepoCheck(name, "ok", expected, actual, "matches"))
    else:
        checks.append(RepoCheck(name, "error", expected, actual, "does not match"))


def _compare_dirty(expected: object, actual: object, checks: list[RepoCheck]) -> None:
    if not isinstance(expected, bool):
        checks.append(
            RepoCheck(
                "dirty",
                "warning",
                expected,
                actual,
                "expected value is not boolean",
            )
        )
        return

    if expected == actual:
        checks.append(RepoCheck("dirty", "ok", expected, actual, "matches"))
    else:
        checks.append(RepoCheck("dirty", "error", expected, actual, "does not match"))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _error(name: str, expected: object, actual: object, message: str) -> RepoCheck:
    return RepoCheck(name, "error", expected, actual, message)
