"""Sandbox — runs replayed agent in isolated environment.

Local dev: subprocess in tmp dir. Production: Firecracker microVM via
specs/domains/13-sandbox.md contract.

This implementation focuses on the in-process version for tests; the
sandbox interface is the same so swapping to Firecracker is mechanical.
"""
from __future__ import annotations

import asyncio
import logging
import os
import resource
import shutil
import signal
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


class SandboxResult:
    def __init__(self, *, stdout: str, stderr: str, exit_code: int, timeout: bool = False) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timeout = timeout


def _set_resource_limits(cpu_seconds: int, mem_mb: int) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except (OSError, ValueError):
        pass
    try:
        mem_bytes = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (OSError, ValueError):
        pass


@contextmanager
def _temp_workspace() -> Iterator[str]:
    d = tempfile.mkdtemp(prefix="replay-sandbox-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def run_in_subprocess(
    code: str,
    *,
    timeout_s: float = 30.0,
    cpu_seconds: int = 30,
    mem_mb: int = 512,
) -> SandboxResult:
    """Run Python code in a subprocess with hard limits. Local dev only."""
    with _temp_workspace() as workdir:
        script_path = os.path.join(workdir, "replay.py")
        with open(script_path, "w") as f:
            f.write(code)
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", script_path,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=lambda: _set_resource_limits(cpu_seconds, mem_mb),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
                return SandboxResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=proc.returncode or 0,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(stdout="", stderr="timeout", exit_code=-1, timeout=True)
        except FileNotFoundError:
            return SandboxResult(stdout="", stderr="python3 not found", exit_code=-1)


async def run_in_process(code: str, *, timeout_s: float = 30.0) -> SandboxResult:
    """For tests: exec code in current process with timeout.

    NOT for production. Production uses run_in_subprocess or Firecracker.
    """
    import io
    import contextlib
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    try:
        async def _run():
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                exec(compile(code, "<sandbox>", "exec"), {"__name__": "__sandbox__"})
        await asyncio.wait_for(_run(), timeout=timeout_s)
        return SandboxResult(stdout=buf_out.getvalue(), stderr=buf_err.getvalue(), exit_code=0)
    except asyncio.TimeoutError:
        return SandboxResult(stdout=buf_out.getvalue(), stderr="timeout", exit_code=-1, timeout=True)
    except Exception as e:
        return SandboxResult(stdout=buf_out.getvalue(), stderr=f"{type(e).__name__}: {e}", exit_code=1)
