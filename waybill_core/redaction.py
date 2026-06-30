"""Redaction helpers for Waybill Bundles."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


REDACTION_PLACEHOLDER = "[REDACTED]"

TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
]

KEY_VALUE_PATTERN = re.compile(
    r"(?P<key_quote>[\"']?)"
    r"(?P<key>api[_-]?key|password|secret|token|cookie)"
    r"(?P=key_quote)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value_quote>[\"']?)"
    r"(?!\[REDACTED\])"
    r"(?P<value>[^\"'\s,}]+)"
    r"(?P=value_quote)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RedactedFile:
    path: str
    replacements: int
    copied_binary: bool = False


@dataclass(frozen=True)
class RedactionReport:
    source: Path
    output: Path
    files: list[RedactedFile]

    @property
    def replacement_count(self) -> int:
        return sum(file.replacements for file in self.files)


def redact_text(text: str) -> tuple[str, int]:
    replacements = 0

    def replace_token(match: re.Match[str]) -> str:
        nonlocal replacements
        replacements += 1
        if match.group(0).lower().startswith("bearer "):
            return f"Bearer {REDACTION_PLACEHOLDER}"
        return REDACTION_PLACEHOLDER

    for pattern in TOKEN_PATTERNS:
        text = pattern.sub(replace_token, text)

    def replace_key_value(match: re.Match[str]) -> str:
        nonlocal replacements
        replacements += 1
        key_quote = match.group("key_quote")
        key = match.group("key")
        separator = match.group("separator")
        value_quote = match.group("value_quote")
        return (
            f"{key_quote}{key}{key_quote}"
            f"{separator}{value_quote}{REDACTION_PLACEHOLDER}{value_quote}"
        )

    text = KEY_VALUE_PATTERN.sub(replace_key_value, text)
    return text, replacements


def redact_bundle(
    bundle_path: str | Path,
    output_path: str | Path,
    *,
    force: bool = False,
) -> RedactionReport:
    source = Path(bundle_path)
    output = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(f"bundle path does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"bundle path is not a directory: {source}")

    source_resolved = source.resolve()
    output_resolved = output.resolve()
    if output_resolved == source_resolved:
        raise ValueError("output path must be different from the source bundle")
    if source_resolved in output_resolved.parents:
        raise ValueError("output path must not be inside the source bundle")

    if output.exists():
        if not force:
            raise FileExistsError(f"output path already exists: {output}")
        if output.is_dir():
            shutil.rmtree(output)
        else:
            output.unlink()

    output.mkdir(parents=True)
    files: list[RedactedFile] = []

    for source_file in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = source_file.relative_to(source)
        output_file = output / relative
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            text = source_file.read_text()
        except UnicodeDecodeError:
            shutil.copy2(source_file, output_file)
            files.append(RedactedFile(str(relative), 0, copied_binary=True))
            continue

        redacted, replacements = redact_text(text)
        output_file.write_text(redacted)
        shutil.copystat(source_file, output_file)
        files.append(RedactedFile(str(relative), replacements))

    return RedactionReport(source, output, files)
