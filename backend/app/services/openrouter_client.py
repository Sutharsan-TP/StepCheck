"""Reusable OpenRouter chat client that returns validated JSON.

Responsibilities: structured-output requests, retries with backoff on rate
limits / provider errors / timeouts, one fallback model when a model is
unavailable or keeps failing, one retry on malformed output, and mapping every
failure to a structured APIError. The API key is only ever placed in the
Authorization header: it is never logged and never included in errors.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar

import httpx

from app.config import settings
from app.utils.errors import APIError

logger = logging.getLogger("stepcheck.openrouter")

T = TypeVar("T")
ModelRole = Literal["vision", "text"]

MAX_RETRY_AFTER_SECONDS = 10.0
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class _ModelUnavailable(Exception):
    pass


class _ProviderFailure(Exception):
    pass


class _RateLimited(Exception):
    pass


def extract_json(content: Any) -> Any:
    """Parse a model message's content as JSON (tolerates code fences and text parts)."""
    if isinstance(content, list):  # some providers return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        raise ValueError("Model content is not text.")
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("Model content is not JSON.") from None
        return json.loads(text[start : end + 1])


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        models: dict[str, str],
        fallback_model: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        app_title: str = "StepCheck",
        app_url: str = "",
    ):
        self._api_key = api_key
        self._models = {role: m for role, m in models.items() if m}
        self._fallback = fallback_model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport
        self._sleep = sleep
        self._headers = {"X-Title": app_title}
        if app_url:
            self._headers["HTTP-Referer"] = app_url

    def model_for(self, role: ModelRole) -> str | None:
        return self._models.get(role)

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def chat_json(
        self,
        messages: list[dict],
        role: ModelRole,
        schema_name: str,
        json_schema: dict,
        validate: Callable[[Any], T],
    ) -> T:
        """Send a chat request and return ``validate(parsed_json)``.

        ``validate`` should raise (e.g. pydantic.ValidationError / ValueError) for
        output that does not match the expected shape; that counts as malformed.
        """
        model = self._models.get(role)
        if not self._api_key or not model:
            raise APIError(503, "AI_UNAVAILABLE", "The AI service is not configured.")
        try:
            return await self._run(model, messages, schema_name, json_schema, validate)
        except (_ModelUnavailable, _ProviderFailure) as first:
            if self._fallback and self._fallback != model:
                logger.warning("OpenRouter model failed (%s); trying fallback model", type(first).__name__)
                try:
                    return await self._run(self._fallback, messages, schema_name, json_schema, validate)
                except _ModelUnavailable:
                    raise APIError(503, "AI_UNAVAILABLE", "No configured AI model is available.") from None
                except _ProviderFailure:
                    raise APIError(502, "AI_PROVIDER_ERROR", "The AI provider failed to respond.") from None
                except _RateLimited:
                    raise APIError(429, "AI_RATE_LIMITED", "The AI provider is rate limiting requests.") from None
            if isinstance(first, _ModelUnavailable):
                raise APIError(503, "AI_UNAVAILABLE", "The configured AI model is not available.") from None
            raise APIError(502, "AI_PROVIDER_ERROR", "The AI provider failed to respond.") from None
        except _RateLimited:
            raise APIError(429, "AI_RATE_LIMITED", "The AI provider is rate limiting requests.") from None

    # ------------------------------------------------------------------ internals

    def _payload(self, model: str, messages: list[dict], schema_name: str, schema: dict, structured: bool) -> dict:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0}
        if structured:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            }
        else:
            payload["messages"] = messages + [
                {"role": "system", "content": "Respond with a single JSON object only, matching the requested fields."}
            ]
        return payload

    def _backoff(self, attempt: int) -> float:
        return 0.5 * (2**attempt) + random.uniform(0, 0.25)

    async def _run(self, model, messages, schema_name, schema, validate):
        structured = True
        malformed_retry_used = False
        last: type[Exception] = _ProviderFailure
        headers = {"Authorization": f"Bearer {self._api_key}", **self._headers}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport, headers=headers
        ) as client:
            attempt = 0
            while attempt <= self._max_retries:
                try:
                    resp = await client.post(
                        "/chat/completions", json=self._payload(model, messages, schema_name, schema, structured)
                    )
                except httpx.TimeoutException:
                    logger.warning("OpenRouter timeout (attempt %d)", attempt + 1)
                    last = _ProviderFailure
                    await self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                except httpx.HTTPError:
                    logger.warning("OpenRouter transport error (attempt %d)", attempt + 1)
                    last = _ProviderFailure
                    await self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue

                status = resp.status_code
                logger.info("OpenRouter response status=%d attempt=%d", status, attempt + 1)
                if status == 429:
                    last = _RateLimited
                    await self._sleep(self._retry_after(resp, attempt))
                    attempt += 1
                    continue
                if status >= 500:
                    last = _ProviderFailure
                    await self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                if status in (401, 403):
                    raise APIError(503, "AI_UNAVAILABLE", "The AI service rejected the configured credentials.")
                format_problem = self._mentions(resp, "response_format", "json_schema", "structured")
                if status == 400 and structured and format_problem:
                    structured = False  # model can't do strict schemas: ask for plain JSON instead
                    continue
                if status == 404 or (status == 400 and not format_problem and self._mentions(resp, "model")):
                    raise _ModelUnavailable()
                if status >= 400:
                    raise APIError(502, "AI_PROVIDER_ERROR", "The AI provider rejected the request.")

                try:
                    body = resp.json()
                    content = body["choices"][0]["message"]["content"]
                    return validate(extract_json(content))
                except Exception:  # malformed envelope, non-JSON content, or schema mismatch
                    if malformed_retry_used:
                        raise APIError(
                            502, "AI_MALFORMED_RESPONSE", "The AI provider returned an unusable response."
                        ) from None
                    malformed_retry_used = True
                    logger.warning("OpenRouter returned malformed output; retrying once")
                    continue
        raise last()

    @staticmethod
    def _mentions(resp: httpx.Response, *words: str) -> bool:
        text = resp.text.lower()
        return any(w in text for w in words)

    def _retry_after(self, resp: httpx.Response, attempt: int) -> float:
        try:
            return min(float(resp.headers.get("retry-after", "")), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            return self._backoff(attempt)


def get_openrouter_client() -> OpenRouterClient:
    """FastAPI dependency (overridable in tests)."""
    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        models={"vision": settings.openrouter_vision_model, "text": settings.openrouter_text_model},
        fallback_model=settings.openrouter_fallback_model,
        base_url=settings.openrouter_base_url,
        timeout=settings.openrouter_timeout_seconds,
        max_retries=settings.openrouter_max_retries,
        app_title=settings.openrouter_app_title,
        app_url=settings.openrouter_app_url,
    )
