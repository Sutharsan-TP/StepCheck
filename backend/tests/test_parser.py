import sympy as sp
import pytest

from app.core.equation_parser import X, clause_equations, parse_statement
from app.core.first_error_detector import analyze_step
from app.utils.errors import ErrorCategory, ErrorCode, MathInputError


def equations(text):
    stmt = parse_statement(text)
    return [eq for c in stmt.clauses for eq in clause_equations(c)]


def lhs_minus_rhs(text):
    (lhs, rhs), = equations(text)
    return sp.expand(lhs - rhs)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2x + 5 = 15", 2 * X - 10),
        ("3(x + 2) = 15", 3 * X - 9),
        ("(x - 2)(x - 3) = 0", X**2 - 5 * X + 6),
        ("x(x + 1) = 0", X**2 + X),
        ("2x^2 = 8", 2 * X**2 - 8),
        ("x² − 5x + 6 = 0", X**2 - 5 * X + 6),  # unicode superscript and minus
        ("x**2 = 4", X**2 - 4),
        ("2 × x = 6", 2 * X - 6),
        ("x ÷ 2 = 3", X / 2 - 3),
        ("-x = 4", -X - 4),
        ("-(x - 1) = 2", -X - 1),
        ("0.5x = 2", X / 2 - 2),  # decimals become exact rationals
        ("x/3 + 1/6 = 1", X / 3 - sp.Rational(5, 6)),
        ("(1/2)x = 3", X / 2 - 3),
        ("2√3 = x", 2 * sp.sqrt(3) - X),
        ("√(3)x = 6", sp.sqrt(3) * X - 6),
        ("x = sqrt(16)", X - 4),
        ("x^(2) = 1", X**2 - 1),
        ("x^0 = 1", sp.Integer(0)),
    ],
)
def test_valid_syntax(text, expected):
    assert sp.expand(lhs_minus_rhs(text) - expected) == 0


def test_decimal_is_exact():
    assert lhs_minus_rhs("0.1x = 0.3") == sp.Rational(1, 10) * X - sp.Rational(3, 10)


def test_plus_minus_expands_to_branches():
    rhs = sorted(r for _, r in equations("x = (5 ± sqrt(1))/2"))
    assert rhs == [2, 3]
    assert len(equations("x = (5 +/- 1)/2")) == 2


def test_disjunctions_and_shorthand():
    assert len(equations("x = 2 or x = 3")) == 2
    assert len(equations("x = 2, x = 3")) == 2
    assert [r for _, r in equations("x = 2 or 3")] == [2, 3]
    assert [r for _, r in equations("x - 2 = 0 or x - 3 = 0")] == [0, 0]


@pytest.mark.parametrize(
    "text, literal_kind",
    [("no solution", "EMPTY"), ("No real solutions.", "EMPTY"), ("∅", "EMPTY"),
     ("all real numbers", "ALL_REAL"), ("x ∈ ℝ", "ALL_REAL")],
)
def test_solution_literals(text, literal_kind):
    assert parse_statement(text).literal.kind.value == literal_kind


def test_latex_preserves_written_form():
    # The student's own form must be rendered, not SymPy's simplification.
    assert parse_statement("2x = 15 - 5").latex == "2 x = 15 - 5"
    assert parse_statement("x = (5 ± sqrt(13))/2").latex == r"x = \frac{5 \pm \sqrt{13}}{2}"


@pytest.mark.parametrize(
    "text, code",
    [
        # malicious / non-math input
        ("__import__('os').system('rm -rf /')", ErrorCode.INVALID_CHARACTER),
        ("x.real = 2", ErrorCode.SYNTAX_ERROR),
        ("eval(1) = 1", ErrorCode.UNKNOWN_IDENTIFIER),
        ("lambda = 1", ErrorCode.UNKNOWN_IDENTIFIER),
        ("x = 1; import os", ErrorCode.INVALID_CHARACTER),
        ("x = [1]", ErrorCode.INVALID_CHARACTER),
        ("x = 'a'", ErrorCode.INVALID_CHARACTER),
        # variables / functions
        ("y = 2", ErrorCode.MULTIPLE_VARIABLES),
        ("2xy = 4", ErrorCode.MULTIPLE_VARIABLES),
        ("x + y = 4", ErrorCode.MULTIPLE_VARIABLES),
        ("X = 2", ErrorCode.UNKNOWN_IDENTIFIER),
        ("sin(x) = 0", ErrorCode.UNSUPPORTED_FUNCTION),
        ("log(x) = 1", ErrorCode.UNSUPPORTED_FUNCTION),
        ("xx = 4", ErrorCode.AMBIGUOUS_EXPRESSION),
        # division / radicals / exponents
        ("1/x = 2", ErrorCode.DIVISION_BY_VARIABLE),
        ("x/x = 1", ErrorCode.DIVISION_BY_VARIABLE),
        ("x/0 = 1", ErrorCode.DIVISION_BY_ZERO),
        ("x/(2-2) = 1", ErrorCode.DIVISION_BY_ZERO),
        ("1/2x = 3", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("sqrt(x) = 2", ErrorCode.RADICAL_OF_VARIABLE),
        ("x = sqrt(-4)", ErrorCode.COMPLEX_VALUE),
        ("√3x = 3", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("x^0.5 = 2", ErrorCode.NON_INTEGER_EXPONENT),
        ("x^-1 = 2", ErrorCode.NEGATIVE_EXPONENT),
        ("x^1000 = 1", ErrorCode.EXPONENT_TOO_LARGE),
        ("(x+1)^1000000 = 1", ErrorCode.EXPONENT_TOO_LARGE),
        ("((x^2)^2)^2 = 1", ErrorCode.NESTED_POWER),
        ("(x+1)^4 (x-1)^4 = 1", ErrorCode.DEGREE_TOO_HIGH),  # pre-expansion bound
        # shape
        ("", ErrorCode.EMPTY_INPUT),
        ("   ", ErrorCode.EMPTY_INPUT),
        ("x + 1", ErrorCode.MISSING_EQUALS),
        ("x = 2 = 3", ErrorCode.CHAINED_EQUALS),
        ("x == 2", ErrorCode.SYNTAX_ERROR),
        ("2 3 = x", ErrorCode.SYNTAX_ERROR),
        ("x2 = 4", ErrorCode.SYNTAX_ERROR),
        ("2x + = 5", ErrorCode.SYNTAX_ERROR),
        ("(x + 1 = 2", ErrorCode.SYNTAX_ERROR),
        ("x = 2 and x = 3", ErrorCode.UNSUPPORTED_CONNECTIVE),
        ("x + 1 = 2 or 3", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("x = 1 ± 2 ± 3 ± 4", ErrorCode.TOO_COMPLEX),
        ("x = 1234567890123", ErrorCode.TOO_COMPLEX),
    ],
)
def test_rejections(text, code):
    with pytest.raises(MathInputError) as info:
        equations(text)
    assert info.value.code == code


def test_oversized_input():
    with pytest.raises(MathInputError) as info:
        parse_statement("x + " * 60 + "1 = 2")
    assert info.value.code == ErrorCode.INPUT_TOO_LONG


def test_deep_nesting_rejected():
    with pytest.raises(MathInputError) as info:
        parse_statement("(" * 40 + "x" + ")" * 40 + " = 1")
    assert info.value.code == ErrorCode.TOO_COMPLEX


def test_too_many_nodes_rejected():
    with pytest.raises(MathInputError) as info:
        parse_statement("+".join(["1"] * 90) + " = x")
    assert info.value.code == ErrorCode.TOO_COMPLEX


def test_categories():
    assert analyze_step(1, "x^3 = 8").error.category is ErrorCategory.UNSUPPORTED
    assert analyze_step(1, "2x + = 5").error.category is ErrorCategory.NEEDS_REVIEW
    assert analyze_step(1, "y = 2").error.category is ErrorCategory.UNSUPPORTED
