"""Pydantic contract for POST /api/v1/correct."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import sympy as sp
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.api.schemas.verification import SolutionSetOut, StepText
from app.core.correction_engine import (
    MAX_HINT_LEVEL,
    CorrectionStep,
    FullCorrection,
    GuidedCorrection,
    RemovedStep,
)
from app.core.types import StepStatus
from app.utils.validators import MAX_STEPS, MIN_STEPS

MAX_PROGRESS_STEPS = 20


class CorrectRequest(BaseModel):
    # Unknown fields (e.g. a client-asserted "status" or "valid") are rejected outright:
    # correctness is decided only by the server.
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID | None = None
    steps: list[StepText] | None = Field(default=None, min_length=MIN_STEPS, max_length=MAX_STEPS)
    variable: Literal["x"] = "x"
    domain: Literal["REAL"] = "REAL"
    mode: Literal["GUIDED", "FULL"]
    attempt: StepText | None = None
    progress: list[StepText] = Field(default_factory=list, max_length=MAX_PROGRESS_STEPS)
    progress_token: Annotated[str, StringConstraints(max_length=128)] | None = None
    hint_level: int = Field(default=1, ge=1, le=MAX_HINT_LEVEL)

    @model_validator(mode="after")
    def _consistent(self) -> "CorrectRequest":
        if (self.verification_id is None) == (self.steps is None):
            raise ValueError("Provide exactly one of 'verification_id' or 'steps'.")
        if self.mode == "FULL" and (self.attempt is not None or self.progress or self.progress_token):
            raise ValueError("'attempt', 'progress' and 'progress_token' are only used in GUIDED mode.")
        if self.progress and not self.progress_token:
            raise ValueError("'progress' must be accompanied by the 'progress_token' returned by the server.")
        return self


class CorrectionStepOut(BaseModel):
    step_number: int
    text: str
    latex: str | None
    source: Literal["STUDENT", "CORRECTED", "GENERATED"]
    rule: str | None
    rule_name: str | None
    explanation: str | None

    @staticmethod
    def of(step: CorrectionStep) -> "CorrectionStepOut":
        return CorrectionStepOut(
            step_number=step.step_number,
            text=step.text,
            latex=step.latex,
            source=step.source.value,
            rule=step.rule,
            rule_name=step.rule_name,
            explanation=step.explanation,
        )


class RemovedStepOut(BaseModel):
    step_number: int
    text: str
    status: StepStatus
    kind: Literal["INCORRECT", "UNNECESSARY", "UNVERIFIABLE"]
    reason: str

    @staticmethod
    def of(r: RemovedStep) -> "RemovedStepOut":
        return RemovedStepOut(step_number=r.step_number, text=r.text, status=r.status, kind=r.kind, reason=r.reason)


class CorrectionVerificationOut(BaseModel):
    overall_status: str
    all_transitions_valid: bool
    solution_complete: bool | None


class FullCorrectionOut(BaseModel):
    action: Literal["NONE", "REPLACE_STEP", "COMPLETE_SOLUTION", "REMOVE_REMAINING_STEPS"]
    complete_answer_step: int | None
    removed_steps: list[RemovedStepOut]
    original_step: str | None
    error_category: str | None
    expected_rule: str | None
    explanation: str | None
    evidence: str | None
    corrected_step: CorrectionStepOut | None
    continuation: list[CorrectionStepOut]
    corrected_solution: list[CorrectionStepOut]
    final_solution: SolutionSetOut | None
    verification: CorrectionVerificationOut | None


class AttemptFeedbackOut(BaseModel):
    valid: bool
    message: str
    reason_code: str | None
    error_category: str | None
    error_code: str | None
    lost_solutions: list[str]
    extraneous_solutions: list[str]


class GuidedCorrectionOut(BaseModel):
    phase: Literal["FIX_ERROR", "CONTINUE"] | None
    error_step: str | None
    current_step: str | None
    step_number: int | None
    error_category: str | None
    expected_rule: str | None
    explanation: str | None
    hint: str | None
    hint_level: int
    max_hint_level: int = MAX_HINT_LEVEL
    reveal_answer: bool
    revealed_step: str | None
    revealed_explanation: str | None
    attempt_feedback: AttemptFeedbackOut | None
    final_solution: SolutionSetOut | None
    complete_answer_step: int | None
    removed_steps: list[RemovedStepOut]
    progress: list[str]  # server-verified accepted steps; send back unchanged with progress_token
    progress_token: str


class CorrectResponse(BaseModel):
    mode: Literal["GUIDED", "FULL"]
    status: str
    message: str
    first_error_step: int | None
    guided: GuidedCorrectionOut | None = None
    full: FullCorrectionOut | None = None

    @staticmethod
    def from_full(c: FullCorrection) -> "CorrectResponse":
        d = c.diagnosis
        v = c.verification
        full = FullCorrectionOut(
            action=c.action.value,
            complete_answer_step=c.complete_answer_step,
            removed_steps=[RemovedStepOut.of(r) for r in c.removed_steps],
            original_step=c.original_step,
            error_category=d.category.value if d else None,
            expected_rule=d.expected_rule if d else None,
            explanation=d.explanation if d else None,
            evidence=d.evidence if d else None,
            corrected_step=CorrectionStepOut.of(c.corrected_step) if c.corrected_step else None,
            continuation=[CorrectionStepOut.of(s) for s in c.continuation],
            corrected_solution=[CorrectionStepOut.of(s) for s in c.corrected_solution],
            final_solution=SolutionSetOut.of(c.final_solution),
            verification=(
                CorrectionVerificationOut(
                    overall_status=v.overall_status.value,
                    all_transitions_valid=all(t.status is StepStatus.VALID for t in v.transitions),
                    solution_complete=v.completeness.solution_complete,
                )
                if v
                else None
            ),
        )
        return CorrectResponse(
            mode="FULL", status=c.status.value, message=c.message, first_error_step=c.first_error_step, full=full
        )

    @staticmethod
    def from_guided(g: GuidedCorrection, progress_token: str) -> "CorrectResponse":
        fb = g.attempt_feedback
        guided = GuidedCorrectionOut(
            phase=g.phase,
            error_step=g.error_step,
            current_step=g.current_step,
            step_number=g.step_number,
            error_category=g.error_category.value if g.error_category else None,
            expected_rule=g.expected_rule,
            explanation=g.explanation,
            hint=g.hint,
            hint_level=g.hint_level,
            reveal_answer=g.reveal_answer,
            revealed_step=g.revealed_step,
            revealed_explanation=g.revealed_explanation,
            attempt_feedback=(
                AttemptFeedbackOut(
                    valid=fb.valid,
                    message=fb.message,
                    reason_code=fb.reason_code,
                    error_category=fb.category.value if fb.category else None,
                    error_code=fb.error_code,
                    lost_solutions=[sp.sstr(v) for v in fb.lost],
                    extraneous_solutions=[sp.sstr(v) for v in fb.extraneous],
                )
                if fb
                else None
            ),
            final_solution=SolutionSetOut.of(g.final_solution),
            complete_answer_step=g.complete_answer_step,
            removed_steps=[RemovedStepOut.of(r) for r in g.removed_steps],
            progress=g.progress,
            progress_token=progress_token,
        )
        return CorrectResponse(
            mode="GUIDED", status=g.status.value, message=g.message, first_error_step=g.first_error_step, guided=guided
        )
