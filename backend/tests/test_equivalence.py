import sympy as sp

from app.core.equivalence_checker import compare, exact_equal
from app.core.first_error_detector import analyze_step
from app.core.types import ReasonCode


def sset(text):
    a = analyze_step(1, text)
    assert a.ok, a.error
    return a.solution_set


def test_exact_equal_radicals():
    assert exact_equal((5 + sp.sqrt(13)) / 2, sp.Rational(5, 2) + sp.sqrt(13) / 2)
    assert exact_equal(sp.sqrt(8), 2 * sp.sqrt(2))
    assert exact_equal(1 / (sp.sqrt(2) - 1), sp.sqrt(2) + 1)
    assert not exact_equal(sp.sqrt(2), sp.Rational(14142135623731, 10**13))


def test_equivalent_forms_of_irrational_roots():
    a = sset("x^2 - 5x + 3 = 0")
    b = sset("x = (5 ± sqrt(13))/2")
    c = sset("x = 5/2 + sqrt(13)/2 or x = 5/2 - sqrt(13)/2")
    assert compare(a, b).equivalent and compare(b, c).equivalent


def test_equivalent_transformations():
    pairs = [
        ("2x + 5 = 15", "2x = 10"),
        ("3(x + 2) = 15", "3x + 6 = 15"),
        ("x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"),
        ("(x - 2)(x - 3) = 0", "x - 2 = 0 or x - 3 = 0"),
        ("2x = 10", "x = 5"),
        ("x/2 = 3", "x = 6"),
        ("x + 1 = x + 2", "0 = 1"),
        ("2(x + 1) = 2x + 2", "0 = 0"),
        ("x^2 + 1 = 0", "x + 1 = x"),  # both empty: equivalent over the reals
    ]
    for before, after in pairs:
        assert compare(sset(before), sset(after)).equivalent, (before, after)


def test_lost_solution():
    cmp = compare(sset("x^2 = x"), sset("x = 1"))
    assert not cmp.equivalent
    assert cmp.reason_code is ReasonCode.LOST_SOLUTIONS
    assert cmp.lost == (0,)


def test_extraneous_solution():
    cmp = compare(sset("x = 2"), sset("x^2 = 4"))
    assert cmp.reason_code is ReasonCode.EXTRANEOUS_SOLUTIONS
    assert cmp.extraneous == (-2,)


def test_changed_solution():
    cmp = compare(sset("2x = 10"), sset("2x = 20"))
    assert cmp.reason_code is ReasonCode.SOLUTIONS_CHANGED
    assert cmp.lost == (5,) and cmp.extraneous == (10,)


def test_identity_and_contradiction_reasons():
    assert compare(sset("2x = 10"), sset("0 = 0")).reason_code is ReasonCode.BECAME_IDENTITY
    assert compare(sset("2x = 10"), sset("0 = 1")).reason_code is ReasonCode.BECAME_CONTRADICTION
    assert compare(sset("0 = 0"), sset("x = 1")).reason_code is ReasonCode.LOST_IDENTITY
