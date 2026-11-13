"""In-memory per-client token-bucket rate limiting.

Per process only (no shared store in the MVP). Each named bucket allows
``per_minute`` requests per client, refilling continuously. Exceeding it gives
429 RATE_LIMITED with a Retry-After header.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from fastapi import Request

from app.config import settings
from app.utils.errors import APIError

MAX_TRACKED_CLIENTS = 10_000


class TokenBucketLimiter:
    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic):
        self.capacity = max(1, per_minute)
        self.rate = self.capacity / 60.0  # tokens per second
        self._clock = clock
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()  # key -> (tokens, updated)
        self._lock = threading.Lock()

    def acquire(self, key: str) -> float:
        """Take a token; return 0 if allowed, otherwise the seconds until one is available."""
        now = self._clock()
        with self._lock:
            tokens, updated = self._buckets.pop(key, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - updated) * self.rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                wait = 0.0
            else:
                self._buckets[key] = (tokens, now)
                wait = (1 - tokens) / self.rate
            while len(self._buckets) > MAX_TRACKED_CLIENTS:
                self._buckets.popitem(last=False)  # forget the least recently seen client
            return wait


limiters: dict[str, TokenBucketLimiter] = {
    name: TokenBucketLimiter(limit) for name, limit in settings.rate_limits_per_minute.items()
}


def client_key(request: Request) -> str:
    if settings.trust_proxy:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-min(settings.trusted_proxy_hops, len(hops))]
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str):
    """FastAPI dependency factory enforcing the named bucket."""

    def dependency(request: Request) -> None:
        wait = limiters[bucket].acquire(client_key(request))
        if wait > 0:
            raise APIError(
                429,
                "RATE_LIMITED",
                "Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(math.ceil(wait))},
            )

    return dependency
