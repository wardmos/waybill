#!/usr/bin/env python3
"""Read-only, standard-library checks for a local Waybill Bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


MAX_FILES = 100
MAX_FILE_BYTES = 5_000_000
MAX_TOTAL_BYTES = 10_000_000
CURRENT_SCHEMA_VERSION = "0.2"
LEGACY_SCHEMA_VERSION = "draft"
REQUIRED_FILES = ("WAYBILL.md", "metadata.json")
RECOMMENDED_FILES = ("diff.patch", "commands.log", "test-summary.md")
PLACEHOLDER_PATTERN = re.compile(r"\{\{[A-Z0-9_]+\}\}")
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SENSITIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"sk-[A-Za-z0-9_-]{10,}",
        r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]+",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"(?<!\S)/(?:home|Users)/[^\s\"'`<>]+",
        r"\b[A-Za-z]:\\Users\\[^\s\"'`<>]+",
        (
            r"(?<![A-Za-z0-9_-])"
            r"['\"]?(api[_-]?key|password|secret|token|cookie)['\"]?"
            r"(?![A-Za-z0-9_-])"
            r"\s*[:=]\s*['\"]?(?!\[REDACTED\])[^\"'\s,}]+"
        ),
    )
)
WAYBILL_SECTIONS = (
    "Original Goal",
    "Current Status",
    "User Constraints",
    "Repo State",
    "Changed Files",
    "Commands Run",
    "Test State",
    "Failed Attempts",
    "Current Hypothesis",
    "Next Recommended Step",
    "Risks / Unknowns",
    "Instructions For Next Agent",
)
DELEGATION_REQUEST_SECTIONS = (
    "Delegation Request",
    "Child Agent Task",
    "Acceptance Criteria",
    "Return Instructions",
)
DELEGATION_RESULT_SECTIONS = (
    "Delegation Result",
    "Work Completed",
    "Parent Review Notes",
    "Parent Next Step",
)
RESULT_STATUSES = {"completed", "partial", "blocked"}


@dataclass(frozen=True)
class Finding:
    """One value-free checker finding."""

    code: str
    message: str
    path: str | None = None


class BundleChecker:
    """Collect bounded, value-free findings without changing the filesystem."""

    def __init__(self) -> None:
        self.errors: list[Finding] = []
        self.warnings: list[Finding] = []

    def error(self, code: str, message: str, path: str | None = None) -> None:
        self.errors.append(Finding(code, message, path))

    def warn(self, code: str, message: str, path: str | None = None) -> None:
        self.warnings.append(Finding(code, message, path))


def _read_regular_bytes(
    path: Path,
    relative: str,
    checker: BundleChecker,
) -> bytes | None:
    """Read one bounded regular file without following a replacement symlink."""

    descriptor: int | None = None
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            checker.error(
                "unsafe-entry",
                "bundle contains a symbolic link or special entry",
                relative,
            )
            return None
        if before.st_size > MAX_FILE_BYTES:
            return None

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            checker.error(
                "unsafe-entry",
                "bundle entry changed or became unsafe while being read",
                relative,
            )
            return None
        if opened.st_size > MAX_FILE_BYTES:
            checker.error(
                "file-limit",
                "bundle file exceeds the per-file size limit",
                relative,
            )
            return None

        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_FILE_BYTES:
            checker.error(
                "file-limit",
                "bundle file exceeds the per-file size limit",
                relative,
            )
            return None
    except OSError:
        checker.error("file-read", "bundle file could not be read safely", relative)
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return raw


def _strict_object(path: Path, checker: BundleChecker) -> dict[str, Any] | None:
    raw = _read_regular_bytes(path, "metadata.json", checker)
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        checker.error("metadata-encoding", "metadata.json must be UTF-8", "metadata.json")
        return None

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON field: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (json.JSONDecodeError, ValueError):
        checker.error("metadata-json", "metadata.json must contain strict JSON", "metadata.json")
        return None
    if not isinstance(document, dict):
        checker.error("metadata-object", "metadata.json must contain one object", "metadata.json")
        return None
    return document


def _inventory_bundle(bundle: Path, checker: BundleChecker) -> dict[str, Path]:
    try:
        root_metadata = bundle.lstat()
    except OSError:
        checker.error("bundle-missing", "bundle directory does not exist")
        return {}
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        checker.error("bundle-type", "bundle path must be a regular directory")
        return {}

    files: dict[str, Path] = {}
    file_count = 0
    total_bytes = 0
    try:
        walker = os.walk(bundle, topdown=True, followlinks=False)
        for current, directory_names, file_names in walker:
            current_path = Path(current)
            safe_directories: list[str] = []
            for name in directory_names:
                candidate = current_path / name
                relative = candidate.relative_to(bundle).as_posix()
                metadata = candidate.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    checker.error(
                        "unsafe-entry",
                        "bundle contains a symbolic link or special entry",
                        relative,
                    )
                    continue
                safe_directories.append(name)
            directory_names[:] = safe_directories

            for name in file_names:
                file_count += 1
                candidate = current_path / name
                relative = candidate.relative_to(bundle).as_posix()
                metadata = candidate.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    checker.error(
                        "unsafe-entry",
                        "bundle contains a symbolic link or special entry",
                        relative,
                    )
                    continue
                if metadata.st_size > MAX_FILE_BYTES:
                    checker.error(
                        "file-limit",
                        "bundle file exceeds the per-file size limit",
                        relative,
                    )
                total_bytes += metadata.st_size
                files[relative] = candidate
    except OSError:
        checker.error("bundle-read", "bundle entries could not be inspected")
        return files

    if file_count > MAX_FILES:
        checker.error("file-count-limit", "bundle contains too many files")
    if total_bytes > MAX_TOTAL_BYTES:
        checker.error("total-size-limit", "bundle exceeds the total size limit")
    return files


def _require_string(
    document: dict[str, Any],
    name: str,
    checker: BundleChecker,
    *,
    path: str = "metadata.json",
) -> str | None:
    value = document.get(name)
    if not isinstance(value, str) or not value.strip():
        checker.error("metadata-field", f"{name} must be a non-empty string", path)
        return None
    return value


def _validate_metadata(
    metadata: dict[str, Any],
    checker: BundleChecker,
    *,
    warn_missing_digests: bool = True,
) -> str:
    schema_version = metadata.get("schema_version")
    if schema_version == LEGACY_SCHEMA_VERSION:
        checker.warn(
            "legacy-schema",
            "bundle uses the legacy draft schema",
            "metadata.json",
        )
    elif schema_version != CURRENT_SCHEMA_VERSION:
        checker.error(
            "schema-version",
            "bundle schema version is unsupported",
            "metadata.json",
        )

    _require_string(metadata, "source_agent", checker)
    created_at = _require_string(metadata, "created_at", checker)
    if created_at is not None and not RFC3339_PATTERN.fullmatch(created_at):
        checker.error(
            "created-at",
            "created_at must be an RFC 3339 timestamp",
            "metadata.json",
        )
    _require_string(metadata, "repo_root", checker)

    git = metadata.get("git")
    if not isinstance(git, dict):
        checker.error("git-object", "git must be an object", "metadata.json")
        git = {}
    for name in ("branch", "base_ref", "head_sha"):
        _require_string(git, name, checker)
    if not isinstance(git.get("dirty"), bool):
        checker.error("git-dirty", "git.dirty must be boolean", "metadata.json")
    for name, missing_code in (
        ("status_digest", "status-digest-missing"),
        ("repo_state_digest", "repo-state-digest-missing"),
    ):
        value = git.get(name)
        if value is None:
            if warn_missing_digests:
                checker.warn(
                    missing_code,
                    f"optional git.{name} was not recorded",
                    "metadata.json",
                )
        elif not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            checker.error(
                "digest-format",
                f"git.{name} must be an exact sha256 digest",
                "metadata.json",
            )

    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict):
        checker.error("artifacts-object", "artifacts must be an object", "metadata.json")
    elif not isinstance(artifacts.get("waybill"), str):
        checker.error(
            "waybill-artifact",
            "artifacts.waybill must name WAYBILL.md",
            "metadata.json",
        )

    source_agent = metadata.get("source_agent")
    handoff = metadata.get("handoff")
    if handoff is None:
        return "handoff"
    if not isinstance(handoff, dict):
        checker.error("handoff-object", "handoff must be an object", "metadata.json")
        return "handoff"
    kind = handoff.get("kind", "handoff")
    if kind not in {"handoff", "delegation_request", "delegation_result"}:
        checker.error("handoff-kind", "handoff kind is unsupported", "metadata.json")
        return "handoff"
    if kind == "delegation_request":
        for name in ("request_id", "parent_agent", "child_agent"):
            _require_string(handoff, name, checker)
        if source_agent != handoff.get("parent_agent"):
            checker.error(
                "delegation-source",
                "delegation request source_agent must equal parent_agent",
                "metadata.json",
            )
    elif kind == "delegation_result":
        for name in ("result_for", "parent_agent", "child_agent"):
            _require_string(handoff, name, checker)
        if handoff.get("result_status") not in RESULT_STATUSES:
            checker.error(
                "delegation-status",
                "delegation result_status is invalid",
                "metadata.json",
            )
        if source_agent != handoff.get("child_agent"):
            checker.error(
                "delegation-source",
                "delegation result source_agent must equal child_agent",
                "metadata.json",
            )
    return str(kind)


def _validate_artifacts(
    metadata: dict[str, Any],
    files: dict[str, Path],
    checker: BundleChecker,
) -> None:
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict):
        return
    for name, value in artifacts.items():
        if not isinstance(value, str) or not value:
            checker.error("artifact-path", "artifact path must be a string", "metadata.json")
            continue
        relative = PurePosixPath(value)
        if (
            "\\" in value
            or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            checker.error(
                "artifact-path",
                "artifact path must stay inside the bundle",
                "metadata.json",
            )
            continue
        normalized = relative.as_posix()
        if normalized not in files:
            finding = Finding(
                "artifact-missing",
                "declared artifact is missing",
                normalized,
            )
            if name == "waybill":
                checker.errors.append(finding)
            else:
                checker.warnings.append(finding)


def _read_utf8(path: Path, relative: str, checker: BundleChecker) -> str | None:
    raw = _read_regular_bytes(path, relative, checker)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        checker.error("text-read", "bundle text file must be readable UTF-8", relative)
        return None


def _validate_bundle_content(
    files: dict[str, Path],
    metadata: dict[str, Any] | None,
    kind: str,
    checker: BundleChecker,
) -> None:
    for name in REQUIRED_FILES:
        if name not in files:
            checker.error("required-file", "required bundle file is missing", name)
    for name in RECOMMENDED_FILES:
        if name not in files:
            checker.warn("recommended-file-missing", "recommended file is missing", name)

    placeholder_files = ("WAYBILL.md", "metadata.json", "commands.log", "test-summary.md")
    for relative in placeholder_files:
        path = files.get(relative)
        if path is None:
            continue
        text = _read_utf8(path, relative, checker)
        if text is not None and PLACEHOLDER_PATTERN.search(text):
            checker.error(
                "unresolved-placeholder",
                "bundle contains an unresolved template placeholder",
                relative,
            )

    waybill_path = files.get("WAYBILL.md")
    if waybill_path is None:
        return
    waybill = _read_utf8(waybill_path, "WAYBILL.md", checker)
    if waybill is None:
        return
    sections = list(WAYBILL_SECTIONS)
    if kind == "delegation_request":
        sections.extend(DELEGATION_REQUEST_SECTIONS)
    elif kind == "delegation_result":
        sections.extend(DELEGATION_RESULT_SECTIONS)
    for heading in sections:
        pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
        if not pattern.search(waybill):
            checker.error(
                "waybill-section",
                "WAYBILL.md is missing a required section",
                "WAYBILL.md",
            )

    if metadata is not None:
        _validate_artifacts(metadata, files, checker)


def _scan_sensitive_content(
    files: dict[str, Path],
    checker: BundleChecker,
) -> None:
    """Scan every bounded regular file without returning matched values."""

    for relative, path in files.items():
        raw = _read_regular_bytes(path, relative, checker)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            checker.warn(
                "content-encoding",
                "could not scan binary or non-UTF-8 file",
                relative,
            )
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                checker.error(
                    "sensitive-content",
                    "bundle contains possible sensitive content",
                    relative,
                )


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    unsafe_names = {
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
            name in unsafe_names
            or name.startswith("GIT_CONFIG_KEY_")
            or name.startswith("GIT_CONFIG_VALUE_")
        ):
            environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return environment


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    if result.returncode != 0:
        raise ValueError("Git repository state could not be read")
    return result.stdout


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


def _repo_state(repo: Path) -> dict[str, object]:
    branch = _git(repo, "branch", "--show-current").decode("utf-8").strip() or "HEAD"
    head_sha = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    status = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    index = _git(repo, "ls-files", "--stage", "-z")
    diff = _git(
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
    return {
        "branch": branch,
        "head_sha": head_sha,
        "dirty": bool(status),
        "status_digest": _digest(
            b"waybill-status-v1",
            [(b"porcelain-v1-z", status)],
        ),
        "repo_state_digest": _digest(
            b"waybill-repo-state-v1",
            [
                (b"porcelain-v1-z", status),
                (b"index-v1-z", index),
                (b"unstaged-diff-v1", diff),
            ],
        ),
    }


def _compare_repo(
    metadata: dict[str, Any],
    repo: Path,
    checker: BundleChecker,
) -> None:
    try:
        current = _repo_state(repo)
    except (OSError, UnicodeDecodeError, ValueError):
        checker.error("repo-state", "target Git repository could not be inspected")
        return
    expected = metadata.get("git")
    if not isinstance(expected, dict):
        return
    for name, code in (
        ("branch", "repo-branch"),
        ("head_sha", "repo-head"),
        ("dirty", "repo-dirty"),
        ("status_digest", "repo-status-digest"),
        ("repo_state_digest", "repo-state-digest"),
    ):
        value = expected.get(name)
        if value in {None, "", "unknown"}:
            continue
        if value != current[name]:
            checker.error(code, f"recorded git.{name} does not match the target repository")


def _check_pair(
    request_path: Path,
    result_metadata: dict[str, Any],
    result_kind: str,
    checker: BundleChecker,
) -> None:
    request_files = _inventory_bundle(request_path, checker)
    request_metadata_path = request_files.get("metadata.json")
    if request_metadata_path is None:
        checker.error("delegation-request", "request bundle metadata is missing")
        return
    request_metadata = _strict_object(request_metadata_path, checker)
    if request_metadata is None:
        return
    request_kind = _validate_metadata(
        request_metadata,
        checker,
        warn_missing_digests=False,
    )
    if request_kind != "delegation_request":
        checker.error("delegation-request-kind", "request bundle kind is invalid")
        return
    if result_kind != "delegation_result":
        checker.error("delegation-result-kind", "checked bundle is not a delegation result")
        return
    request_handoff = request_metadata.get("handoff")
    result_handoff = result_metadata.get("handoff")
    if not isinstance(request_handoff, dict) or not isinstance(result_handoff, dict):
        return
    if result_handoff.get("result_for") != request_handoff.get("request_id"):
        checker.error(
            "delegation-result-for",
            "delegation result does not reference the request ID",
        )
    for name in ("parent_agent", "child_agent"):
        if result_handoff.get(name) != request_handoff.get(name):
            checker.error(
                "delegation-role",
                "delegation request and result roles do not match",
            )


def check_bundle(
    bundle: Path,
    repo: Path,
    request: Path | None,
) -> BundleChecker:
    checker = BundleChecker()
    files = _inventory_bundle(bundle, checker)
    metadata_path = files.get("metadata.json")
    metadata = _strict_object(metadata_path, checker) if metadata_path else None
    kind = _validate_metadata(metadata, checker) if metadata is not None else "handoff"
    _validate_bundle_content(files, metadata, kind, checker)
    _scan_sensitive_content(files, checker)
    if metadata is not None:
        _compare_repo(metadata, repo, checker)
        if request is not None:
            _check_pair(request, metadata, kind, checker)
    elif request is not None:
        checker.error("delegation-result", "result metadata is unavailable")
    return checker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a Waybill Bundle without modifying it or its repository."
    )
    parser.add_argument("bundle", help="path to the Waybill Bundle directory")
    parser.add_argument(
        "--repo",
        default=".",
        help="target Git repository to compare; defaults to the current directory",
    )
    parser.add_argument(
        "--request",
        help="optional delegation request bundle for result correlation checks",
    )
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checker = check_bundle(
        Path(args.bundle),
        Path(args.repo),
        Path(args.request) if args.request else None,
    )
    success = not checker.errors
    if args.json:
        print(
            json.dumps(
                {
                    "success": success,
                    "errors": [asdict(finding) for finding in checker.errors],
                    "warnings": [asdict(finding) for finding in checker.warnings],
                },
                indent=2,
            )
        )
    else:
        for finding in checker.errors:
            location = f" {finding.path}" if finding.path else ""
            print(f"ERROR {finding.code}{location}: {finding.message}")
        for finding in checker.warnings:
            location = f" {finding.path}" if finding.path else ""
            print(f"WARNING {finding.code}{location}: {finding.message}")
        if success:
            print("PASS bundle check completed")
        else:
            print("FAIL bundle check found blocking errors")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
