import time

import pytest

from app.core.calculus.calc_equivalence import Verdict
from app.core.calculus.sandbox import Sandbox, SandboxTimeout
from app.utils.errors import ErrorCode, MathInputError


@pytest.fixture(scope="module")
def box():
    sandbox = Sandbox(workers=1)
    sandbox.warm_up()
    yield sandbox
    sandbox.shutdown()


def test_runs_comparisons_in_the_worker(box):
    assert box.run("compare", "d/dx(x^2)", "2x", "VALUE").verdict is Verdict.EQUAL


def test_runaway_job_is_killed_and_the_worker_replaced(box):
    start = time.monotonic()
    with pytest.raises(SandboxTimeout):
        box.run("sleep", 30, timeout=1)
    assert time.monotonic() - start < 5
    # The next job gets a fresh worker and works normally.
    assert box.run("compare", "d/dx(x^3)", "3x^2", "VALUE").verdict is Verdict.EQUAL


def test_math_errors_cross_the_process_boundary(box):
    with pytest.raises(MathInputError) as info:
        box.run("compare", "d/dx(x^2)", "1/0", "VALUE")
    assert info.value.code is ErrorCode.DIVISION_BY_ZERO


def test_deadline_bounds_the_job(box):
    start = time.monotonic()
    with pytest.raises(SandboxTimeout):
        box.run("sleep", 30, timeout=10, deadline=time.monotonic() + 1)
    assert time.monotonic() - start < 5


def test_expired_deadline_fails_fast_without_running(box):
    with pytest.raises(SandboxTimeout):
        box.run("compare", "d/dx(x)", "1", "VALUE", deadline=time.monotonic() - 1)


def test_running_out_of_time_does_not_kill_the_worker(box):
    box.run("compare", "d/dx(x)", "1", "VALUE")  # make sure a worker is running
    worker = box._all[0]
    pid = worker._proc.pid
    for _ in range(3):
        with pytest.raises(SandboxTimeout):
            box.run("compare", "d/dx(x)", "1", "VALUE", deadline=time.monotonic() + 0.1)
    assert worker._proc is not None and worker._proc.pid == pid  # no restart storm


def test_worker_startup_does_not_count_against_the_job(box):
    box._all[0].stop()  # the next job has to start a fresh worker first
    outcome = box.run("compare", "d/dx(x^2)", "2x", "VALUE", timeout=1)
    assert outcome.verdict is Verdict.EQUAL
