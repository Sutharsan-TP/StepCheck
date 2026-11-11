"""Normalise an equation to ``LHS - RHS = 0`` and validate it as a real polynomial in x."""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

from app.core.equation_parser import X
from app.core.exact import is_zero
from app.utils.errors import ErrorCode, MathInputError

MAX_SUPPORTED_DEGREE = 2


@dataclass(frozen=True)
class NormalizedPolynomial:
    """Exact coefficients, lowest degree first: c0 + c1*x + c2*x^2 = 0."""

    coefficients: tuple[sp.Expr, ...]

    @property
    def degree(self) -> int:
        """-1 for the zero polynomial."""
        return len(self.coefficients) - 1

    def as_expr(self) -> sp.Expr:
        return sp.Add(*(c * X**i for i, c in enumerate(self.coefficients)))

    def __str__(self) -> str:
        return f"{sp.sstr(self.as_expr())} = 0"


def normalize_equation(lhs: sp.Expr, rhs: sp.Expr) -> NormalizedPolynomial:
    expr = sp.expand(lhs - rhs)
    extra = expr.free_symbols - {X}
    if extra:
        raise MathInputError(
            ErrorCode.MULTIPLE_VARIABLES, "Only single-variable equations in x are supported."
        )
    try:
        poly = sp.Poly(expr, X)
    except sp.PolynomialError as exc:
        raise MathInputError(
            ErrorCode.DEGREE_TOO_HIGH, "The equation is not a polynomial equation in x."
        ) from exc

    coeffs = list(reversed(poly.all_coeffs())) if not poly.is_zero else []
    coeffs = [sp.radsimp(sp.expand(c)) for c in coeffs]
    # Strip leading coefficients that are exactly zero (e.g. cancelled radicals).
    while coeffs and is_zero(coeffs[-1]):
        coeffs.pop()
    for c in coeffs:
        if c.free_symbols:
            raise MathInputError(ErrorCode.MULTIPLE_VARIABLES, "Coefficients must be constants.")
    if len(coeffs) - 1 > MAX_SUPPORTED_DEGREE:
        raise MathInputError(
            ErrorCode.DEGREE_TOO_HIGH,
            f"This equation has degree {len(coeffs) - 1}; only linear and quadratic "
            "equations are supported.",
        )
    return NormalizedPolynomial(tuple(coeffs))
