"""Deterministic stand-in for OpenRouter, for local demos and end-to-end tests only.

Enabled only when STEPCHECK_STUB_AI=true. It never contacts the network:
- vision requests recognise the synthetic samples in examples/handwritten_samples
  by perceptual hash and return their exact lines, with the last line marked for
  review so the review screen can be exercised; other images are "unreadable";
- text requests return the engine's own facts as plain prose.
It goes through the real OpenRouterClient, so retries/validation still apply.
"""

from __future__ import annotations

import base64
import io
import json
from functools import lru_cache
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from app.services.openrouter_client import OpenRouterClient

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "examples" / "handwritten_samples"
_SAMPLES = {
    "demo1_correct_linear": ["2x + 5 = 15", "2x = 10", "x = 5"],
    "demo2_first_error": ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"],
    "demo3_lost_root": ["x^2 - 5x + 6 = 0", "(x - 2)(x - 3) = 0", "x - 2 = 0", "x = 2"],
    "demo4_calculus": ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"],
}
_MAX_HASH_DISTANCE = 40  # of 512 bits; the samples are 140+ bits apart
_UNKNOWN = ["?"]


def _average_hash(image: Image.Image) -> int:
    """512-bit average hash of the inked area (blank paper would dominate otherwise)."""
    gray = image.convert("L")
    ink_box = ImageOps.invert(gray).point(lambda p: 255 if p > 80 else 0).getbbox()
    small = (gray.crop(ink_box) if ink_box else gray).resize((32, 16))
    pixels = list(small.tobytes())
    mean = sum(pixels) / len(pixels)
    return sum(1 << i for i, p in enumerate(pixels) if p < mean)


@lru_cache(maxsize=1)
def _sample_hashes() -> dict[str, int]:
    return {
        name: _average_hash(Image.open(SAMPLES_DIR / f"{name}.png"))
        for name in _SAMPLES
        if (SAMPLES_DIR / f"{name}.png").exists()
    }


def _pick_sample(body: dict) -> list[str]:
    """Recognise one of the synthetic demo samples; anything else is 'unreadable'."""
    url = body["messages"][-1]["content"][1]["image_url"]["url"]
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    target = _average_hash(image)
    best = min(
        _sample_hashes().items(), key=lambda kv: bin(kv[1] ^ target).count("1"), default=None
    )
    if best is None or bin(best[1] ^ target).count("1") > _MAX_HASH_DISTANCE:
        return _UNKNOWN
    return _SAMPLES[best[0]]


def _vision_reply(body: dict) -> dict:
    lines = _pick_sample(body)
    if lines is _UNKNOWN:
        return {"question": None, "variable": "x", "steps": [{
            "step_number": 1, "expression": "?", "latex": "?", "confidence": 0.0, "needs_review": True,
            "ambiguity_note": "Stub AI mode only recognises the bundled demo samples.",
        }]}
    steps = []
    for i, line in enumerate(lines, start=1):
        unsure = i == len(lines)
        steps.append({
            "step_number": i,
            "expression": line,
            "latex": line,
            "confidence": 0.72 if unsure else 0.97,
            "needs_review": unsure,
            "ambiguity_note": "The last digit is faint (stub transcription)." if unsure else None,
        })
    return {"question": lines[0], "variable": "x", "steps": steps}


def _text_reply(body: dict) -> dict:
    facts = json.loads(body["messages"][-1]["content"].split("FACTS:\n", 1)[1])
    return {
        "explanation": facts.get("engine_explanation") or facts.get("correction") or "",
        "why_invalid": f"Rule: {facts['rule']}." if facts.get("rule") else "",
        "how_to_avoid": facts.get("evidence") or "",
        "learning_tip": "Check each step by asking whether it keeps exactly the same solutions.",
    }


def _handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    is_vision = isinstance(body["messages"][-1]["content"], list)
    reply = _vision_reply(body) if is_vision else _text_reply(body)
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})


def stub_openrouter_client() -> OpenRouterClient:
    return OpenRouterClient(
        api_key="stub",
        models={"vision": "stub/vision", "text": "stub/text"},
        transport=httpx.MockTransport(_handler),
    )
