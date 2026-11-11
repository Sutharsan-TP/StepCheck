import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.first_error_detector import analyze_step  # noqa: E402
from app.core.types import SolutionKind  # noqa: E402


def solution_of(text: str):
    """Solve a single step; return ('FINITE_SET', ['2', '3']) style tuples."""
    a = analyze_step(1, text)
    assert a.ok, f"{text!r} failed: {a.error.code} {a.error.message}"
    return a.solution_set.kind, a.solution_set.value_strings()


@pytest.fixture
def solve():
    return solution_of


FINITE = SolutionKind.FINITE_SET
EMPTY = SolutionKind.EMPTY
ALL_REAL = SolutionKind.ALL_REAL
