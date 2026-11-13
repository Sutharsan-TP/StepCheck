"""Names the calculus mistake behind a step the verifier has already proved wrong.

Runs inside the sandbox worker. The idea: re-evaluate the last trusted step
with one common wrong rule (product rule as f'g', chain rule without the inner
derivative, ...). If that wrong result equals the student's step, that rule is
the mistake. If no wrong rule reproduces the step, the category is GENERAL_ERROR
— the verdict never depends on this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import sympy as sp

from app.core.calculus.calc_equivalence import Mode, Verdict, compare, to_student_text
from app.core.calculus.calc_parser import Topic, node_to_sympy, parse_calculus
from app.core.equation_parser import X


class CalcErrorCategory(str, Enum):
    PRODUCT_RULE_ERROR = "PRODUCT_RULE_ERROR"
    QUOTIENT_RULE_ERROR = "QUOTIENT_RULE_ERROR"
    CHAIN_RULE_ERROR = "CHAIN_RULE_ERROR"
    POWER_RULE_ERROR = "POWER_RULE_ERROR"
    TRIG_DERIVATIVE_SIGN_ERROR = "TRIG_DERIVATIVE_SIGN_ERROR"
    INTEGRAL_POWER_RULE_ERROR = "INTEGRAL_POWER_RULE_ERROR"
    INTEGRAL_COEFFICIENT_ERROR = "INTEGRAL_COEFFICIENT_ERROR"
    INTEGRAL_TRIG_SIGN_ERROR = "INTEGRAL_TRIG_SIGN_ERROR"
    LIMITS_SWAPPED = "LIMITS_SWAPPED"
    EVALUATION_ERROR = "EVALUATION_ERROR"
    LHOPITAL_NOT_APPLICABLE = "LHOPITAL_NOT_APPLICABLE"
    LHOPITAL_QUOTIENT_ERROR = "LHOPITAL_QUOTIENT_ERROR"
    SIMPLIFICATION_ERROR = "SIMPLIFICATION_ERROR"
    MISSING_CONSTANT = "MISSING_CONSTANT"
    NOT_FINISHED = "NOT_FINISHED"
    GENERAL_ERROR = "GENERAL_ERROR"


# category: (rule, explanation, hint 1, hint 2). {n} is the step number.
_INFO: dict[CalcErrorCategory, tuple[str, str, str, str]] = {
    CalcErrorCategory.PRODUCT_RULE_ERROR: (
        "Product rule: (fg)' = f'g + fg'",
        "Step {n} differentiates a product by multiplying the two derivatives together.",
        "The derivative of a product is not the product of the derivatives.",
        "Write it as f'g + fg': differentiate one factor at a time and keep the other unchanged.",
    ),
    CalcErrorCategory.QUOTIENT_RULE_ERROR: (
        "Quotient rule: (f/g)' = (f'g - fg')/g^2",
        "Step {n} uses the quotient rule with the two terms of the numerator the wrong way round.",
        "The order matters in the quotient rule's numerator.",
        "Start with the derivative of the top: f'g - fg', all over g^2.",
    ),
    CalcErrorCategory.CHAIN_RULE_ERROR: (
        "Chain rule: d/dx f(g(x)) = f'(g(x)) g'(x)",
        "Step {n} differentiates the outer function but forgets to multiply by the derivative of the inside.",
        "Something is inside the function: what is its derivative?",
        "After differentiating the outer function, multiply by the derivative of the inner expression.",
    ),
    CalcErrorCategory.POWER_RULE_ERROR: (
        "Power rule: d/dx x^n = n x^(n-1)",
        "Step {n} brings the power down but does not reduce the exponent by one.",
        "Check the exponent after differentiating.",
        "Multiply by the old exponent, then subtract 1 from it.",
    ),
    CalcErrorCategory.TRIG_DERIVATIVE_SIGN_ERROR: (
        "d/dx sin(x) = cos(x) and d/dx cos(x) = -sin(x)",
        "Step {n} has the wrong sign on the derivative of a trigonometric function.",
        "Check the sign: one of sin and cos picks up a minus sign when differentiated.",
        "d/dx cos(x) = -sin(x), while d/dx sin(x) = cos(x).",
    ),
    CalcErrorCategory.INTEGRAL_POWER_RULE_ERROR: (
        "Power rule for integrals: ∫ x^n dx = x^(n+1)/(n+1) + C",
        "Step {n} raises the power by one but does not divide by the new power.",
        "Differentiate your answer: do you get the integrand back?",
        "After adding 1 to the exponent, divide by the new exponent.",
    ),
    CalcErrorCategory.INTEGRAL_COEFFICIENT_ERROR: (
        "∫ f(ax + b) dx = F(ax + b)/a + C",
        "Step {n} integrates a function of ax + b without dividing by a.",
        "Differentiate your answer: the chain rule produces an extra factor.",
        "Divide by the coefficient of x inside the function to cancel that factor.",
    ),
    CalcErrorCategory.INTEGRAL_TRIG_SIGN_ERROR: (
        "∫ sin(x) dx = -cos(x) + C and ∫ cos(x) dx = sin(x) + C",
        "Step {n} has the wrong sign on the integral of a trigonometric function.",
        "Differentiate your answer and compare the sign with the integrand.",
        "∫ sin(x) dx = -cos(x) + C, while ∫ cos(x) dx = sin(x) + C.",
    ),
    CalcErrorCategory.LIMITS_SWAPPED: (
        "∫ from a to b f(x) dx = F(b) - F(a)",
        "Step {n} subtracts in the wrong order, which flips the sign of the answer.",
        "Which limit goes first when you subtract?",
        "Evaluate at the upper limit first, then subtract the value at the lower limit.",
    ),
    CalcErrorCategory.EVALUATION_ERROR: (
        "[F(x)] from a to b = F(b) - F(a)",
        "Step {n} makes a mistake while substituting the limits into the antiderivative.",
        "Substitute each limit carefully, one at a time.",
        "Work out F(b) and F(a) separately before subtracting.",
    ),
    CalcErrorCategory.LHOPITAL_NOT_APPLICABLE: (
        "L'Hôpital's rule only applies to 0/0 or ∞/∞",
        "Step {n} uses L'Hôpital's rule on a limit that is not of the form 0/0 or ∞/∞.",
        "Substitute the limit point first: what form do you get?",
        "Only use L'Hôpital's rule when direct substitution gives 0/0 or ∞/∞.",
    ),
    CalcErrorCategory.LHOPITAL_QUOTIENT_ERROR: (
        "L'Hôpital's rule: lim f/g = lim f'/g'",
        "Step {n} differentiates the whole fraction instead of the top and bottom separately.",
        "L'Hôpital's rule is not the quotient rule.",
        "Differentiate the numerator and the denominator separately.",
    ),
    CalcErrorCategory.SIMPLIFICATION_ERROR: (
        "Simplifying must not change the value",
        "Step {n} changes the value of the expression while simplifying.",
        "Re-check the algebra in this step.",
        "Simplify one operation at a time and compare with the line before.",
    ),
    CalcErrorCategory.MISSING_CONSTANT: (
        "Every antiderivative of f is F(x) + C",
        "The antiderivative is right, but an indefinite integral needs + C at the end.",
        "An indefinite integral is a whole family of functions.",
        "Add + C to the final answer.",
    ),
    CalcErrorCategory.NOT_FINISHED: (
        "The final answer contains no d/dx, ∫ or lim",
        "Every step so far is valid, but the last line still has an operation left to carry out.",
        "What is still left to evaluate on the last line?",
        "Carry out the remaining derivative, integral or limit to finish.",
    ),
    CalcErrorCategory.GENERAL_ERROR: (
        "Each step must have the same value as the step before it",
        "Step {n} does not have the same value as the step before it.",
        "Compare this step carefully with the step before it.",
        "Redo this step one operation at a time.",
    ),
}


@dataclass(frozen=True)
class CalcDiagnosis:
    category: str
    expected_rule: str
    explanation: str
    evidence: str
    hints: list[str] = field(default_factory=list)


def describe(category: CalcErrorCategory, step: int, evidence: str = "") -> CalcDiagnosis:
    rule, explanation, hint1, hint2 = _INFO[category]
    return CalcDiagnosis(category.value, rule, explanation.format(n=step), evidence, [hint1, hint2])


# ---------------------------------------------------------- derivatives with one injected mistake


def _d(e: sp.Expr, mistake: CalcErrorCategory | None) -> sp.Expr:
    if not e.has(X):
        return sp.Integer(0)
    if e == X:
        return sp.Integer(1)
    if e.is_Add:
        return sp.Add(*[_d(a, mistake) for a in e.args])
    if e.is_Mul:
        const = sp.Mul(*[a for a in e.args if not a.has(X)])
        factors = [a for a in e.args if a.has(X)]
        if len(factors) == 1:
            return const * _d(factors[0], mistake)
        top = [f for f in factors if not (f.is_Pow and f.exp.is_negative)]
        bottom = [f.base ** (-f.exp) for f in factors if f.is_Pow and f.exp.is_negative]
        if mistake is CalcErrorCategory.QUOTIENT_RULE_ERROR and top and bottom:
            f, g = sp.Mul(*top), sp.Mul(*bottom)
            return const * (f * _d(g, None) - _d(f, None) * g) / g**2
        if mistake is CalcErrorCategory.PRODUCT_RULE_ERROR:
            return const * sp.Mul(*[_d(f, None) for f in factors])
        terms = []
        for i, f in enumerate(factors):
            others = sp.Mul(*[g for j, g in enumerate(factors) if j != i])
            terms.append(_d(f, mistake) * others)
        return const * sp.Add(*terms)
    if e.is_Pow:
        base, exponent = e.args
        if not exponent.has(X):
            inner = _d(base, mistake)
            if mistake is CalcErrorCategory.POWER_RULE_ERROR:
                return exponent * base**exponent * inner
            if mistake is CalcErrorCategory.CHAIN_RULE_ERROR and base != X:
                return exponent * base ** (exponent - 1)
            return exponent * base ** (exponent - 1) * inner
        if not base.has(X):
            if mistake is CalcErrorCategory.CHAIN_RULE_ERROR and exponent != X:
                return e * sp.log(base)
            return e * sp.log(base) * _d(exponent, mistake)
        return sp.diff(e, X)
    if isinstance(e, sp.Function) and len(e.args) == 1:
        g = e.args[0]
        outer = _outer_derivative(e, mistake)
        if outer is None:
            return sp.diff(e, X)
        if mistake is CalcErrorCategory.CHAIN_RULE_ERROR and g != X:
            return outer
        return outer * _d(g, mistake)
    return sp.diff(e, X)


def _outer_derivative(e: sp.Expr, mistake: CalcErrorCategory | None) -> sp.Expr | None:
    g = e.args[0]
    flip = mistake is CalcErrorCategory.TRIG_DERIVATIVE_SIGN_ERROR
    if isinstance(e, sp.sin):
        return -sp.cos(g) if flip else sp.cos(g)
    if isinstance(e, sp.cos):
        return sp.sin(g) if flip else -sp.sin(g)
    if isinstance(e, sp.tan):
        return sp.sec(g) ** 2
    if isinstance(e, sp.exp):
        return sp.exp(g)
    if isinstance(e, sp.log):
        return 1 / g
    return None


def _with_mistake(anchor: sp.Expr, mistake: CalcErrorCategory) -> sp.Expr:
    return anchor.replace(lambda n: isinstance(n, sp.Derivative), lambda n: _d(n.expr, mistake))


# ------------------------------------------------------------ antiderivatives with one injected mistake


def _linear(g: sp.Expr) -> sp.Expr | None:
    """Coefficient a when g = a x + b, otherwise None."""
    a = sp.diff(g, X)
    return a if a != 0 and not a.has(X) else None


def _i(f: sp.Expr, mistake: CalcErrorCategory | None) -> sp.Expr | None:
    if not f.has(X):
        return f * X
    if f.is_Add:
        parts = [_i(a, mistake) for a in f.args]
        return None if any(p is None for p in parts) else sp.Add(*parts)
    if f.is_Mul:
        const = sp.Mul(*[a for a in f.args if not a.has(X)])
        rest = sp.Mul(*[a for a in f.args if a.has(X)])
        if const != 1:
            inner = _i(rest, mistake)
            return None if inner is None else const * inner
        return None
    if f == X:
        return X**2 if mistake is CalcErrorCategory.INTEGRAL_POWER_RULE_ERROR else X**2 / 2
    if f.is_Pow and f.base == X and not f.exp.has(X):
        n = f.exp
        if n == -1:
            return sp.log(sp.Abs(X))
        if mistake is CalcErrorCategory.INTEGRAL_POWER_RULE_ERROR:
            return X ** (n + 1)
        return X ** (n + 1) / (n + 1)
    if isinstance(f, (sp.exp, sp.sin, sp.cos)):
        a = _linear(f.args[0])
        if a is None:
            return None
        divide = 1 if mistake is CalcErrorCategory.INTEGRAL_COEFFICIENT_ERROR else a
        flip = -1 if mistake is CalcErrorCategory.INTEGRAL_TRIG_SIGN_ERROR else 1
        g = f.args[0]
        if isinstance(f, sp.exp):
            return sp.exp(g) / divide
        if isinstance(f, sp.sin):
            return flip * -sp.cos(g) / divide
        return flip * sp.sin(g) / divide
    return None


def _integral_with_mistake(anchor: sp.Expr, mistake: CalcErrorCategory) -> sp.Expr | None:
    failed = False

    def replace(node: sp.Integral) -> sp.Expr:
        nonlocal failed
        antiderivative = _i(node.function, mistake)
        if antiderivative is None:
            failed = True
            return node
        limits = node.limits[0]
        if len(limits) == 3:
            _, lower, upper = limits
            return antiderivative.subs(X, upper) - antiderivative.subs(X, lower)
        return antiderivative

    result = anchor.replace(lambda n: isinstance(n, sp.Integral), replace)
    return None if failed else result


# ----------------------------------------------------------------------------- diagnosis


def _matches(candidate: sp.Expr | None, found: sp.Expr, correct: sp.Expr, mode: Mode) -> bool:
    if candidate is None:
        return False
    if compare(correct, candidate, mode).verdict is not Verdict.UNEQUAL:
        return False  # the "mistake" changes nothing here, so it can't explain the step
    return compare(candidate, found, mode).verdict is Verdict.EQUAL


def _evidence(expected_text: str | None, found_text: str | None, step: int) -> str:
    if expected_text and found_text:
        return f"Step {step} works out to {found_text}, but it should equal {expected_text}."
    return ""


def diagnose_texts(anchor_text: str, found_text: str, topic: str, step: int) -> CalcDiagnosis:
    """Sandbox entry point: why does ``found_text`` (step ``step``) not equal ``anchor_text``?"""
    anchor_statement = parse_calculus(anchor_text)
    anchor = node_to_sympy(anchor_statement.links[-1])
    found = node_to_sympy(parse_calculus(found_text).links[-1])
    topic = Topic(topic)
    mode = Mode.ANTIDERIVATIVE if topic is Topic.INTEGRAL else Mode.VALUE

    correct = anchor.doit(deep=True)
    evidence = ""
    try:
        found_value = found.doit(deep=True)
        if mode is Mode.ANTIDERIVATIVE:
            evidence = _evidence(
                f"an antiderivative of {to_student_text(sp.diff(correct, X))}",
                f"{to_student_text(found_value)}, whose derivative is {to_student_text(sp.simplify(sp.diff(found_value, X)))}",
                step,
            )
        else:
            evidence = _evidence(to_student_text(sp.simplify(correct)), to_student_text(found_value), step)
    except Exception:
        pass

    if anchor.has(sp.Derivative):
        # Quotient before product: for a fraction, f'g' can coincide with a flipped
        # quotient-rule numerator, and the quotient rule is what the student was using.
        for mistake in (
            CalcErrorCategory.QUOTIENT_RULE_ERROR,
            CalcErrorCategory.PRODUCT_RULE_ERROR,
            CalcErrorCategory.CHAIN_RULE_ERROR,
            CalcErrorCategory.POWER_RULE_ERROR,
            CalcErrorCategory.TRIG_DERIVATIVE_SIGN_ERROR,
        ):
            if _matches(_with_mistake(anchor, mistake), found, correct, mode):
                return describe(mistake, step, evidence)
        return describe(CalcErrorCategory.GENERAL_ERROR, step, evidence)

    if topic is Topic.DEFINITE_INTEGRAL and _matches(-correct, found, correct, mode):
        return describe(CalcErrorCategory.LIMITS_SWAPPED, step, evidence)

    if anchor.has(sp.Integral):
        for mistake in (
            CalcErrorCategory.INTEGRAL_POWER_RULE_ERROR,
            CalcErrorCategory.INTEGRAL_COEFFICIENT_ERROR,
            CalcErrorCategory.INTEGRAL_TRIG_SIGN_ERROR,
        ):
            if _matches(_integral_with_mistake(anchor, mistake), found, correct, mode):
                return describe(mistake, step, evidence)
        return describe(CalcErrorCategory.GENERAL_ERROR, step, evidence)

    if isinstance(anchor, sp.Limit):
        category = _lhopital_mistake(anchor, found)
        return describe(category or CalcErrorCategory.GENERAL_ERROR, step, evidence)

    if not anchor_statement.evaluated:
        return describe(CalcErrorCategory.EVALUATION_ERROR, step, evidence)  # [F][a, b] was being evaluated
    return describe(CalcErrorCategory.SIMPLIFICATION_ERROR, step, evidence)


def _lhopital_mistake(anchor: sp.Limit, found: sp.Expr) -> CalcErrorCategory | None:
    if not isinstance(found, sp.Limit):
        return None
    body, point = anchor.args[0], anchor.args[2]
    top, bottom = sp.fraction(sp.together(body))
    if bottom == 1:
        return None
    student_body = found.args[0]
    lhopital = sp.diff(top, X) / sp.diff(bottom, X)
    if compare(lhopital, student_body, Mode.VALUE).verdict is Verdict.EQUAL:
        top_limit, bottom_limit = sp.limit(top, X, point), sp.limit(bottom, X, point)
        indeterminate = (top_limit == 0 and bottom_limit == 0) or (
            top_limit.is_infinite and bottom_limit.is_infinite
        )
        return None if indeterminate else CalcErrorCategory.LHOPITAL_NOT_APPLICABLE
    if compare(sp.diff(body, X), student_body, Mode.VALUE).verdict is Verdict.EQUAL:
        return CalcErrorCategory.LHOPITAL_QUOTIENT_ERROR
    return None
