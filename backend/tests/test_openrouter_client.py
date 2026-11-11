"""OpenRouter client behaviour with a mocked transport (never touches the network)."""

import asyncio
import json
import logging

import httpx
import pytest
from pydantic import BaseModel

from app.services.openrouter_client import OpenRouterClient, extract_json
from app.utils.errors import APIError

KEY = "sk-or-test-SECRET-KEY-123"


class Answer(BaseModel):
    answer: str


def ok(content, status=200):
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


class Recorder:
    """Scripted transport: returns queued responses and records requests."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def models(self):
        return [json.loads(r.content)["model"] for r in self.requests]


def make_client(recorder, fallback="fallback/model", key=KEY, models=None):
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    client = OpenRouterClient(
        api_key=key,
        models=models if models is not None else {"text": "primary/model", "vision": "vision/model"},
        fallback_model=fallback,
        max_retries=2,
        transport=httpx.MockTransport(recorder),
        sleep=fake_sleep,
    )
    return client, sleeps


def call(client, role="text"):
    return asyncio.run(
        client.chat_json(
            [{"role": "user", "content": "hi"}], role, "answer",
            {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]},
            Answer.model_validate,
        )
    )


def test_success_sends_structured_request_with_auth_header():
    rec = Recorder(ok('{"answer": "42"}'))
    client, _ = make_client(rec)
    assert call(client) == Answer(answer="42")
    req = rec.requests[0]
    body = json.loads(req.content)
    assert req.url.path.endswith("/chat/completions")
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "primary/model" and body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"


def test_vision_role_uses_vision_model():
    rec = Recorder(ok('{"answer": "x"}'))
    client, _ = make_client(rec)
    call(client, role="vision")
    assert rec.models() == ["vision/model"]


def test_rate_limit_then_success_honours_retry_after():
    rec = Recorder(httpx.Response(429, headers={"Retry-After": "3"}), ok('{"answer": "ok"}'))
    client, sleeps = make_client(rec)
    assert call(client).answer == "ok"
    assert sleeps == [3.0]


def test_retry_after_is_capped():
    rec = Recorder(httpx.Response(429, headers={"Retry-After": "999"}), ok('{"answer": "ok"}'))
    client, sleeps = make_client(rec)
    call(client)
    assert sleeps == [10.0]


def test_persistent_rate_limit_is_429():
    rec = Recorder(*[httpx.Response(429)] * 3)
    client, sleeps = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 429 and info.value.code == "AI_RATE_LIMITED"
    assert len(rec.requests) == 3 and len(sleeps) == 3


def test_timeouts_exhaust_retries_then_use_fallback():
    rec = Recorder(*[httpx.ReadTimeout("slow")] * 3, ok('{"answer": "from fallback"}'))
    client, _ = make_client(rec)
    assert call(client).answer == "from fallback"
    assert rec.models() == ["primary/model"] * 3 + ["fallback/model"]


def test_timeouts_without_fallback_are_502():
    rec = Recorder(*[httpx.ConnectTimeout("down")] * 3)
    client, _ = make_client(rec, fallback="")
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 502 and info.value.code == "AI_PROVIDER_ERROR"


def test_server_errors_fall_back():
    rec = Recorder(httpx.Response(500), httpx.Response(502), httpx.Response(503), ok('{"answer": "fb"}'))
    client, _ = make_client(rec)
    assert call(client).answer == "fb"


def test_unavailable_model_falls_back_immediately():
    rec = Recorder(httpx.Response(404, json={"error": {"message": "No endpoints found"}}), ok('{"answer": "fb"}'))
    client, _ = make_client(rec)
    assert call(client).answer == "fb"
    assert rec.models() == ["primary/model", "fallback/model"]


def test_unknown_model_400_falls_back():
    rec = Recorder(httpx.Response(400, json={"error": {"message": "invalid model ID"}}), ok('{"answer": "fb"}'))
    client, _ = make_client(rec)
    assert call(client).answer == "fb"


def test_unavailable_everywhere_is_503():
    rec = Recorder(httpx.Response(404), httpx.Response(404))
    client, _ = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 503 and info.value.code == "AI_UNAVAILABLE"


def test_structured_output_unsupported_retries_in_plain_json_mode():
    rec = Recorder(
        httpx.Response(400, json={"error": {"message": "response_format json_schema not supported"}}),
        ok('```json\n{"answer": "plain"}\n```'),
    )
    client, _ = make_client(rec)
    assert call(client).answer == "plain"
    second = json.loads(rec.requests[1].content)
    assert "response_format" not in second
    assert "JSON" in second["messages"][-1]["content"]


def test_malformed_output_is_retried_once():
    rec = Recorder(ok("I think the answer is 42"), ok('{"answer": "42"}'))
    client, _ = make_client(rec)
    assert call(client).answer == "42"


def test_persistently_malformed_output_is_502():
    rec = Recorder(ok("not json"), ok('{"wrong": "shape"}'))
    client, _ = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 502 and info.value.code == "AI_MALFORMED_RESPONSE"


def test_malformed_envelope_counts_as_malformed():
    rec = Recorder(httpx.Response(200, json={"unexpected": True}), httpx.Response(200, text="<html>"))
    client, _ = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.code == "AI_MALFORMED_RESPONSE"


@pytest.mark.parametrize("key, models", [("", None), (KEY, {"text": ""})])
def test_missing_key_or_model_is_503_without_any_request(key, models):
    rec = Recorder()
    client, _ = make_client(rec, key=key, models=models)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 503 and info.value.code == "AI_UNAVAILABLE"
    assert rec.requests == []


def test_rejected_credentials_are_503():
    rec = Recorder(httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}}))
    client, _ = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert info.value.status_code == 503
    assert KEY not in info.value.message


def test_api_key_never_logged_or_leaked(caplog):
    caplog.set_level(logging.DEBUG)
    rec = Recorder(
        httpx.Response(429), httpx.ReadTimeout("t"), httpx.Response(500, text=f"echo {KEY}"),
        httpx.Response(500), httpx.Response(500), httpx.Response(500),
    )
    client, _ = make_client(rec)
    with pytest.raises(APIError) as info:
        call(client)
    assert KEY not in caplog.text
    assert KEY not in info.value.message


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 1} thanks') == {"a": 1}
    assert extract_json([{"type": "text", "text": '{"a": 2}'}]) == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("nothing here")
