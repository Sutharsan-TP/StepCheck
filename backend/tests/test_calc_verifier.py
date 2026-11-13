"""Curated calculus cases (examples/calculus_solutions.json) and verifier behaviour."""

import json
from pathlib import Path

import pytest

from app.core.calculus.calc_verifier import verify_calculus
from app.core.calculus.sandbox import Sandbox
from app.core.types import OverallStatus, StepStatus

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "calculus_solutions.json"
CASES = json.loads(EXAMPLES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def box():
    sandbox = Sandbox(workers=1)
    sandbox.warm_up()
    yield sandbox
    sandbox.shutdown()


def test_curated_suite_covers_every_topic():
    assert len(CASES) >= 40
    topics = {c["expected"]["topic"] for c in CASES}
    assert topics == {"DERIVATIVE", "INTEGRAL", "DEFINITE_INTEGRAL", "LIMIT"}
    statuses = {c["expected"]["overall_status"] for c in CASES}
    assert statuses == {"CORRECT", "INCORRECT", "INCOMPLETE", "NEEDS_REVIEW", "UNSUPPORTED"}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_curated_case(case, box):
    result = verify_calculus(case["steps"], sandbox=box)
    expected = case["expected"]
    assert result.topic == expected["topic"]
    assert result.overall_status.value == expected["overall_status"]
    assert result.first_error_step == expected["first_error_step"]
    assert [s.status.value for s in result.steps] == expected["step_statuses"]
    if "missing_constant" in expected:
        assert result.missing_constant is expected["missing_constant"]


def test_first_error_carries_evidence(box):
    result = verify_calculus(["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"], sandbox=box)
    transition = result.transitions[0]
    assert transition.status is StepStatus.FIRST_INVALID
    assert transition.reason_code == "NOT_EQUAL"
    assert transition.compared_to_step == 1
    assert transition.counterexample.startswith("x = ")
    assert transition.found_value_latex == r"2 x \cos{\left(x \right)}"
    assert result.expected_answer == "x*(x*cos(x) + 2*sin(x))"


def test_complete_answer_step_requires_constant_for_integrals(box):
    assert verify_calculus(["int(2x) dx", "x^2", "x^2 + C"], sandbox=box).complete_answer_step == 3
    assert verify_calculus(["d/dx(x^2)", "2x"], sandbox=box).complete_answer_step == 2


def test_error_on_the_problem_line_itself(box):
    result = verify_calculus(["d/dx(x^3) = 3x", "3x^2"], sandbox=box)
    assert result.first_error_step == 1
    assert [s.status for s in result.steps] == [StepStatus.FIRST_INVALID, StepStatus.DOWNSTREAM_DEPENDENT]


def test_problem_line_without_an_operator_needs_review(box):
    result = verify_calculus(["[x^2][0, 1]", "1"], sandbox=box)
    assert result.overall_status is OverallStatus.NEEDS_REVIEW
    assert "derivative, an integral or a limit" in result.steps[0].analysis.error.message


def test_running_out_of_time_needs_review_never_a_verdict(box):
    result = verify_calculus(["d/dx(x^2 sin(x))", "2x sin(x) + x^2 cos(x)", "2x cos(x)"], sandbox=box, budget=0)
    assert result.overall_status is OverallStatus.NEEDS_REVIEW
    assert result.first_error_step is None
    assert result.transitions[0].reason_code == "TIMEOUT"


def test_step_equal_only_for_positive_x_is_noted(box):
    result = verify_calculus(["d/dx(x ln(x^2))", "2ln(x) + 2"], sandbox=box)
    assert result.overall_status is OverallStatus.CORRECT
    assert result.notes == ["Step 2: equal for x > 0."]
