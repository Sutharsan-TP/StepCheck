"""Pydantic contract for POST /api/v1/verify."""

from __future__ import annotations

from typing import Annotated, Literal

import sympy as sp
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.types import (
    FinalAnswerStatus,
    OverallStatus,
    SolutionKind,
    SolutionSet,
    StepStatus,
    VerificationResult,
)
from app.utils.validators import MAX_REQUEST_ID_LENGTH, MAX_STEP_LENGTH, MAX_STEPS, MIN_STEPS

StepText = Annotated[str, StringConstraints(max_length=MAX_STEP_LENGTH)]


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: Annotated[str, StringConstraints(max_length=MAX_REQUEST_ID_LENGTH)] | None = None
    variable: Literal["x"] = "x"
    domain: Literal["REAL"] = "REAL"
    steps: list[StepText] = Field(min_length=MIN_STEPS, max_length=MAX_STEPS)


class SolutionSetOut(BaseModel):
    type: SolutionKind
    values: list[str]
    latex: list[str]

    @staticmethod
    def of(s: SolutionSet | None) -> "SolutionSetOut | None":
        if s is None:
            return None
        return SolutionSetOut(type=s.kind, values=s.value_strings(), latex=s.value_latex())


class StepError(BaseModel):
    code: str
    category: str
    message: str


class StepOut(BaseModel):
    step: int
    input: str
    status: StepStatus
    latex: str | None
    normalized: str | None
    solution_set: SolutionSetOut | None
    solved_form: bool
    error: StepError | None


Topic = Literal["ALGEBRA", "DERIVATIVE", "INTEGRAL", "DEFINITE_INTEGRAL", "LIMIT"]


class TransitionOut(BaseModel):
    from_step: int
    to_step: int
    status: StepStatus
    reason_code: str | None
    compared_to_step: int | None
    locally_valid: bool | None
    matches_original: bool | None
    lost_solutions: list[str]
    extraneous_solutions: list[str]
    # Calculus: the value the step should have, the value it has, and a point where they differ.
    expected_value_latex: str | None = None
    found_value_latex: str | None = None
    counterexample: str | None = None
    note: str | None = None


class VerifyResponse(BaseModel):
    request_id: str | None
    verification_id: str
    topic: Topic = "ALGEBRA"
    overall_status: OverallStatus
    first_error_step: int | None
    complete_answer_step: int | None
    steps: list[StepOut]
    transitions: list[TransitionOut]
    correct_solution: list[str] | None
    correct_solution_set: SolutionSetOut | None
    submitted_solution: list[str] | None
    submitted_solution_set: SolutionSetOut | None
    final_answer_status: FinalAnswerStatus
    final_answer_correct: bool | None
    solution_complete: bool | None
    missing_solutions: list[str] | None
    extraneous_solutions: list[str] | None
    # Calculus: the engine's own final answer, and whether an indefinite integral lacks + C.
    expected_answer: str | None = None
    expected_answer_latex: str | None = None
    missing_constant: bool | None = None
    notes: list[str] = []

    @staticmethod
    def from_result(
        result: VerificationResult, request_id: str | None, verification_id: str
    ) -> "VerifyResponse":
        def strs(values) -> list[str] | None:
            return None if values is None else [sp.sstr(v) for v in values]

        steps = []
        for s in result.steps:
            a = s.analysis
            steps.append(
                StepOut(
                    step=s.step,
                    input=s.raw,
                    status=s.status,
                    latex=a.latex,
                    normalized=a.normalized,
                    solution_set=SolutionSetOut.of(a.solution_set),
                    solved_form=a.solved_form,
                    error=(
                        StepError(
                            code=a.error.code.value,
                            category=a.error.category.value,
                            message=a.error.message,
                        )
                        if a.error
                        else None
                    ),
                )
            )
        transitions = [
            TransitionOut(
                from_step=t.from_step,
                to_step=t.to_step,
                status=t.status,
                reason_code=t.reason_code,
                compared_to_step=t.compared_to_step,
                locally_valid=t.locally_valid,
                matches_original=t.matches_original,
                lost_solutions=strs(t.lost) or [],
                extraneous_solutions=strs(t.extraneous) or [],
                expected_value_latex=t.expected_value_latex,
                found_value_latex=t.found_value_latex,
                counterexample=t.counterexample,
                note=t.note,
            )
            for t in result.transitions
        ]
        c = result.completeness
        return VerifyResponse(
            request_id=request_id,
            verification_id=verification_id,
            topic=result.topic,
            overall_status=result.overall_status,
            first_error_step=result.first_error_step,
            complete_answer_step=result.complete_answer_step,
            steps=steps,
            transitions=transitions,
            correct_solution=result.correct_solution.value_strings() if result.correct_solution else None,
            correct_solution_set=SolutionSetOut.of(result.correct_solution),
            submitted_solution=c.submitted.value_strings() if c.submitted else None,
            submitted_solution_set=SolutionSetOut.of(c.submitted),
            final_answer_status=c.final_answer_status,
            final_answer_correct=c.final_answer_correct,
            solution_complete=c.solution_complete,
            missing_solutions=strs(c.missing),
            extraneous_solutions=strs(c.extraneous),
            expected_answer=result.expected_answer,
            expected_answer_latex=result.expected_answer_latex,
            missing_constant=result.missing_constant,
            notes=result.notes,
        )
