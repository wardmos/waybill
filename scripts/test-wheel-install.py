#!/usr/bin/env python3
"""Build and verify the Waybill wheel in disposable isolated directories."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
IGNORED_SOURCE_NAMES = {
    ".coverage",
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".waybill",
    ".waybill-redacted",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
SOURCE_COPY_FILES = ("LICENSE", "MANIFEST.in", "README.md", "pyproject.toml")
SOURCE_COPY_DIRECTORIES = ("waybill_core", "skills", "adapters")
EXPECTED_TEMPLATE_TARGETS = {
    "claude-code": {
        ".claude/skills/handoff/SKILL.md",
        ".claude/skills/handoff/references/bundle-format.md",
        ".claude/skills/handoff/references/export.md",
        ".claude/skills/handoff/references/import.md",
        ".claude/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".claude/skills/handoff/assets/bundle-template/metadata.json",
        ".claude/skills/handoff/assets/bundle-template/diff.patch",
        ".claude/skills/handoff/assets/bundle-template/commands.log",
        ".claude/skills/handoff/assets/bundle-template/test-summary.md",
        ".claude/skills/waybill/SKILL.md",
    },
    "opencode": {
        ".opencode/commands/handoff.md",
        ".opencode/commands/waybill.md",
        ".opencode/skills/handoff/SKILL.md",
        ".opencode/skills/handoff/references/bundle-format.md",
        ".opencode/skills/handoff/references/export.md",
        ".opencode/skills/handoff/references/import.md",
        ".opencode/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".opencode/skills/handoff/assets/bundle-template/metadata.json",
        ".opencode/skills/handoff/assets/bundle-template/diff.patch",
        ".opencode/skills/handoff/assets/bundle-template/commands.log",
        ".opencode/skills/handoff/assets/bundle-template/test-summary.md",
        ".opencode/skills/waybill/SKILL.md",
    },
    "cursor": {
        ".cursor/rules/handoff.mdc",
        ".cursor/rules/waybill-handoff/references/bundle-format.md",
        ".cursor/rules/waybill-handoff/references/export.md",
        ".cursor/rules/waybill-handoff/references/import.md",
        ".cursor/rules/waybill-handoff/assets/bundle-template/WAYBILL.md",
        ".cursor/rules/waybill-handoff/assets/bundle-template/metadata.json",
        ".cursor/rules/waybill-handoff/assets/bundle-template/diff.patch",
        ".cursor/rules/waybill-handoff/assets/bundle-template/commands.log",
        ".cursor/rules/waybill-handoff/assets/bundle-template/test-summary.md",
        ".cursor/rules/waybill.mdc",
    },
    "gemini-cli": {
        ".gemini/skills/handoff/SKILL.md",
        ".gemini/skills/handoff/references/bundle-format.md",
        ".gemini/skills/handoff/references/export.md",
        ".gemini/skills/handoff/references/import.md",
        ".gemini/skills/handoff/assets/bundle-template/WAYBILL.md",
        ".gemini/skills/handoff/assets/bundle-template/metadata.json",
        ".gemini/skills/handoff/assets/bundle-template/diff.patch",
        ".gemini/skills/handoff/assets/bundle-template/commands.log",
        ".gemini/skills/handoff/assets/bundle-template/test-summary.md",
        ".gemini/skills/waybill/SKILL.md",
    },
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMAND_TIMEOUT_SECONDS = 300


class WheelVerificationError(RuntimeError):
    """Raised when an isolated wheel verification contract fails."""


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_SOURCE_NAMES
        or name.endswith(".egg-info")
        or name.endswith(".pyc")
    }


def _validate_source_directory(path: Path) -> None:
    try:
        root_metadata = path.lstat()
    except FileNotFoundError as exc:
        raise WheelVerificationError(f"required source directory is missing: {path}") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise WheelVerificationError(f"required source directory is unsafe: {path}")

    for current, directory_names, file_names in os.walk(path, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in directory_names:
            if name in _copy_ignore(current, [name]):
                continue
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise WheelVerificationError(f"packaged source path is unsafe: {candidate}")
            safe_directories.append(name)
        directory_names[:] = safe_directories

        for name in file_names:
            if name in _copy_ignore(current, [name]):
                continue
            candidate = current_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise WheelVerificationError(f"packaged source path is unsafe: {candidate}")


def copy_source_tree(source: Path, destination: Path) -> None:
    """Copy repository sources while excluding private and generated state."""

    if source.is_symlink() or not source.is_dir():
        raise WheelVerificationError(f"source root is not a regular directory: {source}")
    destination.mkdir()

    for name in SOURCE_COPY_FILES:
        source_path = source / name
        try:
            metadata = source_path.lstat()
        except FileNotFoundError as exc:
            raise WheelVerificationError(f"required source file is missing: {name}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise WheelVerificationError(f"required source file is unsafe: {name}")
        shutil.copy2(source_path, destination / name)

    for name in SOURCE_COPY_DIRECTORIES:
        source_path = source / name
        _validate_source_directory(source_path)
        shutil.copytree(
            source_path,
            destination / name,
            symlinks=False,
            ignore=_copy_ignore,
        )


def isolated_environment(
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment that cannot inject source directories into Python."""

    environment = dict(os.environ if base is None else base)
    for name in [
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "VIRTUAL_ENV",
    ]:
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    environment["PIP_NO_CACHE_DIR"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return environment


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON field: {key}")
        document[key] = value
    return document


def parse_json_object(text: str) -> dict[str, object]:
    """Parse one strict JSON object, rejecting duplicates and non-finite values."""

    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON output: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("JSON output must be an object")
    return document


def _command_detail(result: subprocess.CompletedProcess[str]) -> str:
    details = "\n".join(
        part for part in [result.stdout.strip(), result.stderr.strip()] if part
    )
    if not details:
        return "no command output"
    return details[-4000:]


def run_command(
    arguments: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    label: str,
) -> subprocess.CompletedProcess[str]:
    """Run one command and raise a concise verification error on failure."""

    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            env=dict(environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise WheelVerificationError(
            f"{label} exceeded {COMMAND_TIMEOUT_SECONDS} seconds"
        ) from exc
    if result.returncode != 0:
        command = shlex.join(arguments)
        raise WheelVerificationError(
            f"{label} failed with exit {result.returncode}: {command}\n"
            f"{_command_detail(result)}"
        )
    return result


def run_json_command(
    arguments: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    label: str,
) -> dict[str, object]:
    """Run a successful JSON CLI command and validate its common envelope."""

    result = run_command(
        arguments,
        cwd=cwd,
        environment=environment,
        label=label,
    )
    if result.stderr:
        raise WheelVerificationError(f"{label} wrote unexpected stderr")
    try:
        report = parse_json_object(result.stdout)
    except ValueError as exc:
        raise WheelVerificationError(f"{label} returned {exc}") from exc
    if report.get("success") is not True:
        raise WheelVerificationError(f"{label} did not return success=true")
    return report


def _extract_version(path: Path, pattern: str, label: str) -> str:
    matches = re.findall(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if len(matches) != 1:
        raise WheelVerificationError(f"could not determine {label} from {path.name}")
    return matches[0]


def expected_version(source: Path) -> str:
    """Read and cross-check the package version without importing source code."""

    project_version = _extract_version(
        source / "pyproject.toml",
        r'^version\s*=\s*"([^"]+)"\s*$',
        "project version",
    )
    package_version = _extract_version(
        source / "waybill_core" / "__init__.py",
        r'^__version__\s*=\s*"([^"]+)"\s*$',
        "package version",
    )
    if project_version != package_version:
        raise WheelVerificationError(
            "pyproject.toml and waybill_core.__version__ do not match"
        )
    return project_version


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _venv_executable(venv_root: Path, name: str) -> Path:
    if os.name == "nt":
        suffix = ".exe" if not name.endswith(".exe") else ""
        return venv_root / "Scripts" / f"{name}{suffix}"
    return venv_root / "bin" / name


def build_wheel(
    source_copy: Path,
    wheelhouse: Path,
    environment: Mapping[str, str],
) -> Path:
    """Build exactly one project wheel from the disposable source copy."""

    wheelhouse.mkdir()
    run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--no-deps",
            "--wheel-dir",
            str(wheelhouse),
            ".",
        ],
        cwd=source_copy,
        environment=environment,
        label="wheel build",
    )
    wheels = sorted(wheelhouse.glob("agent_waybill-*.whl"))
    if len(wheels) != 1:
        names = ", ".join(path.name for path in wheelhouse.glob("*.whl"))
        raise WheelVerificationError(
            f"wheel build produced {len(wheels)} project wheels: {names or 'none'}"
        )
    return wheels[0]


def create_venv(
    venv_root: Path,
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> tuple[Path, Path]:
    """Create a temporary venv and return its Python and console entry point."""

    run_command(
        [sys.executable, "-m", "venv", str(venv_root)],
        cwd=cwd,
        environment=environment,
        label="virtual environment creation",
    )
    python = _venv_executable(venv_root, "python")
    waybill = _venv_executable(venv_root, "waybill")
    if not python.is_file():
        raise WheelVerificationError("temporary venv does not contain Python")
    return python, waybill


PROBE_CODE = r"""
import hashlib
import json
from pathlib import Path

import waybill_core
from waybill_core.adapter_sources import ADAPTER_SOURCES, PACKAGE_TEMPLATE_ROOT

templates = []
for source in ADAPTER_SOURCES:
    path = PACKAGE_TEMPLATE_ROOT / source.install_target
    templates.append(
        {
            "adapter": source.adapter,
            "install_target": source.install_target,
            "path": str(path.resolve()),
            "is_file": path.is_file(),
            "is_symlink": path.is_symlink(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else None,
        }
    )

print(
    json.dumps(
        {
            "version": waybill_core.__version__,
            "module": str(Path(waybill_core.__file__).resolve()),
            "template_root": str(PACKAGE_TEMPLATE_ROOT.resolve()),
            "templates": templates,
        },
        sort_keys=True,
    )
)
"""


def inspect_installed_package(
    python: Path,
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    result = run_command(
        [str(python), "-I", "-c", PROBE_CODE],
        cwd=cwd,
        environment=environment,
        label="installed package probe",
    )
    if result.stderr:
        raise WheelVerificationError("installed package probe wrote unexpected stderr")
    try:
        return parse_json_object(result.stdout)
    except ValueError as exc:
        raise WheelVerificationError(f"installed package probe returned {exc}") from exc


def validate_installed_package(
    report: dict[str, object],
    *,
    version: str,
    repository: Path,
    source_copy: Path,
    venv_root: Path,
) -> dict[str, tuple[str, str]]:
    """Validate import isolation and every packaged adapter template."""

    if report.get("version") != version:
        raise WheelVerificationError("installed package version does not match source")

    module_value = report.get("module")
    template_root_value = report.get("template_root")
    if not isinstance(module_value, str) or not isinstance(template_root_value, str):
        raise WheelVerificationError("installed package probe omitted package paths")
    module_path = Path(module_value)
    template_root = Path(template_root_value)
    if not _is_within(module_path, venv_root):
        raise WheelVerificationError("installed package was not imported from the venv")
    if _is_within(module_path, repository) or _is_within(module_path, source_copy):
        raise WheelVerificationError("installed package imported from a source directory")
    if not _is_within(template_root, module_path.parent):
        raise WheelVerificationError("adapter templates are outside the installed package")

    raw_templates = report.get("templates")
    if not isinstance(raw_templates, list):
        raise WheelVerificationError("installed package probe omitted adapter templates")

    expected = {
        (adapter, target)
        for adapter, targets in EXPECTED_TEMPLATE_TARGETS.items()
        for target in targets
    }
    found: set[tuple[str, str]] = set()
    records: dict[str, tuple[str, str]] = {}
    for item in raw_templates:
        if not isinstance(item, dict):
            raise WheelVerificationError("adapter template report must contain objects")
        adapter = item.get("adapter")
        target = item.get("install_target")
        path_value = item.get("path")
        digest = item.get("sha256")
        if not all(isinstance(value, str) for value in [adapter, target, path_value]):
            raise WheelVerificationError("adapter template report has invalid fields")
        if item.get("is_file") is not True or item.get("is_symlink") is not False:
            raise WheelVerificationError(f"packaged adapter template is unsafe: {target}")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise WheelVerificationError(f"packaged adapter digest is invalid: {target}")
        template_path = Path(path_value)
        if not _is_within(template_path, template_root):
            raise WheelVerificationError(f"packaged adapter escaped template root: {target}")
        key = (adapter, target)
        if key in found or target in records:
            raise WheelVerificationError(f"duplicate packaged adapter template: {target}")
        found.add(key)
        records[target] = (adapter, digest)

    if found != expected:
        missing = sorted(expected - found)
        extra = sorted(found - expected)
        raise WheelVerificationError(
            f"packaged adapter template set differs; missing={missing}, extra={extra}"
        )
    return records


def _all_json_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        keys = list(value)
        for child in value.values():
            keys.extend(_all_json_keys(child))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for child in value:
            keys.extend(_all_json_keys(child))
        return keys
    return []


def validate_manifest(
    target: Path,
    *,
    version: str,
    templates: Mapping[str, tuple[str, str]],
) -> bytes:
    """Validate deterministic manifest data and installed file digests."""

    path = target / ".waybill-adapters.json"
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise WheelVerificationError("waybill init did not create its manifest") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise WheelVerificationError("adapter manifest is not a regular file")

    content = path.read_bytes()
    try:
        document = parse_json_object(content.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise WheelVerificationError(f"adapter manifest is invalid: {exc}") from exc
    if set(document) != {"files", "format_version", "waybill_version"}:
        raise WheelVerificationError("adapter manifest has unexpected top-level fields")
    if any("timestamp" in key.lower() for key in _all_json_keys(document)):
        raise WheelVerificationError("adapter manifest must not contain timestamps")
    if type(document.get("format_version")) is not int:
        raise WheelVerificationError("adapter manifest format_version must be an integer")
    if document.get("format_version") != 1:
        raise WheelVerificationError("adapter manifest format_version must be 1")
    if document.get("waybill_version") != version:
        raise WheelVerificationError("adapter manifest version does not match the wheel")

    files = document.get("files")
    if not isinstance(files, dict) or set(files) != set(templates):
        raise WheelVerificationError("adapter manifest does not cover every template")
    if list(files) != sorted(files):
        raise WheelVerificationError("adapter manifest file paths are not sorted")
    canonical = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if content != canonical:
        raise WheelVerificationError("adapter manifest JSON is not deterministic")

    for relative, (adapter, template_digest) in templates.items():
        record = files[relative]
        if not isinstance(record, dict) or set(record) != {"adapter", "sha256"}:
            raise WheelVerificationError(f"invalid manifest record: {relative}")
        if record.get("adapter") != adapter or record.get("sha256") != template_digest:
            raise WheelVerificationError(f"manifest record differs from template: {relative}")
        installed = target / relative
        try:
            installed_metadata = installed.lstat()
        except FileNotFoundError as exc:
            raise WheelVerificationError(f"installed adapter is missing: {relative}") from exc
        if not stat.S_ISREG(installed_metadata.st_mode):
            raise WheelVerificationError(f"installed adapter is unsafe: {relative}")
        if hashlib.sha256(installed.read_bytes()).hexdigest() != template_digest:
            raise WheelVerificationError(f"installed adapter digest differs: {relative}")
    return content


def validate_init_report(
    report: dict[str, object],
    *,
    expected_paths: set[str],
    expected_action: str | None = None,
) -> None:
    if report.get("dry_run") is not False or report.get("has_conflicts") is not False:
        raise WheelVerificationError("waybill init returned an unexpected lifecycle state")
    if report.get("adapters") != list(EXPECTED_TEMPLATE_TARGETS):
        raise WheelVerificationError("waybill init did not select every managed adapter")
    actions = report.get("actions")
    if not isinstance(actions, list):
        raise WheelVerificationError("waybill init report omitted actions")
    found_paths: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise WheelVerificationError("waybill init action must be an object")
        path = action.get("path")
        value = action.get("action")
        if not isinstance(path, str) or not isinstance(value, str):
            raise WheelVerificationError("waybill init action has invalid fields")
        found_paths.add(path)
        if expected_action is not None and value != expected_action:
            raise WheelVerificationError(
                f"waybill init expected {expected_action} for {path}, got {value}"
            )
    if found_paths != expected_paths:
        raise WheelVerificationError("waybill init actions do not cover managed files")


def validate_doctor_report(
    report: dict[str, object],
    *,
    expected_paths: set[str],
) -> None:
    if report.get("valid") is not True:
        raise WheelVerificationError("waybill doctor did not return valid=true")
    if report.get("codex_plugin_managed_by_init") is not False:
        raise WheelVerificationError("waybill doctor incorrectly treats Codex as init-managed")
    checks = report.get("checks")
    if not isinstance(checks, list):
        raise WheelVerificationError("waybill doctor report omitted checks")
    names: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise WheelVerificationError("waybill doctor check must be an object")
        name = check.get("name")
        if not isinstance(name, str):
            raise WheelVerificationError("waybill doctor check omitted its name")
        names.add(name)
        if check.get("status") != "ok" or check.get("state") != "current":
            raise WheelVerificationError(f"waybill doctor did not report current: {name}")
    if names != expected_paths:
        raise WheelVerificationError("waybill doctor checks do not cover managed files")


def verify_wheel_install(repository: Path = ROOT) -> str:
    """Run the complete disposable wheel build and installation verification."""

    repository = repository.resolve()
    version = expected_version(repository)
    environment = isolated_environment()
    with tempfile.TemporaryDirectory(prefix="waybill-wheel-install-") as parent:
        temporary_root = Path(parent).resolve()
        if _is_within(temporary_root, repository):
            raise WheelVerificationError("temporary directory must be outside the repository")

        source_copy = temporary_root / "source"
        wheelhouse = temporary_root / "wheelhouse"
        venv_root = temporary_root / "venv"
        outside = temporary_root / "outside"
        target = outside / "target-repository"
        copy_source_tree(repository, source_copy)
        outside.mkdir()
        target.mkdir()

        wheel = build_wheel(source_copy, wheelhouse, environment)
        python, waybill = create_venv(
            venv_root,
            cwd=outside,
            environment=environment,
        )
        run_command(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--no-deps",
                "--no-index",
                str(wheel),
            ],
            cwd=outside,
            environment=environment,
            label="wheel installation",
        )
        if not waybill.is_file():
            raise WheelVerificationError("wheel did not install the waybill entry point")

        version_result = run_command(
            [str(waybill), "--version"],
            cwd=outside,
            environment=environment,
            label="installed version check",
        )
        if version_result.stderr or version_result.stdout.strip() != f"waybill {version}":
            raise WheelVerificationError("installed CLI version does not match the wheel")

        probe = inspect_installed_package(
            python,
            cwd=outside,
            environment=environment,
        )
        templates = validate_installed_package(
            probe,
            version=version,
            repository=repository,
            source_copy=source_copy,
            venv_root=venv_root,
        )
        lifecycle_paths = set(templates) | {".gitignore", ".waybill-adapters.json"}

        init_report = run_json_command(
            [
                str(waybill),
                "init",
                "--target",
                str(target),
                "--adapter",
                "all",
                "--json",
            ],
            cwd=outside,
            environment=environment,
            label="installed waybill init",
        )
        validate_init_report(
            init_report,
            expected_paths=lifecycle_paths,
            expected_action="created",
        )
        manifest = validate_manifest(target, version=version, templates=templates)

        second_init_report = run_json_command(
            [
                str(waybill),
                "init",
                "--target",
                str(target),
                "--adapter",
                "all",
                "--json",
            ],
            cwd=outside,
            environment=environment,
            label="installed waybill repeat init",
        )
        validate_init_report(
            second_init_report,
            expected_paths=lifecycle_paths,
            expected_action="unchanged",
        )
        if (target / ".waybill-adapters.json").read_bytes() != manifest:
            raise WheelVerificationError("repeat init changed the deterministic manifest")

        doctor_report = run_json_command(
            [
                str(waybill),
                "doctor",
                "--target",
                str(target),
                "--adapter",
                "all",
                "--json",
            ],
            cwd=outside,
            environment=environment,
            label="installed waybill doctor",
        )
        validate_doctor_report(
            doctor_report,
            expected_paths=lifecycle_paths | {"target"},
        )
        return wheel.name


def main() -> int:
    try:
        wheel_name = verify_wheel_install()
    except (OSError, ValueError, WheelVerificationError) as exc:
        print(f"FAIL wheel installation: {exc}", file=sys.stderr)
        return 1
    print(f"PASS isolated wheel installation: {wheel_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
