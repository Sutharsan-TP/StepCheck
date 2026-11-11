import pytest

from app.core.first_error_detector import analyze_step
from app.utils.errors import ErrorCode
from tests.conftest import ALL_REAL, EMPTY, FINITE


@pytest.mark.parametrize(
    "text, values",
    [
        ("2x + 5 = 15", ["5"]),
        ("2x + 4 = 10", ["3"]),
        ("3(x + 2) = 15", ["3"]),
        ("x = 5", ["5"]),
        ("5 = x", ["5"]),
        ("-3x + 2 = 11", ["-3"]),
        ("x/4 = 1/2", ["2"]),
        ("2x + 1 = 4", ["3/2"]),
        ("0.25x = 1.5", ["6"]),
        ("4x - 7 = 2x + 3", ["5"]),
        ("2(x - 3) - (x + 1) = 0", ["7"]),
        ("x^3 - x^3 + 2x = 4", ["2"]),  # cancels to linear
    ],
)
def test_linear_solutions(solve, text, values):
    assert solve(text) == (FINITE, values)


def test_identity(solve):
    assert solve("2(x + 1) = 2x + 2") == (ALL_REAL, [])
    assert solve("0 = 0") == (ALL_REAL, [])
    assert solve("x - x = 0") == (ALL_REAL, [])


def test_contradiction(solve):
    assert solve("x + 1 = x + 2") == (EMPTY, [])
    assert solve("1 = 2") == (EMPTY, [])


def test_disjunction_of_linear(solve):
    assert solve("x - 2 = 0 or x - 3 = 0") == (FINITE, ["2", "3"])
    assert solve("x = 3 or x = 2") == (FINITE, ["2", "3"])  # sorted
    assert solve("x = 2 or x = 2") == (FINITE, ["2"])  # deduplicated
    assert solve("x = 2 or 0 = 0") == (ALL_REAL, [])


def test_irrational_linear(solve):
    assert solve("sqrt(2) x = 2") == (FINITE, ["sqrt(2)"])


def test_normalized_form():
    assert analyze_step(1, "2x + 5 = 15").normalized == "2*x - 10 = 0"


def test_multiple_variables_unsupported():
    a = analyze_step(1, "x + y = 3")
    assert a.error.code is ErrorCode.MULTIPLE_VARIABLES
