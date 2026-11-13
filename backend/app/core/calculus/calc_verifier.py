"""Step-by-step verification for calculus, mirroring ``first_error_detector``.

Every expression in a step must equal the last trusted expression: as the same
function or value (derivatives, definite integrals, limits), or up to a constant
(indefinite integrals). The first step that provably differs is FIRST_INVALID
and everything after it is DOWNSTREAM_DEPENDENT. Steps the engine cannot decide
(or that run out of time) are NEEDS_REVIEW, never guessed.

Parsing happens here; all evaluation happens in the sandbox worker.
"""

from __future__ import annotations

import logging
import time

from app.core.calculus.calc_equivalence import Answer, Outcome, Verdict, mode_for
from app.core.calculus.calc_parser import CalcStatement, Topic, guess_topic, parse_calculus, to_text
from app.core.calculus.sandbox import Sandbox, SandboxFailure, SandboxTimeout, get_sandbox
from app.core.types import (
    CompletenessResult,
    FinalAnswerStatus,
    OverallStatus,
    ReasonCode,
    StepAnalysis,
    StepResult,
    StepStatus,
    TransitionResult,
    VerificationResult,
)
from app.utils.errors import ErrorCategory, ErrorCode, MathInputError

logger = logging.getLogger("stepcheck.calculus")

REQUEST_BUDGET_SECONDS = 15.0


def analyze_calculus_step(index: int, raw: str) -> StepAnalysis:
    analysis = StepAnalysis(index=index, raw=raw)
    try:
        statement = parse_calculus(raw)
        analysis.statement = statement
        analysis.latex = statement.latex
        analysis.normalized = " = ".join(to_text(link) for link in statement.links)
        analysis.solved_form = statement.evaluated
    except MathInputError as exc:
        analysis.error = exc
    return analysis


def is_complete_calculus_answer(statement: CalcStatement, topic: Topic) -> bool:
    """Shared definition: nothing left to evaluate, and an indefinite integral includes + C."""
    return statement.evaluated and (topic is not Topic.INTEGRAL or statement.has_constant)


def _status_for_error(error: MathInputError) -> StepStatus:
    return StepStatus.UNSUPPORTED if error.category is ErrorCategory.UNSUPPORTED else StepStatus.NEEDS_REVIEW


class _Checker:
    """Runs comparisons in the sandbox within one request's time budget."""

    def __init__(self, sandbox: Sandbox, mode: str, deadline: float) -> None:
        self.sandbox = sandbox
        self.mode = mode
        self.deadline = deadline

    def compare(self, expected_text: str, found_text: str) -> Outcome:
        try:
            return self.sandbox.run("compare", expected_text, found_text, self.mode, deadline=self.deadline)
        except SandboxTimeout:
            return Outcome(Verdict.UNKNOWN, "TIMEOUT")
        except SandboxFailure:
            logger.exception("Calculus comparison failed")
            return Outcome(Verdict.UNKNOWN, "CANNOT_DECIDE")
        except MathInputError:
            return Outcome(Verdict.UNKNOWN, "CANNOT_DECIDE")

    def answer(self, problem_text: str, topic: Topic) -> Answer | None:
        try:
            return self.sandbox.run("answer", problem_text, topic.value, deadline=self.deadline)
        except (SandboxTimeout, SandboxFailure, MathInputError):
            return None


def _check_links(checker: _Checker, anchor_text: str, links: list) -> tuple[Outcome, str]:
    """Compare each expression of a step with the one before it. Returns the decisive outcome and the new anchor."""
    notes = []
    current = anchor_text
    for link in links:
        text = to_text(link)
        outcome = checker.compare(current, text)
        if outcome.verdict is not Verdict.EQUAL:
            return outcome, anchor_text
        if outcome.note:
            notes.append(outcome.note)
        current = text
    return Outcome(Verdict.EQUAL, note="; ".join(dict.fromkeys(notes)) or None), current


def verify_calculus(
    steps: list[str], sandbox: Sandbox | None = None, budget: float = REQUEST_BUDGET_SECONDS
) -> VerificationResult:
    analyses = [analyze_calculus_step(i + 1, s) for i, s in enumerate(steps)]
    original = analyses[0]
    if original.ok and original.statement.topic is None:
        original.error = MathInputError(
            ErrorCode.AMBIGUOUS_EXPRESSION,
            "The problem must be a derivative, an integral or a limit, e.g. d/dx(x^2), int(x^2) dx or lim(x->0, sin(x)/x).",
        )
    if not original.ok:
        return _unverifiable(analyses)

    topic: Topic = original.statement.topic
    sandbox = sandbox or get_sandbox()
    try:
        sandbox.ensure_ready()  # a cold start must not eat the request's checking budget
    except SandboxFailure:
        logger.exception("Calculus worker could not start")
    checker = _Checker(sandbox, mode_for(topic).value, time.monotonic() + budget)

    step_results: list[StepResult] = []
    transitions: list[TransitionResult] = []
    first_error: int | None = None
    unresolved = False
    saw_unverifiable = False
    saw_needs_review = False
    notes: list[str] = []

    # Step 1 is the problem. Any extra expressions on that line ("d/dx(x^2) = 2x") are checked too.
    problem_text = to_text(original.statement.links[0])
    first_outcome, anchor_text = _check_links(checker, problem_text, original.statement.links[1:])
    last_verified = 0
    if first_outcome.verdict is Verdict.EQUAL:
        step_results.append(StepResult(1, original.raw, StepStatus.VALID, original))
    elif first_outcome.verdict is Verdict.UNEQUAL:
        first_error = 1
        step_results.append(StepResult(1, original.raw, StepStatus.FIRST_INVALID, original))
    else:
        # The problem itself is fine, but an extra expression on its line is undecided:
        # step 2 is compared across it, so a mismatch there can't be pinned on step 2.
        saw_unverifiable = saw_needs_review = True
        last_verified = -1
        step_results.append(StepResult(1, original.raw, StepStatus.NEEDS_REVIEW, original))

    for i in range(1, len(analyses)):
        cur = analyses[i]
        base = dict(from_step=i, to_step=i + 1, locally_valid=None, matches_original=None)

        if not cur.ok:
            status = _status_for_error(cur.error)
            if first_error is None:
                saw_unverifiable = True
                saw_needs_review |= status is StepStatus.NEEDS_REVIEW
            transitions.append(TransitionResult(status=status, reason_code=cur.error.code.value, compared_to_step=None, **base))
            step_results.append(StepResult(i + 1, cur.raw, status, cur))
            continue

        if first_error is not None:
            transitions.append(TransitionResult(status=StepStatus.DOWNSTREAM_DEPENDENT, reason_code=None, compared_to_step=None, **base))
            step_results.append(StepResult(i + 1, cur.raw, StepStatus.DOWNSTREAM_DEPENDENT, cur))
            continue

        if unresolved:
            transitions.append(
                TransitionResult(
                    status=StepStatus.NEEDS_REVIEW, reason_code=ReasonCode.AFTER_UNRESOLVED_STEP.value, compared_to_step=None, **base
                )
            )
            step_results.append(StepResult(i + 1, cur.raw, StepStatus.NEEDS_REVIEW, cur))
            continue

        anchor_step = max(last_verified, 0) + 1
        outcome, new_anchor = _check_links(checker, anchor_text, cur.statement.links)
        bridged = last_verified != i - 1
        if outcome.verdict is Verdict.EQUAL:
            status, reason = StepStatus.VALID, None
            anchor_text, last_verified = new_anchor, i
            if outcome.note:
                notes.append(f"Step {i + 1}: {outcome.note}.")
        elif outcome.verdict is Verdict.UNEQUAL and not bridged:
            status, reason = StepStatus.FIRST_INVALID, outcome.reason
            first_error = i + 1
        elif outcome.verdict is Verdict.UNEQUAL:
            # An unverifiable step sits between the anchor and this one: the error could be in either.
            status, reason = StepStatus.NEEDS_REVIEW, ReasonCode.AMBIGUOUS_ERROR_LOCATION.value
            unresolved = saw_needs_review = True
        else:
            # Undecided: like an unreadable step, later steps are compared across it.
            status, reason = StepStatus.NEEDS_REVIEW, outcome.reason
            saw_unverifiable = saw_needs_review = True
        transitions.append(
            TransitionResult(
                status=status,
                reason_code=reason,
                compared_to_step=anchor_step,
                locally_valid=outcome.verdict is Verdict.EQUAL if outcome.verdict is not Verdict.UNKNOWN else None,
                matches_original=None,
                expected_value_latex=outcome.expected_latex,
                found_value_latex=outcome.found_latex,
                counterexample=outcome.counterexample,
                note=outcome.note,
                from_step=i,
                to_step=i + 1,
            )
        )
        step_results.append(StepResult(i + 1, cur.raw, status, cur))

    final = analyses[-1]
    if not final.ok:
        completeness = CompletenessResult(FinalAnswerStatus.UNVERIFIABLE, None, None, None, None, None, None)
        missing_constant = None
    elif not final.statement.evaluated:
        completeness = CompletenessResult(FinalAnswerStatus.NOT_ISOLATED, None, False, False, None, None, None)
        missing_constant = None
    else:
        correct = step_results[-1].status is StepStatus.VALID
        missing_constant = not final.statement.has_constant if topic is Topic.INTEGRAL else None
        completeness = CompletenessResult(
            FinalAnswerStatus.SOLVED, None, correct and not missing_constant, not missing_constant, None, None, None
        )

    if first_error is not None:
        overall = OverallStatus.INCORRECT
    elif saw_unverifiable or unresolved:
        overall = OverallStatus.NEEDS_REVIEW if saw_needs_review else OverallStatus.UNSUPPORTED
    elif completeness.final_answer_status is not FinalAnswerStatus.SOLVED or missing_constant:
        overall = OverallStatus.INCOMPLETE
    else:
        overall = OverallStatus.CORRECT

    answer = checker.answer(problem_text, topic)
    return VerificationResult(
        overall_status=overall,
        first_error_step=first_error,
        steps=step_results,
        transitions=transitions,
        correct_solution=None,
        completeness=completeness,
        complete_answer_step=_first_complete_answer(step_results, topic),
        notes=notes,
        topic=topic.value,
        expected_answer=answer.text if answer else None,
        expected_answer_latex=answer.latex if answer else None,
        missing_constant=missing_constant,
    )


def _first_complete_answer(step_results: list[StepResult], topic: Topic) -> int | None:
    for s in step_results:
        if s.status is not StepStatus.VALID:
            return None
        if is_complete_calculus_answer(s.analysis.statement, topic):
            return s.step
    return None


def _unverifiable(analyses: list[StepAnalysis]) -> VerificationResult:
    """The problem line itself could not be read: nothing can be judged."""
    original = analyses[0]
    step_results = [StepResult(1, original.raw, _status_for_error(original.error), original)]
    transitions = []
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
    unsupported = original.error.category is ErrorCategory.UNSUPPORTED
    return VerificationResult(
        overall_status=OverallStatus.UNSUPPORTED if unsupported else OverallStatus.NEEDS_REVIEW,
        first_error_step=None,
        steps=step_results,
        transitions=transitions,
        correct_solution=None,
        completeness=CompletenessResult(FinalAnswerStatus.UNVERIFIABLE, None, None, None, None, None, None),
        topic=guess_topic(original.raw).value,
    )
