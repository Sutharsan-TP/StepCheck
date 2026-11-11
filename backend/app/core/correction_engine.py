"""Correction engine: repair the first invalid step and complete the solution.

Safety contract: every step this module returns has been re-parsed and checked
with the same equivalence checker as student work, and a FULL correction is
only returned if the entire corrected solution re-verifies as CORRECT with a
complete final answer. Anything else becomes NEEDS_REVIEW.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import sympy as sp

from app.core.diagnosis import Diagnosis, ErrorCategory, diagnose
from app.core.equation_parser import X, to_text
from app.core.equivalence_checker import compare
from app.core.exact import is_zero, sign
from app.core.first_error_detector import analyze_step, is_complete_answer, verify_steps
from app.core.forms import (
    compact,
    is_constant_equation,
    right_side_scale,
    single_clause,
    uses_plus_minus,
    zero_product_factors,
)
from app.core.rendering import expr_text, factored_text, solved_text, sum_text
from app.core.step_generator import (
    RULE_NAMES,
    CorrectionUnsafe,
    GeneratedStep,
    Rule,
    generate_continuation,
    next_step,
    quadratic_formula_step,
    verify_generated,
)
from app.core.types import (
    OverallStatus,
    SolutionKind,
    SolutionSet,
    StepAnalysis,
    StepStatus,
    VerificationResult,
)
from app.utils.errors import MathInputError

MAX_HINT_LEVEL = 3
_UNSAFE_MESSAGE = (
    "StepCheck could not build a correction that it can fully verify for this solution, "
    "so it will not suggest one. Please review the steps manually."
)


class CorrectionStatus(str, Enum):
    CORRECTED = "CORRECTED"
    COMPLETED = "COMPLETED"
    NO_CORRECTION_NEEDED = "NO_CORRECTION_NEEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class GuidedStatus(str, Enum):
    NEEDS_ATTEMPT = "NEEDS_ATTEMPT"
    ACCEPTED = "ACCEPTED"
    NO_PROGRESS = "NO_PROGRESS"
    REJECTED = "REJECTED"
    ATTEMPT_UNREADABLE = "ATTEMPT_UNREADABLE"
    SOLVED = "SOLVED"
    ALREADY_COMPLETE = "ALREADY_COMPLETE"
    NO_CORRECTION_NEEDED = "NO_CORRECTION_NEEDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class CorrectionAction(str, Enum):
    NONE = "NONE"
    REPLACE_STEP = "REPLACE_STEP"  # fix the first invalid step, then continue
    COMPLETE_SOLUTION = "COMPLETE_SOLUTION"  # all valid but unfinished: continue
    REMOVE_REMAINING_STEPS = "REMOVE_REMAINING_STEPS"  # answer already complete: drop later steps


class InvalidProgress(Exception):
    """Client-submitted guided progress failed re-verification (request-level error)."""

    def __init__(self, index: int, message: str):
        super().__init__(message)
        self.index = index
        self.message = message


class StepSource(str, Enum):
    STUDENT = "STUDENT"
    CORRECTED = "CORRECTED"
    GENERATED = "GENERATED"


@dataclass
class CorrectionStep:
    step_number: int
    text: str
    latex: str | None
    source: StepSource
    rule: str | None = None
    rule_name: str | None = None
    explanation: str | None = None


@dataclass
class RemovedStep:
    step_number: int
    text: str
    status: StepStatus
    kind: str  # INCORRECT | UNNECESSARY | UNVERIFIABLE
    reason: str


@dataclass
class FullCorrection:
    status: CorrectionStatus
    message: str
    action: CorrectionAction = CorrectionAction.NONE
    first_error_step: int | None = None
    complete_answer_step: int | None = None
    removed_steps: list[RemovedStep] = field(default_factory=list)
    original_step: str | None = None
    diagnosis: Diagnosis | None = None
    corrected_step: CorrectionStep | None = None
    continuation: list[CorrectionStep] = field(default_factory=list)
    corrected_solution: list[CorrectionStep] = field(default_factory=list)
    final_solution: SolutionSet | None = None
    verification: VerificationResult | None = None


@dataclass
class AttemptFeedback:
    valid: bool
    message: str
    reason_code: str | None = None
    category: ErrorCategory | None = None
    lost: tuple[sp.Expr, ...] = ()
    extraneous: tuple[sp.Expr, ...] = ()
    error_code: str | None = None


@dataclass
class GuidedCorrection:
    status: GuidedStatus
    message: str
    phase: str | None = None  # FIX_ERROR | CONTINUE
    first_error_step: int | None = None
    error_step: str | None = None
    current_step: str | None = None
    step_number: int | None = None  # number of the step the student should write next
    error_category: ErrorCategory | None = None
    expected_rule: str | None = None
    explanation: str | None = None
    hint: str | None = None
    hint_level: int = 1
    reveal_answer: bool = False
    revealed_step: str | None = None
    revealed_explanation: str | None = None
    attempt_feedback: AttemptFeedback | None = None
    final_solution: SolutionSet | None = None
    progress: list[str] = field(default_factory=list)  # server-verified accepted steps
    complete_answer_step: int | None = None
    removed_steps: list[RemovedStep] = field(default_factory=list)


# ----------------------------------------------------------------------- repair


def _step(text: str, rule: Rule, explanation: str) -> GeneratedStep:
    return GeneratedStep(text, rule, explanation, "", "")


def _standard_quadratic(step: StepAnalysis):
    if len(step.equations) != 1:
        return None
    lhs, rhs = step.equations[0]
    poly = sp.expand(lhs - rhs)
    if sp.degree(poly, X) != 2:
        return None
    if sign(poly.coeff(X, 2)) < 0:
        poly = -poly
    return poly


def _repair_candidates(prev: StepAnalysis, cur: StepAnalysis) -> list[GeneratedStep]:
    out: list[GeneratedStep] = []
    prev_set = prev.solution_set
    quad = _standard_quadratic(prev)
    prev_factors = zero_product_factors(prev.statement)
    cur_clause = single_clause(cur.statement)

    # A '±' line is the quadratic formula: repair the substitution, don't skip to the roots.
    if quad is not None and uses_plus_minus(cur.statement):
        a, b, c = quad.coeff(X, 2), quad.coeff(X, 1), quad.subs(X, 0)
        out.append(quadratic_formula_step(a, b, c))

    if cur.solved_form and not is_constant_equation(cur.statement):
        count = len(prev_set.values)
        out.append(
            _step(
                solved_text(prev_set),
                Rule.STATE_SOLUTIONS,
                f"The previous step has {prev_set.describe()} as its solution set, so the answer must state "
                + ("exactly that." if prev_set.kind is not SolutionKind.FINITE_SET
                   else f"all {count} solution{'s' if count != 1 else ''}."),
            )
        )

    factors = prev_factors
    if factors is None and quad is not None and factored_text(quad):
        factors = [f for f, _ in sp.factor_list(quad, X)[1]]
    if factors and (cur_clause is None or len(cur.equations) == 1) and not zero_product_factors(cur.statement):
        out.append(
            _step(
                " or ".join(f"{expr_text(f)} = 0" for f in factors),
                Rule.ZERO_PRODUCT,
                "A product is zero exactly when one of its factors is zero, so every factor must be set "
                "equal to zero — none can be dropped.",
            )
        )

    if quad is not None and zero_product_factors(cur.statement):
        ft = factored_text(quad)
        if ft:
            out.append(
                _step(f"{ft} = 0", Rule.FACTOR, f"The correct factorization is {ft}; it multiplies back to {expr_text(quad)}.")
            )

    p_clause = single_clause(prev.statement)
    if (
        p_clause
        and cur_clause
        and len(prev.equations) == 1
        and len(cur.equations) == 1
        and not uses_plus_minus(prev.statement)
    ):
        (lp, rp), (lc, rc) = prev.equations[0], cur.equations[0]
        l_text, r_text = to_text(cur_clause.lhs), to_text(cur_clause.rhs)
        d_left, d_right = sp.expand(lc - lp), sp.expand(rc - rp)
        if d_left == 0:
            simplified = expr_text(sp.expand(rp))
            out.append(
                _step(
                    f"{l_text} = {simplified}",
                    Rule.CORRECT_ARITHMETIC,
                    f"Keep the left-hand side and simplify the right-hand side correctly: "
                    f"{to_text(p_clause.rhs)} = {simplified}.",
                )
            )
        if d_right == 0:
            simplified = expr_text(sp.expand(lp))
            out.append(
                _step(
                    f"{simplified} = {r_text}",
                    Rule.CORRECT_ARITHMETIC,
                    f"Keep the right-hand side and simplify the left-hand side correctly: "
                    f"{to_text(p_clause.lhs)} = {simplified}.",
                )
            )
        if d_left != 0 and sp.expand(lp) != 0:
            ratio = sp.cancel(sp.expand(lc) / sp.expand(lp))
            if not ratio.has(X) and not is_zero(ratio):
                out.append(
                    _step(
                        f"{l_text} = {expr_text(sp.expand(ratio * rp))}",
                        Rule.MULTIPLY_BOTH_SIDES,
                        f"The left-hand side was multiplied by {expr_text(ratio)}, so the whole right-hand side "
                        "must be multiplied by the same number.",
                    )
                )
        if d_right != 0:
            ratio = right_side_scale(lp, lc, rp, rc)
            if ratio is not None:
                out.append(
                    _step(
                        f"{expr_text(sp.expand(ratio * lp))} = {r_text}",
                        Rule.MULTIPLY_BOTH_SIDES,
                        f"The right-hand side was multiplied by {expr_text(ratio)}, so every term on the "
                        "left-hand side must be multiplied by the same number.",
                    )
                )
        # Only keep the student's left side when that doesn't push x-terms onto a right side they had cleared.
        if d_left != 0 and (rc.has(X) or not sp.expand(rp + d_left).has(X)):
            new_right = _shifted_side_text(sp.expand(rp), d_left)
            verb = f"subtract {expr_text(-d_left)}" if _leading_negative(d_left) else f"add {expr_text(d_left)}"
            out.append(
                _step(
                    f"{l_text} = {new_right}",
                    Rule.ISOLATE_VARIABLE,
                    f"To get the left-hand side you need to {verb} on both sides, so {verb} on the "
                    "right-hand side as well.",
                )
            )
        if d_right != 0:
            new_left = expr_text(sp.expand(lp + d_right))
            out.append(
                _step(
                    f"{new_left} = {r_text}",
                    Rule.ISOLATE_VARIABLE,
                    "Whatever is added to or subtracted from the right-hand side must be applied to the "
                    "left-hand side too.",
                )
            )

    canonical = next_step(prev)
    if canonical is not None:
        out.append(canonical)
    return out


def _shifted_side_text(side: sp.Expr, delta: sp.Expr) -> str:
    """side + delta, keeping the number terms visible: 15 + (-5) -> '15 - 5', x + 10 + (-x - 4) -> '10 - 4'."""
    terms: list[sp.Expr] = []
    for k in (2, 1, 0):
        s_k = side.coeff(X, k) if k else side.subs(X, 0)
        d_k = delta.coeff(X, k) if k else delta.subs(X, 0)
        if is_zero(s_k + d_k):
            continue
        if k == 0 and not is_zero(s_k) and not is_zero(d_k):
            terms += [s_k, d_k]
        else:
            terms.append((s_k + d_k) * X**k)
    return sum_text(terms)


def _leading_negative(expr: sp.Expr) -> bool:
    return expr_text(expr).startswith("-")


def repair_step(prev: StepAnalysis, cur: StepAnalysis) -> tuple[GeneratedStep, StepAnalysis]:
    """The verified replacement for an invalid step ``cur`` derived from valid ``prev``."""
    prev_text = compact(prev.raw)
    for candidate in _repair_candidates(prev, cur):
        if compact(candidate.text) == prev_text:
            continue
        try:
            analysis = verify_generated(prev, candidate)
        except (CorrectionUnsafe, MathInputError):
            continue
        return candidate, analysis
    raise CorrectionUnsafe("No verified replacement step was found.")


# ------------------------------------------------------------------------- FULL


def _as_step(n: int, text: str, source: StepSource, gen: GeneratedStep | None = None) -> CorrectionStep:
    analysis = analyze_step(n, text)
    return CorrectionStep(
        step_number=n,
        text=text,
        latex=analysis.latex,
        source=source,
        rule=gen.rule.value if gen else None,
        rule_name=RULE_NAMES.get(gen.rule) if gen else None,
        explanation=gen.explanation if gen else None,
    )


def _unverifiable_message(result: VerificationResult) -> str:
    for s in result.steps:
        if s.status in (StepStatus.UNSUPPORTED, StepStatus.NEEDS_REVIEW) and s.analysis.error:
            return (
                f"Step {s.step} could not be verified ({s.analysis.error.message}) "
                "so StepCheck cannot safely suggest a correction."
            )
    return "Some steps could not be verified, so StepCheck cannot safely suggest a correction."


def _removed_steps(result: VerificationResult, complete_at: int) -> list[RemovedStep]:
    removed = []
    for s in result.steps[complete_at:]:
        if s.status is StepStatus.FIRST_INVALID:
            kind, reason = "INCORRECT", "This step changes the solutions of the equation."
        elif s.status is StepStatus.DOWNSTREAM_DEPENDENT:
            kind, reason = "INCORRECT", f"This step depends on the incorrect step {result.first_error_step}."
        elif s.status is StepStatus.VALID:
            kind, reason = "UNNECESSARY", "This step is valid but the answer was already complete."
        else:
            kind, reason = "UNVERIFIABLE", "This step could not be verified and is not needed."
        removed.append(RemovedStep(s.step, s.raw, s.status, kind, reason))
    return removed


def _already_complete_message(result: VerificationResult, complete_at: int) -> str:
    n = len(result.steps)
    later = f"step {n} — it is" if n == complete_at + 1 else f"steps {complete_at + 1}–{n} — they are"
    return (
        f"Your solution was already complete at step {complete_at} ({solved_text(result.correct_solution)}). "
        f"Remove {later} not needed."
    )


def _remove_remaining(steps: list[str], result: VerificationResult, complete_at: int) -> FullCorrection:
    """Decision 3: a complete answer was reached before a later invalid or unnecessary step."""
    kept = steps[:complete_at]
    check = verify_steps(kept)
    if check.overall_status is not OverallStatus.CORRECT:  # cannot happen if the definitions agree
        return FullCorrection(CorrectionStatus.NEEDS_REVIEW, _UNSAFE_MESSAGE)
    diag = None
    k = result.first_error_step
    if k is not None:
        prev, cur = result.steps[k - 2].analysis, result.steps[k - 1].analysis
        diag = diagnose(prev, cur, compare(prev.solution_set, cur.solution_set), k)
    return FullCorrection(
        status=CorrectionStatus.CORRECTED,
        message=_already_complete_message(result, complete_at),
        action=CorrectionAction.REMOVE_REMAINING_STEPS,
        first_error_step=k,
        original_step=steps[k - 1] if k else None,
        complete_answer_step=complete_at,
        removed_steps=_removed_steps(result, complete_at),
        diagnosis=diag,
        corrected_solution=[_as_step(i + 1, t, StepSource.STUDENT) for i, t in enumerate(kept)],
        final_solution=check.completeness.submitted,
        verification=check,
    )


def correct_full(steps: list[str]) -> FullCorrection:
    result = verify_steps(steps)
    if result.overall_status is OverallStatus.CORRECT:
        return FullCorrection(CorrectionStatus.NO_CORRECTION_NEEDED, "Every step is valid and the answer is complete.")
    if result.complete_answer_step is not None:
        return _remove_remaining(steps, result, result.complete_answer_step)

    analyses = [s.analysis for s in result.steps]
    diag: Diagnosis | None = None
    repaired: GeneratedStep | None = None
    try:
        if result.first_error_step is not None:
            k = result.first_error_step
            prev, cur = analyses[k - 2], analyses[k - 1]
            diag = diagnose(prev, cur, compare(prev.solution_set, cur.solution_set), k)
            prefix = [s.raw for s in result.steps[: k - 1] if s.status is StepStatus.VALID]
            repaired, anchor = repair_step(prev, cur)
        elif result.overall_status is OverallStatus.INCOMPLETE:
            anchor = analyses[-1]
            prefix = list(steps)
        else:
            return FullCorrection(CorrectionStatus.NEEDS_REVIEW, _unverifiable_message(result))

        continuation = generate_continuation(anchor)
        texts = prefix + ([repaired.text] if repaired else []) + [g.text for g, _ in continuation]
        check = verify_steps(texts)
        if check.overall_status is not OverallStatus.CORRECT or not check.completeness.solution_complete:
            raise CorrectionUnsafe("The corrected solution did not re-verify.")
    except (CorrectionUnsafe, MathInputError):
        return FullCorrection(
            CorrectionStatus.NEEDS_REVIEW,
            _UNSAFE_MESSAGE,
            first_error_step=result.first_error_step,
            diagnosis=diag,
        )

    solution: list[CorrectionStep] = [_as_step(i + 1, t, StepSource.STUDENT) for i, t in enumerate(prefix)]
    corrected_step = None
    if repaired:
        explanation = f"{diag.evidence} {repaired.explanation}".strip()
        repaired = GeneratedStep(repaired.text, repaired.rule, explanation, repaired.hint, repaired.hint_detail)
        corrected_step = _as_step(len(solution) + 1, repaired.text, StepSource.CORRECTED, repaired)
        solution.append(corrected_step)
    generated = []
    for gen, _ in continuation:
        step = _as_step(len(solution) + 1, gen.text, StepSource.GENERATED, gen)
        generated.append(step)
        solution.append(step)

    if repaired:
        message = f"Step {result.first_error_step} was the first incorrect step. Here is a verified correction."
        status, action = CorrectionStatus.CORRECTED, CorrectionAction.REPLACE_STEP
    else:
        message = "Your steps are correct so far but the solution is unfinished. Here is a verified completion."
        status, action = CorrectionStatus.COMPLETED, CorrectionAction.COMPLETE_SOLUTION
    return FullCorrection(
        status=status,
        message=message,
        action=action,
        first_error_step=result.first_error_step,
        original_step=steps[result.first_error_step - 1] if result.first_error_step else None,
        complete_answer_step=check.complete_answer_step,
        diagnosis=diag,
        corrected_step=corrected_step,
        continuation=generated,
        corrected_solution=solution,
        final_solution=check.completeness.submitted,
        verification=check,
    )


# ----------------------------------------------------------------------- GUIDED


def _hint_for(level: int, hints: tuple[str, str], expected: GeneratedStep) -> tuple[str, bool]:
    if level >= MAX_HINT_LEVEL:
        return f"The next step is: {expected.text}", True
    return hints[min(level, 2) - 1], False


def _reject_progress(progress: list[str], reason: str) -> None:
    if progress:
        raise InvalidProgress(0, f"Guided progress is not allowed here: {reason}")


def _replay_progress(anchor: StepAnalysis, progress: list[str], first_number: int, target: SolutionSet) -> StepAnalysis:
    """Re-verify every previously accepted step; the client's word is never trusted."""
    for i, text in enumerate(progress):
        if is_complete_answer(anchor, target) and i > 0:
            raise InvalidProgress(i, f"Progress step {i + 1} comes after the solution was already complete.")
        step = analyze_step(first_number + i, text)
        if not step.ok:
            raise InvalidProgress(i, f"Progress step {i + 1} could not be read: {step.error.message}")
        if not compare(anchor.solution_set, step.solution_set).equivalent:
            raise InvalidProgress(i, f"Progress step {i + 1} is not a valid transformation of the step before it.")
        if compact(step.raw) == compact(anchor.raw):
            raise InvalidProgress(i, f"Progress step {i + 1} repeats the previous step.")
        anchor = step
    return anchor


def correct_guided(
    steps: list[str],
    progress: list[str] | None = None,
    attempt: str | None = None,
    hint_level: int = 1,
) -> GuidedCorrection:
    """Raises InvalidProgress when the submitted progress is not a verified continuation."""
    progress = list(progress or [])
    hint_level = max(1, min(MAX_HINT_LEVEL, hint_level))
    result = verify_steps(steps)
    if result.overall_status is OverallStatus.CORRECT:
        _reject_progress(progress, "the submitted solution is already correct.")
        return GuidedCorrection(GuidedStatus.NO_CORRECTION_NEEDED, "Every step is valid and the answer is complete.")
    if result.complete_answer_step is not None:
        _reject_progress(progress, "the submitted solution was already complete.")
        c = result.complete_answer_step
        return GuidedCorrection(
            GuidedStatus.ALREADY_COMPLETE,
            _already_complete_message(result, c),
            first_error_step=result.first_error_step,
            current_step=steps[c - 1],
            complete_answer_step=c,
            removed_steps=_removed_steps(result, c),
            final_solution=result.correct_solution,
        )

    analyses = [s.analysis for s in result.steps]
    target = result.correct_solution
    diag: Diagnosis | None = None
    if result.first_error_step is not None:
        k = result.first_error_step
        prev, cur = analyses[k - 2], analyses[k - 1]
        diag = diagnose(prev, cur, compare(prev.solution_set, cur.solution_set), k)
        anchor, phase, step_number = prev, "FIX_ERROR", k
    elif result.overall_status is OverallStatus.INCOMPLETE:
        anchor, phase, step_number = analyses[-1], "CONTINUE", len(steps) + 1
    else:
        _reject_progress(progress, "the submitted solution could not be verified.")
        return GuidedCorrection(GuidedStatus.NEEDS_REVIEW, _unverifiable_message(result))

    anchor = _replay_progress(anchor, progress, step_number, target)
    try:
        if progress:
            phase = "CONTINUE"
        step_number += len(progress)
        base = dict(
            phase=phase,
            first_error_step=result.first_error_step,
            error_step=steps[result.first_error_step - 1] if result.first_error_step else None,
            current_step=anchor.raw,
            step_number=step_number,
            hint_level=hint_level,
            progress=progress,
        )
        if progress and is_complete_answer(anchor, target):
            return GuidedCorrection(GuidedStatus.SOLVED, "Solved! Your corrected solution is complete.",
                                    final_solution=anchor.solution_set, **base)
        if phase == "FIX_ERROR":
            expected, _ = repair_step(prev, cur)
            hints = diag.hints
            concept = dict(error_category=diag.category, expected_rule=diag.expected_rule, explanation=diag.explanation)
        else:
            expected = next_step(anchor)
            if expected is None:  # cannot happen: an incomplete line always has a next step
                raise CorrectionUnsafe("No next step for an incomplete solution.")
            verify_generated(anchor, expected)
            hints = (expected.hint, expected.hint_detail)
            concept = dict(expected_rule=RULE_NAMES[expected.rule], explanation=None)

        def reply(status: GuidedStatus, message: str, hint_pair=hints, feedback=None, **extra) -> GuidedCorrection:
            hint, reveal = _hint_for(hint_level, hint_pair, expected)
            fields = {**base, **concept, **extra}
            return GuidedCorrection(
                status, message, hint=hint, reveal_answer=reveal,
                revealed_step=expected.text if reveal else None,
                revealed_explanation=expected.explanation if reveal else None,
                attempt_feedback=feedback, **fields,
            )

        if attempt is None:
            opener = (
                f"Step {result.first_error_step} is the first incorrect step. Try rewriting it."
                if phase == "FIX_ERROR"
                else "Your work so far is correct. What is the next step?"
            )
            return reply(GuidedStatus.NEEDS_ATTEMPT, opener)

        tried = analyze_step(step_number, attempt)
        if not tried.ok:
            fb = AttemptFeedback(False, tried.error.message, error_code=tried.error.code.value)
            return reply(GuidedStatus.ATTEMPT_UNREADABLE, "StepCheck could not read that step.", feedback=fb)

        cmp = compare(anchor.solution_set, tried.solution_set)
        if not cmp.equivalent:
            d = diagnose(anchor, tried, cmp, step_number)
            fb = AttemptFeedback(False, d.explanation, cmp.reason_code.value, d.category, cmp.lost, cmp.extraneous)
            pair = d.hints if d.category is not ErrorCategory.GENERAL_ERROR else hints
            return reply(GuidedStatus.REJECTED, "Not quite — that step changes the solutions.", hint_pair=pair,
                         feedback=fb, error_category=d.category, expected_rule=d.expected_rule)
        if compact(tried.raw) == compact(anchor.raw):
            fb = AttemptFeedback(True, "This is equivalent, but it is the same equation as before.")
            return reply(GuidedStatus.NO_PROGRESS, "That's correct but doesn't move the solution forward.", feedback=fb)

        accepted = {**base, "current_step": tried.raw, "progress": progress + [attempt]}
        if is_complete_answer(tried, target):
            return GuidedCorrection(
                GuidedStatus.SOLVED, "Correct — and your answer is complete!",
                attempt_feedback=AttemptFeedback(True, "This step is valid and states every solution."),
                final_solution=tried.solution_set, **accepted,
            )
        following = next_step(tried)
        return GuidedCorrection(
            GuidedStatus.ACCEPTED,
            "Correct! Add this step to your work and continue.",
            attempt_feedback=AttemptFeedback(True, "This step is a valid transformation."),
            hint=following.hint if following else None,
            expected_rule=RULE_NAMES[following.rule] if following else None,
            **{**accepted, "step_number": step_number + 1, "hint_level": 1},
        )
    except (CorrectionUnsafe, MathInputError):
        return GuidedCorrection(GuidedStatus.NEEDS_REVIEW, _UNSAFE_MESSAGE, first_error_step=result.first_error_step)
