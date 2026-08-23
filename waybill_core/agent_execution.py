"""Shared bounded process execution for agent conformance runners."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping, Sequence


@dataclass(frozen=True)
class AgentExecution:
    """Bounded agent process result without interpretation of agent output."""

    returncode: int | None
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    residual_process_detected: bool
    execution_failed: bool


@dataclass
class _BoundedOutput:
    limit: int
    data: bytearray
    total: int = 0

    @property
    def truncated(self) -> bool:
        return self.total > self.limit


def classify_environment_block(*, stdout: bytes, stderr: bytes) -> str | None:
    """Classify known local sandbox startup failures without returning raw output."""

    output = b"\n".join((stdout, stderr)).lower()
    if (
        b"failed rtm_newaddr" in output
        and b"operation not permitted" in output
    ) or b"bwrap: loopback: failed rtm_newaddr" in output:
        return "network-namespace"
    if any(
        marker in output
        for marker in (
            b"cannot create user namespace",
            b"creating new namespace failed",
            b"failed to create user namespace",
        )
    ):
        return "user-namespace"
    return None


def _read_bounded(stream: BinaryIO, output: _BoundedOutput) -> None:
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            output.total += len(chunk)
            remaining = output.limit - len(output.data)
            if remaining > 0:
                output.data.extend(chunk[:remaining])
    except OSError:
        return


def _process_group_alive(process_group: int) -> bool:
    if os.name != "posix":
        return False
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and _process_group_alive(process.pid):
            time.sleep(0.01)
        if _process_group_alive(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    elif process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()


def execute_agent(
    command: Sequence[str],
    *,
    cwd: Path,
    prompt: str,
    timeout_seconds: float,
    environment: Mapping[str, str],
    output_limit_bytes: int,
) -> AgentExecution:
    """Execute an agent with bounded output and process-group cleanup."""

    if not command or any(
        not isinstance(argument, str) or not argument for argument in command
    ):
        raise ValueError("agent command must contain non-empty string arguments")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if output_limit_bytes <= 0:
        raise ValueError("output_limit_bytes must be greater than zero")
    options: dict[str, object] = {}
    if os.name == "posix":
        options["start_new_session"] = True
    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environment),
            **options,
        )
    except OSError:
        return AgentExecution(None, b"", b"", False, False, False, False, True)

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = _BoundedOutput(output_limit_bytes, bytearray())
    stderr = _BoundedOutput(output_limit_bytes, bytearray())
    stdout_thread = threading.Thread(
        target=_read_bounded,
        args=(process.stdout, stdout),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_bounded,
        args=(process.stderr, stderr),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        process.stdin.write(prompt.encode("utf-8"))
        process.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    timed_out = False
    residual_process_detected = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        residual_process_detected = _process_group_alive(process.pid)
        if residual_process_detected:
            _terminate_process_group(process)

    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    try:
        process.stdout.close()
        process.stderr.close()
    except OSError:
        pass
    return AgentExecution(
        returncode=process.returncode,
        stdout=bytes(stdout.data),
        stderr=bytes(stderr.data),
        stdout_truncated=stdout.truncated,
        stderr_truncated=stderr.truncated,
        timed_out=timed_out,
        residual_process_detected=residual_process_detected,
        execution_failed=False,
    )
