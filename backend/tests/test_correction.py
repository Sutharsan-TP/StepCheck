"""Correction engine: every generated correction must pass the same verification as student work."""

import json
from pathlib import Path

import pytest

from app.core.correction_engine import (
    CorrectionStatus,
    GuidedStatus,
    StepSource,
    correct_full,
    correct_guided,
)
from app.core.diagnosis import ErrorCategory as C
from app.core.first_error_detector import verify_steps
from app.core.forms import compact
from app.core.types import OverallStatus

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# steps, expected category, expected corrected step, expected final solution values
CASES = [
    # addition / subtraction
    (["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"], C.ADDITION_SUBTRACTION_ERROR, "2x = 10", ["5"]),
    (["2x - 5 = 15", "2x = 15 + 5", "2x = 25", "x = 12.5"], C.ADDITION_SUBTRACTION_ERROR, "2x = 20", ["10"]),
    (["2x + 5 = 15", "2x = 15 + 5", "x = 10"], C.SIGN_ERROR_MOVING_TERM, "2x = 15 - 5", ["5"]),
    (["3x + 4 = x + 10", "3x - x = 10 + 4", "2x = 14", "x = 7"], C.SIGN_ERROR_MOVING_TERM, "3x - x = 10 - 4", ["3"]),
    # multiplication / division
    (["x/3 = 4", "x = 7"], C.MULTIPLICATION_DIVISION_ERROR, "x = 12", ["12"]),
    (["5x = 20", "5x/5 = 20/5", "x = 3"], C.MULTIPLICATION_DIVISION_ERROR, "x = 4", ["4"]),
    (["x/2 + 1 = 4", "x + 1 = 8", "x = 7"], C.MULTIPLICATION_DIVISION_ERROR, "x + 2 = 8", ["6"]),
    # expansion / like terms
    (["3(x + 2) = 15", "3x + 2 = 15", "3x = 13", "x = 13/3"], C.EXPANSION_ERROR, "3x + 6 = 15", ["3"]),
    (["2(x - 4) = 6", "2x - 4 = 6", "x = 5"], C.EXPANSION_ERROR, "2x - 8 = 6", ["7"]),
    (["4x + 2x = 12", "8x = 12", "x = 3/2"], C.COMBINING_LIKE_TERMS_ERROR, "6x = 12", ["2"]),
    # factorization / quadratic transformations
    (["x^2 + x - 6 = 0", "(x - 2)(x - 3) = 0", "x = 2 or x = 3"], C.FACTORIZATION_ERROR, "(x + 3)(x - 2) = 0", ["-3", "2"]),
    (["x^2 - 5x + 6 = 0", "x = (-5 ± sqrt(25 - 24))/2", "x = -2 or x = -3"], C.QUADRATIC_FORMULA_ERROR,
     "x = (5 ± sqrt(1))/2", ["2", "3"]),
    (["x^2 - 5x + 3 = 0", "x = (5 ± sqrt(25 + 12))/2"], C.QUADRATIC_FORMULA_ERROR, "x = (5 ± sqrt(13))/2",
     ["5/2 - sqrt(13)/2", "sqrt(13)/2 + 5/2"]),
    # lost solutions
    (["x^2 = x", "x = 1"], C.DIVIDED_BY_VARIABLE, "x = 0 or x = 1", ["0", "1"]),
    (["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"], C.LOST_FACTOR, "x - 2 = 0 or x - 3 = 0", ["2", "3"]),
    (["x^2 = 9", "x = 3"], C.MISSING_NEGATIVE_ROOT, "x = -3 or x = 3", ["-3", "3"]),
    # incomplete quadratic answer
    (["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0 or x - 3 = 0", "x = 2"], C.INCOMPLETE_FINAL_ANSWER,
     "x = 2 or x = 3", ["2", "3"]),
    # repeated roots
    (["x^2 - 4x + 4 = 0", "(x - 2)(x + 2) = 0", "x = 2 or x = -2"], C.FACTORIZATION_ERROR, "(x - 2)^2 = 0", ["2"]),
    (["x^2 - 6x + 9 = 0", "(x - 3)^2 = 0", "x = -3"], C.INCORRECT_FINAL_ANSWER, "x = 3", ["3"]),
    # no real roots
    (["x^2 + 4 = 0", "x = 2 or x = -2"], C.INCORRECT_FINAL_ANSWER, "no real solution", []),
    (["x^2 + x + 1 = 0", "x = (-1 ± sqrt(1 + 4))/2"], C.QUADRATIC_FORMULA_ERROR, "no real solution", []),
    # identity / contradiction
    (["2(x + 1) = 2x + 2", "2x + 2 = 2x + 1", "no solution"], C.ADDITION_SUBTRACTION_ERROR, "2x + 2 = 2x + 2", []),
    (["x + 1 = x + 2", "1 = 1", "all real numbers"], C.INCONSISTENT_OPERATION, "1 = 2", []),
]


def assert_correction_verifies(correction):
    """The invariant: a returned correction re-verifies exactly like student work."""
    texts = [s.text for s in correction.corrected_solution]
    result = verify_steps(texts)
    assert result.overall_status is OverallStatus.CORRECT, (texts, result.overall_status)
    assert result.completeness.solution_complete is True
    assert result.completeness.final_answer_correct is True
    assert [s.step_number for s in correction.corrected_solution] == list(range(1, len(texts) + 1))
    assert correction.verification.overall_status is OverallStatus.CORRECT


@pytest.mark.parametrize("steps, category, corrected, final", CASES, ids=[c[2] for c in CASES])
def test_full_correction(steps, category, corrected, final):
    c = correct_full(steps)
    assert c.status is CorrectionStatus.CORRECTED
    assert c.diagnosis.category is category
    assert c.corrected_step.text == corrected
    assert c.corrected_step.source is StepSource.CORRECTED
    assert c.original_step == steps[c.first_error_step - 1]
    assert c.final_solution.value_strings() == final
    assert all(s.source is StepSource.GENERATED and s.explanation for s in c.continuation)
    assert_correction_verifies(c)


def test_prefix_keeps_valid_student_steps():
    c = correct_full(["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"])
    assert [(s.source, s.text) for s in c.corrected_solution] == [
        (StepSource.STUDENT, "2x + 5 = 15"),
        (StepSource.STUDENT, "2x = 15 - 5"),
        (StepSource.CORRECTED, "2x = 10"),
        (StepSource.GENERATED, "x = 5"),
    ]


def test_explanation_includes_evidence_and_rule():
    c = correct_full(["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"])
    assert "Lost: x = 3" in c.diagnosis.evidence
    assert "Zero-product" in c.diagnosis.expected_rule
    assert "Lost: x = 3" in c.corrected_step.explanation


@pytest.mark.parametrize(
    "steps, final",
    [
        (["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"], ["2", "3"]),
        (["x^2 - 5x + 3 = 0"] * 2, ["5/2 - sqrt(13)/2", "sqrt(13)/2 + 5/2"]),
        (["x^2 - 4x + 4 = 0", "(x - 2)^2 = 0"], ["2"]),
        (["2x^2 = 18", "x^2 = 9"], ["-3", "3"]),
        (["3(x + 2) = 15", "3x + 6 = 15"], ["3"]),
        (["x^2 + 1 = 0", "x^2 = -1"], []),
        (["2(x + 1) = 2x + 2", "2x + 2 = 2x + 2"], []),
    ],
)
def test_incomplete_work_is_completed(steps, final):
    c = correct_full(steps)
    assert c.status is CorrectionStatus.COMPLETED
    assert c.corrected_step is None and c.first_error_step is None
    assert [s.text for s in c.corrected_solution[: len(steps)]] == steps
    assert c.final_solution.value_strings() == final
    assert_correction_verifies(c)


def test_correct_work_needs_no_correction():
    assert correct_full(["2x + 5 = 15", "2x = 10", "x = 5"]).status is CorrectionStatus.NO_CORRECTION_NEEDED


@pytest.mark.parametrize(
    "steps",
    [["x^3 = 8", "x = 2"], ["x + y = 5", "x = 5 - y"], ["2x = 4", "x^3 = 8", "x = 3"], ["__import__('os') = 0", "x = 1"]],
)
def test_unsupported_input_is_never_corrected(steps):
    c = correct_full(steps)
    assert c.status is CorrectionStatus.NEEDS_REVIEW
    assert c.corrected_solution == [] and c.corrected_step is None


def test_error_before_unsupported_step_is_still_corrected():
    c = correct_full(["2x = 4", "x = 3", "y = 3"])
    assert c.status is CorrectionStatus.CORRECTED
    assert c.corrected_step.text == "x = 2"
    assert_correction_verifies(c)




def _curated_incorrect():
    cases = json.loads((EXAMPLES / "incorrect_solutions.json").read_text(encoding="utf-8"))
    return [pytest.param(c["steps"], id=c["id"]) for c in cases]


@pytest.mark.parametrize("steps", _curated_incorrect())
def test_every_curated_correction_verifies(steps):
    c = correct_full(steps)
    if verify_steps(steps).overall_status in (OverallStatus.INCORRECT, OverallStatus.INCOMPLETE):
        assert c.status in (CorrectionStatus.CORRECTED, CorrectionStatus.COMPLETED)
        assert_correction_verifies(c)
    else:
        assert c.status is CorrectionStatus.NEEDS_REVIEW


# ------------------------------------------------------------------- guided

DEMO2 = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]


def test_guided_hints_escalate_and_reveal_only_at_level_3():
    g1 = correct_guided(DEMO2, hint_level=1)
    g2 = correct_guided(DEMO2, hint_level=2)
    g3 = correct_guided(DEMO2, hint_level=3)
    assert g1.status is GuidedStatus.NEEDS_ATTEMPT and g1.phase == "FIX_ERROR"
    assert g1.first_error_step == 3 and g1.current_step == "2x = 15 - 5"
    assert g1.error_category is C.ADDITION_SUBTRACTION_ERROR
    assert not g1.reveal_answer and not g2.reveal_answer and g1.revealed_step is None
    assert g1.hint != g2.hint
    for g in (g1, g2):
        assert "10" not in g.hint and "10" not in g.explanation  # never leaks the answer
    assert g3.reveal_answer and g3.revealed_step == "2x = 10"
    assert g3.revealed_step == correct_full(DEMO2).corrected_step.text


def test_guided_rejects_wrong_attempt_with_diagnosis():
    g = correct_guided(DEMO2, attempt="2x = 11")
    assert g.status is GuidedStatus.REJECTED
    fb = g.attempt_feedback
    assert not fb.valid and fb.reason_code == "SOLUTIONS_CHANGED"
    assert fb.lost == (5,)
    assert fb.category is C.ADDITION_SUBTRACTION_ERROR
    assert g.hint and not g.reveal_answer


def test_guided_unreadable_attempt():
    g = correct_guided(DEMO2, attempt="2x + = 10")
    assert g.status is GuidedStatus.ATTEMPT_UNREADABLE
    assert g.attempt_feedback.error_code == "SYNTAX_ERROR"


def test_guided_no_progress():
    assert correct_guided(DEMO2, attempt="2x = 15 - 5").status is GuidedStatus.NO_PROGRESS


def test_guided_accepts_then_solves():
    g = correct_guided(DEMO2, attempt="2x = 10")
    assert g.status is GuidedStatus.ACCEPTED
    assert g.current_step == "2x = 10" and g.step_number == 4 and g.hint
    done = correct_guided(DEMO2, progress=["2x = 10"], attempt="x = 5")
    assert done.status is GuidedStatus.SOLVED
    assert done.final_solution.value_strings() == ["5"]


def test_guided_accepts_a_different_valid_route():
    # Student fixes the error by dividing straight away instead of simplifying first.
    g = correct_guided(DEMO2, attempt="x = 5")
    assert g.status is GuidedStatus.SOLVED


def test_guided_incomplete_final_answer_in_progress_is_rejected():
    steps = ["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]
    g = correct_guided(steps, attempt="x - 3 = 0")
    assert g.status is GuidedStatus.REJECTED
    assert g.attempt_feedback.category is C.LOST_FACTOR




def test_guided_continue_phase_for_incomplete_work():
    g = correct_guided(["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"])
    assert g.status is GuidedStatus.NEEDS_ATTEMPT and g.phase == "CONTINUE"
    assert g.first_error_step is None and g.expected_rule.startswith("Zero-product")


def test_guided_correct_and_unsupported():
    assert correct_guided(["2x = 4", "x = 2"]).status is GuidedStatus.NO_CORRECTION_NEEDED
    assert correct_guided(["x^3 = 8", "x = 2"]).status is GuidedStatus.NEEDS_REVIEW


@pytest.mark.parametrize("steps", [c[0] for c in CASES] + [["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"]])
def test_guided_walkthrough_reaches_verified_solution(steps):
    """A student who follows each revealed step always ends at a complete, verified answer."""
    progress: list[str] = []
    for _ in range(12):
        reveal = correct_guided(steps, progress=progress, hint_level=3)
        if reveal.status is GuidedStatus.SOLVED:
            break
        assert reveal.status is GuidedStatus.NEEDS_ATTEMPT, reveal
        result = correct_guided(steps, progress=progress, attempt=reveal.revealed_step)
        assert result.status in (GuidedStatus.ACCEPTED, GuidedStatus.SOLVED), result
        progress.append(reveal.revealed_step)
        if result.status is GuidedStatus.SOLVED:
            break
    else:
        pytest.fail("guided walkthrough did not terminate")
    first_error = verify_steps(steps).first_error_step
    kept = steps[: first_error - 1] if first_error else steps
    assert progress, "a correction should require at least one new step"
    guided_result = verify_steps(kept + progress)
    assert guided_result.overall_status is OverallStatus.CORRECT
    # Guided and FULL corrections agree on the answer (FULL may add a final tidy-up step).
    full = correct_full(steps)
    assert guided_result.completeness.submitted.value_strings() == full.final_solution.value_strings()
    assert compact(progress[0]) == compact((full.corrected_step or full.continuation[0]).text)
