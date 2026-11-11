"""Core data types of the verification engine (independent of the API layer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import sympy as sp

from app.utils.errors import MathInputError


class SolutionKind(str, Enum):
    ALL_REAL = "ALL_REAL"
    EMPTY = "EMPTY"
    FINITE_SET = "FINITE_SET"


@dataclass(frozen=True)
class SolutionSet:
    kind: SolutionKind
    values: tuple[sp.Expr, ...] = ()

    @staticmethod
    def all_real() -> "SolutionSet":
        return SolutionSet(SolutionKind.ALL_REAL)

    @staticmethod
    def empty() -> "SolutionSet":
        return SolutionSet(SolutionKind.EMPTY)

    def value_strings(self) -> list[str]:
        return [sp.sstr(v) for v in self.values]

    def value_latex(self) -> list[str]:
        return [sp.latex(v) for v in self.values]

    def describe(self) -> str:
        if self.kind is SolutionKind.ALL_REAL:
            return "all real numbers"
        if self.kind is SolutionKind.EMPTY:
            return "no real solution"
        return "{" + ", ".join(self.value_strings()) + "}"


class StepStatus(str, Enum):
    VALID = "VALID"
    FIRST_INVALID = "FIRST_INVALID"
    DOWNSTREAM_DEPENDENT = "DOWNSTREAM_DEPENDENT"
    UNSUPPORTED = "UNSUPPORTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class OverallStatus(str, Enum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReasonCode(str, Enum):
    LOST_SOLUTIONS = "LOST_SOLUTIONS"
    EXTRANEOUS_SOLUTIONS = "EXTRANEOUS_SOLUTIONS"
    SOLUTIONS_CHANGED = "SOLUTIONS_CHANGED"
    BECAME_IDENTITY = "BECAME_IDENTITY"
    BECAME_CONTRADICTION = "BECAME_CONTRADICTION"
    LOST_IDENTITY = "LOST_IDENTITY"
    AMBIGUOUS_ERROR_LOCATION = "AMBIGUOUS_ERROR_LOCATION"
    AFTER_UNRESOLVED_STEP = "AFTER_UNRESOLVED_STEP"
    NO_VERIFIED_REFERENCE = "NO_VERIFIED_REFERENCE"


class FinalAnswerStatus(str, Enum):
    SOLVED = "SOLVED"
    NOT_ISOLATED = "NOT_ISOLATED"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class Comparison:
    equivalent: bool
    reason_code: ReasonCode | None
    lost: tuple[sp.Expr, ...] = ()
    extraneous: tuple[sp.Expr, ...] = ()


@dataclass
class StepAnalysis:
    """Result of parsing and solving one step in isolation."""

    index: int  # 1-based
    raw: str
    solution_set: SolutionSet | None = None
    normalized: str | None = None
    latex: str | None = None
    solved_form: bool = False
    error: MathInputError | None = None
    statement: Any = None  # ParsedStatement (kept untyped to avoid an import cycle)
    equations: list[tuple[sp.Expr, sp.Expr]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class StepResult:
    step: int
    raw: str
    status: StepStatus
    analysis: StepAnalysis


@dataclass
class TransitionResult:
    from_step: int
    to_step: int
    status: StepStatus
    reason_code: str | None
    compared_to_step: int | None
    locally_valid: bool | None
    matches_original: bool | None
    lost: tuple[sp.Expr, ...] = ()
    extraneous: tuple[sp.Expr, ...] = ()


@dataclass
class CompletenessResult:
    final_answer_status: FinalAnswerStatus
    submitted: SolutionSet | None
    final_answer_correct: bool | None
    solution_complete: bool | None
    missing: tuple[sp.Expr, ...] | None
    extraneous: tuple[sp.Expr, ...] | None
    includes_extraneous: bool | None


@dataclass
class VerificationResult:
    overall_status: OverallStatus
    first_error_step: int | None
    steps: list[StepResult]
    transitions: list[TransitionResult]
    correct_solution: SolutionSet | None
    completeness: CompletenessResult
    complete_answer_step: int | None = None  # earliest step stating the full answer (all prior valid)
    notes: list[str] = field(default_factory=list)
