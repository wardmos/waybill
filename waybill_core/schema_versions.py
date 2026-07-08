"""Waybill Bundle schema version policy."""

from __future__ import annotations


CURRENT_SCHEMA_VERSION = "0.2"
LEGACY_SCHEMA_VERSIONS = frozenset({"draft"})
KNOWN_UNSUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1"})


def schema_version_status(value: object) -> str:
    """Classify a metadata schema version for validation and reporting."""

    if not isinstance(value, str) or not value:
        return "invalid"
    if value == CURRENT_SCHEMA_VERSION:
        return "current"
    if value in LEGACY_SCHEMA_VERSIONS:
        return "legacy"
    return "unsupported"
