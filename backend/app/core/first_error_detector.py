"""Step-by-step verification: first-error localisation and final-answer completeness.

Every step is solved independently into an exact real solution set. A step is a
valid transformation only if its solution set equals that of the step it was
derived from. The first non-equivalent step is FIRST_INVALID; everything after
it is DOWNSTREAM_DEPENDENT (its local validity is still reported). Whether the
final line states the complete solution set is checked separately.
"""

from __future__ import annotations

from app.core.equation_parser import clause_equations, parse_statement
from app.core.equivalence_checker import compare
from app.core.polynomial_validator import normalize_equation
from app.core.solution_solver import solve_polynomial, union
from app.core.types import (
    CompletenessResult,
    FinalAnswerStatus,
    OverallStatus,
    ReasonCode,
    SolutionKind,
    SolutionSet,
    StepAnalysis,
    StepResult,
    StepStatus,
    TransitionResult,
    VerificationResult,
)
from app.utils.errors import ErrorCategory, MathInputError


def analyze_step(index: int, raw: str) -> StepAnalysis:
    """Parse, normalise and solve a single step in isolation."""
    analysis = StepAnalysis(index=index, raw=raw)
    try:
        statement = parse_statement(raw)
        analysis.statement = statement
        analysis.latex = statement.latex
        analysis.solved_form = statement.solved_form
        if statement.literal is not None:
            analysis.solution_set = statement.literal
            analysis.normalized = statement.literal.describe()
            return analysis
        sets: list[SolutionSet] = []
        normalized: list[str] = []
        for clause in statement.clauses:
            for lhs, rhs in clause_equations(clause):
                analysis.equations.append((lhs, rhs))
                poly = normalize_equation(lhs, rhs)
                normalized.append(str(poly))
                sets.append(solve_polynomial(poly))
        analysis.normalized = " or ".join(dict.fromkeys(normalized))
        analysis.solution_set = union(sets)
    except MathInputError as exc:
        analysis.error = exc
    return analysis


def _status_for_error(error: MathInputError) -> StepStatus:
    if error.category is ErrorCategory.UNSUPPORTED:
        return StepStatus.UNSUPPORTED
    return StepStatus.NEEDS_REVIEW


def _safe_compare(a: StepAnalysis, b: StepAnalysis):
    if not (a.ok and b.ok):
        return None
    return compare(a.solution_set, b.solution_set)


def verify_steps(steps: list[str]) -> VerificationResult:
    analyses = [analyze_step(i + 1, s) for i, s in enumerate(steps)]
    original = analyses[0]
    step_results: list[StepResult] = []
    transitions: list[TransitionResult] = []

    # ---- Step 1 is the reference problem. Without it nothing can be judged.
    if not original.ok:
        step_results.append(StepResult(1, original.raw, _status_for_error(original.error), original))
        for a in analyses[1:]:
            status = _status_for_error(a.error) if not a.ok else StepStatus.NEEDS_REVIEW
            step_results.append(StepResult(a.index, a.raw, status, a))
            transitions.append(
                TransitionResult(
                    from_step=a.index - 1,
                    to_step=a.index,
                    status=status,
                    reason_code=a.error.code.value if not a.ok else ReasonCode.NO_VERIFIED_REFERENCE.value,
                    compared_to_step=None,
                    locally_valid=None,
                    matches_original=None,
                )
            )
        overall = (
            OverallStatus.UNSUPPORTED
            if original.error.category is ErrorCategory.UNSUPPORTED
            else OverallStatus.NEEDS_REVIEW
        )
        return VerificationResult(
            overall_status=overall,
            first_error_step=None,
            steps=step_results,
            transitions=transitions,
            correct_solution=None,
            completeness=CompletenessResult(
                FinalAnswerStatus.UNVERIFIABLE, None, None, None, None, None, None
            ),
        )

    step_results.append(StepResult(1, original.raw, StepStatus.VALID, original))
    last_verified = 0  # index into analyses of the latest step trusted as equivalent
    first_error: int | None = None  # 1-based step number
    unresolved = False  # an error exists but cannot be localised with certainty
    saw_unverifiable = False
    saw_needs_review = False

    for i in range(1, len(analyses)):
        cur, prev = analyses[i], analyses[i - 1]
        local = _safe_compare(prev, cur)
        vs_original = _safe_compare(original, cur)
        base = dict(
            from_step=i,
            to_step=i + 1,
            locally_valid=local.equivalent if local else None,
            matches_original=vs_original.equivalent if vs_original else None,
        )

        if not cur.ok:
            status = _status_for_error(cur.error)
            if first_error is None:
                saw_unverifiable = True
                saw_needs_review |= status is StepStatus.NEEDS_REVIEW
            transitions.append(
                TransitionResult(
                    status=status, reason_code=cur.error.code.value, compared_to_step=None, **base
                )
            )
            step_results.append(StepResult(i + 1, cur.raw, status, cur))
            continue

        if first_error is not None:
            transitions.append(
                TransitionResult(
                    status=StepStatus.DOWNSTREAM_DEPENDENT,
                    reason_code=local.reason_code.value if local and local.reason_code else None,
                    compared_to_step=i if local else None,
                    lost=local.lost if local else (),
                    extraneous=local.extraneous if local else (),
                    **base,
                )
            )
            step_results.append(StepResult(i + 1, cur.raw, StepStatus.DOWNSTREAM_DEPENDENT, cur))
            continue

        if unresolved:
            transitions.append(
                TransitionResult(
                    status=StepStatus.NEEDS_REVIEW,
                    reason_code=ReasonCode.AFTER_UNRESOLVED_STEP.value,
                    compared_to_step=None,
                    **base,
                )
            )
            step_results.append(StepResult(i + 1, cur.raw, StepStatus.NEEDS_REVIEW, cur))
            continue

        anchor = analyses[last_verified]
        cmp = compare(anchor.solution_set, cur.solution_set)
        bridged = last_verified != i - 1
        if cmp.equivalent:
            status, reason = StepStatus.VALID, None
            last_verified = i
        elif bridged:
            # An unverifiable step sits between the anchor and this one: the
            # error could be in either, so refuse to guess its location.
            status, reason = StepStatus.NEEDS_REVIEW, ReasonCode.AMBIGUOUS_ERROR_LOCATION.value
            unresolved = True
            saw_needs_review = True
        else:
            status, reason = StepStatus.FIRST_INVALID, cmp.reason_code.value
            first_error = i + 1
        transitions.append(
            TransitionResult(
                status=status,
                reason_code=reason,
                compared_to_step=anchor.index,
                lost=cmp.lost,
                extraneous=cmp.extraneous,
                **base,
            )
        )
        step_results.append(StepResult(i + 1, cur.raw, status, cur))

    completeness = check_completeness(original.solution_set, analyses[-1])

    if first_error is not None:
        overall = OverallStatus.INCORRECT
    elif saw_unverifiable or unresolved:
        overall = OverallStatus.NEEDS_REVIEW if saw_needs_review else OverallStatus.UNSUPPORTED
    elif completeness.final_answer_status is not FinalAnswerStatus.SOLVED:
        overall = OverallStatus.INCOMPLETE
    else:
        overall = OverallStatus.CORRECT

    return VerificationResult(
        overall_status=overall,
        first_error_step=first_error,
        steps=step_results,
        transitions=transitions,
        correct_solution=original.solution_set,
        completeness=completeness,
    )


def check_completeness(correct: SolutionSet, final: StepAnalysis) -> CompletenessResult:
    """Does the final line explicitly state exactly the original solution set?"""
    if not final.ok:
        return CompletenessResult(FinalAnswerStatus.UNVERIFIABLE, None, None, None, None, None, None)
    if not final.solved_form:
        return CompletenessResult(FinalAnswerStatus.NOT_ISOLATED, None, False, False, None, None, None)

    submitted = final.solution_set
    cmp = compare(correct, submitted)
    if correct.kind is SolutionKind.ALL_REAL:
        # Every real number is a solution; any finite answer misses infinitely
        # many, so "missing" cannot be listed.
        complete = submitted.kind is SolutionKind.ALL_REAL
        return CompletenessResult(
            FinalAnswerStatus.SOLVED, submitted, cmp.equivalent, complete,
            () if complete else None, (), False,
        )
    if submitted.kind is SolutionKind.ALL_REAL:
        return CompletenessResult(
            FinalAnswerStatus.SOLVED, submitted, False, True, (), None, True
        )
    return CompletenessResult(
        final_answer_status=FinalAnswerStatus.SOLVED,
        submitted=submitted,
        final_answer_correct=cmp.equivalent,
        solution_complete=not cmp.lost,
        missing=cmp.lost,
        extraneous=cmp.extraneous,
        includes_extraneous=bool(cmp.extraneous),
    )
