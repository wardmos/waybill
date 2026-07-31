#!/usr/bin/env python3
"""Waybill command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from waybill_core import __version__  # noqa: E402
from waybill_core.application import (  # noqa: E402
    InspectBundleReport,
    WaybillApplication,
)
from waybill_core.doctor import (  # noqa: E402
    DoctorCheck,
    DoctorReport,
)
from waybill_core.delegation import (  # noqa: E402
    DelegationPairCheck,
    DelegationPairReport,
)
from waybill_core.install import (  # noqa: E402
    InstallAction,
    InstallReport,
)
from waybill_core.limits import MAX_DIFF_BYTES  # noqa: E402
from waybill_core.packing import (  # noqa: E402
    PackReport,
    PackedFile,
    UnpackReport,
)
from waybill_core.preflight import (  # noqa: E402
    ImportPreflightReport,
)
from waybill_core.readiness import (  # noqa: E402
    ExportReadinessReport,
    ReadinessCheck,
)
from waybill_core.redaction import (  # noqa: E402
    RedactedFile,
    RedactionReport,
)
from waybill_core.repo import (  # noqa: E402
    RepoCheck,
    RepoVerificationReport,
)
from waybill_core.scaffold import DraftBundleReport  # noqa: E402
from waybill_core.schema_versions import schema_version_status  # noqa: E402
from waybill_core.sharing import (  # noqa: E402
    ShareCheckReport,
    ShareFinding,
    ShareReport,
)
from waybill_core.validation import ValidationIssue  # noqa: E402


JSON_HELP = (
    "write one JSON object with a top-level boolean success field; success is "
    "true exactly when the exit status is zero"
)
APPLICATION = WaybillApplication()


class CliUsageError(ValueError):
    """An argparse error retained for either text or JSON rendering."""

    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        self.parser = parser
        self.message = message
        super().__init__(message)


class WaybillArgumentParser(argparse.ArgumentParser):
    """Defer usage-error formatting until the requested output mode is known."""

    def error(self, message: str) -> None:
        raise CliUsageError(self, message)


def print_json_error(message: str) -> None:
    print(json.dumps({"success": False, "error": message}, indent=2))


def operation_error(operation: object) -> str:
    problems = getattr(operation, "problems", ())
    if problems:
        return str(problems[0].message)
    return "operation failed"


def operation_json_report(
    operation: object,
    report: dict[str, object],
) -> dict[str, object]:
    """Bind transport status fields to the facade result, not payload details."""

    rendered = dict(report)
    rendered["success"] = bool(getattr(operation, "success", False))
    valid = getattr(operation, "valid", None)
    if "valid" in rendered and valid is not None:
        rendered["valid"] = bool(valid)
    return rendered


def operation_exit_code(operation: object) -> int:
    """Return the process status represented by an application result."""

    return 0 if getattr(operation, "success", False) else 1


def print_field(label: str, value: object) -> None:
    if value is None or value == "":
        value = "unknown"
    print(f"{label}: {value}")


def issue_to_dict(issue: ValidationIssue) -> dict[str, object]:
    return {
        "severity": issue.severity,
        "message": issue.message,
        "path": issue.path,
    }


def build_validation_report(
    bundle: str | Path,
    issues: list[ValidationIssue],
) -> dict[str, object]:
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    return {
        "bundle": str(bundle),
        "success": len(errors) == 0,
        "valid": len(errors) == 0,
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": [issue_to_dict(issue) for issue in issues],
    }


def doctor_check_to_dict(check: DoctorCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "state": check.state,
        "message": check.message,
    }


def build_doctor_report(report: DoctorReport) -> dict[str, object]:
    return {
        "target": str(report.target),
        "adapters": report.adapters,
        "success": not report.has_errors,
        "valid": not report.has_errors,
        "codex_plugin_managed_by_init": report.codex_plugin_managed_by_init,
        "codex_plugin_message": report.codex_plugin_message,
        "checks": [doctor_check_to_dict(check) for check in report.checks],
    }


def install_action_to_dict(action: InstallAction) -> dict[str, object]:
    return {
        "path": action.path,
        "action": action.action,
    }


def build_install_report(report: InstallReport) -> dict[str, object]:
    return {
        "target": str(report.target),
        "adapters": report.adapters,
        "success": not report.has_conflicts,
        "dry_run": report.dry_run,
        "has_conflicts": report.has_conflicts,
        "actions": [install_action_to_dict(action) for action in report.actions],
    }


def build_draft_report(report: DraftBundleReport) -> dict[str, object]:
    return {
        "output": str(report.output),
        "repo": str(report.repo),
        "source_agent": report.source_agent,
        "dirty": report.dirty,
        "success": True,
        "files": report.files,
    }


def redacted_file_to_dict(file: RedactedFile) -> dict[str, object]:
    return {
        "path": file.path,
        "replacements": file.replacements,
        "copied_binary": file.copied_binary,
    }


def build_redaction_report(report: RedactionReport) -> dict[str, object]:
    return {
        "source": str(report.source),
        "output": str(report.output),
        "success": True,
        "files_processed": len(report.files),
        "replacements": report.replacement_count,
        "files": [redacted_file_to_dict(file) for file in report.files],
    }


def packed_file_to_dict(file: PackedFile) -> dict[str, object]:
    return {
        "path": file.path,
        "size": file.size,
    }


def build_pack_report(
    report: PackReport,
    validation: dict[str, object],
) -> dict[str, object]:
    return {
        "source": str(report.source),
        "output": str(report.output),
        "archive_root": report.archive_root,
        "success": True,
        "file_count": report.file_count,
        "byte_count": report.byte_count,
        "validation": validation,
        "files": [packed_file_to_dict(file) for file in report.files],
    }


def build_share_report(report: ShareReport) -> dict[str, object]:
    validation = build_validation_report(report.redacted, report.validation_issues)
    return {
        "source": str(report.source),
        "redacted": str(report.redacted),
        "archive": str(report.archive),
        "success": True,
        "redaction": build_redaction_report(report.redaction),
        "validation": validation,
        "pack": build_pack_report(report.pack, validation),
    }


def share_finding_to_dict(finding: ShareFinding) -> dict[str, object]:
    return {
        "kind": finding.kind,
        "path": finding.path,
        "count": finding.count,
        "blocking": finding.blocking,
    }


def build_share_check_report(report: ShareCheckReport) -> dict[str, object]:
    return {
        "source": str(report.source),
        "success": report.shareable,
        "shareable": report.shareable,
        "replacement_count": report.replacement_count,
        "error_count": report.error_count,
        "finding_count": report.finding_count,
        "findings": [share_finding_to_dict(finding) for finding in report.findings],
    }


def build_unpack_report(
    report: UnpackReport,
    validation: dict[str, object],
) -> dict[str, object]:
    return {
        "source": str(report.source),
        "output": str(report.output),
        "bundle": str(report.bundle),
        "archive_root": report.archive_root,
        "success": True,
        "file_count": report.file_count,
        "byte_count": report.byte_count,
        "validation": validation,
        "files": [packed_file_to_dict(file) for file in report.files],
    }


def build_render_report(
    bundle: str | Path,
    output: str | Path,
    rendered: str,
    validation: dict[str, object],
) -> dict[str, object]:
    return {
        "bundle": str(bundle),
        "output": str(output),
        "success": True,
        "bytes": len(rendered.encode()),
        "validation": validation,
    }


def repo_check_to_dict(check: RepoCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "expected": check.expected,
        "actual": check.actual,
        "message": check.message,
    }


def build_repo_report(report: RepoVerificationReport) -> dict[str, object]:
    return {
        "bundle": str(report.bundle),
        "repo": str(report.repo),
        "success": not report.has_errors,
        "valid": not report.has_errors,
        "checks": [repo_check_to_dict(check) for check in report.checks],
    }


def delegation_pair_check_to_dict(
    check: DelegationPairCheck,
) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "expected": check.expected,
        "actual": check.actual,
        "message": check.message,
    }


def build_delegation_pair_report(
    report: DelegationPairReport,
) -> dict[str, object]:
    request_handoff = report.request_handoff
    result_handoff = report.result_handoff
    return {
        "request": str(report.request),
        "result": str(report.result),
        "success": not report.has_errors,
        "valid": not report.has_errors,
        "request_id": request_handoff.get("request_id"),
        "result_for": result_handoff.get("result_for"),
        "result_status": result_handoff.get("result_status"),
        "parent_agent": request_handoff.get("parent_agent"),
        "child_agent": request_handoff.get("child_agent"),
        "checks": [
            delegation_pair_check_to_dict(check) for check in report.checks
        ],
    }


def build_preflight_report(report: ImportPreflightReport) -> dict[str, object]:
    validation = build_validation_report(
        report.bundle,
        report.validation_issues,
    )
    return {
        "bundle": str(report.bundle),
        "repo": str(report.repo),
        "success": not report.has_errors,
        "valid": not report.has_errors,
        "validation": validation,
        "repo_checks": [
            repo_check_to_dict(check) for check in report.repo_report.checks
        ],
    }


def readiness_check_to_dict(check: ReadinessCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "status": check.status,
        "message": check.message,
        "path": check.path,
    }


def build_readiness_report(report: ExportReadinessReport) -> dict[str, object]:
    validation = build_validation_report(
        report.bundle,
        report.validation_issues,
    )
    return {
        "bundle": str(report.bundle),
        "repo": str(report.repo),
        "success": not report.has_errors,
        "valid": not report.has_errors,
        "validation": validation,
        "repo_checks": [
            repo_check_to_dict(check) for check in report.repo_report.checks
        ],
        "content_checks": [
            readiness_check_to_dict(check) for check in report.content_checks
        ],
    }


def build_inspect_report(inspection: InspectBundleReport) -> dict[str, object]:
    bundle = inspection.bundle
    metadata = inspection.metadata
    metadata_error = inspection.metadata_error
    issues = inspection.validation_issues
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    handoff_metadata = (
        metadata.get("handoff")
        if isinstance(metadata, dict) and isinstance(metadata.get("handoff"), dict)
        else {"kind": "handoff"}
    )

    return {
        "bundle": str(bundle),
        "success": len(errors) == 0,
        "valid": len(errors) == 0,
        "schema_version_status": (
            schema_version_status(metadata.get("schema_version"))
            if metadata is not None
            else "invalid"
        ),
        "handoff": handoff_metadata,
        "metadata": metadata,
        "metadata_error": metadata_error,
        "artifacts": [
            {
                "name": artifact.name,
                "path": artifact.path,
                "status": artifact.status,
                "bytes": artifact.byte_count,
            }
            for artifact in inspection.artifacts
        ],
        "validation": {
            "errors": len(errors),
            "warnings": len(warnings),
            "issues": [issue_to_dict(issue) for issue in issues],
        },
    }


def cmd_validate(args: argparse.Namespace) -> int:
    operation = APPLICATION.validate(args.bundle)
    issues = operation.payload
    if issues is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    if args.json:
        print(
            json.dumps(
                operation_json_report(
                    operation,
                    build_validation_report(args.bundle, issues),
                ),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    if issues:
        for issue in issues:
            output = sys.stderr if issue.severity == "error" else sys.stdout
            print(issue.format(), file=output)
    if not operation.success:
        print(f"FAIL invalid Waybill Bundle: {args.bundle}", file=sys.stderr)
        return operation_exit_code(operation)
    print(f"PASS valid Waybill Bundle: {args.bundle}")
    return operation_exit_code(operation)


def cmd_init(args: argparse.Namespace) -> int:
    operation = APPLICATION.install_adapters(
        REPO_ROOT,
        args.target,
        args.adapter or ["all"],
        force=args.force,
        dry_run=args.dry_run,
    )
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_install_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    if report.dry_run:
        print(f"Waybill adapter installation plan for: {report.target}")
    else:
        print(f"Initialized Waybill adapters in: {report.target}")
    print(f"Adapters: {', '.join(report.adapters)}")
    for action in report.actions:
        print(f"  - {action.action}: {action.path}")
    if not operation.success:
        print("FAIL adapter installation has conflicts", file=sys.stderr)
        return operation_exit_code(operation)
    return operation_exit_code(operation)


def cmd_doctor(args: argparse.Namespace) -> int:
    operation = APPLICATION.doctor(
        args.target,
        args.adapter or ["all"],
        source_root=REPO_ROOT,
    )
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_doctor_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Waybill doctor target: {report.target}")
    print(f"Adapters: {', '.join(report.adapters)}")
    for check in report.checks:
        print(f"  - {check.status.upper()}: {check.name}: {check.message}")

    if not operation.success:
        print("FAIL Waybill adapter installation has problems", file=sys.stderr)
        return operation_exit_code(operation)

    print("PASS Waybill adapter installation looks ready")
    return operation_exit_code(operation)


def cmd_verify_repo(args: argparse.Namespace) -> int:
    operation = APPLICATION.verify_repo(args.bundle, args.repo)
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_repo_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Bundle: {report.bundle}")
    print(f"Repo: {report.repo}")
    for check in report.checks:
        print(
            f"  - {check.status.upper()}: {check.name}: "
            f"expected={check.expected!r} actual={check.actual!r} - {check.message}"
        )

    if not operation.success:
        sys.stdout.flush()
        print("FAIL bundle repo state does not match current repo", file=sys.stderr)
        return operation_exit_code(operation)

    print("PASS bundle repo state matches current repo")
    return operation_exit_code(operation)


def cmd_verify_pair(args: argparse.Namespace) -> int:
    operation = APPLICATION.verify_pair(args.request, args.result)
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    if args.json:
        print(
            json.dumps(
                operation_json_report(
                    operation,
                    build_delegation_pair_report(report),
                ),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Delegation request: {report.request}")
    print(f"Delegation result: {report.result}")
    for check in report.checks:
        print(
            f"  - {check.status.upper()}: {check.name}: "
            f"expected={check.expected!r} actual={check.actual!r} - {check.message}"
        )

    if not operation.success:
        sys.stdout.flush()
        print("FAIL delegation result does not match request", file=sys.stderr)
        return operation_exit_code(operation)

    print("PASS delegation result matches request")
    return operation_exit_code(operation)


def cmd_new(args: argparse.Namespace) -> int:
    operation = APPLICATION.create_draft(
        args.output,
        args.repo,
        source_agent=args.source_agent,
        goal=args.goal,
        force=args.force,
        max_diff_bytes=args.max_diff_bytes,
    )
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_draft_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Draft bundle: {report.output}")
    print(f"Repo: {report.repo}")
    print(f"Source agent: {report.source_agent}")
    print(f"Dirty: {report.dirty}")
    print("Files:")
    for file in report.files:
        print(f"  - {file}")
    print("Review and edit the draft bundle before importing it elsewhere.")
    return operation_exit_code(operation)


def cmd_preflight(args: argparse.Namespace) -> int:
    operation = APPLICATION.preflight(args.bundle, args.repo)
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    errors = report.validation_errors
    warnings = report.validation_warnings
    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_preflight_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Bundle: {report.bundle}")
    print(f"Repo: {report.repo}")
    print(f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)")
    for issue in report.validation_issues:
        print(f"  - {issue.format()}")

    print("Repo checks:")
    for check in report.repo_report.checks:
        print(
            f"  - {check.status.upper()}: {check.name}: "
            f"expected={check.expected!r} actual={check.actual!r} - {check.message}"
        )

    if not operation.success:
        sys.stdout.flush()
        print("FAIL import preflight found blocking issues", file=sys.stderr)
        return operation_exit_code(operation)

    print("PASS import preflight passed")
    return operation_exit_code(operation)


def cmd_ready(args: argparse.Namespace) -> int:
    operation = APPLICATION.ready(args.bundle, args.repo)
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    errors = [
        issue for issue in report.validation_issues if issue.severity == "error"
    ]
    warnings = [
        issue for issue in report.validation_issues if issue.severity == "warning"
    ]
    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_readiness_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Bundle: {report.bundle}")
    print(f"Repo: {report.repo}")
    print(f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)")
    for issue in report.validation_issues:
        print(f"  - {issue.format()}")

    print("Repo checks:")
    for check in report.repo_report.checks:
        print(
            f"  - {check.status.upper()}: {check.name}: "
            f"expected={check.expected!r} actual={check.actual!r} - {check.message}"
        )

    print("Content checks:")
    for check in report.content_checks:
        path = f" {check.path}" if check.path else ""
        print(f"  - {check.status.upper()}: {check.name}{path}: {check.message}")

    if not operation.success:
        sys.stdout.flush()
        print("FAIL bundle is not ready for handoff", file=sys.stderr)
        return operation_exit_code(operation)

    print("PASS bundle is ready for handoff")
    return operation_exit_code(operation)


def cmd_inspect(args: argparse.Namespace) -> int:
    operation = APPLICATION.inspect(args.bundle)
    inspection = operation.payload
    if inspection is None:
        message = operation_error(operation)
        if args.json:
            print_json_error(message)
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)
    bundle = inspection.bundle
    issues = inspection.validation_issues
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    metadata = inspection.metadata
    metadata_error = inspection.metadata_error

    if args.json:
        report = build_inspect_report(inspection)
        print(json.dumps(operation_json_report(operation, report), indent=2))
        return operation_exit_code(operation)

    print(f"Bundle: {bundle}")
    print_field(
        "Schema version status",
        (
            schema_version_status(metadata.get("schema_version"))
            if metadata is not None
            else "invalid"
        ),
    )

    if metadata_error:
        print(f"Metadata: {metadata_error}")
    elif metadata is not None:
        git = metadata.get("git") if isinstance(metadata.get("git"), dict) else {}
        handoff = (
            metadata.get("handoff")
            if isinstance(metadata.get("handoff"), dict)
            else {}
        )
        print_field("Schema version", metadata.get("schema_version"))
        print_field("Source agent", metadata.get("source_agent"))
        print_field("Created at", metadata.get("created_at"))
        print_field("Repo root", metadata.get("repo_root"))
        print_field("Git branch", git.get("branch"))
        print_field("Git base ref", git.get("base_ref"))
        print_field("Git head SHA", git.get("head_sha"))
        print_field("Git dirty", git.get("dirty"))
        print_field("Handoff kind", handoff.get("kind", "handoff"))
        print_field("Parent agent", handoff.get("parent_agent"))
        print_field("Child agent", handoff.get("child_agent"))
        if handoff.get("kind") == "delegation_request":
            print_field("Delegation request ID", handoff.get("request_id"))
        elif handoff.get("kind") == "delegation_result":
            print_field("Delegation result for", handoff.get("result_for"))
            print_field("Delegation result status", handoff.get("result_status"))

        print("Artifacts:")
        for artifact in inspection.artifacts:
            if artifact.status == "invalid":
                print(f"  - {artifact.name}: invalid path")
                continue
            print(f"  - {artifact.name}: {artifact.path} ({artifact.status})")

    print(f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)")
    for issue in issues:
        print(f"  - {issue.format()}")

    return operation_exit_code(operation)


def cmd_redact(args: argparse.Namespace) -> int:
    operation = APPLICATION.redact(args.bundle, args.output, force=args.force)
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_redaction_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Redacted bundle: {report.output}")
    print(f"Source bundle: {report.source}")
    print(f"Files processed: {len(report.files)}")
    print(f"Replacements: {report.replacement_count}")

    for file in report.files:
        suffix = " copied binary" if file.copied_binary else ""
        print(f"  - {file.path}: {file.replacements} replacement(s){suffix}")

    print("Review the redacted bundle before sharing it.")
    return operation_exit_code(operation)


def cmd_pack(args: argparse.Namespace) -> int:
    operation = APPLICATION.pack(args.bundle, args.output, force=args.force)
    application_report = operation.payload
    if application_report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    issues = application_report.validation_issues
    report = application_report.pack
    if report is None and operation.valid is False:
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": "bundle is invalid; refusing to pack",
                        "validation": build_validation_report(args.bundle, issues),
                    },
                    indent=2,
                )
            )
            return operation_exit_code(operation)
        for issue in issues:
            if issue.severity == "error":
                print(issue.format(), file=sys.stderr)
        print("FAIL bundle is invalid; refusing to pack", file=sys.stderr)
        return operation_exit_code(operation)

    warnings = [issue for issue in issues if issue.severity == "warning"]
    if not args.json:
        for warning in warnings:
            print(warning.format())

    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    if args.json:
        validation = build_validation_report(args.bundle, issues)
        print(
            json.dumps(
                operation_json_report(
                    operation,
                    build_pack_report(report, validation),
                ),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Packed bundle: {report.output}")
    print(f"Source bundle: {report.source}")
    print(f"Archive root: {report.archive_root}")
    print(f"Files packed: {report.file_count}")
    print(f"Bytes packed: {report.byte_count}")
    print("Review the archive before sharing it.")
    return operation_exit_code(operation)


def cmd_share(args: argparse.Namespace) -> int:
    if args.check:
        operation = APPLICATION.share_check(args.bundle)
        report = operation.payload
        if report is None:
            message = operation_error(operation)
            if args.json:
                print(json.dumps({"success": False, "error": message}, indent=2))
                return operation_exit_code(operation)
            print(f"FAIL {message}", file=sys.stderr)
            return operation_exit_code(operation)
        if args.json:
            print(
                json.dumps(
                    operation_json_report(
                        operation,
                        build_share_check_report(report),
                    ),
                    indent=2,
                )
            )
            return operation_exit_code(operation)

        print(f"Shareability check: {report.source}")
        for finding in report.findings:
            blocking = "blocking" if finding.blocking else "planned"
            print(
                f"  - {blocking}: {finding.kind}: {finding.path}: "
                f"{finding.count}"
            )
        if not report.shareable:
            print("FAIL bundle is not shareable", file=sys.stderr)
            return operation_exit_code(operation)
        print("PASS bundle is shareable after planned redactions")
        return operation_exit_code(operation)

    if args.output is None:
        message = "--output is required unless --check is used"
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return 1
        print(f"FAIL {message}", file=sys.stderr)
        return 1

    operation = APPLICATION.share(
        args.bundle,
        args.output,
        redacted_output=args.redacted_output,
        force=args.force,
    )
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    warnings = [
        issue for issue in report.validation_issues if issue.severity == "warning"
    ]
    if args.json:
        print(
            json.dumps(
                operation_json_report(operation, build_share_report(report)),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Source bundle: {report.source}")
    print(f"Redacted review bundle: {report.redacted}")
    print(f"Archive: {report.archive}")
    print(f"Redaction replacements: {report.redaction.replacement_count}")
    print(f"Files packed: {report.pack.file_count}")
    print(f"Bytes packed: {report.pack.byte_count}")
    if warnings:
        print("Validation warnings:")
        for warning in warnings:
            print(f"  - {warning.format()}")
    print("Review the redacted bundle and archive before sharing them.")
    return operation_exit_code(operation)


def cmd_unpack(args: argparse.Namespace) -> int:
    operation = APPLICATION.unpack(args.archive, args.output, force=args.force)
    application_report = operation.payload
    if application_report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    report = application_report.unpack
    issues = application_report.validation_issues
    if args.json:
        validation = build_validation_report(report.bundle, issues)
        if not operation.success:
            failure = build_unpack_report(report, validation)
            failure["success"] = False
            failure["error"] = "unpacked bundle is invalid"
            print(
                json.dumps(
                    failure,
                    indent=2,
                )
            )
            return operation_exit_code(operation)
        print(
            json.dumps(
                operation_json_report(
                    operation,
                    build_unpack_report(report, validation),
                ),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Unpacked archive: {report.source}")
    print(f"Output directory: {report.output}")
    print(f"Bundle path: {report.bundle}")
    print(f"Archive root: {report.archive_root}")
    print(f"Files unpacked: {report.file_count}")
    print(f"Bytes unpacked: {report.byte_count}")

    if issues:
        for issue in issues:
            output = sys.stderr if issue.severity == "error" else sys.stdout
            print(issue.format(), file=output)
    if not operation.success:
        print("FAIL unpacked bundle is invalid", file=sys.stderr)
        return operation_exit_code(operation)

    print(f"PASS valid Waybill Bundle: {report.bundle}")
    return operation_exit_code(operation)


def cmd_render(args: argparse.Namespace) -> int:
    if args.json and not args.output:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "--json requires --output for render",
                },
                indent=2,
            )
        )
        return 1

    operation = APPLICATION.render(
        args.bundle,
        output=args.output,
        force=args.force,
    )
    report = operation.payload
    if report is None:
        message = operation_error(operation)
        if args.json:
            print(json.dumps({"success": False, "error": message}, indent=2))
            return operation_exit_code(operation)
        print(f"FAIL {message}", file=sys.stderr)
        return operation_exit_code(operation)

    if report.output is None:
        print(report.rendered, end="")
        return operation_exit_code(operation)

    if args.json:
        validation = build_validation_report(args.bundle, report.validation_issues)
        print(
            json.dumps(
                operation_json_report(
                    operation,
                    build_render_report(
                        args.bundle,
                        report.output,
                        report.rendered,
                        validation,
                    ),
                ),
                indent=2,
            )
        )
        return operation_exit_code(operation)

    print(f"Rendered bundle report: {report.output}")
    print("Review the report before sharing it.")
    return operation_exit_code(operation)


def build_parser() -> argparse.ArgumentParser:
    parser = WaybillArgumentParser(
        prog="waybill",
        description="Work with local Waybill Bundles.",
        epilog=(
            "JSON-capable commands emit one object with a top-level boolean "
            "success field; success is true exactly when the exit status is zero."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"waybill {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a Waybill Bundle")
    validate.add_argument("bundle", help="path to a Waybill Bundle directory")
    validate.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    validate.set_defaults(func=cmd_validate)

    init = subparsers.add_parser(
        "init",
        help="plan or install managed Waybill adapter files",
        description=(
            "Plan or install managed adapter files and .waybill-adapters.json."
        ),
        epilog=(
            "Dry-run actions are would-create, would-update, unchanged, or "
            "would-conflict. Codex plugin is not managed by init."
        ),
    )
    init.add_argument(
        "--target",
        default=".",
        help="target repository directory; defaults to the current directory",
    )
    add_adapter_argument(init, "install")
    init.add_argument(
        "--force",
        action="store_true",
        help="replace conflicting regular files; never follows symbolic links",
    )
    init.add_argument(
        "--dry-run",
        action="store_true",
        help="report planned actions without writing files or the manifest",
    )
    init.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    init.set_defaults(func=cmd_init)

    doctor = subparsers.add_parser(
        "doctor",
        help="classify managed Waybill adapter files",
        description=(
            "Classify managed adapter files as current, missing, stale, or modified."
        ),
        epilog=(
            "Without a manifest, changed files are modified rather than stale. "
            "Codex plugin is not managed by init or doctor."
        ),
    )
    doctor.add_argument(
        "--target",
        default=".",
        help="target repository directory; defaults to the current directory",
    )
    add_adapter_argument(doctor, "check")
    doctor.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    doctor.set_defaults(func=cmd_doctor)

    verify_repo = subparsers.add_parser(
        "verify-repo",
        help="compare bundle metadata with a repository",
    )
    verify_repo.add_argument("bundle", help="path to a Waybill Bundle directory")
    verify_repo.add_argument(
        "--repo",
        default=".",
        help="repository directory to compare; defaults to the current directory",
    )
    verify_repo.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    verify_repo.set_defaults(func=cmd_verify_repo)

    verify_pair = subparsers.add_parser(
        "verify-pair",
        help="verify a delegation result against its request",
    )
    verify_pair.add_argument(
        "request",
        help="path to a delegation_request Waybill Bundle",
    )
    verify_pair.add_argument(
        "result",
        help="path to a delegation_result Waybill Bundle",
    )
    verify_pair.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    verify_pair.set_defaults(func=cmd_verify_pair)

    new = subparsers.add_parser("new", help="create a draft Waybill Bundle")
    new.add_argument(
        "--output",
        default=".waybill",
        help="bundle directory to write; defaults to .waybill",
    )
    new.add_argument(
        "--repo",
        default=".",
        help="repository directory to inspect; defaults to the current directory",
    )
    new.add_argument(
        "--source-agent",
        default="waybill-cli",
        help="metadata source_agent value; defaults to waybill-cli",
    )
    new.add_argument(
        "--goal",
        help="optional original goal text to place in WAYBILL.md",
    )
    new.add_argument(
        "--force",
        action="store_true",
        help="replace existing standard Waybill files in the output directory",
    )
    new.add_argument(
        "--max-diff-bytes",
        type=int,
        default=MAX_DIFF_BYTES,
        help=f"maximum git diff bytes to capture; defaults to {MAX_DIFF_BYTES}",
    )
    new.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    new.set_defaults(func=cmd_new)

    preflight = subparsers.add_parser(
        "preflight",
        help="validate a bundle and compare repository state before import",
    )
    preflight.add_argument("bundle", help="path to a Waybill Bundle directory")
    preflight.add_argument(
        "--repo",
        default=".",
        help="repository directory to compare; defaults to the current directory",
    )
    preflight.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    preflight.set_defaults(func=cmd_preflight)

    ready = subparsers.add_parser(
        "ready",
        help="check whether a bundle is ready for handoff",
    )
    ready.add_argument("bundle", help="path to a Waybill Bundle directory")
    ready.add_argument(
        "--repo",
        default=".",
        help="repository directory to compare; defaults to the current directory",
    )
    ready.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    ready.set_defaults(func=cmd_ready)

    inspect = subparsers.add_parser("inspect", help="summarize a Waybill Bundle")
    inspect.add_argument("bundle", help="path to a Waybill Bundle directory")
    inspect.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    inspect.set_defaults(func=cmd_inspect)

    redact = subparsers.add_parser("redact", help="copy a bundle with secrets redacted")
    redact.add_argument("bundle", help="path to a Waybill Bundle directory")
    redact.add_argument(
        "--output",
        required=True,
        help="directory to write the redacted bundle into",
    )
    redact.add_argument(
        "--force",
        action="store_true",
        help="replace the output directory if it already exists",
    )
    redact.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    redact.set_defaults(func=cmd_redact)

    pack = subparsers.add_parser("pack", help="validate and zip a Waybill Bundle")
    pack.add_argument("bundle", help="path to a Waybill Bundle directory")
    pack.add_argument(
        "--output",
        required=True,
        help="zip file to write",
    )
    pack.add_argument(
        "--force",
        action="store_true",
        help="replace the output file if it already exists",
    )
    pack.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    pack.set_defaults(func=cmd_pack)

    share = subparsers.add_parser(
        "share",
        help="check or create a redacted Waybill archive",
        description=(
            "Check shareability without writes, or redact, validate, and zip a "
            "Waybill Bundle."
        ),
        epilog=(
            "--check performs no writes and does not require --output. Findings "
            "report only kind, path, count, and blocking, and never include "
            "matched secret values."
        ),
    )
    share.add_argument("bundle", help="path to a Waybill Bundle directory")
    share.add_argument(
        "--output",
        help="zip file to write; required unless --check is used",
    )
    share.add_argument(
        "--check",
        action="store_true",
        help="run the read-only shareability preflight",
    )
    share.add_argument(
        "--redacted-output",
        help="directory for the redacted review bundle; defaults near output",
    )
    share.add_argument(
        "--force",
        action="store_true",
        help="replace existing redacted output or zip file",
    )
    share.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    share.set_defaults(func=cmd_share)

    unpack = subparsers.add_parser("unpack", help="unzip and validate a Waybill Bundle")
    unpack.add_argument("archive", help="path to a Waybill Bundle zip archive")
    unpack.add_argument(
        "--output",
        required=True,
        help="directory to unpack the archive into",
    )
    unpack.add_argument(
        "--force",
        action="store_true",
        help="replace the output directory if it already exists",
    )
    unpack.add_argument(
        "--json",
        action="store_true",
        help=JSON_HELP,
    )
    unpack.set_defaults(func=cmd_unpack)

    render = subparsers.add_parser("render", help="render a bundle review report")
    render.add_argument("bundle", help="path to a Waybill Bundle directory")
    render.add_argument(
        "--output",
        help="Markdown file to write; defaults to stdout",
    )
    render.add_argument(
        "--force",
        action="store_true",
        help="replace the output file if it already exists",
    )
    render.add_argument(
        "--json",
        action="store_true",
        help=f"{JSON_HELP}; requires --output",
    )
    render.set_defaults(func=cmd_render)

    return parser


def add_adapter_argument(parser: argparse.ArgumentParser, verb: str) -> None:
    parser.add_argument(
        "--adapter",
        action="append",
        choices=["all", "claude-code", "opencode", "cursor", "gemini-cli"],
        help=(
            f"file-based adapter to {verb}; may be repeated; "
            "Codex plugin is installed separately"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
    except CliUsageError as exc:
        if "--json" in arguments:
            print_json_error(exc.message)
        else:
            exc.parser.print_usage(sys.stderr)
            print(f"{exc.parser.prog}: error: {exc.message}", file=sys.stderr)
        return 2

    try:
        return args.func(args)
    except Exception as exc:
        if getattr(args, "json", False):
            print_json_error(str(exc))
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
