"""Repository checks for Waybill adapter installation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .install import SUPPORTED_ADAPTERS, adapter_target_files


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class DoctorReport:
    target: Path
    adapters: list[str]
    checks: list[DoctorCheck]

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)


def doctor_repository(target_root: str | Path, adapters: list[str]) -> DoctorReport:
    target = Path(target_root)
    selected = _normalize_adapters(adapters)
    checks: list[DoctorCheck] = []

    if not target.exists():
        return DoctorReport(
            target,
            selected,
            [DoctorCheck("target", "error", f"target path does not exist: {target}")],
        )
    if not target.is_dir():
        return DoctorReport(
            target,
            selected,
            [
                DoctorCheck(
                    "target",
                    "error",
                    f"target path is not a directory: {target}",
                )
            ],
        )

    checks.append(DoctorCheck("target", "ok", f"target directory exists: {target}"))
    _check_gitignore(target, checks)

    for adapter in selected:
        for relative in adapter_target_files(adapter):
            path = target / relative
            if path.is_file():
                checks.append(DoctorCheck(relative, "ok", "installed"))
            else:
                checks.append(DoctorCheck(relative, "error", "missing"))

    return DoctorReport(target, selected, checks)


def _normalize_adapters(adapters: list[str]) -> list[str]:
    if not adapters:
        return list(SUPPORTED_ADAPTERS)
    if "all" in adapters:
        return list(SUPPORTED_ADAPTERS)

    selected: list[str] = []
    for adapter in adapters:
        if adapter not in SUPPORTED_ADAPTERS:
            raise ValueError(f"unsupported adapter: {adapter}")
        if adapter not in selected:
            selected.append(adapter)
    return selected


def _check_gitignore(target: Path, checks: list[DoctorCheck]) -> None:
    path = target / ".gitignore"
    if not path.is_file():
        checks.append(DoctorCheck(".gitignore", "error", "missing .waybill/ ignore"))
        return

    lines = path.read_text().splitlines()
    if ".waybill/" in lines:
        checks.append(DoctorCheck(".gitignore", "ok", "contains .waybill/"))
    else:
        checks.append(DoctorCheck(".gitignore", "error", "missing .waybill/ ignore"))
