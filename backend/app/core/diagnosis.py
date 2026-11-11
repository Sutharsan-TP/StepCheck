"""Deterministic classification of an invalid step into a teachable error category.

The verdict (invalid) always comes from the equivalence checker; this module
only describes *what kind* of mistake the structure of the step suggests, so
hints and explanations can target it. When no pattern fits, the category is
GENERAL_ERROR — never a guess dressed up as certainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp

from app.core.equation_parser import X, Node
from app.core.exact import is_zero, sign
from app.core.forms import (
    right_side_scale,
    side_texts,
    single_clause,
    uses_plus_minus,
    zero_product_factors,
)
from app.core.rendering import expr_text
from app.core.types import Comparison, SolutionKind, StepAnalysis


class ErrorCategory(str, Enum):
    ADDITION_SUBTRACTION_ERROR = "ADDITION_SUBTRACTION_ERROR"
    MULTIPLICATION_DIVISION_ERROR = "MULTIPLICATION_DIVISION_ERROR"
    EXPANSION_ERROR = "EXPANSION_ERROR"
    COMBINING_LIKE_TERMS_ERROR = "COMBINING_LIKE_TERMS_ERROR"
    SIGN_ERROR_MOVING_TERM = "SIGN_ERROR_MOVING_TERM"
    INCONSISTENT_OPERATION = "INCONSISTENT_OPERATION"
    FACTORIZATION_ERROR = "FACTORIZATION_ERROR"
    QUADRATIC_FORMULA_ERROR = "QUADRATIC_FORMULA_ERROR"
    LOST_FACTOR = "LOST_FACTOR"
    DIVIDED_BY_VARIABLE = "DIVIDED_BY_VARIABLE"
    MISSING_NEGATIVE_ROOT = "MISSING_NEGATIVE_ROOT"
    INCOMPLETE_FINAL_ANSWER = "INCOMPLETE_FINAL_ANSWER"
    EXTRANEOUS_SOLUTIONS = "EXTRANEOUS_SOLUTIONS"
    INCORRECT_FINAL_ANSWER = "INCORRECT_FINAL_ANSWER"
    GENERAL_ERROR = "GENERAL_ERROR"


_INFO: dict[ErrorCategory, tuple[str, str, str, str]] = {
    # category: (expected rule, explanation, hint 1, hint 2)  -- {side}/{focus}/{n} are filled in
    ErrorCategory.ADDITION_SUBTRACTION_ERROR: (
        "Simplifying a side must not change its value",
        "Step {n} changes the value of the {side} side: {focus} was not simplified correctly.",
        "Re-check the arithmetic on the {side} side.",
        "Work out {focus} again, one operation at a time.",
    ),
    ErrorCategory.MULTIPLICATION_DIVISION_ERROR: (
        "Multiply or divide the whole of both sides by the same nonzero number",
        "Step {n} contains a multiplication or division mistake.",
        "Check your multiplication and division in this step.",
        "{detail}",
    ),
    ErrorCategory.EXPANSION_ERROR: (
        "Distributive property: a(b + c) = ab + ac",
        "Step {n} expands the brackets in {focus} incorrectly.",
        "Check how you expanded the brackets.",
        "In {focus}, multiply the number outside the brackets by every term inside.",
    ),
    ErrorCategory.COMBINING_LIKE_TERMS_ERROR: (
        "Combine like terms: ax + bx = (a + b)x",
        "Step {n} combines the like terms in {focus} incorrectly.",
        "Check how you combined the x-terms.",
        "In {focus}, add the coefficients of the x-terms (and separately the numbers).",
    ),
    ErrorCategory.SIGN_ERROR_MOVING_TERM: (
        "Do the same operation to both sides of the equation",
        "Step {n} moves a term to the other side but changes its sign incorrectly.",
        "Look at the signs of the terms you moved across the equals sign.",
        "If you subtract a term from one side, you must also subtract it (not add it) on the other side.",
    ),
    ErrorCategory.INCONSISTENT_OPERATION: (
        "Do the same operation to both sides of the equation",
        "In step {n} the two sides were not changed in the same way.",
        "Did you do exactly the same thing to both sides?",
        "Compare what you added or subtracted on the left with what you did on the right.",
    ),
    ErrorCategory.FACTORIZATION_ERROR: (
        "A factorization must multiply back to the original expression",
        "The factorization in step {n} does not multiply back to the quadratic.",
        "Expand your factors and compare them with the quadratic.",
        "{detail}",
    ),
    ErrorCategory.QUADRATIC_FORMULA_ERROR: (
        "Quadratic formula: x = (−b ± √(b² − 4ac)) / (2a)",
        "The quadratic formula in step {n} was not applied correctly.",
        "Check the values you substituted into the quadratic formula.",
        "{detail}",
    ),
    ErrorCategory.LOST_FACTOR: (
        "Zero-product property: if A·B = 0 then A = 0 or B = 0",
        "Step {n} keeps only part of the product, so a solution is lost.",
        "A product is zero when any one of its factors is zero.",
        "Set every factor equal to zero. How many factors are there?",
    ),
    ErrorCategory.DIVIDED_BY_VARIABLE: (
        "Don't divide by an expression that could be zero; factor instead",
        "Step {n} divides by an expression containing x, which loses the solution where it equals zero.",
        "Dividing by x assumes x ≠ 0. What happens if x = 0?",
        "Move every term to one side and factor out x instead of dividing by it.",
    ),
    ErrorCategory.MISSING_NEGATIVE_ROOT: (
        "Square-root property: if x² = k > 0 then x = √k or x = −√k",
        "Step {n} keeps only one square root, so a solution is lost.",
        "A positive number has two square roots.",
        "Which other number has the same square?",
    ),
    ErrorCategory.INCOMPLETE_FINAL_ANSWER: (
        "State every solution of the equation",
        "The answer in step {n} leaves out at least one solution.",
        "Your answer is missing a solution.",
        "The equation has {count} — find them all.",
    ),
    ErrorCategory.EXTRANEOUS_SOLUTIONS: (
        "Each step must not add solutions the previous step did not have",
        "Step {n} introduces a value that does not satisfy the previous equation.",
        "Does every value that solves your new step also solve the previous one?",
        "Squaring both sides, or multiplying by an expression with x, can add extra solutions.",
    ),
    ErrorCategory.INCORRECT_FINAL_ANSWER: (
        "The answer must satisfy the previous equation",
        "The value in step {n} does not satisfy the previous step.",
        "Substitute your answer into the previous step and check it.",
        "Redo the last calculation carefully.",
    ),
    ErrorCategory.GENERAL_ERROR: (
        "Each step must have exactly the same solutions as the step before",
        "Step {n} changes the solutions of the equation.",
        "Compare this step with the previous one: what operation did you intend?",
        "Apply that operation to every term on both sides.",
    ),
}


@dataclass(frozen=True)
class Diagnosis:
    category: ErrorCategory
    expected_rule: str
    explanation: str  # never reveals the corrected step or solutions
    evidence: str  # concrete solution sets (reveals answers)
    hints: tuple[str, str]
    side: str | None = None


def _quadratic_coefficients(step: StepAnalysis):
    if len(step.equations) != 1:
        return None
    lhs, rhs = step.equations[0]
    poly = sp.expand(lhs - rhs)
    if sp.degree(poly, X) != 2:
        return None
    a, b, c = poly.coeff(X, 2), poly.coeff(X, 1), poly.subs(X, 0)
    if sign(a) < 0:
        a, b, c = -a, -b, -c
    return a, b, c


def _additive_terms(node: Node) -> list[Node]:
    node = node.unwrap()
    if node.kind in ("add", "sub"):
        return _additive_terms(node.children[0]) + _additive_terms(node.children[1])
    return [node]


def _has(node: Node, kinds: set[str]) -> bool:
    return node.kind in kinds or any(_has(c, kinds) for c in node.children)


def _has_bracket_product(node: Node) -> bool:
    if node.kind in ("imul", "mul"):
        for child in node.children:
            inner = child.unwrap()
            if child.kind == "paren" and inner.kind in ("add", "sub") and inner.contains_var():
                return True
    return any(_has_bracket_product(c) for c in node.children)


def _classify_side(node: Node) -> ErrorCategory:
    if _has_bracket_product(node):
        return ErrorCategory.EXPANSION_ERROR
    if sum(1 for t in _additive_terms(node) if t.contains_var()) >= 2:
        return ErrorCategory.COMBINING_LIKE_TERMS_ERROR
    if _has(node, {"div"}) or (_has(node, {"mul", "imul", "pow"}) and not node.contains_var()):
        return ErrorCategory.MULTIPLICATION_DIVISION_ERROR
    return ErrorCategory.ADDITION_SUBTRACTION_ERROR


def _coefficients(expr: sp.Expr) -> list[sp.Expr]:
    expr = sp.expand(expr)
    return [expr.coeff(X, k) if k else expr.subs(X, 0) for k in range(3)]


def _evidence(n: int, prev: StepAnalysis, cur: StepAnalysis, cmp: Comparison) -> str:
    parts = [
        f"Step {n - 1} has solution set {prev.solution_set.describe()}, "
        f"but step {n} has {cur.solution_set.describe()}."
    ]
    if cmp.lost:
        parts.append("Lost: " + ", ".join(f"x = {expr_text(v)}" for v in cmp.lost) + ".")
    if cmp.extraneous:
        parts.append("Added: " + ", ".join(f"x = {expr_text(v)}" for v in cmp.extraneous) + ".")
    return " ".join(parts)


def diagnose(prev: StepAnalysis, cur: StepAnalysis, cmp: Comparison, step_number: int) -> Diagnosis:
    category, side, focus, detail = _categorise(prev, cur, cmp)
    rule, explanation, hint1, hint2 = _INFO[category]
    count = len(prev.solution_set.values)
    fields = dict(
        n=step_number,
        side=f"{side}-hand" if side else "",
        focus=focus or "this step",
        detail=detail or hint1,
        count=f"{count} solution{'s' if count != 1 else ''}",
    )
    return Diagnosis(
        category=category,
        expected_rule=rule,
        explanation=explanation.format(**fields),
        evidence=_evidence(step_number, prev, cur, cmp),
        hints=(hint1.format(**fields), hint2.format(**fields)),
        side=side,
    )


def _categorise(prev: StepAnalysis, cur: StepAnalysis, cmp: Comparison):
    """Returns (category, side, focus text, detail text)."""
    quad = _quadratic_coefficients(prev)
    prev_factors = zero_product_factors(prev.statement)

    if cmp.lost and not cmp.extraneous and cur.solution_set.kind is not SolutionKind.ALL_REAL:
        if prev_factors:
            return ErrorCategory.LOST_FACTOR, None, None, None
        if quad and is_zero(quad[2]) and any(is_zero(v) for v in cmp.lost):
            return ErrorCategory.DIVIDED_BY_VARIABLE, None, None, None
        if (
            quad
            and is_zero(quad[1])
            and len(cmp.lost) == 1
            and any(is_zero(v + cmp.lost[0]) for v in cur.solution_set.values)
        ):
            return ErrorCategory.MISSING_NEGATIVE_ROOT, None, None, None
        if cur.solved_form:
            return ErrorCategory.INCOMPLETE_FINAL_ANSWER, None, None, None

    if quad and zero_product_factors(cur.statement):
        a, b, c = quad
        detail = (
            f"Find two numbers that multiply to {expr_text(c)} and add to {expr_text(b)}."
            if a == 1
            else f"Look for two numbers that multiply to a·c = {expr_text(sp.expand(a * c))} and add to {expr_text(b)}."
        )
        return ErrorCategory.FACTORIZATION_ERROR, None, None, detail

    if quad and uses_plus_minus(cur.statement):
        a, b, c = quad
        detail = (
            f"Here a = {expr_text(a)}, b = {expr_text(b)}, c = {expr_text(c)}. "
            "Check the sign of −b and recompute b² − 4ac."
        )
        return ErrorCategory.QUADRATIC_FORMULA_ERROR, None, None, detail

    if quad and cur.solved_form:
        if cmp.lost and not cmp.extraneous:
            return ErrorCategory.INCOMPLETE_FINAL_ANSWER, None, None, None
        return ErrorCategory.INCORRECT_FINAL_ANSWER, None, None, None

    p_clause, c_clause = single_clause(prev.statement), single_clause(cur.statement)
    if (
        p_clause
        and c_clause
        and len(prev.equations) == 1
        and len(cur.equations) == 1
        and not uses_plus_minus(prev.statement)
    ):
        (lp, rp), (lc, rc) = prev.equations[0], cur.equations[0]
        d_left, d_right = sp.expand(lc - lp), sp.expand(rc - rp)
        p_left_text, p_right_text = side_texts(p_clause)
        if d_left == 0 and d_right != 0:
            return _classify_side(p_clause.rhs), "right", p_right_text, None
        if d_right == 0 and d_left != 0:
            return _classify_side(p_clause.lhs), "left", p_left_text, None
        if d_left != 0 and d_right != 0:
            ratio = sp.cancel(sp.expand(lc) / sp.expand(lp)) if sp.expand(lp) != 0 else None
            if ratio is not None and not ratio.has(X) and not is_zero(ratio):
                verb = "multiplied" if abs(sp.N(ratio)) >= 1 else "divided"
                factor = expr_text(ratio if verb == "multiplied" else 1 / ratio)
                detail = f"You {verb} the left-hand side by {factor}; do exactly the same to the right-hand side."
                return ErrorCategory.MULTIPLICATION_DIVISION_ERROR, None, None, detail
            ratio = right_side_scale(lp, lc, rp, rc)
            if ratio is not None:
                verb, base = ("multiplied", "multiply") if abs(sp.N(ratio)) >= 1 else ("divided", "divide")
                factor = expr_text(ratio if verb == "multiplied" else 1 / ratio)
                detail = (
                    f"You {verb} the right-hand side by {factor}; {base} every term on the "
                    "left-hand side by the same number."
                )
                return ErrorCategory.MULTIPLICATION_DIVISION_ERROR, None, None, detail
            cl, cr = _coefficients(d_left), _coefficients(d_right)
            if any(not is_zero(a) and is_zero(a + b) for a, b in zip(cl, cr)):
                return ErrorCategory.SIGN_ERROR_MOVING_TERM, None, None, None
            return ErrorCategory.INCONSISTENT_OPERATION, None, None, None

    if cmp.extraneous and not cmp.lost and not cur.solved_form:
        return ErrorCategory.EXTRANEOUS_SOLUTIONS, None, None, None
    if cur.solved_form:
        if cmp.lost and not cmp.extraneous:
            return ErrorCategory.INCOMPLETE_FINAL_ANSWER, None, None, None
        return ErrorCategory.INCORRECT_FINAL_ANSWER, None, None, None
    return ErrorCategory.GENERAL_ERROR, None, None, None
