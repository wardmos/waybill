"""Capability quality gates for the five supported agent adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .agent_identity import (
    DEFAULT_EXECUTABLES,
    AgentIdentity,
    current_observed_at,
    probe_agent_identity,
)
from .conformance import REQUIRED_IMPORT_SCENARIO_IDS
from .export_conformance import REQUIRED_EXPORT_SCENARIO_IDS


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

_OBSERVATION_STATUSES = frozenset({"passed", "failed"})
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_VERSION_PATTERN = re.compile(
    r"\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?"
)
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)


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
    scenarios: tuple[str, ...]

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        document: dict[str, object] = {
            "report_ref": self.report_ref,
            "report_sha256": self.report_sha256,
            "observed_at": self.observed_at,
            "identity": self.identity.to_dict(),
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

    def to_dict(self, *, include_private: bool) -> dict[str, object]:
        document: dict[str, object] = {
            "capability": self.capability,
            "required": self.required,
            "status": self.status,
            "evidence_identity_match": self.evidence_identity_match,
            "evidence": (
                self.evidence.to_dict(include_private=include_private)
                if self.evidence is not None
                else None
            ),
        }
        return document


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


def load_conformance_report(path: str | Path) -> CapabilityObservation:
    """Load one complete report and derive its evidence-bound observation."""

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

    required_fields = {
        "schema_version",
        "capability",
        "adapter",
        "observed_at",
        "identity",
        "dry_run",
        "execution_mode",
        "success",
        "results",
    }
    missing = sorted(required_fields - set(document))
    if missing:
        raise ValueError(f"{report_path}: report missing fields: {', '.join(missing)}")
    if document["schema_version"] != "1":
        raise ValueError(f"{report_path}: schema_version must be '1'")

    capability = document["capability"]
    if (
        not isinstance(capability, str)
        or capability not in CAPABILITY_SCENARIO_REQUIREMENTS
    ):
        raise ValueError(f"{report_path}: capability must be export or import")
    adapter = document["adapter"]
    if not isinstance(adapter, str) or adapter not in ADAPTER_CAPABILITY_REQUIREMENTS:
        raise ValueError(f"{report_path}: adapter is not supported")

    observed_at = _validated_observed_at(
        document["observed_at"],
        report_path,
        "observed_at",
    )
    if type(document["dry_run"]) is not bool:
        raise ValueError(f"{report_path}: dry_run must be a boolean")
    if document["dry_run"]:
        raise ValueError(f"{report_path}: dry_run must be false")
    if type(document["success"]) is not bool:
        raise ValueError(f"{report_path}: success must be a boolean")

    required_execution_mode = "unsafe_manual" if capability == "export" else "manual"
    if document["execution_mode"] != required_execution_mode:
        raise ValueError(
            f"{report_path}: {capability} execution_mode must be "
            f"{required_execution_mode}"
        )
    identity = _load_reported_identity(
        document["identity"],
        adapter=adapter,
        capability=capability,
        observed_at=observed_at,
        report_path=report_path,
    )
    scenarios, all_passed = _load_report_results(
        document["results"],
        capability=capability,
        report_path=report_path,
    )
    if document["success"] is not all_passed:
        raise ValueError(
            f"{report_path}: success does not match result outcomes"
        )

    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    evidence = CapabilityEvidence(
        report_path=report_path.resolve(),
        report_ref=f"{adapter}:{capability}:{digest[7:23]}",
        report_sha256=digest,
        observed_at=observed_at,
        identity=identity,
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
) -> dict[tuple[str, str], CapabilityObservation]:
    """Load report files and reject duplicate adapter-capability evidence."""

    observations: dict[tuple[str, str], CapabilityObservation] = {}
    for path in paths:
        observation = load_conformance_report(path)
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
    capability: str,
    observed_at: str,
    report_path: Path,
) -> ReportedAgentIdentity:
    if not isinstance(value, dict):
        raise ValueError(f"{report_path}: identity must be an object")
    required = {"adapter", "status", "sha256", "product", "version", "observed_at"}
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
    identity_kind = value.get("identity_kind")
    if capability == "export" and identity_kind != "executable":
        raise ValueError(
            f"{report_path}: identity.identity_kind must be executable"
        )
    if capability == "import" and identity_kind != "executable":
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


def _load_report_results(
    value: object,
    *,
    capability: str,
    report_path: Path,
) -> tuple[tuple[str, ...], bool]:
    if not isinstance(value, list):
        raise ValueError(f"{report_path}: results must be a list")
    scenarios: list[str] = []
    outcomes: list[bool] = []
    for index, result in enumerate(value):
        if not isinstance(result, dict):
            raise ValueError(f"{report_path}: results[{index}] must be an object")
        scenario = result.get("scenario")
        passed = result.get("passed")
        if not isinstance(scenario, str) or not scenario:
            raise ValueError(
                f"{report_path}: results[{index}].scenario must be non-empty"
            )
        if type(passed) is not bool:
            raise ValueError(
                f"{report_path}: results[{index}].passed must be a boolean"
            )
        scenarios.append(scenario)
        outcomes.append(passed)

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
    return tuple(sorted(scenarios)), all(outcomes)


def build_adapter_matrix(
    *,
    adapters: Sequence[str] | None = None,
    executable_overrides: Mapping[str, str] | None = None,
    capability_observations: Mapping[
        tuple[str, str], CapabilityObservation
    ] | None = None,
    identity_probe: IdentityProbe = probe_agent_identity,
    observed_at: str | None = None,
) -> AdapterMatrixReport:
    """Probe identities and bind complete conformance reports to those binaries."""

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
            evidence_match = (
                observation.evidence.identity.matches(identity)
                if observation is not None
                else None
            )
            if not identity.verified:
                status = identity.status
            elif observation is None:
                status = "not_run"
            elif not evidence_match:
                status = "evidence_mismatch"
            else:
                status = observation.status
            capabilities.append(
                AdapterCapabilityResult(
                    capability=capability,
                    required=required,
                    status=status,
                    evidence=(observation.evidence if observation is not None else None),
                    evidence_identity_match=evidence_match,
                )
            )
        entries.append(AdapterMatrixEntry(adapter, identity, tuple(capabilities)))

    return AdapterMatrixReport(timestamp, tuple(entries))
