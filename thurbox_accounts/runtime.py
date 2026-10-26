"""Trusted argv checks, bounded capture and process-group timeout cleanup."""

from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from .core import redact


def execute(argv: list[str], cwd: Path, *, timeout: float = 600, limit: int = 65536, env: dict[str, str] | None = None) -> dict:
    if not math.isfinite(timeout) or timeout <= 0 or limit < 1:
        raise ValueError("timeout and output limit must be positive and finite")
    start = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated, timed_out = False, False
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except OSError as error:
        return dict(command=argv, status="ERROR", exit_code=None, stdout="", stderr=redact(str(error)),
                    truncated=False, duration=time.monotonic() - start)
    try:
        with selectors.DefaultSelector() as selector:
            for stream, key in [(process.stdout, "stdout"), (process.stderr, "stderr")]:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, key)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    timed_out = True
                    break
                for event, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(event.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(event.fileobj)
                        continue
                    buffer = buffers[event.data]
                    buffer.extend(data)
                    if len(buffer) > limit:
                        del buffer[:-limit]
                        truncated = True
            if not timed_out:
                try:
                    process.wait(timeout=max(0.001, timeout - (time.monotonic() - start)))
                except subprocess.TimeoutExpired:
                    timed_out = True
    finally:
        # The process may have spawned children which hold pipes or survive it.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()
    return dict(command=argv, status="TIMEOUT" if timed_out else ("PASS" if process.returncode == 0 else "FAIL"),
                exit_code=process.returncode, stdout=redact(buffers["stdout"].decode(errors="replace")),
                stderr=redact(buffers["stderr"].decode(errors="replace")), truncated=truncated,
                duration=round(time.monotonic() - start, 3))
