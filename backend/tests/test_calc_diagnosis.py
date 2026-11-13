"""Mistake categories for calculus steps, and calculus explanations (AI mocked)."""

import asyncio
import json

import httpx
import pytest

from app.core.calculus.calc_diagnosis import CalcErrorCategory, diagnose_texts
from app.services.explanation_service import explain
from app.services.openrouter_client import OpenRouterClient


@pytest.mark.parametrize(
    "anchor, found, topic, category",
    [
        ("d/dx(x^2 sin(x))", "2x cos(x)", "DERIVATIVE", "PRODUCT_RULE_ERROR"),
        ("d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "DERIVATIVE", "PRODUCT_RULE_ERROR"),
        ("d/dx(x/(x + 1))", "(x - (x + 1))/(x + 1)^2", "DERIVATIVE", "QUOTIENT_RULE_ERROR"),
        ("d/dx(sin(x^2))", "cos(x^2)", "DERIVATIVE", "CHAIN_RULE_ERROR"),
        ("d/dx(e^(3x))", "e^(3x)", "DERIVATIVE", "CHAIN_RULE_ERROR"),
        ("d/dx(x^3)", "3x^3", "DERIVATIVE", "POWER_RULE_ERROR"),
        ("d/dx(3cos(x))", "3sin(x)", "DERIVATIVE", "TRIG_DERIVATIVE_SIGN_ERROR"),
        ("d/dx(x^3)", "5x", "DERIVATIVE", "GENERAL_ERROR"),
        ("int(x^2) dx", "x^3 + C", "INTEGRAL", "INTEGRAL_POWER_RULE_ERROR"),
        ("int(e^(2x)) dx", "e^(2x) + C", "INTEGRAL", "INTEGRAL_COEFFICIENT_ERROR"),
        ("int(sin(x)) dx", "cos(x) + C", "INTEGRAL", "INTEGRAL_TRIG_SIGN_ERROR"),
        ("int[1, 3](2x) dx", "[x^2][3, 1]", "DEFINITE_INTEGRAL", "LIMITS_SWAPPED"),
        ("[x^3/3][0, 2]", "8/3 - 1", "DEFINITE_INTEGRAL", "EVALUATION_ERROR"),
        ("8/3 - 0", "5/3", "DEFINITE_INTEGRAL", "SIMPLIFICATION_ERROR"),
        ("lim(x->1, (x + 1)/x)", "lim(x->1, 1/1)", "LIMIT", "LHOPITAL_NOT_APPLICABLE"),
        ("lim(x->0, sin(x)/x)", "lim(x->0, (x cos(x) - sin(x))/x^2)", "LIMIT", "LHOPITAL_QUOTIENT_ERROR"),
        ("lim(x->0, sin(3x)/x)", "1", "LIMIT", "GENERAL_ERROR"),
    ],
)
def test_mistake_category(anchor, found, topic, category):
    d = diagnose_texts(anchor, found, topic, 2)
    assert d.category == category
    assert d.explanation.startswith("Step 2") or category in ("MISSING_CONSTANT", "NOT_FINISHED")
    assert len(d.hints) == 2


def test_correct_lhopital_is_not_called_a_mistake():
    # 0/0, so L'Hopital applies; the (wrong) final value is a general error, not misuse of the rule.
    assert diagnose_texts("lim(x->0, sin(x)/x)", "lim(x->0, cos(x)/1)", "LIMIT", 2).category != "LHOPITAL_NOT_APPLICABLE"


def test_evidence_states_both_values():
    d = diagnose_texts("d/dx(x^3)", "3x^3", "DERIVATIVE", 2)
    assert d.evidence == "Step 2 works out to 3*x^3, but it should equal 3*x^2."


def test_every_category_has_teaching_text():
    from app.core.calculus.calc_diagnosis import _INFO

    assert set(_INFO) == set(CalcErrorCategory)


# --------------------------------------------------------------- explanations

PRODUCT_SLIP = ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"]


def ai(*responses, seen=None, key="test-key"):
    queue = list(responses)

    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return queue.pop(0)

    async def no_sleep(_):
        return None

    return OpenRouterClient(api_key=key, models={"text": "text/model"}, max_retries=1,
                            transport=httpx.MockTransport(handler), sleep=no_sleep)


def reply(**fields):
    body = {
        "explanation": "In step 2 you multiplied the two derivatives, which gives 2x cos(x).",
        "why_invalid": "The product rule says (fg)' = f'g + fg'.",
        "how_to_avoid": "Differentiate one factor at a time.",
        "learning_tip": "Product rule: first times derivative of second, plus second times derivative of first.",
    }
    body.update(fields)
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}]})


def run(steps, client):
    return asyncio.run(explain(steps, client))


def test_calculus_explanation_uses_engine_facts():
    seen = []
    r = run(PRODUCT_SLIP, ai(reply(), seen=seen))
    assert r.source == "LLM"
    assert r.overall_status == "INCORRECT" and r.first_error_step == 2
    assert r.error_category == "PRODUCT_RULE_ERROR"
    assert r.expected_rule == "Product rule: (fg)' = f'g + fg'"
    assert r.corrected_step is None and r.correction_action is None
    facts = json.loads(seen[0]["messages"][1]["content"].removeprefix("FACTS:\n"))
    assert facts["topic"] == "DERIVATIVE"
    assert facts["error_category"] == "PRODUCT_RULE_ERROR"
    assert facts["correct_final_answer"] == "x*(x*cos(x) + 2*sin(x))"


def test_calculus_falls_back_to_template_without_ai():
    r = run(PRODUCT_SLIP, ai(key=""))
    assert r.source == "TEMPLATE" and r.ai_status == "AI_UNAVAILABLE"
    assert r.explanation.startswith("Step 2 differentiates a product")
    assert r.why_invalid == "Rule: Product rule: (fg)' = f'g + fg'."


def test_guard_rejects_prose_that_praises_wrong_work():
    r = run(PRODUCT_SLIP, ai(reply(explanation="Your solution is correct, well done.")))
    assert r.source == "TEMPLATE" and r.ai_status == "REJECTED_BY_GUARD"


def test_missing_constant_is_explained():
    r = run(["int(2x) dx", "x^2"], ai(key=""))
    assert r.overall_status == "INCOMPLETE"
    assert r.error_category == "MISSING_CONSTANT"
    assert "+ C" in r.explanation


def test_correct_and_undecidable_work_never_calls_the_model():
    seen = []
    r = run(["d/dx(x^2)", "2x"], ai(seen=seen))
    assert r.source == "ENGINE" and r.explanation == "Every step is valid and the final answer is complete."
    r = run(["lim(x->0, 1/x)", "oo"], ai(seen=seen))
    assert r.source == "ENGINE" and "undefined" in r.explanation
    assert seen == []
