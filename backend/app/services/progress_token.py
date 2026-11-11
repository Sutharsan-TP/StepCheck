"""HMAC tokens binding guided-correction progress to the original submission.

The server returns a token over (original steps, accepted progress) every time
it answers a guided request. The next request must send that token back with
the same progress, so a client cannot present steps the server never accepted
for this solution. Progress is still fully re-verified on every request; the
token only proves provenance.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from app.config import settings


def _payload(steps: list[str], progress: list[str]) -> bytes:
    return json.dumps({"steps": steps, "progress": progress}, ensure_ascii=False, separators=(",", ":")).encode()


def sign(steps: list[str], progress: list[str]) -> str:
    return hmac.new(settings.progress_token_secret.encode(), _payload(steps, progress), hashlib.sha256).hexdigest()


def is_valid(token: str | None, steps: list[str], progress: list[str]) -> bool:
    return token is not None and hmac.compare_digest(token, sign(steps, progress))
