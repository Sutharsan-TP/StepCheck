"""Deterministic generation of the next solution step.

Given a verified step, :func:`next_step` proposes the canonical next
transformation (simplify, isolate, divide, factor, zero-product, quadratic
formula, ...). :func:`generate_continuation` chains these until the solution
set is stated explicitly. Every proposed step is re-parsed and checked with the
same equivalence checker used for student work; nothing unverified escapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp

from app.core.equation_parser import X, node_to_sympy, to_text
from app.core.equivalence_checker import compare
from app.core.exact import is_zero, sign
from app.core.first_error_detector import analyze_step
from app.core.forms import (
    compact,
    is_constant_equation,
    side_texts,
    single_clause,
    uses_plus_minus,
    zero_product_factors,
)
from app.core.rendering import (
    ALL_REAL_TEXT,
    EMPTY_TEXT,
    equation_text,
    expr_text,
    factored_text,
    solved_text,
    value_text,
)
from app.core.types import SolutionKind, StepAnalysis

MAX_GENERATED_STEPS = 10


class Rule(str, Enum):
    SIMPLIFY_SIDES = "SIMPLIFY_SIDES"
    ISOLATE_VARIABLE = "ISOLATE_VARIABLE"
    DIVIDE_BOTH_SIDES = "DIVIDE_BOTH_SIDES"
    MULTIPLY_BOTH_SIDES = "MULTIPLY_BOTH_SIDES"
    STANDARD_FORM = "STANDARD_FORM"
    FACTOR = "FACTOR"
    ZERO_PRODUCT = "ZERO_PRODUCT"
    QUADRATIC_FORMULA = "QUADRATIC_FORMULA"
    SQUARE_ROOT_PROPERTY = "SQUARE_ROOT_PROPERTY"
    NEGATIVE_DISCRIMINANT = "NEGATIVE_DISCRIMINANT"
    NEGATIVE_SQUARE = "NEGATIVE_SQUARE"
    SOLVE_EACH_EQUATION = "SOLVE_EACH_EQUATION"
    STATE_SOLUTIONS = "STATE_SOLUTIONS"
    STATE_SOLUTION_SET = "STATE_SOLUTION_SET"
    CORRECT_ARITHMETIC = "CORRECT_ARITHMETIC"


RULE_NAMES = {
    Rule.SIMPLIFY_SIDES: "Expand brackets and combine like terms",
    Rule.ISOLATE_VARIABLE: "Do the same operation to both sides",
    Rule.DIVIDE_BOTH_SIDES: "Divide both sides by the same nonzero number",
    Rule.MULTIPLY_BOTH_SIDES: "Multiply both sides by the same nonzero number",
    Rule.STANDARD_FORM: "Write the quadratic in standard form ax² + bx + c = 0",
    Rule.FACTOR: "Factor the quadratic",
    Rule.ZERO_PRODUCT: "Zero-product property: if A·B = 0 then A = 0 or B = 0",
    Rule.QUADRATIC_FORMULA: "Quadratic formula x = (−b ± √(b² − 4ac)) / (2a)",
    Rule.SQUARE_ROOT_PROPERTY: "Square-root property: if x² = k > 0 then x = ±√k",
    Rule.NEGATIVE_DISCRIMINANT: "A negative discriminant means no real solutions",
    Rule.NEGATIVE_SQUARE: "A real square cannot be negative",
    Rule.SOLVE_EACH_EQUATION: "Solve each simple equation",
    Rule.STATE_SOLUTIONS: "State every solution",
    Rule.STATE_SOLUTION_SET: "Interpret an identity or contradiction",
    Rule.CORRECT_ARITHMETIC: "Simplify correctly",
}


@dataclass(frozen=True)
class GeneratedStep:
    text: str
    rule: Rule
    explanation: str
    hint: str  # names the idea without revealing the step
    hint_detail: str  # more specific, still without the resulting equation


class CorrectionUnsafe(Exception):
    """A generated step failed verification; the caller must return NEEDS_REVIEW."""


def _num(value: sp.Expr) -> str:
    return expr_text(value)


def _linear_parts(expr: sp.Expr) -> tuple[sp.Expr, sp.Expr]:
    expr = sp.expand(expr)
    return expr.coeff(X, 1), expr.subs(X, 0)


def _move_description(a2: sp.Expr, b1: sp.Expr) -> str:
    moves = []
    if not is_zero(a2):
        term = _num(a2 * X)
        moves.append(f"subtract {term} from both sides" if sign(a2) > 0 else f"add {_num(-a2 * X)} to both sides")
    if not is_zero(b1):
        moves.append(f"subtract {_num(b1)} from both sides" if sign(b1) > 0 else f"add {_num(-b1)} to both sides")
    text = " and ".join(moves)
    return text[0].upper() + text[1:] + ", then combine like terms." if text else "Combine like terms."


def _literal_step(current: StepAnalysis) -> GeneratedStep:
    if current.solution_set.kind is SolutionKind.ALL_REAL:
        return GeneratedStep(
            ALL_REAL_TEXT,
            Rule.STATE_SOLUTION_SET,
            "The x-terms cancel and leave a statement that is always true, so every real number is a solution.",
            "Is the statement true for every value of x, or for none?",
            "A true statement with no x left means the equation holds for all x.",
        )
    return GeneratedStep(
        EMPTY_TEXT,
        Rule.STATE_SOLUTION_SET,
        "The x-terms cancel and leave a statement that is never true, so there is no solution.",
        "Is the statement true for every value of x, or for none?",
        "A false statement with no x left means no value of x works.",
    )


def _quadratic_step(current: StepAnalysis, lhs: sp.Expr, rhs: sp.Expr) -> GeneratedStep:
    poly = sp.expand(lhs - rhs)
    a, b, c = poly.coeff(X, 2), poly.coeff(X, 1), poly.subs(X, 0)
    if sign(a) < 0:
        poly, a, b, c = -poly, -a, -b, -c
    current_text = compact(current.raw)

    if is_zero(b):
        k = sp.radsimp(-c / a)
        isolated = f"x^2 = {_num(k)}"
        if compact(isolated) != current_text and not (
            single_clause(current.statement) and compact(side_texts(single_clause(current.statement))[0]) == "x^2"
        ):
            return GeneratedStep(
                isolated,
                Rule.ISOLATE_VARIABLE,
                "Get x² on its own: move the constant term to the other side"
                + ("" if a == 1 else f" and divide both sides by {_num(a)}") + ".",
                "Get x² by itself on one side.",
                "Move the number term across, then divide by the coefficient of x².",
            )
        s = sign(k)
        if s < 0:
            return GeneratedStep(
                EMPTY_TEXT,
                Rule.NEGATIVE_SQUARE,
                f"x² = {_num(k)} is impossible for real x, because a square is never negative.",
                "Can the square of a real number be negative?",
                "x² is always zero or positive.",
            )
        if s == 0:
            return GeneratedStep("x = 0", Rule.SQUARE_ROOT_PROPERTY, "Only 0 squares to 0.",
                                 "Which number squares to 0?", "x² = 0 has exactly one solution.")
        root = sp.sqrt(k)
        return GeneratedStep(
            f"x = ±{_num(root)}",
            Rule.SQUARE_ROOT_PROPERTY,
            f"Take the square root of both sides. A positive number has two square roots, so x = ±√{_num(k)}.",
            "Undo the square by taking a square root.",
            "Remember there are two square roots: one positive and one negative.",
        )

    standard = f"{_num(poly)} = 0"
    if compact(standard) != current_text:
        return GeneratedStep(
            standard,
            Rule.STANDARD_FORM,
            "Expand and move every term to the left-hand side, so the equation has the form ax² + bx + c = 0.",
            "Get all the terms on one side, with 0 on the other.",
            "Expand any brackets, then subtract the right-hand side from both sides.",
        )

    discriminant = sp.expand(b**2 - 4 * a * c)
    d_sign = sign(discriminant)
    if d_sign < 0:
        return GeneratedStep(
            EMPTY_TEXT,
            Rule.NEGATIVE_DISCRIMINANT,
            f"The discriminant b² − 4ac = ({_num(b)})² − 4·({_num(a)})·({_num(c)}) = {_num(discriminant)} "
            "is negative, so there are no real solutions.",
            "Check the discriminant b² − 4ac before solving.",
            f"Here a = {_num(a)}, b = {_num(b)}, c = {_num(c)}. What is the sign of b² − 4ac?",
        )

    factored = factored_text(poly)
    if factored:
        product = sp.expand(a * c)
        detail = (
            f"Find two numbers that multiply to {_num(c)} and add to {_num(b)}."
            if a == 1
            else f"Find two numbers that multiply to a·c = {_num(product)} and add to {_num(b)}."
        )
        return GeneratedStep(
            f"{factored} = 0",
            Rule.FACTOR,
            f"Factor the left-hand side: {factored} multiplies back to {_num(poly)}.",
            "Try factoring the quadratic.",
            detail,
        )

    return quadratic_formula_step(a, b, c)


def quadratic_formula_step(a: sp.Expr, b: sp.Expr, c: sp.Expr) -> GeneratedStep:
    """x = (-b ± sqrt(b^2 - 4ac))/(2a) with the numbers substituted."""
    discriminant = sp.expand(b**2 - 4 * a * c)
    d_sign = sign(discriminant)
    if d_sign < 0:
        return GeneratedStep(
            EMPTY_TEXT,
            Rule.NEGATIVE_DISCRIMINANT,
            f"The discriminant b² − 4ac = {_num(discriminant)} is negative, so there are no real solutions.",
            "Check the discriminant b² − 4ac before solving.",
            f"Here a = {_num(a)}, b = {_num(b)}, c = {_num(c)}. What is the sign of b² − 4ac?",
        )
    neg_b, den = -b, 2 * a
    if d_sign == 0:
        return GeneratedStep(
            f"x = {_num(sp.radsimp(neg_b / den))}",
            Rule.QUADRATIC_FORMULA,
            f"The discriminant b² − 4ac is 0, so the quadratic formula gives one repeated root x = −b / (2a).",
            "Check the discriminant b² − 4ac.",
            f"Here a = {_num(a)}, b = {_num(b)}, c = {_num(c)}. A zero discriminant gives a single root.",
        )
    root = f"sqrt({_num(discriminant)})"
    numerator = f"{_num(neg_b)} ± {root}" if not is_zero(neg_b) else f"±{root}"
    if den == 1:
        text = f"x = {numerator}"
    else:
        den_text = _num(den) if den.is_Integer and den > 0 else f"({_num(den)})"
        text = f"x = ({numerator})/{den_text}"
    return GeneratedStep(
        text,
        Rule.QUADRATIC_FORMULA,
        f"Use the quadratic formula with a = {_num(a)}, b = {_num(b)}, c = {_num(c)}; "
        f"the discriminant is b² − 4ac = {_num(discriminant)}.",
        "Use the quadratic formula.",
        f"Substitute a = {_num(a)}, b = {_num(b)}, c = {_num(c)} into x = (−b ± √(b² − 4ac)) / (2a).",
    )


def _linear_step(current: StepAnalysis, lhs: sp.Expr, rhs: sp.Expr) -> GeneratedStep | None:
    clause = single_clause(current.statement)
    lhs_e, rhs_e = sp.expand(lhs), sp.expand(rhs)
    l_text, r_text = side_texts(clause)
    simplified = equation_text(lhs_e, rhs_e)
    if (compact(l_text) != compact(expr_text(lhs_e)) or compact(r_text) != compact(expr_text(rhs_e))) and compact(
        simplified
    ) != compact(current.raw):
        return GeneratedStep(
            simplified,
            Rule.SIMPLIFY_SIDES,
            "Simplify each side: expand any brackets and combine like terms.",
            "Simplify each side before moving terms.",
            "Expand brackets (multiply every term inside) and add up like terms.",
        )

    q1, q2 = lhs_e.coeff(X, 2), rhs_e.coeff(X, 2)
    if not is_zero(q2) or not is_zero(q1):  # x² terms that cancel between the sides
        lhs_x, rhs_x = sp.expand(lhs_e - q2 * X**2), sp.expand(rhs_e - q2 * X**2)
        return GeneratedStep(
            equation_text(lhs_x, rhs_x),
            Rule.ISOLATE_VARIABLE,
            f"Subtract {_num(q2 * X**2)} from both sides; the x² terms cancel.",
            "Look for terms that appear on both sides.",
            "Subtracting the same x² term from both sides removes it.",
        )
    a1, b1 = _linear_parts(lhs_e)
    a2, b2 = _linear_parts(rhs_e)
    if is_zero(a1):  # keep x on the left
        a1, b1, a2, b2 = a2, b2, a1, b1
        if is_zero(b1) and is_zero(a2):
            return GeneratedStep(
                f"{_num(a1 * X)} = {_num(b2)}",
                Rule.ISOLATE_VARIABLE,
                "Swap the two sides so that x is on the left.",
                "Write the side containing x first.",
                "a = b means the same as b = a.",
            )
    if not is_zero(a2) or not is_zero(b1):
        a, b = sp.expand(a1 - a2), sp.expand(b2 - b1)
        if is_zero(a):
            return None  # constant equation: handled by caller
        return GeneratedStep(
            f"{_num(a * X)} = {_num(b)}",
            Rule.ISOLATE_VARIABLE,
            _move_description(a2, b1),
            "Collect the x-terms on one side and the numbers on the other.",
            "Whatever you add or subtract on one side, do the same on the other side.",
        )
    if a1 == 1:
        return None
    value = sp.radsimp(b2 / a1)
    if a1 == -1:
        return GeneratedStep(
            f"x = {_num(value)}",
            Rule.MULTIPLY_BOTH_SIDES,
            "Multiply both sides by −1.",
            "Make the coefficient of x equal to 1.",
            "Multiply both sides by −1 to change the sign of x.",
        )
    return GeneratedStep(
        f"x = {_num(value)}",
        Rule.DIVIDE_BOTH_SIDES,
        f"Divide both sides by {_num(a1)}.",
        "Make the coefficient of x equal to 1.",
        f"What number is multiplying x? Divide both sides by it.",
    )


def _is_plain_value(clause) -> bool:
    """True for 'x = 4', 'x = -3', 'x = 12.5', 'x = (5 - sqrt(13))/2'; False for 'x = 20/5'."""
    lhs, rhs = clause.lhs.unwrap(), clause.rhs.unwrap()
    value_node = rhs if lhs.kind == "var" else lhs if rhs.kind == "var" else None
    if value_node is None:
        return False  # constant equation such as 0 = 1
    if value_node.kind == "num" or (value_node.kind == "neg" and value_node.children[0].kind == "num"):
        return True
    value = node_to_sympy(value_node)
    written = compact(to_text(value_node))
    return written in (compact(expr_text(value)), compact(value_text(value)))


def next_step(current: StepAnalysis) -> GeneratedStep | None:
    """The canonical next step after a verified step, or None when it is final."""
    stmt = current.statement
    target = current.solution_set
    if stmt is None or stmt.literal is not None:
        return None
    if is_constant_equation(stmt):
        return _literal_step(current)
    if uses_plus_minus(stmt):
        return GeneratedStep(
            solved_text(target),
            Rule.STATE_SOLUTIONS,
            "Write the two solutions separately (one with +, one with −) and simplify.",
            "Split the ± into two separate answers.",
            "Evaluate once with + and once with −.",
        )
    if stmt.solved_form:
        # 'x = 20/5' or 'x = 2 or 0 = 1' still need tidying into a plain answer.
        if all(_is_plain_value(c) for c in stmt.clauses):
            return None
        return GeneratedStep(
            solved_text(target),
            Rule.STATE_SOLUTIONS,
            "Simplify the answer.",
            "Can the answer be simplified further?",
            "Work out the value on the right-hand side.",
        )
    if len(stmt.clauses) > 1:
        return GeneratedStep(
            solved_text(target),
            Rule.SOLVE_EACH_EQUATION,
            "Solve each of the simpler equations; together their solutions solve the original equation.",
            "Solve each equation separately.",
            "Isolate x in each equation.",
        )
    factors = zero_product_factors(stmt)
    if factors:
        text = " or ".join(f"{expr_text(f)} = 0" for f in factors)
        many = len(factors) > 1
        return GeneratedStep(
            text,
            Rule.ZERO_PRODUCT,
            "A product equals zero exactly when one of its factors is zero, so set "
            + ("each factor equal to zero." if many else "the repeated factor equal to zero."),
            "When is a product equal to zero?",
            "Set every factor equal to zero. Don't leave any factor out.",
        )
    lhs, rhs = current.equations[0]
    degree = sp.degree(sp.expand(lhs - rhs), X)
    if degree == 2:
        return _quadratic_step(current, lhs, rhs)
    if degree == 1:
        return _linear_step(current, lhs, rhs)
    # Constant: the x-terms cancel. Show the remaining numbers.
    lhs_e, rhs_e = sp.expand(lhs), sp.expand(rhs)
    text = equation_text(lhs_e.subs(X, 0), rhs_e.subs(X, 0))
    if compact(text) == compact(current.raw):
        return _literal_step(current)
    return GeneratedStep(
        text,
        Rule.ISOLATE_VARIABLE,
        "Subtract the x-terms from both sides; they cancel completely.",
        "What happens when you collect the x-terms on one side?",
        "Subtract the same x-term from both sides.",
    )


def verify_generated(previous: StepAnalysis, step: GeneratedStep) -> StepAnalysis:
    """Re-parse and re-check a generated step exactly like student work."""
    analysis = analyze_step(previous.index + 1, step.text)
    if not analysis.ok:
        raise CorrectionUnsafe(f"Generated step {step.text!r} could not be parsed: {analysis.error.message}")
    if not compare(previous.solution_set, analysis.solution_set).equivalent:
        raise CorrectionUnsafe(f"Generated step {step.text!r} is not equivalent to {previous.raw!r}")
    return analysis


def generate_continuation(start: StepAnalysis) -> list[tuple[GeneratedStep, StepAnalysis]]:
    """Verified steps from ``start`` until the solution set is stated explicitly."""
    steps: list[tuple[GeneratedStep, StepAnalysis]] = []
    current = start
    seen = {compact(start.raw)}
    while True:
        step = next_step(current)
        if step is None:
            return steps
        if compact(step.text) in seen or len(steps) >= MAX_GENERATED_STEPS:
            raise CorrectionUnsafe("The step generator stopped making progress.")
        current = verify_generated(current, step)
        seen.add(compact(step.text))
        steps.append((step, current))
