import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

DEMO2 = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]
DEMO3 = ["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]


def verification_id(steps):
    r = client.post("/api/v1/verify", json={"steps": steps})
    assert r.status_code == 200
    return r.json()["verification_id"]


def correct(**payload):
    return client.post("/api/v1/correct", json=payload)


def test_full_correction_by_verification_id():
    r = correct(verification_id=verification_id(DEMO3), mode="FULL")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "FULL" and body["status"] == "CORRECTED"
    assert body["first_error_step"] == 3 and body["guided"] is None
    full = body["full"]
    assert full["original_step"] == "x - 2 = 0"
    assert full["error_category"] == "LOST_FACTOR"
    assert full["corrected_step"]["text"] == "x - 2 = 0 or x - 3 = 0"
    assert full["corrected_step"]["source"] == "CORRECTED"
    assert [s["source"] for s in full["corrected_solution"]] == ["STUDENT", "STUDENT", "CORRECTED", "GENERATED"]
    assert full["final_solution"] == {"type": "FINITE_SET", "values": ["2", "3"], "latex": ["2", "3"]}
    assert full["verification"] == {
        "overall_status": "CORRECT",
        "all_transitions_valid": True,
        "solution_complete": True,
    }
    assert all(s["latex"] for s in full["corrected_solution"])


def test_full_correction_with_inline_steps():
    body = correct(steps=DEMO2, mode="FULL").json()
    assert body["full"]["corrected_step"]["text"] == "2x = 10"


def test_guided_flow_over_api():
    vid = verification_id(DEMO2)
    start = correct(verification_id=vid, mode="GUIDED").json()
    assert start["status"] == "NEEDS_ATTEMPT"
    g = start["guided"]
    assert g["phase"] == "FIX_ERROR" and g["reveal_answer"] is False and g["revealed_step"] is None
    assert g["max_hint_level"] == 3 and g["hint"]

    wrong = correct(verification_id=vid, mode="GUIDED", attempt="2x = 11", hint_level=2).json()
    assert wrong["status"] == "REJECTED"
    assert wrong["guided"]["attempt_feedback"]["lost_solutions"] == ["5"]
    assert wrong["guided"]["attempt_feedback"]["extraneous_solutions"] == ["11/2"]

    reveal = correct(verification_id=vid, mode="GUIDED", hint_level=3).json()
    assert reveal["guided"]["reveal_answer"] is True
    assert reveal["guided"]["revealed_step"] == "2x = 10"

    ok = correct(verification_id=vid, mode="GUIDED", attempt="2x = 10").json()
    assert ok["status"] == "ACCEPTED"
    assert ok["guided"]["progress"] == ["2x = 10"]

    done = correct(
        verification_id=vid, mode="GUIDED", progress=ok["guided"]["progress"],
        progress_token=ok["guided"]["progress_token"], attempt="x = 5",
    ).json()
    assert done["status"] == "SOLVED"
    assert done["guided"]["final_solution"]["values"] == ["5"]
    assert done["guided"]["progress"] == ["2x = 10", "x = 5"]


def test_correct_solution_needs_no_correction():
    body = correct(steps=["2x + 5 = 15", "2x = 10", "x = 5"], mode="FULL").json()
    assert body["status"] == "NO_CORRECTION_NEEDED"


def test_unsupported_returns_needs_review_without_correction():
    body = correct(steps=["x^3 = 8", "x = 2"], mode="FULL").json()
    assert body["status"] == "NEEDS_REVIEW"
    assert body["full"]["corrected_step"] is None and body["full"]["corrected_solution"] == []


def test_unknown_verification_id_is_404():
    r = correct(verification_id=str(uuid.uuid4()), mode="FULL")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "VERIFICATION_NOT_FOUND"


def test_malformed_verification_id_is_422():
    assert correct(verification_id="does-not-exist", mode="FULL").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "FULL"},  # no source
        {"mode": "FULL", "steps": DEMO2, "verification_id": str(uuid.uuid4())},  # two sources
        {"mode": "PARTIAL", "steps": DEMO2},
        {"mode": "GUIDED", "steps": DEMO2, "hint_level": 4},
        {"mode": "GUIDED", "steps": DEMO2, "hint_level": 0},
        {"mode": "FULL", "steps": DEMO2, "attempt": "2x = 10"},
        {"mode": "GUIDED", "steps": DEMO2, "progress": ["x = 5"] * 21},
        {"mode": "GUIDED", "steps": DEMO2, "attempt": "x" * 201},
    ],
)
def test_invalid_correct_requests(payload):
    r = client.post("/api/v1/correct", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_REQUEST"
