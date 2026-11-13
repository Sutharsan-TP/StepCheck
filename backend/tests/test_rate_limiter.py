import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import rate_limiter
from app.services.rate_limiter import TokenBucketLimiter

client = TestClient(app, raise_server_exceptions=False)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_bucket_allows_burst_then_refills():
    clock = Clock()
    limiter = TokenBucketLimiter(per_minute=3, clock=clock)
    assert [limiter.acquire("a") for _ in range(3)] == [0, 0, 0]
    wait = limiter.acquire("a")
    assert wait == pytest.approx(20.0)  # one token every 20 s
    assert limiter.acquire("b") == 0  # clients are independent
    clock.now += 20
    assert limiter.acquire("a") == 0


def test_tracked_clients_are_bounded(monkeypatch):
    monkeypatch.setattr(rate_limiter, "MAX_TRACKED_CLIENTS", 5)
    limiter = TokenBucketLimiter(per_minute=1)
    for i in range(20):
        limiter.acquire(f"client-{i}")
    assert len(limiter._buckets) == 5


@pytest.fixture
def tight_limits(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(
        rate_limiter, "limiters", {name: TokenBucketLimiter(2, clock) for name in ("verify", "correct", "transcribe", "explain")}
    )
    return clock


def test_api_returns_429_with_retry_after(tight_limits):
    payload = {"steps": ["2x = 4", "x = 2"]}
    assert client.post("/api/v1/verify", json=payload).status_code == 200
    assert client.post("/api/v1/verify", json=payload).status_code == 200
    r = client.post("/api/v1/verify", json=payload)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert r.headers["retry-after"] == "30"
    # Other endpoints have their own buckets; health is never limited.
    assert client.post("/api/v1/correct", json={**payload, "mode": "FULL"}).status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    tight_limits.now += 30
    assert client.post("/api/v1/verify", json=payload).status_code == 200


def test_forwarded_for_is_ignored_unless_proxy_trusted(tight_limits, monkeypatch):
    payload = {"steps": ["2x = 4", "x = 2"]}
    for i in range(2):
        client.post("/api/v1/verify", json=payload, headers={"X-Forwarded-For": f"10.0.0.{i}"})
    # Spoofing a new X-Forwarded-For does not get a fresh bucket by default.
    r = client.post("/api/v1/verify", json=payload, headers={"X-Forwarded-For": "10.9.9.9"})
    assert r.status_code == 429

    monkeypatch.setattr(rate_limiter, "settings", dataclasses.replace(rate_limiter.settings, trust_proxy=True))
    r = client.post("/api/v1/verify", json=payload, headers={"X-Forwarded-For": "10.9.9.9, 172.16.0.1"})
    assert r.status_code == 200


def test_trusted_proxy_uses_the_address_the_proxy_appended(tight_limits, monkeypatch):
    # The proxy appends the real client address on the right; anything to its left came
    # from the client, so changing it must not give the client a fresh bucket.
    monkeypatch.setattr(rate_limiter, "settings", dataclasses.replace(rate_limiter.settings, trust_proxy=True))
    payload = {"steps": ["2x = 4", "x = 2"]}
    for i in range(2):
        client.post("/api/v1/verify", json=payload, headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"})
    r = client.post("/api/v1/verify", json=payload, headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.7"})
    assert r.status_code == 429


def test_trusted_proxy_hops_selects_entry_from_the_right(monkeypatch):
    from starlette.requests import Request

    def key(forwarded: str, hops: int) -> str:
        monkeypatch.setattr(
            rate_limiter,
            "settings",
            dataclasses.replace(rate_limiter.settings, trust_proxy=True, trusted_proxy_hops=hops),
        )
        scope = {"type": "http", "headers": [(b"x-forwarded-for", forwarded.encode())], "client": ("127.0.0.1", 1)}
        return rate_limiter.client_key(Request(scope))

    assert key("spoofed, 203.0.113.7", 1) == "203.0.113.7"
    assert key("spoofed, 203.0.113.7, 10.0.0.1", 2) == "203.0.113.7"
    assert key("203.0.113.7", 3) == "203.0.113.7"  # fewer entries than hops: leftmost
