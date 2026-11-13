import pytest

from app.core.calculus.calc_equivalence import Verdict, compare_texts, expected_answer, to_student_text
from app.core.calculus.calc_parser import parse_calculus

V, A = "VALUE", "ANTIDERIVATIVE"


@pytest.mark.parametrize(
    "expected, found, mode",
    [
        ("d/dx(x^2 sin(x))", "2x sin(x) + x^2 cos(x)", V),
        ("d/dx(x^2 sin(x))", "d/dx(x^2) sin(x) + x^2 d/dx(sin(x))", V),
        ("d/dx(sin(x^2))", "2x cos(x^2)", V),
        ("d/dx(e^(3x))", "3e^(3x)", V),
        ("d/dx(ln(x))", "1/x", V),
        ("d/dx(x/(x+1))", "1/(x+1)^2", V),
        ("sin(x)^2 + cos(x)^2", "1", V),
        ("tan(x)", "sin(x)/cos(x)", V),
        ("int(2x) dx", "x^2", A),
        ("int(2x) dx", "x^2 + C", A),
        ("int(2x) dx", "x^2 + 7", A),  # any constant is fine between integral steps
        ("int(x sin(x)) dx", "-x cos(x) + int(cos(x)) dx", A),
        ("int(1/x) dx", "ln(abs(x)) + C", A),
        ("int(cos(x)) dx", "sin(x) + C", A),
        ("int[0, 2](x^2) dx", "[x^3/3][0, 2]", V),
        ("int[0, 2](x^2) dx", "8/3", V),
        ("int[0, pi](sin(x)) dx", "2", V),
        ("lim(x->0, sin(x)/x)", "1", V),
        ("lim(x->0, sin(x)/x)", "lim(x->0, cos(x)/1)", V),
        ("lim(x->oo, (2x+1)/(x-3))", "2", V),
        ("lim(x->oo, x^2)", "oo", V),
    ],
)
def test_proved_equal(expected, found, mode):
    assert compare_texts(expected, found, mode).verdict is Verdict.EQUAL


@pytest.mark.parametrize(
    "expected, found, mode, reason",
    [
        ("d/dx(x^2 sin(x))", "2x cos(x)", V, "NOT_EQUAL"),  # product rule as f'g'
        ("d/dx(sin(x^2))", "cos(x^2)", V, "NOT_EQUAL"),  # chain rule: inner derivative dropped
        ("d/dx(cos(x))", "sin(x)", V, "NOT_EQUAL"),
        ("int(2x) dx", "x^3", A, "DIFFERS_BY_NON_CONSTANT"),
        ("int(x^2) dx", "x^3", A, "DIFFERS_BY_NON_CONSTANT"),  # forgot to divide by 3
        ("int[0, 2](x^2) dx", "3", V, "NOT_EQUAL"),
        ("int[0, 2](x^2) dx", "[x^3/3][2, 0]", V, "NOT_EQUAL"),  # limits swapped
        ("lim(x->0, sin(x)/x)", "0", V, "NOT_EQUAL"),
        ("lim(x->oo, x^2)", "-oo", V, None),
    ],
)
def test_proved_unequal_with_evidence(expected, found, mode, reason):
    outcome = compare_texts(expected, found, mode)
    assert outcome.verdict is Verdict.UNEQUAL
    if reason:
        assert outcome.reason == reason


def test_counterexample_and_values_explain_the_difference():
    outcome = compare_texts("d/dx(x^2 sin(x))", "2x cos(x)", V)
    assert outcome.counterexample and outcome.counterexample.startswith("x = ")
    assert outcome.expected_latex and "sin" in outcome.expected_latex
    assert outcome.found_latex == r"2 x \cos{\left(x \right)}"
    # For integrals the evidence is about derivatives: d/dx of each side.
    outcome = compare_texts("int(2x) dx", "x^3", A)
    assert (outcome.expected_latex, outcome.found_latex) == ("2 x", "3 x^{2}")


def test_equal_only_where_both_sides_are_real_is_noted():
    outcome = compare_texts("ln(x^2)", "2ln(x)", V)
    assert outcome.verdict is Verdict.EQUAL
    assert outcome.note == "equal for x > 0"


@pytest.mark.parametrize(
    "expected, found, reason",
    [
        ("lim(x->0, 1/x)", "oo", "UNDEFINED"),  # two-sided limit does not exist
        ("lim(x->0, sin(1/x))", "0", "UNDEFINED"),
        ("lim(x->oo, x)", "x", "CANNOT_DECIDE"),
    ],
)
def test_undecidable_cases_are_never_guessed(expected, found, reason):
    outcome = compare_texts(expected, found, V)
    assert outcome.verdict is Verdict.UNKNOWN
    assert outcome.reason == reason


@pytest.mark.parametrize(
    "problem, topic, text",
    [
        ("d/dx(x^3 + 2x)", "DERIVATIVE", "3*x^2 + 2"),
        ("int(cos(x)) dx", "INTEGRAL", "sin(x) + C"),
        ("int[0, 2](x^2) dx", "DEFINITE_INTEGRAL", "8/3"),
        ("lim(x->0, sin(x)/x)", "LIMIT", "1"),
        ("lim(x->0, 1/x)", "LIMIT", None),  # does not exist: no answer offered
    ],
)
def test_expected_answer(problem, topic, text):
    answer = expected_answer(problem, topic)
    assert (answer.text if answer else None) == text


def test_expected_answer_text_reparses():
    for problem, topic in [("d/dx(x^2 ln(x))", "DERIVATIVE"), ("int(e^x x) dx", "INTEGRAL"), ("d/dx(sec(x))", "DERIVATIVE")]:
        parse_calculus(expected_answer(problem, topic).text)


def test_expected_answer_outside_the_input_syntax_is_withheld():
    assert expected_answer("d/dx(abs(x))", "DERIVATIVE") is None  # SymPy says sign(x)


def test_student_text_uses_input_syntax():
    import sympy as sp

    x = sp.Symbol("x", real=True)
    assert to_student_text(sp.log(x) + sp.Abs(x) + sp.E + x**2) == "x^2 + ln(x) + abs(x) + e"
