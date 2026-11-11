"""Structured error types shared by the math engine and the API layer."""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """How an input problem should be surfaced to the student.

    NEEDS_REVIEW: the input is malformed or ambiguous; the student (or the
        transcription) should be corrected and resubmitted.
    UNSUPPORTED: the input is well-formed but outside StepCheck's mathematical
        scope, so the engine refuses to issue a verdict.
    """

    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSUPPORTED = "UNSUPPORTED"


class ErrorCode(str, Enum):
    # Input shape / syntax -> NEEDS_REVIEW
    EMPTY_INPUT = "EMPTY_INPUT"
    INPUT_TOO_LONG = "INPUT_TOO_LONG"
    INVALID_CHARACTER = "INVALID_CHARACTER"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    MISSING_EQUALS = "MISSING_EQUALS"
    CHAINED_EQUALS = "CHAINED_EQUALS"
    AMBIGUOUS_EXPRESSION = "AMBIGUOUS_EXPRESSION"
    UNKNOWN_IDENTIFIER = "UNKNOWN_IDENTIFIER"
    UNSUPPORTED_CONNECTIVE = "UNSUPPORTED_CONNECTIVE"
    DIVISION_BY_ZERO = "DIVISION_BY_ZERO"
    VERIFICATION_INDETERMINATE = "VERIFICATION_INDETERMINATE"
    # Outside mathematical scope -> UNSUPPORTED
    TOO_COMPLEX = "TOO_COMPLEX"
    MULTIPLE_VARIABLES = "MULTIPLE_VARIABLES"
    UNSUPPORTED_FUNCTION = "UNSUPPORTED_FUNCTION"
    DIVISION_BY_VARIABLE = "DIVISION_BY_VARIABLE"
    NON_INTEGER_EXPONENT = "NON_INTEGER_EXPONENT"
    NEGATIVE_EXPONENT = "NEGATIVE_EXPONENT"
    EXPONENT_TOO_LARGE = "EXPONENT_TOO_LARGE"
    NESTED_POWER = "NESTED_POWER"
    RADICAL_OF_VARIABLE = "RADICAL_OF_VARIABLE"
    COMPLEX_VALUE = "COMPLEX_VALUE"
    DEGREE_TOO_HIGH = "DEGREE_TOO_HIGH"


_UNSUPPORTED_CODES = {
    ErrorCode.TOO_COMPLEX,
    ErrorCode.MULTIPLE_VARIABLES,
    ErrorCode.UNSUPPORTED_FUNCTION,
    ErrorCode.DIVISION_BY_VARIABLE,
    ErrorCode.NON_INTEGER_EXPONENT,
    ErrorCode.NEGATIVE_EXPONENT,
    ErrorCode.EXPONENT_TOO_LARGE,
    ErrorCode.NESTED_POWER,
    ErrorCode.RADICAL_OF_VARIABLE,
    ErrorCode.COMPLEX_VALUE,
    ErrorCode.DEGREE_TOO_HIGH,
}


def category_for(code: ErrorCode) -> ErrorCategory:
    return ErrorCategory.UNSUPPORTED if code in _UNSUPPORTED_CODES else ErrorCategory.NEEDS_REVIEW


class APIError(Exception):
    """A request-level failure returned as {"error": {"code", "message"}} with an HTTP status."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class MathInputError(Exception):
    """Raised when a step cannot be verified. Never carries a stack trace to users."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category_for(code)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"MathInputError({self.code.value}, {self.message!r})"
