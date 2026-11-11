"""Exact real solution sets for normalised polynomials of degree <= 2."""

from __future__ import annotations

from collections.abc import Iterable

import sympy as sp

from app.core.exact import exact_equal, numeric_key, sign
from app.core.polynomial_validator import NormalizedPolynomial
from app.core.types import SolutionKind, SolutionSet


def _simplify_root(value: sp.Expr) -> sp.Expr:
    return sp.radsimp(sp.expand(value))


def finite_set(values: Iterable[sp.Expr]) -> SolutionSet:
    """Build a FINITE_SET (deduplicated exactly, sorted by value)."""
    unique: list[sp.Expr] = []
    for v in values:
        if not any(exact_equal(v, u) for u in unique):
            unique.append(v)
    if not unique:
        return SolutionSet.empty()
    unique.sort(key=numeric_key)
    return SolutionSet(SolutionKind.FINITE_SET, tuple(unique))


def solve_polynomial(poly: NormalizedPolynomial) -> SolutionSet:
    c = poly.coefficients
    if poly.degree == -1:
        return SolutionSet.all_real()
    if poly.degree == 0:
        return SolutionSet.empty()
    if poly.degree == 1:
        b, a = c
        return finite_set([_simplify_root(-b / a)])
    cc, b, a = c
    discriminant = sp.expand(b**2 - 4 * a * cc)
    s = sign(discriminant)
    if s < 0:
        return SolutionSet.empty()
    if s == 0:
        return finite_set([_simplify_root(-b / (2 * a))])
    root = sp.sqrt(discriminant)
    return finite_set(
        [_simplify_root((-b + root) / (2 * a)), _simplify_root((-b - root) / (2 * a))]
    )


def union(sets: Iterable[SolutionSet]) -> SolutionSet:
    values: list[sp.Expr] = []
    for s in sets:
        if s.kind is SolutionKind.ALL_REAL:
            return SolutionSet.all_real()
        values.extend(s.values)
    return finite_set(values)
