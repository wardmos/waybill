"""Capability quality gates for the five supported agent adapters."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from .agent_identity import (
    DEFAULT_EXECUTABLES,
    AgentIdentity,
    current_observed_at,
    probe_agent_identity,
)
from .conformance import (
    REQUIRED_IMPORT_SCENARIO_IDS,
    load_scenario,
    validate_observation,
)
from .export_conformance import REQUIRED_EXPORT_SCENARIO_IDS


REPORT_SCHEMA_VERSION = "2"
DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[1]

ADAPTER_CAPABILITY_REQUIREMENTS = {
    "claude-code": {"export": True, "import": True},
    "codex": {"export": True, "import": True},
    "opencode": {"export": False, "import": True},
    "cursor": {"export": False, "import": True},
    "gemini-cli": {"export": False, "import": True},
}

CAPABILITY_SCENARIO_REQUIREMENTS = {
    "import": REQUIRED_IMPORT_SCENARIO_IDS,
    "export": REQUIRED_EXPORT_SCENARIO_IDS,
}

SCENARIO_DIRECTORIES = {
    "import": "conformance/scenarios",
    "export": "conformance/export-scenarios",
}
IMPORT_FIXTURE_DIRECTORY = "conformance/import-fixtures"

ADAPTER_ENTRYPOINT_PATHS = {
    "claude-code": "adapters/claude-code/skills/handoff/SKILL.md",
    "codex": "adapters/codex/skills/handoff/SKILL.md",
    "cursor": "adapters/cursor/rules/handoff.mdc",
    "gemini-cli": "adapters/gemini-cli/skills/handoff/SKILL.md",
    "opencode": "adapters/opencode/skills/handoff/SKILL.md",
}

# These files define report production, identity binding, and the gates whose
# booleans are summarized by each result. The Git revision binds the rest of the
# tree; this narrower digest makes runner-contract drift independently visible.
RUNNER_CONTRACT_PATHS = {
    "import": (
        "scripts/conformance-agents.py",
        "waybill_core/agent_identity.py",
        "waybill_core/conformance.py",
    ),
    "export": (
        "scripts/conformance-exports.py",
        "waybill_core/agent_identity.py",
        "waybill_core/delegation.py",
        "waybill_core/export_conformance.py",
        "waybill_core/limits.py",
        "waybill_core/readiness.py",
        "waybill_core/repo.py",
        "waybill_core/validation.py",
    ),
}

_IMPORT_RESULT_FIELDS = {
    "scenario",
    "passed",
    "returncode",
    "observation",
    "shape_match",
    "semantic_match",
    "effects_match",
    "measured_unexpected_writes",
    "boundary_escape_detected",
    "git_write_detected",
    "stdout_truncated",
    "stderr_truncated",
    "residual_process_detected",
    "command_canary_triggered",
    "network_canary_triggered",
    "errors",
}
_EXPORT_RESULT_FIELDS = {
    "scenario",
    "handoff_kind",
    "passed",
    "agent",
    "adapter",
    "date",
    "returncode",
    "gates",
    "semantic_match",
    "semantic_checks",
    "allowed_writes",
    "unexpected_writes",
    "canaries",
    "bundle_files",
    "errors",
}
_EXPORT_GATE_FIELDS = {"validate", "ready", "verify_repo", "verify_pair"}
_EXPORT_CANARY_FIELDS = {"command_triggered", "network_triggered"}
_EXPORT_SEMANTIC_FIELDS = {
    "changed_files",
    "delegation",
    "diff",
    "goal",
    "next_step",
    "repo_state_digest",
    "risks",
    "source_agent",
    "status",
    "status_digest",
    "test_state",
}
_IMPORT_REPORT_FIELDS = {
    "schema_version",
    "capability",
    "agent",
    "adapter",
    "observed_at",
    "identity",
    "identity_probe_unexpected_writes",
    "execution_mode",
    "safety",
    "dry_run",
    "success",
    "provenance",
    "results",
}
_IMPORT_SAFETY_FIELDS = {
    "disposable_workspace",
    "environment_allowlist",
    "git_state_measured",
    "output_limit_bytes_per_stream",
    "process_group_cleanup",
    "outside_disposable_root_detection",
    "operating_system_sandbox",
    "manual_risk_acknowledged",
}
_IMPORT_OUTPUT_LIMIT_BYTES = 256 * 1024
_EXPORT_REPORT_FIELDS = {
    "schema_version",
    "capability",
    "mode",
    "execution_mode",
    "dry_run",
    "success",
    "agent",
    "identity",
    "adapter",
    "date",
    "observed_at",
    "provenance",
    "results",
}
_PROVENANCE_FIELDS = {
    "waybill_revision",
    "waybill_clean",
    "scenario_corpus_sha256",
    "adapter_entrypoint_sha256",
    "runner_contract_sha256",
}
_OBSERVATION_STATUSES = frozenset({"passed", "failed"})
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_VERSION_PATTERN = re.compile(
    r"\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?"
)
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)


@dataclass(frozen=True)
class SourceProvenance:
    """Content provenance for the clean Waybill source used by a run."""

    waybill_revision: str
    waybill_clean: bool
    scenario_corpus_sha256: str
    adapter_entrypoint_sha256: str
    runner_contract_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "waybill_revision": self.waybill_revision,
            "waybill_clean": self.waybill_clean,
            "scenario_corpus_sha256": self.scenario_corpus_sha256,
            "adapter_entrypoint_sha256": self.adapter_entrypoint_sha256,
            "runner_contract_sha256": self.runner_contract_sha256,
        }


@dataclass(frozen=True)
class ReportedAgentIdentity:
    """Verified executable identity embedded in a conformance report."""

    adapter: str
    status: str
    sha256: str
    product: str
    version: str
    observed_at: str
    identity_kind: str

    def matches(self, current: AgentIdentity) -> bool:
        """Return whether this historical evidence matches the current binary."""

        return (
            current.verified
            and self.adapter == current.adapter
            and self.status == "verified"
            and self.sha256 == current.sha256
            and self.product == current.product
            and self.version == current.version
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "adapter": self.adapter,
            "status": self.status,
            "sha256": self.sha256,
            "product": self.product,
            "version": self.version,
            "observed_at": self.observed_at,
            "identity_kind": self.identity_kind,
        }


@dataclass(frozen=True)
class CapabilityEvidence:
    """Content-addressed reference to one real conformance report file."""

    report_path: Path
    report_ref: str
    report_sha256: str
    observed_at: str
    identity: ReportedAgentIdentity
    provenance: SourceProvenance
    scenarios: tuple[str, ...]

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        document: dict[str, object] = {
            "report_ref": self.report_ref,
            "report_sha256": self.report_sha256,
            "observed_at": self.observed_at,
            "identity": self.identity.to_dict(),
            "provenance": self.provenance.to_dict(),
            "scenarios": list(self.scenarios),
        }
        if include_private:
            document["report_path"] = str(self.report_path)
        return document


@dataclass(frozen=True)
class CapabilityObservation:
    """Result derived from a complete, non-dry-run conformance report."""

    adapter: str
    capability: str
    status: str
    evidence: CapabilityEvidence

    def __post_init__(self) -> None:
        if self.status not in _OBSERVATION_STATUSES:
            allowed = ", ".join(sorted(_OBSERVATION_STATUSES))
            raise ValueError(f"capability status must be one of: {allowed}")


@dataclass(frozen=True)
class AdapterCapabilityResult:
    capability: str
    required: bool
    status: str
    evidence: CapabilityEvidence | None
    evidence_identity_match: bool | None
    evidence_source_match: bool | None

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        return {
            "capability": self.capability,
            "required": self.required,
            "status": self.status,
            "evidence_identity_match": self.evidence_identity_match,
            "evidence_source_match": self.evidence_source_match,
            "evidence": (
                self.evidence.to_dict(include_private=include_private)
                if self.evidence is not None
                else None
            ),
        }


@dataclass(frozen=True)
class AdapterMatrixEntry:
    adapter: str
    identity: AgentIdentity
    capabilities: tuple[AdapterCapabilityResult, ...]

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "identity": self.identity.to_dict(include_private=include_private),
            "capabilities": [
                capability.to_dict(include_private=include_private)
                for capability in self.capabilities
            ],
        }


@dataclass(frozen=True)
class AdapterMatrixReport:
    observed_at: str
    entries: tuple[AdapterMatrixEntry, ...]

    @property
    def identity_success(self) -> bool:
        return all(entry.identity.verified for entry in self.entries)

    @property
    def success(self) -> bool:
        return self.identity_success and all(
            capability.status == "passed"
            for entry in self.entries
            for capability in entry.capabilities
            if capability.required
        )

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        return {
            "schema_version": "1",
            "observed_at": self.observed_at,
            "identity_success": self.identity_success,
            "success": self.success,
            "entries": [
                entry.to_dict(include_private=include_private) for entry in self.entries
            ],
        }


IdentityProbe = Callable[..., AgentIdentity]


def compute_source_provenance(
    source_root: str | Path,
    *,
    adapter: str,
    capability: str,
) -> SourceProvenance:
    """Fingerprint a clean committed Waybill source checkout."""

    if adapter not in ADAPTER_ENTRYPOINT_PATHS:
        raise ValueError(f"unsupported adapter: {adapter}")
    if capability not in CAPABILITY_SCENARIO_REQUIREMENTS:
        raise ValueError(f"unsupported capability: {capability}")

    requested_root = Path(source_root).resolve()
    top_level = _run_git(requested_root, "rev-parse", "--show-toplevel")
    git_root = Path(top_level).resolve()
    if git_root != requested_root:
        raise ValueError("Waybill source root must be the Git worktree root")
    revision = _run_git(git_root, "rev-parse", "--verify", "HEAD^{commit}")
    if _REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("Waybill source revision is not a commit object id")
    status = _run_git(
        git_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        raise ValueError("Waybill source worktree must be clean")

    scenario_paths = _scenario_corpus_paths(git_root, capability)
    adapter_paths = (ADAPTER_ENTRYPOINT_PATHS[adapter],)
    runner_paths = RUNNER_CONTRACT_PATHS[capability]
    all_paths = tuple(sorted(set(scenario_paths + adapter_paths + runner_paths)))
    _require_tracked_files(git_root, all_paths)

    return SourceProvenance(
        waybill_revision=revision,
        waybill_clean=True,
        scenario_corpus_sha256=_digest_source_files(git_root, scenario_paths),
        adapter_entrypoint_sha256=_digest_source_files(git_root, adapter_paths),
        runner_contract_sha256=_digest_source_files(git_root, runner_paths),
    )


def _scenario_corpus_paths(root: Path, capability: str) -> tuple[str, ...]:
    paths = [
        f"{SCENARIO_DIRECTORIES[capability]}/{scenario}.json"
        for scenario in sorted(CAPABILITY_SCENARIO_REQUIREMENTS[capability])
    ]
    if capability != "import":
        return tuple(paths)

    fixture_roots = [
        f"{IMPORT_FIXTURE_DIRECTORY}/{scenario}"
        for scenario in sorted(CAPABILITY_SCENARIO_REQUIREMENTS[capability])
    ]
    tracked = tuple(
        sorted(
            path
            for path in _run_git(root, "ls-files", "-z", "--", *fixture_roots).split(
                "\0"
            )
            if path
        )
    )
    for fixture_root in fixture_roots:
        prefix = fixture_root + "/"
        if not any(path.startswith(prefix) for path in tracked):
            raise ValueError(
                "Waybill import fixture has no tracked artifacts: " + fixture_root
            )
    return tuple(sorted(set(paths).union(tracked)))


def _run_git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            env=_git_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValueError("could not inspect Waybill source Git state") from exc
    if completed.returncode != 0:
        raise ValueError("could not inspect Waybill source Git state")
    return completed.stdout.strip()


def _git_environment() -> dict[str, str]:
    allowed = (
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    )
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    return environment


def _require_tracked_files(root: Path, relative_paths: Sequence[str]) -> None:
    tracked = _run_git(root, "ls-files", "-z", "--", *relative_paths)
    tracked_paths = set(filter(None, tracked.split("\0")))
    missing = sorted(set(relative_paths) - tracked_paths)
    if missing:
        raise ValueError(
            "Waybill source contract files must be tracked: " + ", ".join(missing)
        )


def _digest_source_files(root: Path, relative_paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"waybill-source-contract-v1\0")
    for relative in sorted(relative_paths):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Waybill source contract file is invalid: {relative}")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ValueError(
                f"could not read Waybill source contract file: {relative}"
            ) from exc
        encoded_relative = relative.encode("utf-8")
        digest.update(len(encoded_relative).to_bytes(8, "big"))
        digest.update(encoded_relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def load_conformance_report(
    path: str | Path,
    *,
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
) -> CapabilityObservation:
    """Load one complete report and rederive its evidence-bound observation."""

    report_path = Path(path)
    try:
        raw = report_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{report_path}: could not read report: {exc}") from exc
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{report_path}: invalid report JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{report_path}: report must be a JSON object")
    if document.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"{report_path}: schema_version must be '{REPORT_SCHEMA_VERSION}'"
        )

    capability = document.get("capability")
    if (
        not isinstance(capability, str)
        or capability not in CAPABILITY_SCENARIO_REQUIREMENTS
    ):
        raise ValueError(f"{report_path}: capability must be export or import")
    if "dry_run" in document:
        if type(document["dry_run"]) is not bool:
            raise ValueError(f"{report_path}: dry_run must be a boolean")
        if document["dry_run"]:
            raise ValueError(
                f"{report_path}: dry_run preview cannot be capability evidence"
            )
    expected_report_fields = (
        _IMPORT_REPORT_FIELDS if capability == "import" else _EXPORT_REPORT_FIELDS
    )
    _require_exact_fields(
        document,
        expected_report_fields,
        report_path=report_path,
        label="report",
    )

    adapter = document["adapter"]
    if not isinstance(adapter, str) or adapter not in ADAPTER_CAPABILITY_REQUIREMENTS:
        raise ValueError(f"{report_path}: adapter is not supported")
    observed_at = _validated_observed_at(
        document["observed_at"],
        report_path,
        "observed_at",
    )
    if type(document["success"]) is not bool:
        raise ValueError(f"{report_path}: success must be a boolean")

    required_mode = "unsafe_manual"
    if document["execution_mode"] != required_mode:
        raise ValueError(
            f"{report_path}: {capability} execution_mode must be {required_mode}"
        )
    identity = _load_reported_identity(
        document["identity"],
        adapter=adapter,
        observed_at=observed_at,
        report_path=report_path,
    )
    provenance = _load_source_provenance(document["provenance"], report_path)

    if capability == "import":
        _validate_import_report_header(document, report_path)
    else:
        _validate_export_report_header(
            document,
            adapter=adapter,
            observed_at=observed_at,
            identity=identity,
            report_path=report_path,
        )

    scenarios, outcomes = _load_report_results(
        document["results"],
        capability=capability,
        adapter=adapter,
        report_agent=document["agent"],
        report_date=document.get("date"),
        report_path=report_path,
        source_root=Path(source_root).resolve(),
    )
    all_passed = all(outcomes)
    if document["success"] is not all_passed:
        raise ValueError(
            f"{report_path}: success does not match derived outcomes"
        )

    report_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    evidence = CapabilityEvidence(
        report_path=report_path.resolve(),
        report_ref=f"{adapter}:{capability}:{report_digest[7:23]}",
        report_sha256=report_digest,
        observed_at=observed_at,
        identity=identity,
        provenance=provenance,
        scenarios=scenarios,
    )
    return CapabilityObservation(
        adapter=adapter,
        capability=capability,
        status="passed" if all_passed else "failed",
        evidence=evidence,
    )


def load_capability_observations(
    paths: Sequence[str | Path],
    *,
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
) -> dict[tuple[str, str], CapabilityObservation]:
    """Load report files and reject duplicate adapter-capability evidence."""

    observations: dict[tuple[str, str], CapabilityObservation] = {}
    for path in paths:
        observation = load_conformance_report(path, source_root=source_root)
        key = (observation.adapter, observation.capability)
        if key in observations:
            raise ValueError(
                "duplicate conformance report for "
                f"{observation.adapter}:{observation.capability}"
            )
        observations[key] = observation
    return observations


def _reject_duplicate_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _require_exact_fields(
    value: object,
    expected: set[str],
    *,
    report_path: Path,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{report_path}: {label} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        raise ValueError(
            f"{report_path}: {label} missing fields: {', '.join(missing)}"
        )
    if extra:
        raise ValueError(
            f"{report_path}: {label} unexpected fields: {', '.join(extra)}"
        )
    return value


def _validated_observed_at(
    value: object,
    report_path: Path,
    field: str,
) -> str:
    if not isinstance(value, str) or _RFC3339_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{report_path}: {field} must be an RFC 3339 timestamp"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{report_path}: {field} must be an RFC 3339 timestamp"
        ) from exc
    return value


def _load_reported_identity(
    value: object,
    *,
    adapter: str,
    observed_at: str,
    report_path: Path,
) -> ReportedAgentIdentity:
    if not isinstance(value, dict):
        raise ValueError(f"{report_path}: identity must be an object")
    required = {
        "adapter",
        "status",
        "sha256",
        "product",
        "version",
        "observed_at",
        "identity_kind",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(
            f"{report_path}: identity missing fields: {', '.join(missing)}"
        )
    if value["status"] != "verified":
        raise ValueError(f"{report_path}: identity.status must be verified")
    if value["adapter"] != adapter:
        raise ValueError(f"{report_path}: identity.adapter must match adapter")
    if value["product"] != adapter:
        raise ValueError(f"{report_path}: identity.product must match adapter")
    if value["identity_kind"] != "executable":
        raise ValueError(
            f"{report_path}: identity.identity_kind must be executable"
        )
    sha256 = value["sha256"]
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise ValueError(
            f"{report_path}: identity.sha256 must be a lowercase SHA-256 digest"
        )
    version = value["version"]
    if not isinstance(version, str) or _VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(
            f"{report_path}: identity.version must be a normalized version"
        )
    identity_observed_at = _validated_observed_at(
        value["observed_at"],
        report_path,
        "identity.observed_at",
    )
    if identity_observed_at != observed_at:
        raise ValueError(
            f"{report_path}: identity.observed_at must match observed_at"
        )
    return ReportedAgentIdentity(
        adapter=adapter,
        status="verified",
        sha256=sha256,
        product=adapter,
        version=version,
        observed_at=identity_observed_at,
        identity_kind="executable",
    )


def _load_source_provenance(value: object, report_path: Path) -> SourceProvenance:
    provenance = _require_exact_fields(
        value,
        _PROVENANCE_FIELDS,
        report_path=report_path,
        label="provenance",
    )
    revision = provenance["waybill_revision"]
    if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError(
            f"{report_path}: provenance.waybill_revision must be a commit object id"
        )
    if provenance["waybill_clean"] is not True:
        raise ValueError(f"{report_path}: provenance.waybill_clean must be true")
    hashes: dict[str, str] = {}
    for field in (
        "scenario_corpus_sha256",
        "adapter_entrypoint_sha256",
        "runner_contract_sha256",
    ):
        value_hash = provenance[field]
        if (
            not isinstance(value_hash, str)
            or _SHA256_PATTERN.fullmatch(value_hash) is None
        ):
            raise ValueError(
                f"{report_path}: provenance.{field} must be a SHA-256 digest"
            )
        hashes[field] = value_hash
    return SourceProvenance(
        waybill_revision=revision,
        waybill_clean=True,
        scenario_corpus_sha256=hashes["scenario_corpus_sha256"],
        adapter_entrypoint_sha256=hashes["adapter_entrypoint_sha256"],
        runner_contract_sha256=hashes["runner_contract_sha256"],
    )


def _validate_import_report_header(
    document: dict[str, object],
    report_path: Path,
) -> None:
    if not _is_non_empty_string(document["agent"]):
        raise ValueError(f"{report_path}: agent must be a non-empty string")
    writes = _validated_path_list(
        document["identity_probe_unexpected_writes"],
        report_path=report_path,
        field="identity_probe_unexpected_writes",
    )
    if writes:
        raise ValueError(
            f"{report_path}: identity_probe_unexpected_writes must be empty"
        )
    safety = _require_exact_fields(
        document["safety"],
        _IMPORT_SAFETY_FIELDS,
        report_path=report_path,
        label="safety",
    )
    for field in (
        "disposable_workspace",
        "environment_allowlist",
        "git_state_measured",
        "manual_risk_acknowledged",
    ):
        if safety[field] is not True:
            raise ValueError(f"{report_path}: safety.{field} must be true")
    if safety["operating_system_sandbox"] is not False:
        raise ValueError(
            f"{report_path}: safety.operating_system_sandbox must be false"
        )
    if safety["output_limit_bytes_per_stream"] != _IMPORT_OUTPUT_LIMIT_BYTES:
        raise ValueError(
            f"{report_path}: safety.output_limit_bytes_per_stream must be "
            f"{_IMPORT_OUTPUT_LIMIT_BYTES}"
        )
    for field in (
        "process_group_cleanup",
        "outside_disposable_root_detection",
    ):
        if safety[field] != "best_effort":
            raise ValueError(f"{report_path}: safety.{field} must be best_effort")


def _validate_export_report_header(
    document: dict[str, object],
    *,
    adapter: str,
    observed_at: str,
    identity: ReportedAgentIdentity,
    report_path: Path,
) -> None:
    if document["mode"] != "export":
        raise ValueError(f"{report_path}: mode must be export")
    report_date = _validated_date(document["date"], report_path, "date")
    if report_date != observed_at[:10]:
        raise ValueError(f"{report_path}: date must match observed_at")
    agent = _validated_export_agent(
        document["agent"],
        report_path=report_path,
        field="agent",
    )
    if agent["product"] != adapter or agent["version"] != identity.version:
        raise ValueError(
            f"{report_path}: agent product/version must match identity"
        )


def _load_report_results(
    value: object,
    *,
    capability: str,
    adapter: str,
    report_agent: object,
    report_date: object,
    report_path: Path,
    source_root: Path,
) -> tuple[tuple[str, ...], tuple[bool, ...]]:
    if not isinstance(value, list):
        raise ValueError(f"{report_path}: results must be a list")
    scenarios: list[str] = []
    outcomes: list[bool] = []
    for index, result_value in enumerate(value):
        if capability == "import":
            scenario, outcome = _load_import_result(
                result_value,
                index=index,
                report_path=report_path,
                source_root=source_root,
            )
        else:
            scenario, outcome = _load_export_result(
                result_value,
                index=index,
                adapter=adapter,
                report_agent=report_agent,
                report_date=report_date,
                report_path=report_path,
            )
        scenarios.append(scenario)
        outcomes.append(outcome)

    duplicates = sorted(
        scenario for scenario in set(scenarios) if scenarios.count(scenario) > 1
    )
    if duplicates:
        raise ValueError(
            f"{report_path}: duplicate result scenarios: {', '.join(duplicates)}"
        )
    expected = CAPABILITY_SCENARIO_REQUIREMENTS[capability]
    actual = set(scenarios)
    if actual != expected:
        details: list[str] = []
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError(
            f"{report_path}: scenario coverage mismatch: {'; '.join(details)}"
        )
    return tuple(sorted(scenarios)), tuple(outcomes)


def _load_import_result(
    value: object,
    *,
    index: int,
    report_path: Path,
    source_root: Path,
) -> tuple[str, bool]:
    label = f"results[{index}] result"
    result = _require_exact_fields(
        value,
        _IMPORT_RESULT_FIELDS,
        report_path=report_path,
        label=label,
    )
    scenario = _validated_scenario(result["scenario"], report_path, index)
    passed = _validated_boolean(result["passed"], report_path, f"{label}.passed")
    returncode = _validated_returncode(
        result["returncode"],
        report_path,
        f"{label}.returncode",
    )
    shape_match = _validated_boolean(
        result["shape_match"], report_path, f"{label}.shape_match"
    )
    semantic_match = _validated_boolean(
        result["semantic_match"], report_path, f"{label}.semantic_match"
    )
    effects_match = _validated_boolean(
        result["effects_match"], report_path, f"{label}.effects_match"
    )
    observation = result["observation"]
    actual_shape_match = not validate_observation(observation)
    if shape_match is not actual_shape_match:
        raise ValueError(
            f"{report_path}: {label}.shape_match does not match observation shape"
        )
    expected = _load_import_expected_observation(
        source_root,
        scenario,
        report_path,
    )
    actual_semantic_match = bool(
        actual_shape_match
        and isinstance(observation, dict)
        and all(
            observation[field] == expected[field]
            for field in expected
            if field != "unexpected_writes"
        )
    )
    if semantic_match is not actual_semantic_match:
        raise ValueError(
            f"{report_path}: {label}.semantic_match does not match "
            "scenario observation"
        )
    measured_writes = _validated_path_list(
        result["measured_unexpected_writes"],
        report_path=report_path,
        field=f"{label}.measured_unexpected_writes",
    )
    actual_effects_match = bool(
        actual_shape_match
        and isinstance(observation, dict)
        and observation["unexpected_writes"] == measured_writes
        and measured_writes == expected["unexpected_writes"]
    )
    if effects_match is not actual_effects_match:
        raise ValueError(
            f"{report_path}: {label}.effects_match does not match measured effects"
        )
    safety_signals = [
        _validated_boolean(result[field], report_path, f"{label}.{field}")
        for field in (
            "boundary_escape_detected",
            "git_write_detected",
            "stdout_truncated",
            "stderr_truncated",
            "residual_process_detected",
            "command_canary_triggered",
            "network_canary_triggered",
        )
    ]
    errors = _validated_errors(result["errors"], report_path, label)
    derived = (
        returncode == 0
        and shape_match
        and actual_semantic_match
        and actual_effects_match
        and not measured_writes
        and not any(safety_signals)
    )
    _require_derived_outcome(
        passed=passed,
        derived=derived,
        errors=errors,
        report_path=report_path,
        label=label,
        capability="import",
    )
    return scenario, derived


def _load_import_expected_observation(
    source_root: Path,
    scenario: str,
    report_path: Path,
) -> dict[str, object]:
    scenario_path = source_root / SCENARIO_DIRECTORIES["import"] / f"{scenario}.json"
    try:
        loaded = load_scenario(scenario_path)
    except ValueError as exc:
        raise ValueError(
            f"{report_path}: could not load import scenario oracle: {scenario}"
        ) from exc
    return loaded.expected


def _load_export_result(
    value: object,
    *,
    index: int,
    adapter: str,
    report_agent: object,
    report_date: object,
    report_path: Path,
) -> tuple[str, bool]:
    label = f"results[{index}] result"
    result = _require_exact_fields(
        value,
        _EXPORT_RESULT_FIELDS,
        report_path=report_path,
        label=label,
    )
    scenario = _validated_scenario(result["scenario"], report_path, index)
    handoff_kind = result["handoff_kind"]
    expected_kind = _expected_export_handoff_kind(scenario)
    if handoff_kind != expected_kind:
        raise ValueError(
            f"{report_path}: {label}.handoff_kind does not match scenario"
        )
    passed = _validated_boolean(result["passed"], report_path, f"{label}.passed")
    if result["adapter"] != adapter:
        raise ValueError(f"{report_path}: {label}.adapter must match report adapter")
    result_agent = _validated_export_agent(
        result["agent"],
        report_path=report_path,
        field=f"{label}.agent",
    )
    if result_agent != report_agent:
        raise ValueError(f"{report_path}: {label}.agent must match report agent")
    result_date = _validated_date(result["date"], report_path, f"{label}.date")
    if result_date != report_date:
        raise ValueError(f"{report_path}: {label}.date must match report date")
    returncode = _validated_returncode(
        result["returncode"], report_path, f"{label}.returncode"
    )

    gates = _require_exact_fields(
        result["gates"],
        _EXPORT_GATE_FIELDS,
        report_path=report_path,
        label=f"{label}.gates",
    )
    validate_gate = _validated_boolean(
        gates["validate"], report_path, f"{label}.gates.validate"
    )
    ready_gate = _validated_boolean(
        gates["ready"], report_path, f"{label}.gates.ready"
    )
    repo_gate = _validated_boolean(
        gates["verify_repo"], report_path, f"{label}.gates.verify_repo"
    )
    pair_gate = gates["verify_pair"]
    if expected_kind == "delegation_result":
        pair_ok = _validated_boolean(
            pair_gate, report_path, f"{label}.gates.verify_pair"
        )
    else:
        if pair_gate is not None:
            raise ValueError(
                f"{report_path}: {label}.gates.verify_pair must be null"
            )
        pair_ok = True

    semantic_checks = _require_exact_fields(
        result["semantic_checks"],
        _EXPORT_SEMANTIC_FIELDS,
        report_path=report_path,
        label=f"{label}.semantic_checks",
    )
    semantic_values = [
        _validated_boolean(
            semantic_checks[field],
            report_path,
            f"{label}.semantic_checks.{field}",
        )
        for field in sorted(_EXPORT_SEMANTIC_FIELDS)
    ]
    semantic_match = _validated_boolean(
        result["semantic_match"], report_path, f"{label}.semantic_match"
    )
    if semantic_match is not all(semantic_values):
        raise ValueError(
            f"{report_path}: {label}.semantic_match does not match semantic_checks"
        )

    _validated_path_list(
        result["allowed_writes"],
        report_path=report_path,
        field=f"{label}.allowed_writes",
    )
    unexpected_writes = _validated_path_list(
        result["unexpected_writes"],
        report_path=report_path,
        field=f"{label}.unexpected_writes",
    )
    _validated_path_list(
        result["bundle_files"],
        report_path=report_path,
        field=f"{label}.bundle_files",
    )
    canaries = _require_exact_fields(
        result["canaries"],
        _EXPORT_CANARY_FIELDS,
        report_path=report_path,
        label=f"{label}.canaries",
    )
    command_triggered = _validated_boolean(
        canaries["command_triggered"],
        report_path,
        f"{label}.canaries.command_triggered",
    )
    network_triggered = _validated_boolean(
        canaries["network_triggered"],
        report_path,
        f"{label}.canaries.network_triggered",
    )
    errors = _validated_errors(result["errors"], report_path, label)
    derived = (
        returncode == 0
        and validate_gate
        and ready_gate
        and repo_gate
        and pair_ok
        and semantic_match
        and not unexpected_writes
        and not command_triggered
        and not network_triggered
    )
    _require_derived_outcome(
        passed=passed,
        derived=derived,
        errors=errors,
        report_path=report_path,
        label=label,
        capability="export",
    )
    return scenario, derived


def _require_derived_outcome(
    *,
    passed: bool,
    derived: bool,
    errors: list[str],
    report_path: Path,
    label: str,
    capability: str,
) -> None:
    if passed is not derived:
        raise ValueError(
            f"{report_path}: {label}.passed does not match derived "
            f"{capability} outcome"
        )
    if (not errors) is not derived:
        raise ValueError(
            f"{report_path}: {label}.errors do not match derived "
            f"{capability} outcome"
        )


def _validated_export_agent(
    value: object,
    *,
    report_path: Path,
    field: str,
) -> dict[str, str]:
    agent = _require_exact_fields(
        value,
        {"agent", "product", "version"},
        report_path=report_path,
        label=field,
    )
    for name in ("agent", "product", "version"):
        if not _is_non_empty_string(agent[name]):
            raise ValueError(f"{report_path}: {field}.{name} must be non-empty")
    return {
        "agent": str(agent["agent"]),
        "product": str(agent["product"]),
        "version": str(agent["version"]),
    }


def _validated_scenario(value: object, report_path: Path, index: int) -> str:
    if not _is_non_empty_string(value):
        raise ValueError(
            f"{report_path}: results[{index}].scenario must be non-empty"
        )
    return str(value)


def _validated_boolean(value: object, report_path: Path, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{report_path}: {field} must be a boolean")
    return bool(value)


def _validated_returncode(value: object, report_path: Path, field: str) -> int | None:
    if value is not None and (type(value) is not int):
        raise ValueError(f"{report_path}: {field} must be an integer or null")
    return value


def _validated_date(value: object, report_path: Path, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{report_path}: {field} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{report_path}: {field} must be an ISO date") from exc
    return value


def _validated_path_list(
    value: object,
    *,
    report_path: Path,
    field: str,
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{report_path}: {field} must be a list of paths")
    if value != sorted(value) or len(value) != len(set(value)):
        raise ValueError(f"{report_path}: {field} paths must be sorted and unique")
    for item in value:
        normalized = item[:-1] if item.endswith("/") else item
        path = PurePosixPath(normalized)
        if (
            not normalized
            or normalized == "."
            or "\\" in item
            or any(ord(character) < 32 for character in item)
            or path.is_absolute()
            or ".." in path.parts
        ):
            raise ValueError(f"{report_path}: {field} contains an unsafe path")
    return list(value)


def _validated_errors(value: object, report_path: Path, label: str) -> list[str]:
    if not isinstance(value, list) or any(not _is_non_empty_string(item) for item in value):
        raise ValueError(f"{report_path}: {label}.errors must be a list of strings")
    return list(value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _expected_export_handoff_kind(scenario: str) -> str:
    if scenario == "delegation-request":
        return "delegation_request"
    if scenario.startswith("delegation-result-"):
        return "delegation_result"
    return "handoff"


def build_adapter_matrix(
    *,
    adapters: Sequence[str] | None = None,
    executable_overrides: Mapping[str, str] | None = None,
    capability_observations: Mapping[
        tuple[str, str], CapabilityObservation
    ] | None = None,
    identity_probe: IdentityProbe = probe_agent_identity,
    observed_at: str | None = None,
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
) -> AdapterMatrixReport:
    """Probe identities and bind reports to current binaries and source."""

    selected = list(ADAPTER_CAPABILITY_REQUIREMENTS if adapters is None else adapters)
    if not selected:
        raise ValueError("adapter selection must include at least one adapter")
    if len(selected) != len(set(selected)):
        raise ValueError("adapter selection contains duplicates")
    unknown_adapters = sorted(set(selected) - set(ADAPTER_CAPABILITY_REQUIREMENTS))
    if unknown_adapters:
        raise ValueError("unknown adapters: " + ", ".join(unknown_adapters))

    overrides = dict(executable_overrides or {})
    unknown_overrides = sorted(set(overrides) - set(ADAPTER_CAPABILITY_REQUIREMENTS))
    if unknown_overrides:
        raise ValueError(
            "executable override has unknown adapters: " + ", ".join(unknown_overrides)
        )
    unselected_overrides = sorted(set(overrides) - set(selected))
    if unselected_overrides:
        raise ValueError(
            "executable override is for unselected adapter: "
            + ", ".join(unselected_overrides)
        )

    observations = dict(capability_observations or {})
    for (adapter, capability), observation in observations.items():
        requirements = ADAPTER_CAPABILITY_REQUIREMENTS.get(adapter)
        if requirements is None or capability not in requirements:
            raise ValueError(f"unknown adapter capability: {adapter}:{capability}")
        if adapter not in selected:
            raise ValueError(
                f"capability observation is for unselected adapter: {adapter}:{capability}"
            )
        if observation.adapter != adapter or observation.capability != capability:
            raise ValueError(
                f"capability observation key does not match report: {adapter}:{capability}"
            )

    current_sources = {
        key: compute_source_provenance(
            source_root,
            adapter=key[0],
            capability=key[1],
        )
        for key in observations
    }

    timestamp = observed_at or current_observed_at()
    entries: list[AdapterMatrixEntry] = []
    for adapter in selected:
        executable = overrides.get(adapter, DEFAULT_EXECUTABLES[adapter])
        identity = identity_probe(
            adapter,
            executable=executable,
            observed_at=timestamp,
        )
        capabilities: list[AdapterCapabilityResult] = []
        for capability, required in ADAPTER_CAPABILITY_REQUIREMENTS[adapter].items():
            observation = observations.get((adapter, capability))
            identity_match = (
                observation.evidence.identity.matches(identity)
                if observation is not None
                else None
            )
            source_match = (
                observation.evidence.provenance
                == current_sources[(adapter, capability)]
                if observation is not None
                else None
            )
            if observation is not None and not source_match:
                status = "source_mismatch"
            elif not identity.verified:
                status = identity.status
            elif observation is None:
                status = "not_run"
            elif not identity_match:
                status = "evidence_mismatch"
            else:
                status = observation.status
            capabilities.append(
                AdapterCapabilityResult(
                    capability=capability,
                    required=required,
                    status=status,
                    evidence=(observation.evidence if observation is not None else None),
                    evidence_identity_match=identity_match,
                    evidence_source_match=source_match,
                )
            )
        entries.append(AdapterMatrixEntry(adapter, identity, tuple(capabilities)))

    return AdapterMatrixReport(timestamp, tuple(entries))
