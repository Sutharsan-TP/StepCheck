from app.core.first_error_detector import verify_steps
from app.core.types import FinalAnswerStatus, OverallStatus, StepStatus

V, FI, DD, UN, NR = (
    StepStatus.VALID,
    StepStatus.FIRST_INVALID,
    StepStatus.DOWNSTREAM_DEPENDENT,
    StepStatus.UNSUPPORTED,
    StepStatus.NEEDS_REVIEW,
)


def statuses(result):
    return [s.status for s in result.steps]


def test_demo_1_correct_linear():
    r = verify_steps(["2x + 5 = 15", "2x = 10", "x = 5"])
    assert r.overall_status is OverallStatus.CORRECT
    assert r.first_error_step is None
    assert statuses(r) == [V, V, V]
    assert r.correct_solution.value_strings() == ["5"]
    assert r.completeness.submitted.value_strings() == ["5"]
    assert r.completeness.solution_complete is True
    assert r.completeness.final_answer_correct is True


def test_demo_2_first_error_detection():
    r = verify_steps(["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"])
    assert r.overall_status is OverallStatus.INCORRECT
    assert r.first_error_step == 3
    assert statuses(r) == [V, V, FI, DD]
    t = r.transitions
    assert [x.status for x in t] == [V, FI, DD]
    assert t[1].reason_code == "SOLUTIONS_CHANGED"
    assert t[1].lost == (5,) and t[1].extraneous == (10,)
    # Step 4 follows correctly from step 3 but not from the original problem.
    assert t[2].locally_valid is True and t[2].matches_original is False
    assert r.completeness.missing == (5,)
    assert r.completeness.final_answer_correct is False


def test_demo_3_lost_quadratic_solution():
    r = verify_steps(["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"])
    assert r.overall_status is OverallStatus.INCORRECT
    assert r.first_error_step == 3
    assert statuses(r) == [V, V, FI, DD]
    assert r.transitions[1].reason_code == "LOST_SOLUTIONS"
    assert r.transitions[1].lost == (3,)
    assert r.correct_solution.value_strings() == ["2", "3"]
    c = r.completeness
    assert c.solution_complete is False
    assert c.missing == (3,)
    assert c.extraneous == ()


def test_complete_quadratic_solution():
    r = verify_steps(["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0 or x - 3 = 0", "x = 2 or x = 3"])
    assert r.overall_status is OverallStatus.CORRECT
    assert r.completeness.solution_complete is True


def test_lost_solution_by_dividing_by_x():
    r = verify_steps(["x^2 = x", "x = 1"])
    assert r.first_error_step == 2
    assert r.transitions[0].reason_code == "LOST_SOLUTIONS"
    assert r.transitions[0].lost == (0,)


def test_error_then_cancelling_error_is_still_incorrect():
    # 2x = 10 -> 2x = 12 (wrong) -> x = 5 (wrong again, happens to match)
    r = verify_steps(["2x + 5 = 15", "2x = 12", "x = 5"])
    assert r.overall_status is OverallStatus.INCORRECT
    assert r.first_error_step == 2
    assert statuses(r) == [V, FI, DD]
    assert r.transitions[1].matches_original is True
    assert r.transitions[1].locally_valid is False
    assert r.completeness.final_answer_correct is True  # reported separately


def test_multiplying_by_zero_becomes_identity():
    r = verify_steps(["2x = 10", "0 = 0"])
    assert r.first_error_step == 2
    assert r.transitions[0].reason_code == "BECAME_IDENTITY"


def test_quadratic_formula_with_plus_minus():
    r = verify_steps(["x^2 - 5x + 3 = 0", "x = (5 ± sqrt(25 - 12))/2", "x = (5 ± sqrt(13))/2"])
    assert r.overall_status is OverallStatus.CORRECT


def test_quadratic_formula_arithmetic_error():
    r = verify_steps(["x^2 - 5x + 3 = 0", "x = (5 ± sqrt(25 + 12))/2"])
    assert r.first_error_step == 2
    assert r.transitions[0].reason_code == "SOLUTIONS_CHANGED"


def test_shorthand_final_answer():
    r = verify_steps(["x^2 = 9", "x = 3 or -3"])
    assert r.overall_status is OverallStatus.CORRECT


def test_no_solution_literal():
    r = verify_steps(["x + 1 = x + 2", "1 = 2", "no solution"])
    assert r.overall_status is OverallStatus.CORRECT
    assert r.completeness.solution_complete is True


def test_wrong_no_solution_claim():
    r = verify_steps(["x^2 = 4", "no real solution"])
    assert r.first_error_step == 2
    assert r.transitions[0].reason_code == "BECAME_CONTRADICTION"


def test_identity_solution():
    r = verify_steps(["2(x + 1) = 2x + 2", "2x + 2 = 2x + 2", "all real numbers"])
    assert r.overall_status is OverallStatus.CORRECT


def test_final_answer_not_isolated_is_incomplete():
    r = verify_steps(["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"])
    assert r.overall_status is OverallStatus.INCOMPLETE
    assert r.completeness.final_answer_status is FinalAnswerStatus.NOT_ISOLATED
    assert r.completeness.solution_complete is False


def test_extraneous_root_in_final_answer():
    r = verify_steps(["x = 2", "x^2 = 4", "x = 2 or x = -2"])
    assert r.first_error_step == 2
    assert r.completeness.extraneous == (-2,)
    assert r.completeness.includes_extraneous is True


def test_unsupported_step_bridged_successfully():
    r = verify_steps(["2x = 4", "sin(x) = 2", "x = 2"])
    assert statuses(r) == [V, UN, V]
    assert r.transitions[1].compared_to_step == 1
    assert r.first_error_step is None
    assert r.overall_status is OverallStatus.UNSUPPORTED


def test_error_after_unsupported_step_is_not_localised():
    r = verify_steps(["2x = 4", "x^3 = 8", "x = 3", "x - 3 = 0"])
    assert statuses(r) == [V, UN, NR, NR]
    assert r.transitions[1].reason_code == "AMBIGUOUS_ERROR_LOCATION"
    assert r.transitions[2].reason_code == "AFTER_UNRESOLVED_STEP"
    assert r.first_error_step is None
    assert r.overall_status is OverallStatus.NEEDS_REVIEW


def test_error_after_reanchoring_is_localised():
    r = verify_steps(["2x = 4", "sin(x) = 2", "x = 2", "x = 3"])
    assert statuses(r) == [V, UN, V, FI]
    assert r.first_error_step == 4
    assert r.overall_status is OverallStatus.INCORRECT


def test_unverifiable_step_after_first_error():
    r = verify_steps(["2x = 4", "x = 3", "y = 3"])
    assert statuses(r) == [V, FI, UN]
    assert r.overall_status is OverallStatus.INCORRECT
    assert r.completeness.final_answer_status is FinalAnswerStatus.UNVERIFIABLE


def test_unsupported_original_problem():
    r = verify_steps(["x^3 = 8", "x = 2"])
    assert r.overall_status is OverallStatus.UNSUPPORTED
    assert statuses(r) == [UN, NR]
    assert r.correct_solution is None
    assert r.transitions[0].reason_code == "NO_VERIFIED_REFERENCE"


def test_unparseable_original_problem():
    r = verify_steps(["2x + = 5", "x = 2"])
    assert r.overall_status is OverallStatus.NEEDS_REVIEW


def test_syntax_error_mid_solution():
    r = verify_steps(["2x + 5 = 15", "2x = = 10", "x = 5"])
    assert statuses(r) == [V, NR, V]
    assert r.overall_status is OverallStatus.NEEDS_REVIEW
