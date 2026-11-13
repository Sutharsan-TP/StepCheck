"""Deciding whether two calculus expressions are equal. Runs inside the sandbox worker.

Two kinds of equality:

* VALUE: the expressions are the same function of x (or the same number), once
  derivatives, integrals and limits are carried out.
* ANTIDERIVATIVE: the expressions differ only by a constant, which is how
  indefinite-integral steps relate. This is checked by differentiating the
  difference, so SymPy never has to find an antiderivative itself.

A verdict is only EQUAL when SymPy proves the difference is zero, and only
UNEQUAL when high-precision evaluation at a sample point in the shared domain
gives a clearly non-zero difference (a counterexample). Anything else is
UNKNOWN, which the verifier reports as NEEDS_REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp
from sympy.calculus.accumulationbounds import AccumulationBounds
from sympy.printing.str import StrPrinter

from app.core.calculus.calc_parser import C, Topic, node_to_sympy, parse_calculus
from app.core.equation_parser import X
from app.utils.errors import MathInputError

PRECISION = 50
_SAMPLE_POINTS = [sp.Rational(n, 100) for n in (37, 129, 271, -83, -191, 61, 370, -260, 17, 523)]
_C_VALUE = sp.Rational(731, 1000)
_MIN_AGREEING_POINTS = 3
_RELATIVE_TOLERANCE = sp.Float("1e-25", PRECISION)
_XP = sp.Symbol("x", positive=True)
_XN = sp.Symbol("x", negative=True)


class Mode(str, Enum):
    VALUE = "VALUE"
    ANTIDERIVATIVE = "ANTIDERIVATIVE"


class Verdict(str, Enum):
    EQUAL = "EQUAL"
    UNEQUAL = "UNEQUAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Outcome:
    """Plain, picklable result of one comparison."""

    verdict: Verdict
    reason: str | None = None  # NOT_EQUAL, DIFFERS_BY_NON_CONSTANT, CANNOT_DECIDE, UNDEFINED
    counterexample: str | None = None  # e.g. "x = 37/100"
    expected_latex: str | None = None  # value the step should have
    found_latex: str | None = None  # value the step actually has
    note: str | None = None  # e.g. "equal for x > 0"


def mode_for(topic: Topic) -> Mode:
    return Mode.ANTIDERIVATIVE if topic is Topic.INTEGRAL else Mode.VALUE


# ------------------------------------------------------------------- comparison


def compare_texts(expected_text: str, found_text: str, mode: str) -> Outcome:
    """Sandbox entry point: both arguments are single expressions in calculus syntax."""
    expected = node_to_sympy(parse_calculus(expected_text).links[-1])
    found = node_to_sympy(parse_calculus(found_text).links[-1])
    return compare(expected, found, Mode(mode))


def compare(expected: sp.Expr, found: sp.Expr, mode: Mode) -> Outcome:
    if mode is Mode.ANTIDERIVATIVE:
        a, b = _evaluate(sp.diff(expected, X)), _evaluate(sp.diff(found, X))
        outcome = _compare_values(a, b)
        if outcome.verdict is Verdict.UNEQUAL:
            return Outcome(
                Verdict.UNEQUAL, "DIFFERS_BY_NON_CONSTANT", outcome.counterexample,
                expected_latex=_latex(a), found_latex=_latex(b),
            )
        return outcome
    a, b = _evaluate(expected), _evaluate(found)
    outcome = _compare_values(a, b)
    if outcome.verdict is Verdict.UNEQUAL:
        return Outcome(
            Verdict.UNEQUAL, "NOT_EQUAL", outcome.counterexample, expected_latex=_latex(a), found_latex=_latex(b)
        )
    return outcome


def _evaluate(expr: sp.Expr) -> sp.Expr:
    return expr.doit(deep=True) if expr.has(sp.Derivative, sp.Integral, sp.Limit) else expr


def _undefined(v: sp.Expr) -> bool:
    return v.has(sp.nan, sp.zoo, AccumulationBounds) or isinstance(v, AccumulationBounds)


def _compare_values(a: sp.Expr, b: sp.Expr) -> Outcome:
    if _undefined(a) or _undefined(b):
        return Outcome(Verdict.UNKNOWN, "UNDEFINED")
    if a.has(sp.Limit) or b.has(sp.Limit):
        return Outcome(Verdict.UNKNOWN, "CANNOT_DECIDE")  # SymPy could not evaluate a limit

    infinite = {sp.oo, -sp.oo}
    if a in infinite or b in infinite:
        if a == b:
            return Outcome(Verdict.EQUAL)
        if (a in infinite and b in infinite) or not (a.free_symbols | b.free_symbols):
            return Outcome(Verdict.UNEQUAL, counterexample=None)
        return Outcome(Verdict.UNKNOWN, "CANNOT_DECIDE")

    difference = a - b
    if difference == 0:
        return Outcome(Verdict.EQUAL)

    # A numeric counterexample is quick to find, so look for one before simplifying.
    agreeing: list[sp.Rational] = []
    points = _SAMPLE_POINTS if X in difference.free_symbols else _SAMPLE_POINTS[:1]
    for point in points:
        va, vb = _numeric(a, point), _numeric(b, point)
        if va is None or vb is None:
            continue  # outside the shared real domain
        if abs(va - vb) > _RELATIVE_TOLERANCE * (1 + abs(va) + abs(vb)):
            where = f"x = {point}" if X in difference.free_symbols else None
            return Outcome(Verdict.UNEQUAL, counterexample=where)
        agreeing.append(point)

    if _proved_zero(difference):
        return Outcome(Verdict.EQUAL)
    if len(agreeing) >= _MIN_AGREEING_POINTS and X in difference.free_symbols:
        # Numerically equal wherever both sides are real: prove it separately for
        # x > 0 and x < 0, which handles |x| and logarithms of x.
        positive = any(p > 0 for p in agreeing) and _proved_zero(difference.subs(X, _XP))
        negative = any(p < 0 for p in agreeing) and _proved_zero(difference.subs(X, _XN))
        if positive and negative:
            return Outcome(Verdict.EQUAL)
        if positive and not any(p < 0 for p in agreeing):
            return Outcome(Verdict.EQUAL, note="equal for x > 0")
        if negative and not any(p > 0 for p in agreeing):
            return Outcome(Verdict.EQUAL, note="equal for x < 0")
    return Outcome(Verdict.UNKNOWN, "CANNOT_DECIDE")


def _proved_zero(d: sp.Expr) -> bool:
    if d == 0:
        return True
    for attempt in (
        sp.simplify,
        lambda e: sp.simplify(sp.expand_trig(e)),
        lambda e: sp.simplify(e.rewrite(sp.exp)),
        lambda e: sp.simplify(sp.expand_log(e)),
    ):
        try:
            if attempt(d) == 0:
                return True
        except Exception:  # a failed rewrite proves nothing; try the next one
            continue
    return False


def _numeric(expr: sp.Expr, point: sp.Rational) -> sp.Float | None:
    try:
        value = expr.subs({X: point, C: _C_VALUE}).evalf(PRECISION)
    except Exception:
        return None
    if value.free_symbols or not value.is_real or not value.is_finite:
        return None
    return value


# --------------------------------------------------------------- expected answer


@dataclass(frozen=True)
class Answer:
    text: str
    latex: str


def expected_answer(problem_text: str, topic: str) -> Answer | None:
    """Sandbox entry point: the engine's own result for the problem, or None if SymPy can't find it."""
    expr = node_to_sympy(parse_calculus(problem_text).links[0])
    value = expr.doit(deep=True)
    if value.has(sp.Derivative, sp.Integral, sp.Limit) or _undefined(value):
        return None
    simplified = sp.simplify(value)
    if sp.count_ops(simplified) < sp.count_ops(value):
        value = simplified
    text, latex = to_student_text(value), _latex(value)
    if Topic(topic) is Topic.INTEGRAL:
        text, latex = f"{text} + C", f"{latex} + C"
    try:
        parse_calculus(text)  # e.g. d/dx|x| = sign(x): not something a student could write
    except MathInputError:
        return None
    return Answer(text=text, latex=latex)


class _StudentPrinter(StrPrinter):
    """SymPy -> the calculus input syntax (ln for natural log, ^ for powers)."""

    def _print_log(self, expr):
        if len(expr.args) == 1:
            return f"ln({self._print(expr.args[0])})"
        return f"ln({self._print(expr.args[0])})/ln({self._print(expr.args[1])})"

    def _print_Abs(self, expr):
        return f"abs({self._print(expr.args[0])})"

    def _print_Exp1(self, expr):
        return "e"

    def _print_Infinity(self, expr):
        return "oo"

    def _print_NegativeInfinity(self, expr):
        return "-oo"


def to_student_text(expr: sp.Expr) -> str:
    return _StudentPrinter().doprint(expr).replace("**", "^")


def _latex(expr: sp.Expr) -> str:
    return sp.latex(expr, ln_notation=True)
