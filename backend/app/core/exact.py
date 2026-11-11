"""Exact zero / sign tests for the real algebraic constants the parser can produce.

Every constant reachable through the grammar is built from rationals with
+, -, *, /, integer powers and square roots of non-negative constants, so it is
a real algebraic number. For such numbers ``minimal_polynomial`` gives an exact
zero test; high-precision numerics are only used to short-circuit the obvious
non-zero case and to read the sign of a number already known to be non-zero.
"""

from __future__ import annotations

import sympy as sp

from app.utils.errors import ErrorCode, MathInputError

_PRECISION = 50
_NUMERIC_ZERO_THRESHOLD = sp.Float("1e-40", _PRECISION)
_t = sp.Symbol("t")


def is_zero(value: sp.Expr) -> bool:
    d = sp.radsimp(sp.expand(value))
    if d == 0:
        return True
    if d.is_Rational:
        return False
    if d.free_symbols:
        raise MathInputError(
            ErrorCode.VERIFICATION_INDETERMINATE, "Expected a constant but found a variable."
        )
    approx = sp.N(d, _PRECISION)
    if not approx.is_real:
        raise MathInputError(ErrorCode.COMPLEX_VALUE, "Complex values are not supported.")
    if abs(approx) > _NUMERIC_ZERO_THRESHOLD:
        return False
    try:
        return sp.minimal_polynomial(d, _t) == _t
    except Exception as exc:  # NotAlgebraic or internal failure: never guess
        raise MathInputError(
            ErrorCode.VERIFICATION_INDETERMINATE,
            "Could not decide exactly whether a value is zero.",
        ) from exc


def sign(value: sp.Expr) -> int:
    """Exact sign (-1, 0, 1) of a real algebraic constant."""
    if is_zero(value):
        return 0
    approx = sp.N(value, _PRECISION)
    return 1 if approx > 0 else -1


def exact_equal(a: sp.Expr, b: sp.Expr) -> bool:
    return is_zero(a - b)


def numeric_key(value: sp.Expr) -> float:
    """Sort key for real constants (ordering only; never used for equality)."""
    return float(sp.N(value, 30))
