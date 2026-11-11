"""In-memory store mapping verification ids to submitted steps.

The MVP has no database, so ids survive only for the life of one server
process (and one instance). /correct therefore also accepts the steps directly,
which keeps the API usable after a restart or behind several instances.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict

DEFAULT_TTL_SECONDS = 60 * 60
DEFAULT_MAX_ENTRIES = 1000


class VerificationStore:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._items: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, steps: list[str]) -> str:
        verification_id = uuid.uuid4().hex
        with self._lock:
            self._purge()
            self._items[verification_id] = (time.monotonic() + self._ttl, list(steps))
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return verification_id

    def get(self, verification_id: str) -> list[str] | None:
        with self._lock:
            self._purge()
            item = self._items.get(verification_id)
            return list(item[1]) if item else None

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [k for k, (expiry, _) in self._items.items() if expiry <= now]
        for k in expired:
            del self._items[k]


verification_store = VerificationStore()
