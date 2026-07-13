"""Read-only verification for paired delegation bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .validation import DELEGATION_RESULT_STATUSES, validate_bundle


@dataclass(frozen=True)
class DelegationPairCheck:
    name: str
    status: str
    expected: object
    actual: object
    message: str


@dataclass(frozen=True)
class DelegationPairReport:
    request: Path
    result: Path
    request_metadata: dict[str, Any] | None
    result_metadata: dict[str, Any] | None
    checks: list[DelegationPairCheck]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)

    @property
    def request_handoff(self) -> dict[str, Any]:
        return _handoff(self.request_metadata)

    @property
    def result_handoff(self) -> dict[str, Any]:
        return _handoff(self.result_metadata)


def verify_delegation_pair(
    request_path: str | Path,
    result_path: str | Path,
) -> DelegationPairReport:
    """Compare a delegation request and result without changing either bundle."""

    request = Path(request_path)
    result = Path(result_path)
    request_metadata = _read_metadata(request)
    result_metadata = _read_metadata(result)
    request_handoff = _handoff(request_metadata)
    result_handoff = _handoff(result_metadata)
    checks: list[DelegationPairCheck] = []

    _check_validation("request_bundle", request, checks)
    _check_validation("result_bundle", result, checks)
    _check_equal(
        "request_kind",
        "delegation_request",
        request_handoff.get("kind"),
        checks,
    )
    _check_equal(
        "result_kind",
        "delegation_result",
        result_handoff.get("kind"),
        checks,
    )
    _check_equal(
        "correlation",
        request_handoff.get("request_id"),
        result_handoff.get("result_for"),
        checks,
        require_non_empty=True,
    )
    _check_equal(
        "parent_agent",
        request_handoff.get("parent_agent"),
        result_handoff.get("parent_agent"),
        checks,
        require_non_empty=True,
    )
    _check_equal(
        "child_agent",
        request_handoff.get("child_agent"),
        result_handoff.get("child_agent"),
        checks,
        require_non_empty=True,
    )
    _check_equal(
        "request_source",
        request_handoff.get("parent_agent"),
        _metadata_value(request_metadata, "source_agent"),
        checks,
        require_non_empty=True,
    )
    _check_equal(
        "result_source",
        result_handoff.get("child_agent"),
        _metadata_value(result_metadata, "source_agent"),
        checks,
        require_non_empty=True,
    )

    result_status = result_handoff.get("result_status")
    if result_status in DELEGATION_RESULT_STATUSES:
        checks.append(
            DelegationPairCheck(
                "result_status",
                "ok",
                list(DELEGATION_RESULT_STATUSES),
                result_status,
                "recognized",
            )
        )
    else:
        checks.append(
            DelegationPairCheck(
                "result_status",
                "error",
                list(DELEGATION_RESULT_STATUSES),
                result_status,
                "missing or invalid",
            )
        )

    return DelegationPairReport(
        request,
        result,
        request_metadata,
        result_metadata,
        checks,
    )


def _read_metadata(bundle: Path) -> dict[str, Any] | None:
    path = bundle / "metadata.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _handoff(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    handoff = metadata.get("handoff")
    return handoff if isinstance(handoff, dict) else {}


def _metadata_value(metadata: dict[str, Any] | None, field: str) -> object:
    if not isinstance(metadata, dict):
        return None
    return metadata.get(field)


def _check_validation(
    name: str,
    bundle: Path,
    checks: list[DelegationPairCheck],
) -> None:
    errors = [
        issue for issue in validate_bundle(bundle) if issue.severity == "error"
    ]
    if errors:
        checks.append(
            DelegationPairCheck(
                name,
                "error",
                "valid bundle",
                f"{len(errors)} error(s)",
                errors[0].message,
            )
        )
        return
    checks.append(
        DelegationPairCheck(
            name,
            "ok",
            "valid bundle",
            "valid bundle",
            "valid",
        )
    )


def _check_equal(
    name: str,
    expected: object,
    actual: object,
    checks: list[DelegationPairCheck],
    *,
    require_non_empty: bool = False,
) -> None:
    complete = not require_non_empty or (
        isinstance(expected, str)
        and bool(expected.strip())
        and isinstance(actual, str)
        and bool(actual.strip())
    )
    if complete and expected == actual:
        checks.append(
            DelegationPairCheck(name, "ok", expected, actual, "matches")
        )
        return
    checks.append(
        DelegationPairCheck(name, "error", expected, actual, "does not match")
    )
