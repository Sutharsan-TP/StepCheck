"""Handwriting transcription via a vision model, followed by server-side checks.

The model only transcribes. Every expression is then run through the same
restricted parser used for verification: anything it cannot read, anything the
model marked ambiguous and anything below the confidence threshold is flagged
for the student to review. Results are always REVIEW_REQUIRED; transcription
never triggers verification on its own.
"""

from __future__ import annotations

import uuid

from app.api.schemas.transcription import (
    MODEL_JSON_SCHEMA,
    ImageInfo,
    ModelTranscription,
    TranscribedStep,
    TranscriptionResponse,
)
from app.core.equation_parser import parse_statement
from app.services.image_service import PreparedImage
from app.services.openrouter_client import OpenRouterClient
from app.utils.errors import MathInputError
from app.utils.validators import MAX_STEP_LENGTH, MAX_STEPS

CONFIDENCE_THRESHOLD = 0.8

SYSTEM_PROMPT = """You transcribe photographs of handwritten mathematics for a verification tool.

Transcribe EXACTLY what is written, line by line, in reading order.
Rules:
- Do NOT solve the problem, check it, correct mistakes, simplify, rearrange or reorder anything.
- Do NOT add missing steps or remove steps, even if they are wrong or repeated.
- Each written line is one step. Keep the student's own form (e.g. keep "15 - 5"; do not write "10").
- Use plain text with ^ for powers, * or implicit multiplication, / for division, sqrt(...) for roots,
  ± for plus-minus, and "or" between alternatives (e.g. "x = 2 or x = 3").
- Also give a LaTeX version of each line.
- confidence is your estimate (0 to 1) that the line is transcribed exactly.
- If any symbol is unclear (e.g. 1 vs 7, x vs ×, 2 vs z, a faint minus sign), set needs_review to true,
  lower the confidence, and describe the doubt in ambiguity_note. Never guess silently.
- question is the first line (the problem) if one is written, otherwise null.
- variable is the letter used as the unknown.
Return only the JSON object."""


def _user_message(image: PreparedImage) -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Transcribe this handwritten solution exactly."},
            {"type": "image_url", "image_url": {"url": image.data_url}},
        ],
    }


def review_transcription(raw: ModelTranscription, image: PreparedImage) -> TranscriptionResponse:
    """Apply the server-side checks to the model's raw transcription."""
    warnings: list[str] = []
    lines = [s for s in sorted(raw.steps, key=lambda s: s.step_number) if s.expression.strip()]
    if len(lines) < len(raw.steps):
        warnings.append("Empty lines returned by the transcription model were removed.")
    if len(lines) > MAX_STEPS:
        warnings.append(f"Only the first {MAX_STEPS} lines were kept.")
        lines = lines[:MAX_STEPS]
    if raw.variable.strip() != "x":
        warnings.append(f"The variable appears to be '{raw.variable}'; StepCheck only supports x.")
    if not lines:
        warnings.append("No mathematical steps were found in the image.")

    steps: list[TranscribedStep] = []
    for number, line in enumerate(lines, start=1):
        expression = line.expression.strip()
        reasons: list[str] = []
        parse_code = None
        latex = line.latex
        if line.needs_review:
            reasons.append(line.ambiguity_note or "The transcription model was unsure about this line.")
        if line.confidence < CONFIDENCE_THRESHOLD:
            reasons.append(f"Low transcription confidence ({line.confidence:.2f}).")
        if len(expression) > MAX_STEP_LENGTH:
            reasons.append(f"Longer than {MAX_STEP_LENGTH} characters.")
        else:
            try:
                latex = parse_statement(expression).latex  # our own rendering of the exact text
            except MathInputError as exc:
                parse_code = exc.code.value
                reasons.append(f"StepCheck cannot read this line yet: {exc.message}")
        steps.append(
            TranscribedStep(
                step_number=number,
                expression=expression,
                latex=latex,
                confidence=line.confidence,
                needs_review=bool(reasons),
                review_reasons=reasons,
                parse_error_code=parse_code,
            )
        )
    return TranscriptionResponse(
        request_id=str(uuid.uuid4()),
        question=raw.question or (steps[0].expression if steps else None),
        variable=raw.variable,
        steps=steps,
        warnings=warnings,
        image=ImageInfo(width=image.width, height=image.height),
    )


async def transcribe(client: OpenRouterClient, image: PreparedImage) -> TranscriptionResponse:
    raw = await client.chat_json(
        [{"role": "system", "content": SYSTEM_PROMPT}, _user_message(image)],
        role="vision",
        schema_name="handwriting_transcription",
        json_schema=MODEL_JSON_SCHEMA,
        validate=ModelTranscription.model_validate,
    )
    return review_transcription(raw, image)
