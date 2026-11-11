"""Schemas for handwriting transcription (model output and API response)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelStep(BaseModel):
    """One transcribed line exactly as the vision model must return it."""

    model_config = ConfigDict(extra="ignore")

    step_number: int
    expression: str = Field(max_length=500)
    latex: str = Field(default="", max_length=1000)
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False
    ambiguity_note: str | None = Field(default=None, max_length=300)


class ModelTranscription(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str | None = Field(default=None, max_length=500)
    variable: str = Field(default="x", max_length=5)
    steps: list[ModelStep] = Field(max_length=60)


# Strict JSON schema sent to the model (structured outputs need every field listed).
MODEL_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["question", "variable", "steps"],
    "properties": {
        "question": {"type": ["string", "null"]},
        "variable": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["step_number", "expression", "latex", "confidence", "needs_review", "ambiguity_note"],
                "properties": {
                    "step_number": {"type": "integer"},
                    "expression": {"type": "string"},
                    "latex": {"type": "string"},
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                    "ambiguity_note": {"type": ["string", "null"]},
                },
            },
        },
    },
}


class TranscribedStep(BaseModel):
    step_number: int
    expression: str
    latex: str
    confidence: float
    needs_review: bool
    review_reasons: list[str]
    parse_error_code: str | None


class ImageInfo(BaseModel):
    width: int
    height: int


class TranscriptionResponse(BaseModel):
    request_id: str
    question: str | None
    variable: str
    steps: list[TranscribedStep]
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    warnings: list[str]
    image: ImageInfo
