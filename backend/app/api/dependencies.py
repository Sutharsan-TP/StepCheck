"""Shared request helpers for routes."""

from __future__ import annotations

from uuid import UUID

from app.services.verification_store import LookupStatus, verification_store
from app.utils.errors import APIError


def resolve_steps(verification_id: UUID | None, steps: list[str] | None) -> list[str]:
    """Original submitted steps, either sent directly or looked up by verification id."""
    if steps is not None:
        return list(steps)
    lookup = verification_store.get(str(verification_id))
    if lookup.status is LookupStatus.EXPIRED:
        raise APIError(
            410,
            "VERIFICATION_EXPIRED",
            "This verification has expired. Submit the steps again (or send them directly in 'steps').",
        )
    if lookup.status is LookupStatus.NOT_FOUND:
        raise APIError(
            404,
            "VERIFICATION_NOT_FOUND",
            "No verification exists with this id. It may have been cleared by a server restart; "
            "submit the steps again.",
        )
    return list(lookup.entry.steps)
