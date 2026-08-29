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


_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001

# Non-secret routing inputs used by authenticated CLI wrappers. Credentials,
# proxy variables, and general-purpose injection variables remain excluded.
MANUAL_AGENT_RUNTIME_ENV_ALLOWLIST = (
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
    "CLAUDE_GATEWAY_MODEL",
    "CLAUDE_MODEL",
    "CODEX_LITELLM_MODEL_INDEX",
    "CODEX_MODEL",
    "LITELLM_BASE_URL",
)


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


class _WindowsJob:
    """Minimal kill-on-close Windows Job Object for one agent process tree."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time_limit", ctypes.c_longlong),
                ("per_job_user_time_limit", ctypes.c_longlong),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set_size", ctypes.c_size_t),
                ("maximum_working_set_size", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("read_operation_count", ctypes.c_ulonglong),
                ("write_operation_count", ctypes.c_ulonglong),
                ("other_operation_count", ctypes.c_ulonglong),
                ("read_transfer_count", ctypes.c_ulonglong),
                ("write_transfer_count", ctypes.c_ulonglong),
                ("other_transfer_count", ctypes.c_ulonglong),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("basic_limit_information", BasicLimitInformation),
                ("io_info", IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        class BasicAccountingInformation(ctypes.Structure):
            _fields_ = [
                ("total_user_time", ctypes.c_longlong),
                ("total_kernel_time", ctypes.c_longlong),
                ("this_period_total_user_time", ctypes.c_longlong),
                ("this_period_total_kernel_time", ctypes.c_longlong),
                ("total_page_fault_count", wintypes.DWORD),
                ("total_processes", wintypes.DWORD),
                ("active_processes", wintypes.DWORD),
                ("total_terminated_processes", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        information = ExtendedLimitInformation()
        information.basic_limit_information.limit_flags = (
            _JOB_OBJECT_LIMIT_KILL_ON_CLOSE
        )
        if not kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(error)

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = kernel32
        self._handle = handle
        self._accounting_type = BasicAccountingInformation

    def assign(self, process_id: int) -> None:
        process_handle = self._kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE,
            False,
            process_id,
        )
        if not process_handle:
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        try:
            if not self._kernel32.AssignProcessToJobObject(
                self._handle,
                process_handle,
            ):
                raise self._ctypes.WinError(self._ctypes.get_last_error())
        finally:
            self._kernel32.CloseHandle(process_handle)

    def active_processes(self) -> int:
        information = self._accounting_type()
        returned = self._wintypes.DWORD()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            self._ctypes.byref(information),
            self._ctypes.sizeof(information),
            self._ctypes.byref(returned),
        ):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return int(information.active_processes)

    def terminate(self) -> None:
        if not self._kernel32.TerminateJobObject(self._handle, 1):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def classify_environment_block(*, stdout: bytes, stderr: bytes) -> str | None:
    """Classify known local sandbox startup failures without returning raw output."""

    del stdout
    for raw_line in stderr.lower().splitlines():
        line = raw_line.strip()
        if not line.startswith(b"bwrap:"):
            continue
        if (
            b"loopback: failed rtm_newaddr" in line
            and b"operation not permitted" in line
        ):
            return "network-namespace"
        if any(
            marker in line
            for marker in (
                b"cannot create user namespace",
                b"creating new namespace failed",
                b"failed to create user namespace",
                b"no permissions to create a new namespace",
                b"kernel does not allow non-privileged user namespaces",
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


def _write_prompt(stream: BinaryIO, prompt: bytes) -> None:
    try:
        stream.write(prompt)
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


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


def _terminate_windows_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Best-effort fail-closed fallback when Job Object assignment fails."""

    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _close_process_pipes(process: subprocess.Popen[bytes]) -> None:
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            pass


def execute_agent(
    command: Sequence[str],
    *,
    cwd: Path,
    prompt: str,
    timeout_seconds: float,
    environment: Mapping[str, str],
    output_limit_bytes: int,
) -> AgentExecution:
    """Execute an agent with bounded output and process-tree cleanup."""

    if not command or any(
        not isinstance(argument, str) or not argument for argument in command
    ):
        raise ValueError("agent command must contain non-empty string arguments")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if output_limit_bytes <= 0:
        raise ValueError("output_limit_bytes must be greater than zero")
    prompt_bytes = prompt.encode("utf-8")
    options: dict[str, object] = {}
    windows_job: _WindowsJob | None = None
    if os.name == "posix":
        options["start_new_session"] = True
    elif os.name == "nt":
        try:
            windows_job = _WindowsJob()
        except OSError:
            return AgentExecution(None, b"", b"", False, False, False, False, True)
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
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
        if windows_job is not None:
            windows_job.close()
        return AgentExecution(None, b"", b"", False, False, False, False, True)

    if windows_job is not None:
        try:
            windows_job.assign(process.pid)
        except OSError:
            _terminate_windows_process_tree(process)
            _close_process_pipes(process)
            windows_job.close()
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
    stdin_thread = threading.Thread(
        target=_write_prompt,
        args=(process.stdin, prompt_bytes),
        daemon=True,
    )
    deadline = time.monotonic() + timeout_seconds
    stdout_thread.start()
    stderr_thread.start()
    stdin_thread.start()

    timed_out = False
    residual_process_detected = False
    execution_failed = False
    try:
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        timed_out = True
        if windows_job is not None:
            try:
                windows_job.terminate()
            except OSError:
                execution_failed = True
        else:
            _terminate_process_group(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        if windows_job is not None:
            try:
                residual_process_detected = windows_job.active_processes() > 0
            except OSError:
                residual_process_detected = True
                execution_failed = True
        else:
            residual_process_detected = _process_group_alive(process.pid)
        if residual_process_detected:
            if windows_job is not None:
                try:
                    windows_job.terminate()
                except OSError:
                    execution_failed = True
            else:
                _terminate_process_group(process)

    if windows_job is not None:
        windows_job.close()

    stdin_thread.join(timeout=2)
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)
    _close_process_pipes(process)
    return AgentExecution(
        returncode=process.returncode,
        stdout=bytes(stdout.data),
        stderr=bytes(stderr.data),
        stdout_truncated=stdout.truncated,
        stderr_truncated=stderr.truncated,
        timed_out=timed_out,
        residual_process_detected=residual_process_detected,
        execution_failed=execution_failed,
    )
