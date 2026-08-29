"""Repository state verification for Waybill Bundles."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .limits import (
    BundleLimitError,
    MAX_BUNDLE_FILE_BYTES,
    MAX_DIFF_BYTES,
    format_bytes,
    list_bundle_files,
)


CANONICAL_DIFF_OPTIONS = (
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
)
CANONICAL_DIFF_ARGUMENTS = (
    "diff",
    *CANONICAL_DIFF_OPTIONS,
    "HEAD",
    "--",
)
CANONICAL_UNBORN_INDEX_DIFF_ARGUMENTS = (
    "diff",
    *CANONICAL_DIFF_OPTIONS,
    "--cached",
    "--",
)
CANONICAL_UNBORN_WORKTREE_DIFF_ARGUMENTS = (
    "diff",
    *CANONICAL_DIFF_OPTIONS,
    "--",
)
NO_TRACKED_DIFF_NOTE = (
    b"# No tracked diff captured.\n"
    b"#\n"
    b"# The repository may still have untracked files. Review git status before\n"
    b"# sharing or importing this bundle.\n"
)


def diff_omission_note(max_diff_bytes: int) -> bytes:
    """Return the complete canonical note for an over-limit tracked diff."""

    return (
        "# Diff omitted.\n"
        "#\n"
        "# `git diff --binary HEAD --` exceeded the Waybill draft limit of "
        f"{format_bytes(max_diff_bytes)}.\n"
        "# Review the repository directly and capture only the relevant changes\n"
        "# before sharing this bundle.\n"
    ).encode("utf-8")


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


@dataclass(frozen=True)
class RepoFidelity:
    status: bytes
    status_digest: str
    repo_state_digest: str


@dataclass(frozen=True)
class RepoDiff:
    """One bounded canonical tracked diff for bundle fidelity checks."""

    content: bytes
    truncated: bool


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
    _compare_optional_digest(
        "status_digest",
        git.get("status_digest"),
        current.get("status_digest"),
        checks,
    )
    _compare_optional_digest(
        "repo_state_digest",
        git.get("repo_state_digest"),
        current.get("repo_state_digest"),
        checks,
    )
    _compare_diff_patch(bundle, metadata, repo, checks)

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
    head = _git(repo, "rev-parse", "--verify", "HEAD")
    if branch.returncode != 0 or (
        head.returncode != 0 and not _is_git_work_tree(repo)
    ):
        failed = branch if branch.returncode != 0 else head
        message = (
            failed.stderr.strip()
            or failed.stdout.strip()
            or "git command failed"
        )
        checks.append(_error("repo", "git repository", str(repo), message))
        return None

    try:
        fidelity = read_repo_fidelity(repo)
    except ValueError as exc:
        checks.append(_error("repo", "readable git state", str(repo), str(exc)))
        return None

    checks.append(RepoCheck("repo", "ok", "git repository", str(repo), "read"))
    return {
        "branch": branch.stdout.strip() or "HEAD",
        "head_sha": head.stdout.strip() if head.returncode == 0 else "unknown",
        "dirty": bool(fidelity.status),
        "status_digest": fidelity.status_digest,
        "repo_state_digest": fidelity.repo_state_digest,
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
                "error",
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


def _compare_optional_digest(
    name: str,
    expected: object,
    actual: object,
    checks: list[RepoCheck],
) -> None:
    if expected in [None, "", "unknown"]:
        checks.append(
            RepoCheck(
                name,
                "warning",
                expected,
                actual,
                "bundle does not record this optional repository digest",
            )
        )
        return

    if expected == actual:
        checks.append(RepoCheck(name, "ok", expected, actual, "matches"))
    else:
        checks.append(RepoCheck(name, "error", expected, actual, "does not match"))


def _compare_diff_patch(
    bundle: Path,
    metadata: dict[str, Any],
    repo: Path,
    checks: list[RepoCheck],
) -> None:
    git = metadata.get("git")
    if not isinstance(git, dict) or not isinstance(git.get("dirty"), bool):
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                "boolean git.dirty",
                "missing or invalid",
                "cannot determine whether a live diff is required",
            )
        )
        return
    diff_limit = git.get("diff_max_bytes", MAX_DIFF_BYTES)
    if (
        type(diff_limit) is not int
        or diff_limit < 1
        or diff_limit > MAX_BUNDLE_FILE_BYTES
    ):
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                f"integer from 1 to {MAX_BUNDLE_FILE_BYTES}",
                diff_limit,
                "git.diff_max_bytes is invalid",
            )
        )
        return
    if git["dirty"] is False:
        checks.append(
            RepoCheck(
                "diff_patch",
                "ok",
                "live diff for a dirty export",
                "clean or proposed-patch bundle",
                "not required for a bundle that records a clean repository",
            )
        )
        return
    artifacts = metadata.get("artifacts")
    value = artifacts.get("diff") if isinstance(artifacts, dict) else None
    if not isinstance(value, str) or not value.strip():
        checks.append(
            RepoCheck(
                "diff_patch",
                "warning",
                "declared diff artifact",
                "not declared",
                "bundle does not declare a diff artifact",
            )
        )
        return

    relative = PurePosixPath(value)
    if (
        "\\" in value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                "safe relative diff artifact",
                "invalid path",
                "declared diff artifact path is invalid",
            )
        )
        return

    try:
        inventory = {
            item.relative_path.as_posix(): item for item in list_bundle_files(bundle)
        }
    except (BundleLimitError, OSError):
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                "safe regular diff artifact",
                "unsafe bundle",
                "bundle entries could not be safely inspected",
            )
        )
        return
    item = inventory.get(value)
    if item is None:
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                "declared diff artifact",
                "missing",
                "declared diff artifact is missing",
            )
        )
        return

    try:
        omission_note = diff_omission_note(diff_limit)
        artifact_limit = max(
            diff_limit,
            len(omission_note),
            len(NO_TRACKED_DIFF_NOTE),
        )
        recorded = _read_regular_file(item.path, artifact_limit)
        current = read_repo_diff(repo, max_bytes=diff_limit)
    except (OSError, ValueError):
        checks.append(
            RepoCheck(
                "diff_patch",
                "error",
                "readable current diff and bundle artifact",
                "unreadable",
                "diff fidelity could not be inspected",
            )
        )
        return

    if current.truncated:
        if recorded == omission_note:
            checks.append(
                RepoCheck(
                    "diff_patch",
                    "warning",
                    "canonical tracked diff",
                    "omission note",
                    "live tracked diff exceeds the comparison limit",
                )
            )
        else:
            checks.append(
                RepoCheck(
                    "diff_patch",
                    "error",
                    "canonical diff omission note",
                    "other content",
                    "does not match",
                )
            )
        return

    if not current.content:
        matches = recorded in {b"", NO_TRACKED_DIFF_NOTE}
    else:
        matches = recorded == current.content
    checks.append(
        RepoCheck(
            "diff_patch",
            "ok" if matches else "error",
            "canonical tracked diff",
            "bundle diff.patch",
            "matches" if matches else "does not match",
        )
    )


def _read_regular_file(path: Path, max_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("diff artifact is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError("diff artifact exceeds the comparison limit")
        return content
    finally:
        os.close(descriptor)


def read_repo_diff(
    repo: Path,
    *,
    max_bytes: int = MAX_DIFF_BYTES,
) -> RepoDiff:
    """Read the canonical tracked diff without allowing unbounded output."""

    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max diff bytes must be positive")
    command_arguments: tuple[tuple[str, ...], ...]
    if _has_head(repo):
        command_arguments = (CANONICAL_DIFF_ARGUMENTS,)
    elif _is_git_work_tree(repo):
        command_arguments = (
            CANONICAL_UNBORN_INDEX_DIFF_ARGUMENTS,
            CANONICAL_UNBORN_WORKTREE_DIFF_ARGUMENTS,
        )
    else:
        raise ValueError("git diff failed")

    content = bytearray()
    for arguments in command_arguments:
        part = _read_git_limited(repo, arguments, max_bytes - len(content))
        if part.truncated:
            return RepoDiff(b"", True)
        content.extend(part.content)
    return RepoDiff(bytes(content), False)


def _read_git_limited(
    repo: Path,
    arguments: tuple[str, ...],
    max_bytes: int,
) -> RepoDiff:
    process = subprocess.Popen(
        _git_command(repo, *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
    )
    assert process.stdout is not None
    with process.stdout:
        stdout = process.stdout.read(max_bytes + 1)
    if len(stdout) > max_bytes:
        process.kill()
        process.wait()
        return RepoDiff(b"", True)
    process.wait()
    if process.returncode != 0:
        raise ValueError("git diff failed")
    return RepoDiff(stdout, False)


def canonical_diff_commands(repo: Path) -> tuple[tuple[str, ...], ...]:
    """Return the exact tracked-diff command or unborn-repository fallback."""

    if _has_head(repo):
        arguments = (CANONICAL_DIFF_ARGUMENTS,)
    elif _is_git_work_tree(repo):
        arguments = (
            CANONICAL_UNBORN_INDEX_DIFF_ARGUMENTS,
            CANONICAL_UNBORN_WORKTREE_DIFF_ARGUMENTS,
        )
    else:
        raise ValueError("repo path is not a git work tree")
    return tuple(_git_command(repo, *item) for item in arguments)


def read_repo_fidelity(repo: Path) -> RepoFidelity:
    status = _git_bytes(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    index = _git_bytes(repo, "ls-files", "--stage", "-z")
    unstaged_diff = _git_bytes(
        repo,
        "diff",
        "--binary",
        "--full-index",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--diff-algorithm=myers",
        "--no-indent-heuristic",
        "--unified=0",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--",
    )

    status_bytes = _require_git_bytes(status, "git status")
    index_bytes = _require_git_bytes(index, "git ls-files")
    unstaged_diff_bytes = _require_git_bytes(unstaged_diff, "git diff")
    return RepoFidelity(
        status=status_bytes,
        status_digest=_digest(
            b"waybill-status-v1",
            [(b"porcelain-v1-z", status_bytes)],
        ),
        repo_state_digest=_digest(
            b"waybill-repo-state-v1",
            [
                (b"porcelain-v1-z", status_bytes),
                (b"index-v1-z", index_bytes),
                (b"unstaged-diff-v1", unstaged_diff_bytes),
            ],
        ),
    )


def _digest(domain: bytes, components: list[tuple[bytes, bytes]]) -> str:
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(b"\0")
    for name, value in components:
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return f"sha256:{digest.hexdigest()}"


def _git_environment() -> dict[str, str]:
    # Repository evidence must not vary with a caller's user/system Git config.
    # safe.directory is restored narrowly on each explicit read-only command.
    environment = os.environ.copy()
    unsafe_overrides = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
    for name in list(environment):
        if (
            name in unsafe_overrides
            or name.startswith("GIT_CONFIG_KEY_")
            or name.startswith("GIT_CONFIG_VALUE_")
        ):
            environment.pop(name)
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _git_bytes(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        _git_command(repo, *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )


def _require_git_bytes(
    result: subprocess.CompletedProcess[bytes],
    command: str,
) -> bytes:
    if result.returncode == 0:
        return result.stdout
    detail = (result.stderr or result.stdout).decode(errors="replace").strip()
    raise ValueError(f"{command} failed: {detail or 'unknown git error'}")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _git_command(repo, *args),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )


def read_repo_git_text(repo: Path, *args: str) -> str | None:
    """Read one Git value under the same isolated fidelity environment."""

    result = _git(repo, *args)
    return result.stdout.strip() if result.returncode == 0 else None


def _has_head(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--verify", "HEAD").returncode == 0


def _is_git_work_tree(repo: Path) -> bool:
    result = _git(repo, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_command(repo: Path, *args: str) -> tuple[str, ...]:
    return (
        "git",
        "-c",
        "safe.directory=*",
        "-c",
        f"core.attributesFile={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(repo),
        *args,
    )


def _error(name: str, expected: object, actual: object, message: str) -> RepoCheck:
    return RepoCheck(name, "error", expected, actual, message)
