"""In-memory store of verification results keyed by UUID.

The MVP has no database: entries live only in this server process, so a
restart (or a deploy) clears them and multiple instances do not share them.
/correct therefore also accepts the original steps directly.

Entries expire after a TTL. When the store is full, expired entries are evicted
first, then the oldest live entries. Ids of recently expired or evicted entries
are remembered (bounded) so clients can be told "expired" rather than "missing".
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.core.types import VerificationResult

DEFAULT_TTL_SECONDS = 60 * 60
DEFAULT_MAX_ENTRIES = 1000


class LookupStatus(str, Enum):
    FOUND = "FOUND"
    EXPIRED = "EXPIRED"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class StoredVerification:
    verification_id: str
    steps: tuple[str, ...]
    result: VerificationResult
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class Lookup:
    status: LookupStatus
    entry: StoredVerification | None = None


class VerificationStore:
    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._items: OrderedDict[str, StoredVerification] = OrderedDict()  # insertion = age order
        self._expired: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, steps: list[str], result: VerificationResult) -> str:
        now = self._clock()
        verification_id = str(uuid.uuid4())
        entry = StoredVerification(verification_id, tuple(steps), result, now, now + self._ttl)
        with self._lock:
            self._purge_expired(now)
            while len(self._items) >= self._max:  # full even after expiry: evict the oldest
                oldest, _ = self._items.popitem(last=False)
                self._remember_expired(oldest)
            self._items[verification_id] = entry
        return verification_id

    def get(self, verification_id: str) -> Lookup:
        with self._lock:
            self._purge_expired(self._clock())
            entry = self._items.get(verification_id)
            if entry is not None:
                return Lookup(LookupStatus.FOUND, entry)
            if verification_id in self._expired:
                return Lookup(LookupStatus.EXPIRED)
            return Lookup(LookupStatus.NOT_FOUND)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _purge_expired(self, now: float) -> None:
        for key in [k for k, e in self._items.items() if e.expires_at <= now]:
            del self._items[key]
            self._remember_expired(key)

    def _remember_expired(self, key: str) -> None:
        self._expired[key] = None
        while len(self._expired) > self._max:
            self._expired.popitem(last=False)


verification_store = VerificationStore()
