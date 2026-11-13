"""The offline stub used for local demos and end-to-end tests (STEPCHECK_STUB_AI=true)."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import stub_ai
from app.services.openrouter_client import get_openrouter_client

client = TestClient(app, raise_server_exceptions=False)
SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "handwritten_samples"


@pytest.fixture(autouse=True)
def use_stub():
    app.dependency_overrides[get_openrouter_client] = stub_ai.stub_openrouter_client
    yield
    app.dependency_overrides.clear()


def test_samples_are_distinguishable():
    hashes = stub_ai._sample_hashes()
    assert len(hashes) == len(stub_ai._SAMPLES) == 4
    values = list(hashes.values())
    distances = [bin(a ^ b).count("1") for i, a in enumerate(values) for b in values[i + 1 :]]
    assert min(distances) > 3 * stub_ai._MAX_HASH_DISTANCE


@pytest.mark.parametrize("name", list(stub_ai._SAMPLES))
def test_each_sample_is_transcribed(name):
    data = (SAMPLES / f"{name}.png").read_bytes()
    body = client.post("/api/v1/transcribe", files={"file": (f"{name}.png", data, "image/png")}).json()
    assert [s["expression"] for s in body["steps"]] == stub_ai._SAMPLES[name]
    assert body["steps"][-1]["needs_review"] is True
    assert body["status"] == "REVIEW_REQUIRED"


def test_unknown_image_is_flagged_not_guessed():
    buf = io.BytesIO()
    Image.new("RGB", (800, 400), "gray").save(buf, format="PNG")
    body = client.post("/api/v1/transcribe", files={"file": ("x.png", buf.getvalue(), "image/png")}).json()
    assert len(body["steps"]) == 1 and body["steps"][0]["needs_review"]


def test_stub_explanations_restate_engine_facts():
    body = client.post("/api/v1/explain", json={"steps": ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]}).json()
    assert body["source"] == "LLM" and "15 - 5" in body["explanation"]


def test_stub_explains_calculus_from_engine_facts():
    body = client.post("/api/v1/explain", json={"steps": ["d/dx(x^2 sin(x))", "d/dx(x^2) d/dx(sin(x))", "2x cos(x)"]}).json()
    assert body["source"] == "LLM"  # the stub answers through the real client and guard
    assert body["error_category"] == "PRODUCT_RULE_ERROR"
    assert "product" in body["explanation"].lower()
