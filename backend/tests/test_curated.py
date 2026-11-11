"""Curated end-to-end cases from examples/*.json (also used for demos)."""

import json
from pathlib import Path

import pytest

from app.core.first_error_detector import verify_steps

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _load():
    cases = []
    for name in ("correct_solutions.json", "incorrect_solutions.json"):
        for case in json.loads((EXAMPLES / name).read_text(encoding="utf-8")):
            cases.append(pytest.param(case, id=case["id"]))
    return cases


CASES = _load()


def test_curated_suite_is_large_enough():
    assert len(CASES) >= 24


@pytest.mark.parametrize("case", CASES)
def test_curated_case(case):
    expected = case["expected"]
    r = verify_steps(case["steps"])
    assert r.overall_status.value == expected["overall_status"]
    assert r.first_error_step == expected["first_error_step"]
    assert [s.status.value for s in r.steps] == expected["step_statuses"]
    if expected["correct_solution"] is None:
        assert r.correct_solution is None
    else:
        assert r.correct_solution.value_strings() == expected["correct_solution"]
    if "correct_solution_type" in expected:
        assert r.correct_solution.kind.value == expected["correct_solution_type"]
    assert r.completeness.solution_complete == expected["solution_complete"]
