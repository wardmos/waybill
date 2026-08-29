"""Fail-closed identity probes for supported coding-agent executables."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


SUPPORTED_AGENT_PRODUCTS = (
    "claude-code",
    "codex",
    "opencode",
    "cursor",
    "gemini-cli",
)

DEFAULT_EXECUTABLES = {
    "claude-code": "claude",
    "codex": "codex",
    "opencode": "opencode",
    "cursor": "agent",
    "gemini-cli": "gemini",
}
IDENTITY_KINDS = ("executable", "launcher")

_PRODUCT_PATTERNS = (
    ("grok", re.compile(r"\bgrok\b", re.IGNORECASE)),
    ("claude-code", re.compile(r"\bclaude(?:\s+code)?\b", re.IGNORECASE)),
    ("codex", re.compile(r"\bcodex(?:-cli)?\b", re.IGNORECASE)),
    ("opencode", re.compile(r"\bopencode\b", re.IGNORECASE)),
    ("cursor", re.compile(r"\bcursor(?:\s+(?:agent|cli))?\b", re.IGNORECASE)),
    ("gemini-cli", re.compile(r"\bgemini(?:\s+cli)?\b", re.IGNORECASE)),
)
_VERSION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])v?(\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?)"
)


@dataclass(frozen=True)
class AgentIdentity:
    """Observed executable identity and provenance for one adapter."""

    adapter: str
    status: str
    requested_executable: str
    resolved_path: Path | None
    sha256: str | None
    product: str | None
    version: str | None
    observed_at: str
    version_output: str
    identity_output: str
    error_code: str | None
    error_detail: str | None

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def to_dict(
        self,
        *,
        include_private: bool,
        identity_kind: str = "executable",
    ) -> dict[str, object]:
        """Serialize a direct executable or launcher-scoped identity report."""

        if identity_kind not in IDENTITY_KINDS:
            raise ValueError(
                "identity_kind must be one of: " + ", ".join(IDENTITY_KINDS)
            )

        document: dict[str, object] = {
            "adapter": self.adapter,
            "identity_kind": identity_kind,
            "status": self.status,
            "sha256": self.sha256,
            "observed_at": self.observed_at,
            "error_code": self.error_code,
        }
        if identity_kind == "launcher":
            document.update(
                {
                    "reported_product": self.product,
                    "reported_version": self.version,
                }
            )
        else:
            document.update(
                {
                    "product": self.product,
                    "version": self.version,
                }
            )
        if include_private:
            document.update(
                {
                    "requested_executable": self.requested_executable,
                    "resolved_path": (
                        str(self.resolved_path) if self.resolved_path is not None else None
                    ),
                    "version_output": self.version_output,
                    "identity_output": self.identity_output,
                    "error_detail": self.error_detail,
                }
            )
        return document


def current_observed_at() -> str:
    """Return the current UTC time as a whole-second RFC 3339 value."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def probe_agent_identity(
    adapter: str,
    *,
    executable: str | None = None,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: float = 10.0,
    observed_at: str | None = None,
) -> AgentIdentity:
    """Resolve, fingerprint, and verify an adapter executable without model use."""

    if adapter not in SUPPORTED_AGENT_PRODUCTS:
        raise ValueError(f"unsupported adapter: {adapter}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    requested = executable or DEFAULT_EXECUTABLES[adapter]
    timestamp = observed_at or current_observed_at()
    search_path = environment.get("PATH") if environment is not None else None
    found = shutil.which(requested, path=search_path)
    if found is None:
        return _identity_failure(
            adapter,
            "missing",
            requested,
            timestamp,
            error_code="executable_not_found",
            error_detail=f"executable was not found: {requested}",
        )

    try:
        resolved = Path(found).resolve(strict=True)
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            return _identity_failure(
                adapter,
                "probe_failed",
                requested,
                timestamp,
                resolved_path=resolved,
                error_code="executable_not_runnable",
                error_detail="resolved executable is not a runnable regular file",
            )
        digest = _sha256_file(resolved)
    except OSError as exc:
        return _identity_failure(
            adapter,
            "probe_failed",
            requested,
            timestamp,
            error_code="executable_resolution_failed",
            error_detail=str(exc),
        )

    version_probe, probe_error = _run_probe(
        resolved,
        "--version",
        environment,
        timeout_seconds,
    )
    if probe_error is not None:
        return _identity_failure(
            adapter,
            "probe_failed",
            requested,
            timestamp,
            resolved_path=resolved,
            sha256=digest,
            error_code="version_probe_failed",
            error_detail=probe_error,
        )
    assert version_probe is not None
    version_output = _completed_output(version_probe)
    if version_probe.returncode != 0:
        return _identity_failure(
            adapter,
            "probe_failed",
            requested,
            timestamp,
            resolved_path=resolved,
            sha256=digest,
            version_output=version_output,
            error_code="version_probe_failed",
            error_detail=f"--version exited with status {version_probe.returncode}",
        )

    version = _detect_version(version_output)
    if version is None:
        return _identity_failure(
            adapter,
            "probe_failed",
            requested,
            timestamp,
            resolved_path=resolved,
            sha256=digest,
            version_output=version_output,
            error_code="version_unrecognized",
            error_detail="--version did not contain a recognized version",
        )

    product = _detect_product(version_output)
    identity_output = ""
    if product is None:
        help_probe, help_error = _run_probe(
            resolved,
            "--help",
            environment,
            timeout_seconds,
        )
        if help_error is not None:
            return _identity_failure(
                adapter,
                "probe_failed",
                requested,
                timestamp,
                resolved_path=resolved,
                sha256=digest,
                version_output=version_output,
                error_code="identity_probe_failed",
                error_detail=help_error,
            )
        assert help_probe is not None
        identity_output = _completed_output(help_probe)
        if help_probe.returncode == 0:
            product = _detect_product(identity_output)

    if product != adapter:
        return AgentIdentity(
            adapter=adapter,
            status="identity_mismatch",
            requested_executable=requested,
            resolved_path=resolved,
            sha256=digest,
            product=product,
            version=version,
            observed_at=timestamp,
            version_output=version_output,
            identity_output=identity_output,
            error_code="unexpected_product",
            error_detail=(
                f"expected product {adapter}, observed {product or 'unrecognized'}"
            ),
        )

    return AgentIdentity(
        adapter=adapter,
        status="verified",
        requested_executable=requested,
        resolved_path=resolved,
        sha256=digest,
        product=product,
        version=version,
        observed_at=timestamp,
        version_output=version_output,
        identity_output=identity_output,
        error_code=None,
        error_detail=None,
    )


def _identity_failure(
    adapter: str,
    status: str,
    requested: str,
    observed_at: str,
    *,
    resolved_path: Path | None = None,
    sha256: str | None = None,
    version_output: str = "",
    identity_output: str = "",
    error_code: str,
    error_detail: str,
) -> AgentIdentity:
    return AgentIdentity(
        adapter=adapter,
        status=status,
        requested_executable=requested,
        resolved_path=resolved_path,
        sha256=sha256,
        product=None,
        version=None,
        observed_at=observed_at,
        version_output=version_output,
        identity_output=identity_output,
        error_code=error_code,
        error_detail=error_detail,
    )


def _run_probe(
    executable: Path,
    argument: str,
    environment: Mapping[str, str] | None,
    timeout_seconds: float,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    try:
        return (
            subprocess.run(
                [str(executable), argument],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(environment) if environment is not None else None,
                timeout=timeout_seconds,
            ),
            None,
        )
    except subprocess.TimeoutExpired:
        return None, f"{argument} timed out after {timeout_seconds:g} seconds"
    except OSError as exc:
        return None, str(exc)


def _completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )


def _detect_product(output: str) -> str | None:
    for product, pattern in _PRODUCT_PATTERNS:
        if pattern.search(output):
            return product
    return None


def _detect_version(output: str) -> str | None:
    match = _VERSION_PATTERN.search(output)
    return match.group(1) if match is not None else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
