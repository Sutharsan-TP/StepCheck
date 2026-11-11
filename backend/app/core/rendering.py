"""Render exact SymPy values back into student-style text that our parser accepts.

Every string produced here is re-parsed and re-verified before it is shown, so
the renderer only has to be readable, not trusted.
"""

from __future__ import annotations

import re

import sympy as sp

from app.core.equation_parser import X
from app.core.types import SolutionKind, SolutionSet

_IMPLICIT_MUL = re.compile(r"(?<=[\dx)])\*(?=[x(]|sqrt)")

EMPTY_TEXT = "no real solution"
ALL_REAL_TEXT = "all real numbers"


def expr_text(expr: sp.Expr) -> str:
    expr = sp.sympify(expr)
    text = sp.sstr(expr, order="lex") if expr.has(X) else sp.sstr(expr)
    text = text.replace("**", "^")
    return _IMPLICIT_MUL.sub("", text)


def value_text(value: sp.Expr) -> str:
    """A root written compactly, e.g. (5 - sqrt(13))/2 rather than 5/2 - sqrt(13)/2."""
    combined = sp.together(value)
    text = expr_text(combined)
    return text if len(text) <= len(expr_text(value)) else expr_text(value)


def equation_text(lhs: sp.Expr, rhs: sp.Expr) -> str:
    return f"{expr_text(lhs)} = {expr_text(rhs)}"


def solved_text(solutions: SolutionSet) -> str:
    if solutions.kind is SolutionKind.EMPTY:
        return EMPTY_TEXT
    if solutions.kind is SolutionKind.ALL_REAL:
        return ALL_REAL_TEXT
    return " or ".join(f"x = {value_text(v)}" for v in solutions.values)


def factored_text(poly_expr: sp.Expr) -> str | None:
    """'(x - 2)(x - 3)' style factorisation over the rationals, or None if irreducible."""
    if any(not c.is_Rational for c in sp.Poly(poly_expr, X).all_coeffs()):
        return None
    const, factors = sp.factor_list(poly_expr, X)
    degrees = [sp.degree(f, X) for f, _ in factors]
    if not factors or max(degrees) > 1:
        return None
    factors.sort(key=lambda fm: float(-fm[0].subs(X, 0) / fm[0].coeff(X, 1)))  # by root
    parts = []
    for f, mult in factors:
        body = expr_text(f)
        part = body if body == "x" else f"({body})"
        parts.append(part + (f"^{mult}" if mult > 1 else ""))
    prefix = "" if const == 1 else "-" if const == -1 else f"({expr_text(const)})" if not const.is_Integer else expr_text(const)
    return prefix + "".join(parts)


def sum_text(terms: list[sp.Expr]) -> str:
    """Join terms without combining them, e.g. [15, -5] -> '15 - 5'."""
    out = ""
    for i, t in enumerate(terms):
        s = expr_text(t)
        if i == 0:
            out = s
        elif s.startswith("-"):
            out += f" - {s[1:]}"
        else:
            out += f" + {s}"
    return out or "0"
