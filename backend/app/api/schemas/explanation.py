"""Schemas for POST /api/v1/explain."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.verification import StepText
from app.utils.validators import MAX_STEPS, MIN_STEPS


class ExplainRequest(BaseModel):
    # The client sends only the original work; the verification result is always
    # recomputed on the server and never accepted from the client.
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID | None = None
    steps: list[StepText] | None = Field(default=None, min_length=MIN_STEPS, max_length=MAX_STEPS)
    variable: Literal["x"] = "x"
    domain: Literal["REAL"] = "REAL"

    @model_validator(mode="after")
    def _one_source(self) -> "ExplainRequest":
        if (self.verification_id is None) == (self.steps is None):
            raise ValueError("Provide exactly one of 'verification_id' or 'steps'.")
        return self


class LLMExplanation(BaseModel):
    """The only fields the language model is allowed to write (prose)."""

    model_config = ConfigDict(extra="ignore")

    explanation: str = Field(min_length=1, max_length=1200)
    why_invalid: str = Field(default="", max_length=800)
    how_to_avoid: str = Field(default="", max_length=800)
    learning_tip: str = Field(default="", max_length=400)


LLM_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["explanation", "why_invalid", "how_to_avoid", "learning_tip"],
    "properties": {
        "explanation": {"type": "string"},
        "why_invalid": {"type": "string"},
        "how_to_avoid": {"type": "string"},
        "learning_tip": {"type": "string"},
    },
}


class ExplainResponse(BaseModel):
    source: Literal["LLM", "TEMPLATE", "ENGINE"]
    ai_status: str | None  # why the LLM was not used, e.g. AI_UNAVAILABLE or REJECTED_BY_GUARD
    # Decided by the deterministic engine:
    overall_status: str
    first_error_step: int | None
    error_category: str | None
    expected_rule: str | None
    corrected_step: str | None
    suggested_next_step: str | None
    correction_action: str | None
    # Prose (LLM when available and consistent, otherwise deterministic templates):
    explanation: str
    why_invalid: str | None
    how_to_avoid: str | None
    learning_tip: str | None
