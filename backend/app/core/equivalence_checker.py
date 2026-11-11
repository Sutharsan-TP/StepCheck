"""Solution-set equivalence between two equations (the only notion of a valid step)."""

from __future__ import annotations

import sympy as sp

from app.core.exact import exact_equal
from app.core.types import Comparison, ReasonCode, SolutionKind, SolutionSet

__all__ = ["compare", "exact_equal", "same_set"]


def _difference(a: tuple[sp.Expr, ...], b: tuple[sp.Expr, ...]) -> tuple[sp.Expr, ...]:
    return tuple(v for v in a if not any(exact_equal(v, w) for w in b))


def same_set(a: SolutionSet, b: SolutionSet) -> bool:
    return compare(a, b).equivalent


def compare(before: SolutionSet, after: SolutionSet) -> Comparison:
    """Compare the solution set of a step with the one it was derived from."""
    if before.kind is SolutionKind.ALL_REAL or after.kind is SolutionKind.ALL_REAL:
        if before.kind is after.kind:
            return Comparison(True, None)
        if after.kind is SolutionKind.ALL_REAL:
            return Comparison(False, ReasonCode.BECAME_IDENTITY)
        return Comparison(False, ReasonCode.LOST_IDENTITY, lost=(), extraneous=after.values)

    lost = _difference(before.values, after.values)
    extraneous = _difference(after.values, before.values)
    if not lost and not extraneous:
        return Comparison(True, None)
    if after.kind is SolutionKind.EMPTY:
        return Comparison(False, ReasonCode.BECAME_CONTRADICTION, lost=lost)
    if lost and extraneous:
        reason = ReasonCode.SOLUTIONS_CHANGED
    elif lost:
        reason = ReasonCode.LOST_SOLUTIONS
    else:
        reason = ReasonCode.EXTRANEOUS_SOLUTIONS
    return Comparison(False, reason, lost=lost, extraneous=extraneous)
