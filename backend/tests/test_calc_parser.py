import pytest
import sympy as sp

from app.core.calculus.calc_parser import C, Topic, looks_like_calculus, parse_calculus, to_text
from app.core.equation_parser import X
from app.utils.errors import ErrorCategory, ErrorCode, MathInputError


def value(text: str) -> sp.Expr:
    return parse_calculus(text).expressions()[-1]


@pytest.mark.parametrize(
    "text, topic",
    [
        ("d/dx(x^2 sin(x))", Topic.DERIVATIVE),
        ("int(x^2) dx", Topic.INTEGRAL),
        ("∫ x^2 + 1 dx", Topic.INTEGRAL),
        ("int[0, 2](x^2) dx", Topic.DEFINITE_INTEGRAL),
        ("∫[0, π](sin(x)) dx", Topic.DEFINITE_INTEGRAL),
        ("lim(x->0, sin(x)/x)", Topic.LIMIT),
        ("lim(x→∞, 1/x)", Topic.LIMIT),
        ("2 d/dx(x^3) = 6x^2", Topic.DERIVATIVE),
    ],
)
def test_topic_of_problem_lines(text, topic):
    assert parse_calculus(text).topic is topic
    assert looks_like_calculus(text)


@pytest.mark.parametrize("text", ["2x + 5 = 15", "x = 2 or x = 3", "x^2 - 5x + 6 = 0", "x = sqrt(13)"])
def test_algebra_lines_are_not_routed_to_calculus(text):
    assert not looks_like_calculus(text)


def test_operators_stay_unevaluated():
    assert value("d/dx(x^2)") == sp.Derivative(X**2, X)
    assert value("int(x^2) dx") == sp.Integral(X**2, X)
    assert value("int[0, 2](x^2) dx") == sp.Integral(X**2, (X, 0, 2))
    assert value("lim(x->0, sin(x)/x)") == sp.Limit(sp.sin(X) / X, X, 0, dir="+-")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2x e^x", 2 * X * sp.exp(X)),
        ("e^(2x)", sp.exp(2 * X)),
        ("sin^2(x) + cos^2(x)", sp.sin(X) ** 2 + sp.cos(X) ** 2),
        ("x^-1", 1 / X),
        ("x^(1/2)", sp.sqrt(X)),
        ("ln(x)", sp.log(X)),
        ("log(x)", sp.log(X, 10)),
        ("arctan(x) + asin(x)", sp.atan(X) + sp.asin(X)),
        ("abs(x)", sp.Abs(X)),
        ("√(x+1)", sp.sqrt(X + 1)),
        ("sec(x)tan(x)", sp.sec(X) * sp.tan(X)),
        ("x^3/3 + C", X**3 / 3 + C),
        ("[x^3/3][0, 2]", sp.Rational(8, 3)),
        ("2π + ∞", 2 * sp.pi + sp.oo),
        ("1.5x", sp.Rational(3, 2) * X),
    ],
)
def test_expressions_build_exact_sympy(text, expected):
    assert sp.simplify(value(text) - expected) == 0 if expected.is_finite is not False else value(text) == expected


def test_chain_of_equal_expressions_gives_one_link_each():
    statement = parse_calculus("d/dx(x^2 sin(x)) = 2x sin(x) + x^2 cos(x)")
    assert len(statement.links) == 2
    assert not parse_calculus("d/dx(x^2)").evaluated
    assert statement.evaluated  # only the last expression counts


def test_constant_and_evaluation_flags():
    assert parse_calculus("x^2 + C").has_constant
    assert not parse_calculus("x^2").has_constant
    assert not parse_calculus("[x^2][0, 1]").evaluated
    assert parse_calculus("8/3").evaluated


@pytest.mark.parametrize(
    "text",
    ["d/dx(x^2 sin(x))", "int(x^2 + 1) dx", "int[0, pi](sin(x)) dx", "lim(x->oo, 1/x)", "[x^3/3][0, 2]", "2 x e^x + C"],
)
def test_text_rendering_reparses_to_the_same_value(text):
    first = parse_calculus(text)
    again = parse_calculus(" = ".join(to_text(link) for link in first.links))
    assert [str(e) for e in again.expressions()] == [str(e) for e in first.expressions()]


def test_latex_rendering():
    assert parse_calculus("d/dx(x^2)").latex == r"\frac{d}{dx}\left({x}^{2}\right)"
    assert parse_calculus("int[0, 1](x) dx").latex == r"\int_{0}^{1} x \, dx"
    assert parse_calculus("lim(x->0, sin(x)/x)").latex == r"\lim_{x \to 0} \frac{\sin\left(x\right)}{x}"
    assert parse_calculus("sin^2(x)").latex == r"\sin^{2}\left(x\right)"
    assert parse_calculus("int(x^2 + 1) dx").latex == r"\int \left({x}^{2} + 1\right) \, dx"


@pytest.mark.parametrize(
    "text, code",
    [
        ("sinx", ErrorCode.SYNTAX_ERROR),
        ("sin x", ErrorCode.SYNTAX_ERROR),
        ("int(x)", ErrorCode.SYNTAX_ERROR),
        ("d/dx", ErrorCode.SYNTAX_ERROR),
        ("y + 1", ErrorCode.MULTIPLE_VARIABLES),
        ("lim(y->0, y)", ErrorCode.MULTIPLE_VARIABLES),
        ("sinh(x)", ErrorCode.UNSUPPORTED_FUNCTION),
        ("9^(9^9)", ErrorCode.EXPONENT_TOO_LARGE),
        ("x^25", ErrorCode.EXPONENT_TOO_LARGE),
        ("2^(10^2)", ErrorCode.EXPONENT_TOO_LARGE),
        ("sin^9(x)", ErrorCode.EXPONENT_TOO_LARGE),
        ("int[0, x](x) dx", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("lim(x->x, x)", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("[x][0, C]", ErrorCode.AMBIGUOUS_EXPRESSION),
        ("1/0", ErrorCode.DIVISION_BY_ZERO),
        ("x == 1", ErrorCode.SYNTAX_ERROR),
        ("__import__('os')", ErrorCode.INVALID_CHARACTER),
        ("x; 1", ErrorCode.INVALID_CHARACTER),
    ],
)
def test_rejected_input(text, code):
    with pytest.raises(MathInputError) as info:
        parse_calculus(text)
    assert info.value.code is code


def test_size_limits():
    with pytest.raises(MathInputError) as info:
        parse_calculus("d/dx(" * 6 + "x" + ")" * 6)
    assert info.value.code is ErrorCode.TOO_COMPLEX  # more than 4 operators in one step
    with pytest.raises(MathInputError) as info:
        parse_calculus("(" * 25 + "x" + ")" * 25)
    assert info.value.code is ErrorCode.TOO_COMPLEX
    with pytest.raises(MathInputError) as info:
        parse_calculus("x+" * 80 + "x")  # under 200 characters but over the node limit
    assert info.value.code is ErrorCode.TOO_COMPLEX
    with pytest.raises(MathInputError) as info:
        parse_calculus("x + " * 60 + "x")
    assert info.value.code is ErrorCode.INPUT_TOO_LONG


def test_unsupported_function_is_out_of_scope_not_a_typo():
    with pytest.raises(MathInputError) as info:
        parse_calculus("cosh(x)")
    assert info.value.category is ErrorCategory.UNSUPPORTED
