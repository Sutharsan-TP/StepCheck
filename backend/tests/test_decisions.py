"""Tests for the three approved architecture decisions and engine consistency.

1. In-memory verification storage (UUID ids, TTL, capacity, expired vs missing).
2. Stateless guided correction (server re-verifies all progress; tokens bind it).
3. A complete answer before a later invalid/unnecessary step: recommend removal.
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.correction_engine import (
    CorrectionAction,
    CorrectionStatus,
    GuidedStatus,
    InvalidProgress,
    StepSource,
    correct_full,
    correct_guided,
)
from app.core.first_error_detector import check_completeness, is_complete_answer, verify_steps
from app.core.types import FinalAnswerStatus, OverallStatus, StepStatus
from app.main import app
from app.services import progress_token
from app.services.verification_store import LookupStatus, VerificationStore, verification_store

client = TestClient(app, raise_server_exceptions=False)
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DEMO2 = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _result(steps=("2x = 4", "x = 2")):
    return verify_steps(list(steps))


# --------------------------------------------------------- 1. verification storage


def test_ids_are_canonical_uuid4():
    vid = VerificationStore().save(["2x = 4", "x = 2"], _result())
    assert str(uuid.UUID(vid)) == vid and uuid.UUID(vid).version == 4


def test_store_keeps_steps_and_result():
    store = VerificationStore()
    result = _result()
    lookup = store.get(store.save(["2x = 4", "x = 2"], result))
    assert lookup.status is LookupStatus.FOUND
    assert lookup.entry.steps == ("2x = 4", "x = 2")
    assert lookup.entry.result is result


def test_ttl_is_one_hour_and_expired_is_distinguished_from_missing():
    clock = FakeClock()
    store = VerificationStore(clock=clock)
    vid = store.save(["2x = 4", "x = 2"], _result())
    clock.now += 3599
    assert store.get(vid).status is LookupStatus.FOUND
    clock.now += 2
    assert store.get(vid).status is LookupStatus.EXPIRED
    assert store.get(str(uuid.uuid4())).status is LookupStatus.NOT_FOUND


def test_default_limits():
    store = VerificationStore()
    assert store._ttl == 3600 and store._max == 1000


def test_capacity_evicts_expired_entries_before_oldest_live_ones():
    clock = FakeClock()
    store = VerificationStore(ttl_seconds=100, max_entries=3, clock=clock)
    old_live = store.save(["a"], _result())
    clock.now += 60
    second = store.save(["b"], _result())
    third = store.save(["c"], _result())
    clock.now += 50  # only the first entry has expired
    newest = store.save(["d"], _result())
    assert store.get(old_live).status is LookupStatus.EXPIRED
    assert all(store.get(v).status is LookupStatus.FOUND for v in (second, third, newest))
    assert len(store) == 3


def test_capacity_evicts_oldest_when_nothing_expired():
    store = VerificationStore(max_entries=2)
    ids = [store.save([str(i)], _result()) for i in range(3)]
    assert store.get(ids[0]).status is LookupStatus.EXPIRED  # evicted ids report as expired
    assert store.get(ids[1]).status is LookupStatus.FOUND
    assert store.get(ids[2]).entry.steps == ("2",)
    assert len(store) == 2


def test_api_expired_id_returns_structured_410(monkeypatch):
    clock = FakeClock()
    store = VerificationStore(clock=clock)
    monkeypatch.setattr("app.api.routes.correct.verification_store", store)
    vid = store.save(DEMO2, verify_steps(DEMO2))
    clock.now += 3601
    r = client.post("/api/v1/correct", json={"verification_id": vid, "mode": "FULL"})
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "VERIFICATION_EXPIRED"


def test_api_missing_id_returns_structured_404():
    r = client.post("/api/v1/correct", json={"verification_id": str(uuid.uuid4()), "mode": "GUIDED"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "VERIFICATION_NOT_FOUND"


def test_verify_stores_result_under_returned_uuid():
    body = client.post("/api/v1/verify", json={"steps": DEMO2}).json()
    entry = verification_store.get(body["verification_id"]).entry
    assert entry.steps == tuple(DEMO2)
    assert entry.result.first_error_step == body["first_error_step"] == 3


def test_direct_submission_with_context_needs_no_id():
    r = client.post(
        "/api/v1/correct", json={"steps": DEMO2, "variable": "x", "domain": "REAL", "mode": "FULL"}
    )
    assert r.status_code == 200 and r.json()["full"]["corrected_step"]["text"] == "2x = 10"
    bad = client.post("/api/v1/correct", json={"steps": DEMO2, "variable": "y", "mode": "FULL"})
    assert bad.status_code == 422


# ------------------------------------------------------ 2. stateless guided correction


def _guided(**payload):
    return client.post("/api/v1/correct", json={"steps": DEMO2, "mode": "GUIDED", **payload})


def test_progress_is_rejected_without_the_server_token():
    r = _guided(progress=["2x = 10"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_forged_or_mismatched_token_is_rejected():
    forged = _guided(progress=["2x = 10"], progress_token="0" * 64)
    assert forged.status_code == 422 and forged.json()["error"]["code"] == "PROGRESS_TOKEN_INVALID"
    # A real token for a *different* solution cannot be replayed here.
    other = ["2x + 1 = 11", "2x = 12", "x = 6"]
    token = progress_token.sign(other, ["2x = 10"])
    reused = _guided(progress=["2x = 10"], progress_token=token)
    assert reused.json()["error"]["code"] == "PROGRESS_TOKEN_INVALID"


def test_client_correctness_claims_are_rejected():
    r = _guided(attempt="2x = 11", status="ACCEPTED", valid=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"
    r = client.post("/api/v1/verify", json={"steps": DEMO2, "overall_status": "CORRECT"})
    assert r.status_code == 422


def test_server_reverifies_progress_even_with_a_valid_token():
    # Even a correctly signed token cannot smuggle in an invalid step.
    token = progress_token.sign(DEMO2, ["2x = 12"])
    r = _guided(progress=["2x = 12"], progress_token=token)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_PROGRESS"


@pytest.mark.parametrize(
    "progress, reason",
    [
        (["2x = 12"], "not a valid transformation"),  # skipping past the error with another error
        (["2x + = 10"], "could not be read"),
        (["2x = 15 - 5"], "repeats the previous step"),
        (["2x = 10", "2x = 10"], "repeats the previous step"),
        (["x = 5", "2x = 10"], "after the solution was already complete"),
        (["2x = 10", "x = 6"], "not a valid transformation"),
    ],
)
def test_engine_never_accepts_invalid_progress(progress, reason):
    with pytest.raises(InvalidProgress) as info:
        correct_guided(DEMO2, progress=progress)
    assert reason in info.value.message


def test_progress_not_allowed_when_nothing_to_correct():
    with pytest.raises(InvalidProgress):
        correct_guided(["2x = 4", "x = 2"], progress=["x = 2"])
    with pytest.raises(InvalidProgress):
        correct_guided(["x^3 = 8", "x = 2"], progress=["x = 2"])


def test_returned_progress_is_exactly_what_the_server_accepted():
    rejected = correct_guided(DEMO2, attempt="2x = 11")
    assert rejected.status is GuidedStatus.REJECTED and rejected.progress == []
    accepted = correct_guided(DEMO2, attempt="2x = 10")
    assert accepted.progress == ["2x = 10"]
    no_progress = correct_guided(DEMO2, progress=["2x = 10"], attempt="2x = 10")
    assert no_progress.status is GuidedStatus.NO_PROGRESS and no_progress.progress == ["2x = 10"]


def test_full_guided_session_over_api_with_tokens():
    state = _guided().json()["guided"]
    for _ in range(10):
        reveal = _guided(progress=state["progress"], progress_token=state["progress_token"], hint_level=3).json()
        attempt = reveal["guided"]["revealed_step"]
        nxt = _guided(progress=state["progress"], progress_token=state["progress_token"], attempt=attempt).json()
        assert nxt["status"] in ("ACCEPTED", "SOLVED")
        state = nxt["guided"]
        if nxt["status"] == "SOLVED":
            break
    assert state["progress"] == ["2x = 10", "x = 5"]
    assert verify_steps(DEMO2[:2] + state["progress"]).overall_status is OverallStatus.CORRECT


def test_attempt_and_progress_limits():
    too_many = ["x = 5"] * 21
    assert _guided(progress=too_many, progress_token="x").status_code == 422
    assert _guided(attempt="1" * 201).status_code == 422
    assert _guided(hint_level=4).status_code == 422


# ------------------------------------------- 3. complete answer before a later step


def test_spec_example_remove_final_step():
    steps = ["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"]
    c = correct_full(steps)
    assert c.status is CorrectionStatus.CORRECTED
    assert c.action is CorrectionAction.REMOVE_REMAINING_STEPS
    assert c.complete_answer_step == 3 and c.first_error_step == 4
    assert [s.text for s in c.corrected_solution] == steps[:3]  # preserved verbatim
    assert all(s.source is StepSource.STUDENT for s in c.corrected_solution)
    assert c.corrected_step is None and c.continuation == []  # nothing invented
    assert [(r.step_number, r.text, r.kind) for r in c.removed_steps] == [(4, "x = 10", "INCORRECT")]
    assert "already complete at step 3" in c.message and "Remove step 4" in c.message
    assert c.diagnosis is not None  # step 4 is still explained
    assert c.verification.overall_status is OverallStatus.CORRECT


def test_several_removed_steps_are_each_identified():
    c = correct_full(["2x + 5 = 15", "2x = 10", "x = 5", "x = 10", "x - 10 = 0"])
    assert [(r.step_number, r.status, r.kind) for r in c.removed_steps] == [
        (4, StepStatus.FIRST_INVALID, "INCORRECT"),
        (5, StepStatus.DOWNSTREAM_DEPENDENT, "INCORRECT"),
    ]
    assert "steps 4–5" in c.message


def test_valid_but_unnecessary_trailing_step():
    steps = ["2x + 5 = 15", "x = 5", "2x = 10"]
    assert verify_steps(steps).overall_status is OverallStatus.INCOMPLETE
    c = correct_full(steps)
    assert c.action is CorrectionAction.REMOVE_REMAINING_STEPS
    assert [s.text for s in c.corrected_solution] == steps[:2]
    assert c.removed_steps[0].kind == "UNNECESSARY" and c.first_error_step is None


def test_unverifiable_trailing_step_after_complete_answer():
    c = correct_full(["2x = 4", "x = 2", "y = 3"])
    assert c.action is CorrectionAction.REMOVE_REMAINING_STEPS
    assert c.removed_steps[0].kind == "UNVERIFIABLE"


@pytest.mark.parametrize(
    "steps, complete_at",
    [
        (["x^2 = 9", "x = 3 or x = -3", "x = 3"], 2),
        (["x + 1 = x + 2", "1 = 2", "x = 5"], 2),
        (["x^2 - 5x + 6 = 0", "x = (5 ± sqrt(1))/2", "x = 2"], 2),
        (["5x = 20", "x = 20/5", "x = 3"], 2),
    ],
)
def test_complete_answer_forms(steps, complete_at):
    c = correct_full(steps)
    assert c.action is CorrectionAction.REMOVE_REMAINING_STEPS and c.complete_answer_step == complete_at


def test_guided_reports_already_complete():
    g = correct_guided(["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"])
    assert g.status is GuidedStatus.ALREADY_COMPLETE
    assert g.complete_answer_step == 3 and g.current_step == "x = 5"
    assert [r.step_number for r in g.removed_steps] == [4]
    assert g.revealed_step is None and g.hint is None


def test_api_exposes_removal():
    body = client.post(
        "/api/v1/correct", json={"steps": ["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"], "mode": "FULL"}
    ).json()
    full = body["full"]
    assert full["action"] == "REMOVE_REMAINING_STEPS" and full["complete_answer_step"] == 3
    assert full["removed_steps"] == [
        {"step_number": 4, "text": "x = 10", "status": "FIRST_INVALID", "kind": "INCORRECT",
         "reason": "This step changes the solutions of the equation."}
    ]
    verify = client.post("/api/v1/verify", json={"steps": ["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"]}).json()
    assert verify["complete_answer_step"] == 3


def test_error_before_any_complete_answer_still_replaces_the_step():
    c = correct_full(DEMO2)
    assert c.action is CorrectionAction.REPLACE_STEP and c.removed_steps == []


# ------------------------------------------------------------------ 4. consistency


def _all_cases():
    cases = []
    for name in ("correct_solutions.json", "incorrect_solutions.json"):
        cases += [c["steps"] for c in json.loads((EXAMPLES / name).read_text(encoding="utf-8"))]
    from tests.test_correction import CASES

    cases += [c[0] for c in CASES]
    cases += [
        ["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"],
        ["2x + 5 = 15", "x = 5", "2x = 10"],
        ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"],
        ["5x = 20", "x = 20/5", "x = 3"],
    ]
    return cases


@pytest.mark.parametrize("steps", _all_cases())
def test_engines_agree(steps):
    result = verify_steps(steps)
    analyses = [s.analysis for s in result.steps]
    target = result.correct_solution

    # Completeness checker == shared definition, on every step used as a final line.
    if target is not None:
        for a in analyses:
            comp = check_completeness(target, a)
            if comp.final_answer_status is FinalAnswerStatus.SOLVED:
                assert comp.final_answer_correct == is_complete_answer(a, target)

    # Verifier's CORRECT  <=>  final line is a complete answer and every step is valid.
    final_ok = is_complete_answer(analyses[-1], target)
    all_valid = all(s.status is StepStatus.VALID for s in result.steps)
    assert (result.overall_status is OverallStatus.CORRECT) == (final_ok and all_valid)
    if result.overall_status is OverallStatus.CORRECT:
        assert result.complete_answer_step is not None

    full = correct_full(steps)
    guided = correct_guided(steps)
    if result.overall_status is OverallStatus.CORRECT:
        assert full.status is CorrectionStatus.NO_CORRECTION_NEEDED
        assert guided.status is GuidedStatus.NO_CORRECTION_NEEDED
        return
    if full.status is CorrectionStatus.NEEDS_REVIEW:
        assert guided.status is GuidedStatus.NEEDS_REVIEW
        assert result.overall_status in (OverallStatus.UNSUPPORTED, OverallStatus.NEEDS_REVIEW)
        return

    # Every correction re-verifies as CORRECT and complete, through the same engine.
    corrected = verify_steps([s.text for s in full.corrected_solution])
    assert corrected.overall_status is OverallStatus.CORRECT
    assert corrected.completeness.solution_complete is True
    assert corrected.completeness.submitted.kind is target.kind
    assert corrected.completeness.submitted.value_strings() == target.value_strings()

    # FULL and GUIDED agree on what kind of fix is needed.
    if full.action is CorrectionAction.REMOVE_REMAINING_STEPS:
        assert guided.status is GuidedStatus.ALREADY_COMPLETE
        assert guided.complete_answer_step == full.complete_answer_step == result.complete_answer_step
    else:
        assert guided.status is GuidedStatus.NEEDS_ATTEMPT
        assert guided.first_error_step == full.first_error_step == result.first_error_step
        if full.corrected_step:
            revealed = correct_guided(steps, hint_level=3).revealed_step
            assert revealed == full.corrected_step.text
