import pytest

from app.core.first_error_detector import analyze_step
from app.utils.errors import ErrorCategory, ErrorCode
from tests.conftest import ALL_REAL, EMPTY, FINITE


@pytest.mark.parametrize(
    "text, values",
    [
        ("x² - 5x + 6 = 0", ["2", "3"]),
        ("(x - 2)(x - 3) = 0", ["2", "3"]),
        ("x^2 = x", ["0", "1"]),
        ("x^2 = 9", ["-3", "3"]),
        ("2x^2 + 3x - 2 = 0", ["-2", "1/2"]),
        ("x(x + 4) = 0", ["-4", "0"]),
        ("x^2 - 5x + 3 = 0", ["5/2 - sqrt(13)/2", "sqrt(13)/2 + 5/2"]),
        ("x^2 = 2", ["-sqrt(2)", "sqrt(2)"]),
        ("(x - sqrt(2))(x + sqrt(2)) = 0", ["-sqrt(2)", "sqrt(2)"]),
        ("x = (5 ± sqrt(25 - 24))/2", ["2", "3"]),
        ("x = (-(-5) ± sqrt((-5)^2 - 4(1)(6)))/(2(1))", ["2", "3"]),
    ],
)
def test_two_real_roots(solve, text, values):
    assert solve(text) == (FINITE, values)


def test_repeated_root(solve):
    assert solve("x^2 - 4x + 4 = 0") == (FINITE, ["2"])
    assert solve("(x - 2)^2 = 0") == (FINITE, ["2"])


def test_no_real_roots(solve):
    assert solve("x^2 + 1 = 0") == (EMPTY, [])
    assert solve("x^2 + x + 1 = 0") == (EMPTY, [])


def test_quadratic_identity(solve):
    assert solve("(x + 1)^2 = x^2 + 2x + 1") == (ALL_REAL, [])


def test_quadratic_reduces_to_linear(solve):
    assert solve("x^2 + 2x = x^2 + 4") == (FINITE, ["2"])


def test_irrational_coefficient_quadratic(solve):
    # discriminant (2√2)^2 - 4*1*2 = 0 exactly -> repeated root
    assert solve("x^2 - 2sqrt(2)x + 2 = 0") == (FINITE, ["sqrt(2)"])


@pytest.mark.parametrize("text", ["x^3 = 8", "x^3 - 6x^2 + 11x - 6 = 0", "x(x-1)(x-2) = 0", "x^4 = 1"])
def test_cubic_and_higher_unsupported(text):
    a = analyze_step(1, text)
    assert a.error.code is ErrorCode.DEGREE_TOO_HIGH
    assert a.error.category is ErrorCategory.UNSUPPORTED
