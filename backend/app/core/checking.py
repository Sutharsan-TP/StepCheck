"""Single entry point for checking a solution: algebra or calculus, decided by the problem line."""

from __future__ import annotations

from app.core.calculus.calc_parser import looks_like_calculus, split_definitions
from app.core.calculus.calc_verifier import verify_calculus
from app.core.first_error_detector import verify_steps
from app.core.types import VerificationResult


def is_calculus(steps: list[str]) -> bool:
    skipped = len(split_definitions(steps)[0])  # lines such as "f(x) = x^2" come before the problem
    return skipped < len(steps) and looks_like_calculus(steps[skipped])


def check_steps(steps: list[str]) -> VerificationResult:
    return verify_calculus(steps) if is_calculus(steps) else verify_steps(steps)
