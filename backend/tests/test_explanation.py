"""Explanations: the engine decides, the LLM only phrases — with deterministic fallbacks."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.schemas.explanation import LLMExplanation
from app.main import app
from app.services.explanation_service import explain
from app.services.openrouter_client import OpenRouterClient, get_openrouter_client

client = TestClient(app, raise_server_exceptions=False)
DEMO2 = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]
DEMO3 = ["x² - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"]


def llm_reply(**fields):
    body = {
        "explanation": "In step 3 you wrote 2x = 20, but 15 - 5 is 10, so the right-hand side should be 10.",
        "why_invalid": "Simplifying one side must keep its value the same.",
        "how_to_avoid": "Work out subtraction carefully before moving on.",
        "learning_tip": "Check each side's arithmetic separately.",
    }
    body.update(fields)
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})


def ai(*responses, key="test-key", seen=None):
    queue = list(responses)

    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return queue.pop(0)

    async def no_sleep(_):
        return None

    return OpenRouterClient(api_key=key, models={"text": "text/model"}, max_retries=1,
                            transport=httpx.MockTransport(handler), sleep=no_sleep)


def run(steps, c):
    return asyncio.run(explain(steps, c))


def test_llm_prose_with_engine_facts():
    seen = []
    r = run(DEMO2, ai(llm_reply(), seen=seen))
    assert r.source == "LLM" and r.ai_status is None
    assert r.explanation.startswith("In step 3")
    # Mathematical fields always come from the engine:
    assert r.overall_status == "INCORRECT" and r.first_error_step == 3
    assert r.error_category == "ADDITION_SUBTRACTION_ERROR"
    assert r.corrected_step == "2x = 10" and r.suggested_next_step == "x = 5"
    assert r.correction_action == "REPLACE_STEP"
    facts = seen[0]["messages"][1]["content"]
    assert '"first_error_step": 3' in facts and "2x = 10" in facts
    assert "engine is always right" in seen[0]["messages"][0]["content"]


def test_llm_cannot_override_engine_fields():
    # Even if the model returns extra "math" fields, they are ignored.
    r = run(DEMO2, ai(llm_reply(corrected_step="2x = 99", error_category="NONE")))
    assert r.corrected_step == "2x = 10" and r.error_category == "ADDITION_SUBTRACTION_ERROR"


@pytest.mark.parametrize(
    "bad",
    [
        {"explanation": "Great job, your solution is correct!"},
        {"explanation": "There are no mistakes here."},
        {"explanation": "The right-hand side should be 12."},  # invented number
        {"learning_tip": "Remember that x = 7.5 here."},
    ],
)
def test_contradicting_or_inventing_prose_falls_back_to_template(bad):
    r = run(DEMO2, ai(llm_reply(**bad)))
    assert r.source == "TEMPLATE" and r.ai_status == "REJECTED_BY_GUARD"
    assert "15 - 5" in r.explanation and r.corrected_step == "2x = 10"


@pytest.mark.parametrize(
    "responses, status",
    [
        ((), "AI_UNAVAILABLE"),
        ((httpx.Response(429), httpx.Response(429)), "AI_RATE_LIMITED"),
        ((httpx.Response(200, text="garbage"), httpx.Response(200, text="garbage")), "AI_MALFORMED_RESPONSE"),
        ((httpx.ReadTimeout("t"), httpx.ReadTimeout("t")), "AI_PROVIDER_ERROR"),
    ],
)
def test_ai_failures_fall_back_to_template(responses, status):
    def raising(*items):
        queue = list(items)

        def handler(request):
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        async def no_sleep(_):
            return None

        key = "" if not items else "k"
        return OpenRouterClient(api_key=key, models={"text": "m"}, max_retries=1,
                                transport=httpx.MockTransport(handler), sleep=no_sleep)

    r = run(DEMO3, raising(*responses))
    assert r.source == "TEMPLATE" and r.ai_status == status
    assert r.error_category == "LOST_FACTOR"
    assert "Lost: x = 3" in r.explanation
    assert r.corrected_step == "x - 2 = 0 or x - 3 = 0"


@pytest.mark.parametrize(
    "steps",
    [
        ["x^3 = 8", "x = 2"],  # unsupported
        ["2x + = 5", "x = 2"],  # unreadable
        ["2x + 5 = 15", "2x = 10", "x = 5"],  # correct
    ],
)
def test_no_model_call_without_a_verified_mistake(steps):
    seen = []
    r = run(steps, ai(seen=seen))
    assert r.source == "ENGINE" and seen == []
    assert r.corrected_step is None


def test_remove_steps_case_is_explained_without_inventing():
    r = run(["2x + 5 = 15", "2x = 10", "x = 5", "x = 10"], ai(key=""))
    assert r.correction_action == "REMOVE_REMAINING_STEPS"
    assert "already complete at step 3" in r.explanation
    assert r.corrected_step is None and r.suggested_next_step is None


def test_incomplete_work_suggests_verified_next_step():
    r = run(["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0"], ai(key=""))
    assert r.correction_action == "COMPLETE_SOLUTION"
    assert r.suggested_next_step == "x - 2 = 0 or x - 3 = 0"


def test_guard_allows_numbers_from_the_facts():
    from app.services.explanation_service import consistent_with_facts

    facts = {"overall_status": "INCORRECT", "x": "2x + 5 = 15, 2x = 10"}
    assert consistent_with_facts(LLMExplanation(explanation="Subtract 5 from 15 to get 10, step 2."), facts)
    assert not consistent_with_facts(LLMExplanation(explanation="That gives 11."), facts)


# ------------------------------------------------------------------ API


@pytest.fixture
def override():
    def install(c):
        app.dependency_overrides[get_openrouter_client] = lambda: c

    yield install
    app.dependency_overrides.clear()


def test_explain_endpoint_by_verification_id(override):
    override(ai(llm_reply()))
    vid = client.post("/api/v1/verify", json={"steps": DEMO2}).json()["verification_id"]
    r = client.post("/api/v1/explain", json={"verification_id": vid})
    assert r.status_code == 200 and r.json()["source"] == "LLM"


def test_explain_endpoint_rejects_client_verdicts(override):
    override(ai())
    r = client.post("/api/v1/explain", json={"steps": DEMO2, "verification": {"overall_status": "CORRECT"}})
    assert r.status_code == 422


def test_explain_endpoint_works_without_ai_key(override):
    override(ai(key=""))
    r = client.post("/api/v1/explain", json={"steps": DEMO2})
    assert r.status_code == 200 and r.json()["source"] == "TEMPLATE"
