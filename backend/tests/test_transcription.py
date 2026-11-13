"""Transcription: model output is reviewed by the server and never auto-verified."""

import asyncio
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services.image_service import prepare_image
from app.services.openrouter_client import OpenRouterClient, get_openrouter_client
from app.services.vision_service import transcribe

client = TestClient(app, raise_server_exceptions=False)


def png(size=(600, 300)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def step(n, expr, confidence=0.97, needs_review=False, note=None, latex=""):
    return {"step_number": n, "expression": expr, "latex": latex, "confidence": confidence,
            "needs_review": needs_review, "ambiguity_note": note}


def model_reply(steps, question="2x + 5 = 15", variable="x"):
    content = json.dumps({"question": question, "variable": variable, "steps": steps})
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def ai_client(*responses, key="test-key", seen=None):
    queue = list(responses)

    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return queue.pop(0)

    async def no_sleep(_):
        return None

    return OpenRouterClient(
        api_key=key, models={"vision": "vision/model", "text": "text/model"}, max_retries=1,
        transport=httpx.MockTransport(handler), sleep=no_sleep,
    )


def run(c, image=None):
    return asyncio.run(transcribe(c, image or prepare_image(png())))


def test_clean_transcription_is_still_review_required():
    seen = []
    result = run(ai_client(model_reply([step(1, "2x + 5 = 15"), step(2, "2x = 10"), step(3, "x = 5")]), seen=seen))
    assert result.status == "REVIEW_REQUIRED"
    assert [s.expression for s in result.steps] == ["2x + 5 = 15", "2x = 10", "x = 5"]
    assert not any(s.needs_review for s in result.steps)
    assert result.steps[0].latex == "2 x + 5 = 15"  # server's own LaTeX of the exact text
    # The image is sent as a data URL with a prompt that forbids solving or correcting.
    message = seen[0]["messages"]
    assert "Do NOT solve" in message[0]["content"]
    assert message[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen[0]["model"] == "vision/model"


def test_low_confidence_and_model_flags_need_review():
    result = run(ai_client(model_reply([
        step(1, "2x + 5 = 15"),
        step(2, "2x = 1O", confidence=0.95),
        step(3, "x = 5", confidence=0.55),
        step(4, "x = 7", needs_review=True, note="Could be 1 or 7"),
    ])))
    flags = {s.step_number: s for s in result.steps}
    assert flags[2].needs_review and flags[2].parse_error_code is not None  # letter O, not zero
    assert flags[3].needs_review and "Low transcription confidence" in flags[3].review_reasons[0]
    assert flags[4].needs_review and flags[4].review_reasons == ["Could be 1 or 7"]
    assert not flags[1].needs_review


def test_lines_are_reordered_cleaned_and_kept_verbatim():
    result = run(ai_client(model_reply([step(2, " 2x = 15 - 5 "), step(1, "2x + 5 = 15"), step(3, "   ")])))
    assert [s.expression for s in result.steps] == ["2x + 5 = 15", "2x = 15 - 5"]  # not "2x = 10"
    assert [s.step_number for s in result.steps] == [1, 2]
    assert any("Empty lines" in w for w in result.warnings)


def test_unsupported_variable_and_too_many_lines_warn():
    result = run(ai_client(model_reply([step(i, "y = 1") for i in range(1, 35)], variable="y")))
    assert len(result.steps) == 30
    assert any("only supports x" in w for w in result.warnings)
    assert all(s.parse_error_code == "MULTIPLE_VARIABLES" for s in result.steps)


def test_missing_question_defaults_to_first_line():
    result = run(ai_client(model_reply([step(1, "x^2 = 9"), step(2, "x = 3")], question=None)))
    assert result.question == "x^2 = 9"


def test_empty_transcription_warns():
    result = run(ai_client(model_reply([])))
    assert result.steps == [] and "No mathematical steps" in result.warnings[-1]


def test_malformed_model_output_is_502():
    bad = httpx.Response(200, json={"choices": [{"message": {"content": '{"steps": "nope"}'}}]})
    with pytest.raises(Exception) as info:
        run(ai_client(bad, bad))
    assert getattr(info.value, "code", None) == "AI_MALFORMED_RESPONSE"


# ---------------------------------------------------------------- API endpoint


@pytest.fixture
def override():
    def install(ai):
        app.dependency_overrides[get_openrouter_client] = lambda: ai

    yield install
    app.dependency_overrides.clear()


def test_transcribe_endpoint(override):
    override(ai_client(model_reply([step(1, "2x + 5 = 15"), step(2, "2x = 10")])))
    r = client.post("/api/v1/transcribe", files={"file": ("work.png", png(), "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REVIEW_REQUIRED" and len(body["steps"]) == 2
    assert body["image"] == {"width": 600, "height": 300}
    assert "overall_status" not in body  # transcription never verifies


def test_transcribe_without_key_is_503(override):
    override(ai_client(key=""))
    r = client.post("/api/v1/transcribe", files={"file": ("work.png", png(), "image/png")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_transcribe_rejects_bad_files_before_calling_ai(override):
    calls = []
    override(ai_client(seen=calls))
    gif = io.BytesIO()
    Image.new("RGB", (100, 100)).save(gif, format="GIF")
    r = client.post("/api/v1/transcribe", files={"file": ("work.png", gif.getvalue(), "image/png")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"
    big = client.post("/api/v1/transcribe", files={"file": ("big.png", b"0" * (5 * 1024 * 1024 + 1), "image/png")})
    assert big.status_code == 413
    assert calls == []


def test_transcribe_requires_a_file():
    r = client.post("/api/v1/transcribe")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_provider_errors_are_structured(override):
    override(ai_client(httpx.Response(429), httpx.Response(429)))
    r = client.post("/api/v1/transcribe", files={"file": ("work.png", png(), "image/png")})
    assert r.status_code == 429 and r.json()["error"]["code"] == "AI_RATE_LIMITED"


def test_calculus_lines_are_checked_with_the_calculus_parser():
    lines = ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)", "sin x cos"]
    reply = model_reply([step(i, e) for i, e in enumerate(lines, start=1)], question=lines[0])
    result = run(ai_client(reply))
    assert [s.needs_review for s in result.steps] == [False, False, False, True]
    assert result.steps[0].latex == r"\frac{d}{dx}\left({x}^{2} \sin\left(x\right)\right)"  # the server's own LaTeX
    assert result.steps[3].parse_error_code == "SYNTAX_ERROR"
    assert result.status == "REVIEW_REQUIRED"


def test_algebra_is_not_parsed_as_calculus():
    result = run(ai_client(model_reply([step(1, "2x + 5 = 15"), step(2, "2x = d/dx(x)")])))
    assert result.steps[0].needs_review is False
    assert result.steps[1].parse_error_code is not None  # the equation parser rejects d/dx


def test_prompt_teaches_the_calculus_syntax():
    seen = []
    run(ai_client(model_reply([step(1, "int(2x) dx"), step(2, "x^2 + C")], question="int(2x) dx"), seen=seen))
    prompt = seen[0]["messages"][0]["content"]
    for syntax in ("d/dx(f)", "int(f) dx", "int[a, b](f) dx", "lim(x->a, f)", "[F][a, b]", "+ C"):
        assert syntax in prompt
