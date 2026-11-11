"""Structural forms of a parsed step (factored, ±-formula, single equation, ...).

These only describe how the student *wrote* a step; they never decide whether
it is correct (that is the equivalence checker's job).
"""

from __future__ import annotations

import sympy as sp

from app.core.equation_parser import (
    X,
    Clause,
    Node,
    ParsedStatement,
    has_plus_minus,
    node_to_sympy,
    to_text,
)
from app.core.exact import is_zero, numeric_key


def single_clause(statement: ParsedStatement | None) -> Clause | None:
    if statement is None or statement.literal is not None or len(statement.clauses) != 1:
        return None
    return statement.clauses[0]


def uses_plus_minus(statement: ParsedStatement | None) -> bool:
    if statement is None or statement.literal is not None:
        return False
    return any(has_plus_minus(c.lhs) or has_plus_minus(c.rhs) for c in statement.clauses)


def is_constant_equation(statement: ParsedStatement | None) -> bool:
    clause = single_clause(statement)
    return clause is not None and not clause.lhs.contains_var() and not clause.rhs.contains_var()


def _factor_nodes(node: Node) -> list[Node]:
    node = node.unwrap()
    if node.kind == "imul":
        return [f for child in node.children for f in _factor_nodes(child)]
    if node.kind == "mul":
        return _factor_nodes(node.children[0]) + _factor_nodes(node.children[1])
    if node.kind == "neg":
        return _factor_nodes(node.children[0])
    return [node]


def zero_product_factors(statement: ParsedStatement | None) -> list[sp.Expr] | None:
    """Distinct non-constant linear factors if the step reads 'product = 0', else None."""
    clause = single_clause(statement)
    if clause is None or has_plus_minus(clause.lhs) or has_plus_minus(clause.rhs):
        return None
    for prod, zero in ((clause.lhs, clause.rhs), (clause.rhs, clause.lhs)):
        if zero.contains_var() or not is_zero(node_to_sympy(zero)):
            continue
        factors: list[tuple[sp.Expr, sp.Expr]] = []  # (factor, its root)
        count = 0
        for f in _factor_nodes(prod):
            if not f.contains_var():
                continue
            base = f.children[0].unwrap() if f.kind == "pow" else f
            expr = sp.expand(node_to_sympy(base))
            if sp.degree(expr, X) != 1:
                return None
            count += int(f.value) if f.kind == "pow" else 1
            root = -expr.subs(X, 0) / expr.coeff(X, 1)
            if not any(is_zero(root - r) for _, r in factors):
                factors.append((expr, root))
        if count >= 2:
            factors.sort(key=lambda fr: numeric_key(fr[1]))
            return [f for f, _ in factors]
    return None


def side_texts(clause: Clause) -> tuple[str, str]:
    return to_text(clause.lhs), to_text(clause.rhs)


def compact(text: str) -> str:
    return text.replace(" ", "").replace("*", "")
