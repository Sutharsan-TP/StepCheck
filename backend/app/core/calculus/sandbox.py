"""Runs heavy SymPy work (doit, integrate, limit, simplify) in worker processes.

Some inputs make SymPy run for minutes. Threads cannot be stopped, so each job
runs in a separate process that is killed and replaced if it overruns its time
limit. The API process itself never evaluates calculus.

Jobs are named entries in ``_JOBS``; arguments and results are plain picklable
values (strings and frozen dataclasses), never live SymPy objects.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from app.utils.errors import ErrorCode, MathInputError

logger = logging.getLogger("stepcheck.sandbox")

JOB_TIMEOUT_SECONDS = float(os.getenv("CALC_JOB_TIMEOUT_SECONDS", "4"))
STARTUP_TIMEOUT_SECONDS = 60.0
MIN_JOB_SECONDS = 0.25


class SandboxTimeout(Exception):
    """The job overran its time limit (its worker was killed), or no worker was free in time."""


class SandboxFailure(Exception):
    """The job raised an unexpected error inside the worker."""


def _sleep_job(seconds: float) -> str:  # used by tests to simulate a runaway computation
    time.sleep(seconds)
    return "slept"


def _jobs() -> dict[str, Callable[..., Any]]:
    from app.core.calculus.calc_diagnosis import diagnose_texts
    from app.core.calculus.calc_equivalence import compare_texts, expected_answer

    return {"compare": compare_texts, "answer": expected_answer, "diagnose": diagnose_texts, "sleep": _sleep_job}


def _serve(conn) -> None:  # pragma: no cover - runs in the child process
    jobs = _jobs()
    # SymPy loads much of itself lazily; pay that once here, not inside a student's time limit.
    for expected, found, mode in (
        ("d/dx(x^2 sin(x))", "2x cos(x)", "VALUE"),
        ("int(2x) dx", "x^2 + C", "ANTIDERIVATIVE"),
        ("lim(x->0, sin(x)/x)", "1", "VALUE"),
        ("int[0, 1](x) dx", "1/2", "VALUE"),
    ):
        jobs["compare"](expected, found, mode)
    conn.send(("ready", None))
    while True:
        try:
            name, args = conn.recv()
        except EOFError:
            return
        try:
            conn.send(("ok", jobs[name](*args)))
        except MathInputError as exc:
            conn.send(("math_error", (exc.code.value, exc.message)))
        except Exception as exc:
            conn.send(("error", f"{type(exc).__name__}: {exc}"))


class _Worker:
    def __init__(self, ctx) -> None:
        self._ctx = ctx
        self._proc = None
        self._conn = None

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        parent, child = self._ctx.Pipe()
        self._proc = self._ctx.Process(target=_serve, args=(child,), daemon=True, name="stepcheck-calc")
        self._proc.start()
        child.close()
        self._conn = parent
        if not parent.poll(STARTUP_TIMEOUT_SECONDS):
            self.stop()
            raise SandboxFailure("The calculus worker did not start.")
        parent.recv()  # ("ready", None)

    def call(self, name: str, args: tuple, timeout: float) -> Any:
        self._ensure_started()
        self._conn.send((name, args))
        if not self._conn.poll(timeout):
            logger.warning("Calculus job %s exceeded %.1fs; restarting its worker", name, timeout)
            self.stop()
            raise SandboxTimeout()
        try:
            kind, payload = self._conn.recv()
        except EOFError:
            self.stop()
            raise SandboxFailure("The calculus worker stopped unexpectedly.") from None
        if kind == "ok":
            return payload
        if kind == "math_error":
            code, message = payload
            raise MathInputError(ErrorCode(code), message)
        raise SandboxFailure(payload)

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(timeout=5)
        if self._conn is not None:
            self._conn.close()
        self._proc = None
        self._conn = None


class Sandbox:
    def __init__(self, workers: int = 1) -> None:
        ctx = mp.get_context("spawn")  # same behaviour on Windows and Linux, no forked threads
        self._idle: queue.Queue[_Worker] = queue.Queue()
        self._all = [_Worker(ctx) for _ in range(max(1, workers))]
        for w in self._all:
            self._idle.put(w)

    def run(self, name: str, *args: Any, timeout: float = JOB_TIMEOUT_SECONDS, deadline: float | None = None) -> Any:
        """Run a job. ``deadline`` (time.monotonic()) also bounds the wait for a free worker."""
        if deadline is not None and deadline - time.monotonic() < MIN_JOB_SECONDS:
            raise SandboxTimeout()  # out of time: don't start a job only to kill its worker
        try:
            worker = self._idle.get(timeout=None if deadline is None else deadline - time.monotonic())
        except queue.Empty:
            raise SandboxTimeout() from None
        try:
            # Starting a worker (after a kill, or on first use) is not part of the job's limit.
            worker._ensure_started()
            if deadline is not None:
                timeout = min(timeout, deadline - time.monotonic())
                if timeout < MIN_JOB_SECONDS:
                    raise SandboxTimeout()
            return worker.call(name, args, timeout)
        finally:
            self._idle.put(worker)

    def ensure_ready(self) -> None:
        """Start any idle worker that is not running (e.g. after a kill). Busy workers are left alone."""
        for _ in self._all:
            try:
                worker = self._idle.get_nowait()
            except queue.Empty:
                return
            try:
                worker._ensure_started()
            finally:
                self._idle.put(worker)

    def warm_up(self) -> None:
        """Start the workers ahead of the first request (SymPy takes a few seconds to import)."""
        for _ in self._all:
            worker = self._idle.get()
            try:
                worker._ensure_started()
            finally:
                self._idle.put(worker)

    def shutdown(self) -> None:
        for w in self._all:
            w.stop()


_sandbox: Sandbox | None = None
_lock = threading.Lock()


def get_sandbox() -> Sandbox:
    global _sandbox
    with _lock:
        if _sandbox is None:
            _sandbox = Sandbox(workers=int(os.getenv("CALC_WORKERS", "1")))
        return _sandbox
