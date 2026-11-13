"""Educational explanations of a verified result.

The deterministic engine decides everything mathematical (status, first error,
category, corrected step, next step). The language model only turns those facts
into friendlier prose. Its output is rejected — and deterministic template text
used instead — when it is unavailable, malformed, claims the work is correct
when it is not, or mentions numbers that do not occur in the verified facts.
For unsupported or unverifiable work no model is called at all.
"""

from __future__ import annotations

import json
import re

from starlette.concurrency import run_in_threadpool

from app.api.schemas.explanation import LLM_JSON_SCHEMA, ExplainResponse, LLMExplanation
from app.core.calculus.calc_diagnosis import CalcDiagnosis, CalcErrorCategory, describe
from app.core.calculus.calc_parser import to_text
from app.core.calculus.calc_verifier import verify_calculus
from app.core.calculus.sandbox import SandboxFailure, SandboxTimeout, get_sandbox
from app.core.checking import is_calculus
from app.core.correction_engine import CorrectionAction, FullCorrection, correct_full
from app.core.first_error_detector import verify_steps
from app.core.types import OverallStatus, StepStatus, VerificationResult
from app.utils.errors import MathInputError
from app.services.openrouter_client import OpenRouterClient
from app.utils.errors import APIError

SYSTEM_PROMPT = """You are a patient mathematics tutor writing for a secondary-school student.
You receive FACTS produced by a verified symbolic mathematics engine. The engine is always right.
Explain those facts clearly and kindly.
Rules:
- Never contradict the facts. Never say the work is correct if the facts say it is not.
- Do not solve anything yourself and do not introduce any new equation, number or solution.
  Only use equations and numbers that appear in the facts.
- explanation: what the student attempted and what went wrong (2-3 sentences).
- why_invalid: which mathematical rule applies and why the step breaks it (1-2 sentences).
- how_to_avoid: how to avoid the same mistake next time (1-2 sentences).
- learning_tip: one short, memorable tip.
Return only the JSON object."""

_PRAISE = re.compile(
    r"\b(no (mistakes?|errors?)|(your|the) (solution|answer|work) (is|was) (completely |entirely |fully |all )?"
    r"(correct|right|valid)|every step is (correct|valid)|all (of )?(your |the )?steps are (correct|valid))\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _facts(steps: list[str], result: VerificationResult, full: FullCorrection) -> dict:
    d = full.diagnosis
    return {
        "student_steps": [{"step": i + 1, "text": s} for i, s in enumerate(steps)],
        "step_statuses": [s.status.value for s in result.steps],
        "overall_status": result.overall_status.value,
        "first_error_step": result.first_error_step,
        "correct_solution": result.correct_solution.describe() if result.correct_solution else None,
        "error_category": d.category.value if d else None,
        "rule": d.expected_rule if d else None,
        "engine_explanation": d.explanation if d else full.message,
        "evidence": d.evidence if d else None,
        "correction": full.message,
        "corrected_step": full.corrected_step.text if full.corrected_step else None,
        "corrected_solution": [s.text for s in full.corrected_solution],
    }


def _allowed_numbers(facts: dict) -> set[str]:
    text = json.dumps(facts, ensure_ascii=False)
    allowed = set(_NUMBER.findall(text))
    allowed |= {str(i) for i in range(0, 11)}  # step counts, "two solutions", etc.
    return {_canonical(n) for n in allowed}


def _canonical(number: str) -> str:
    return number.rstrip("0").rstrip(".") if "." in number else number.lstrip("0") or "0"


def consistent_with_facts(prose: LLMExplanation, facts: dict) -> bool:
    """Deterministic guard against contradicting or inventing mathematics."""
    text = " ".join([prose.explanation, prose.why_invalid, prose.how_to_avoid, prose.learning_tip])
    if facts["overall_status"] != OverallStatus.CORRECT.value and _PRAISE.search(text):
        return False
    allowed = _allowed_numbers(facts)
    return all(_canonical(n) in allowed for n in _NUMBER.findall(text))


def _next_step(full: FullCorrection) -> str | None:
    if full.action is CorrectionAction.REPLACE_STEP:
        return full.continuation[0].text if full.continuation else None
    if full.action is CorrectionAction.COMPLETE_SOLUTION:
        return full.continuation[0].text if full.continuation else None
    return None


def _template(full: FullCorrection) -> LLMExplanation:
    d = full.diagnosis
    if full.action is CorrectionAction.REMOVE_REMAINING_STEPS:
        return LLMExplanation(
            explanation=full.message + (f" {d.explanation}" if d else ""),
            why_invalid=d.evidence if d else "",
            how_to_avoid="Once every solution is stated with x on its own, the solution is finished.",
            learning_tip="Stop when the answer is complete — extra steps can only introduce mistakes.",
        )
    if full.action is CorrectionAction.COMPLETE_SOLUTION:
        first = full.continuation[0] if full.continuation else None
        return LLMExplanation(
            explanation=full.message,
            why_invalid="",
            how_to_avoid=first.explanation if first and first.explanation else "",
            learning_tip=f"Next idea: {first.rule_name}." if first and first.rule_name else "",
        )
    return LLMExplanation(
        explanation=f"{d.explanation} {d.evidence}",
        why_invalid=f"Rule: {d.expected_rule}.",
        how_to_avoid=d.hints[1],
        learning_tip=d.hints[0],
    )


def _response(result, full, prose: LLMExplanation, source: str, ai_status: str | None) -> ExplainResponse:
    d = full.diagnosis
    return ExplainResponse(
        source=source,
        ai_status=ai_status,
        overall_status=result.overall_status.value,
        first_error_step=result.first_error_step,
        error_category=d.category.value if d else None,
        expected_rule=d.expected_rule if d else None,
        corrected_step=full.corrected_step.text if full.corrected_step else None,
        suggested_next_step=_next_step(full),
        correction_action=full.action.value,
        explanation=prose.explanation,
        why_invalid=prose.why_invalid or None,
        how_to_avoid=prose.how_to_avoid or None,
        learning_tip=prose.learning_tip or None,
    )


async def explain(steps: list[str], client: OpenRouterClient) -> ExplainResponse:
    if is_calculus(steps):
        return await _explain_calculus(steps, client)
    result = verify_steps(steps)
    full = correct_full(steps)

    if full.action is CorrectionAction.NONE:
        # Correct work, unsupported/unverifiable work, or no verified correction:
        # the engine's own words, and no model call (it must not invent a verdict).
        message = (
            "Every step is valid and the final answer is complete."
            if result.overall_status is OverallStatus.CORRECT
            else full.message
        )
        return _response(result, full, LLMExplanation(explanation=message), "ENGINE", None)

    template = _template(full)
    facts = _facts(steps, result, full)
    try:
        prose = await client.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=1)},
            ],
            role="text",
            schema_name="step_explanation",
            json_schema=LLM_JSON_SCHEMA,
            validate=LLMExplanation.model_validate,
        )
    except APIError as exc:
        return _response(result, full, template, "TEMPLATE", exc.code)
    if not consistent_with_facts(prose, facts):
        return _response(result, full, template, "TEMPLATE", "REJECTED_BY_GUARD")
    return _response(result, full, prose, "LLM", None)


# ------------------------------------------------------------------------ calculus


_UNDECIDED_REASONS = {
    "TIMEOUT": "Step {n} took too long to check, so StepCheck cannot say whether it is right.",
    "UNDEFINED": "In step {n} a limit or value is undefined (for example a two-sided limit that does not exist), "
    "so StepCheck cannot confirm it.",
    "CANNOT_DECIDE": "StepCheck could not decide whether step {n} is equal to the step before it.",
}


def _calculus_engine_message(result: VerificationResult) -> str:
    if result.overall_status is OverallStatus.CORRECT:
        return "Every step is valid and the final answer is complete."
    for s in result.steps:
        if s.analysis.error:
            return f"Step {s.step} could not be checked: {s.analysis.error.message}"
    for t in result.transitions:
        if t.status is StepStatus.NEEDS_REVIEW:
            reason = _UNDECIDED_REASONS.get(t.reason_code or "", "Step {n} needs to be reviewed by a teacher.")
            return reason.format(n=t.to_step)
    return "StepCheck could not check this work."


def _calculus_diagnosis(steps: list[str], result: VerificationResult) -> CalcDiagnosis:
    """The engine's own account of the mistake (or of what is missing)."""
    if result.first_error_step is None:
        if result.missing_constant:
            return describe(CalcErrorCategory.MISSING_CONSTANT, len(steps))
        return describe(CalcErrorCategory.NOT_FINISHED, len(steps))

    n = result.first_error_step
    wrong = result.steps[n - 1].analysis.statement
    # The problem line has no earlier step to compare with (lines before it only define functions).
    if n == 1 or result.transitions[n - 2].compared_to_step is None:
        anchor_text = to_text(wrong.links[0])
    else:
        transition = result.transitions[n - 2]
        anchor = result.steps[(transition.compared_to_step or n - 1) - 1].analysis.statement
        anchor_text = to_text(anchor.links[-1])
    try:
        return get_sandbox().run("diagnose", anchor_text, to_text(wrong.links[-1]), result.topic, n)
    except (SandboxTimeout, SandboxFailure, MathInputError):
        return describe(CalcErrorCategory.GENERAL_ERROR, n)


def _calculus_facts(steps: list[str], result: VerificationResult, d: CalcDiagnosis) -> dict:
    first = next((t for t in result.transitions if t.status is StepStatus.FIRST_INVALID), None)
    return {
        "topic": result.topic,
        "student_steps": [{"step": i + 1, "text": s} for i, s in enumerate(steps)],
        "step_statuses": [s.status.value for s in result.steps],
        "overall_status": result.overall_status.value,
        "first_error_step": result.first_error_step,
        "error_category": d.category,
        "rule": d.expected_rule,
        "engine_explanation": d.explanation,
        "evidence": d.evidence or None,
        "point_where_values_differ": first.counterexample if first else None,
        "missing_constant_c": result.missing_constant,
        "correct_final_answer": result.expected_answer,
    }


def _calculus_response(result: VerificationResult, d: CalcDiagnosis | None, prose: LLMExplanation, source: str, ai_status: str | None) -> ExplainResponse:
    return ExplainResponse(
        source=source,
        ai_status=ai_status,
        overall_status=result.overall_status.value,
        first_error_step=result.first_error_step,
        error_category=d.category if d else None,
        expected_rule=d.expected_rule if d else None,
        corrected_step=None,
        suggested_next_step=None,
        correction_action=None,
        explanation=prose.explanation,
        why_invalid=prose.why_invalid or None,
        how_to_avoid=prose.how_to_avoid or None,
        learning_tip=prose.learning_tip or None,
    )


async def _explain_calculus(steps: list[str], client: OpenRouterClient) -> ExplainResponse:
    # The verifier waits on the sandbox; keep that off the event loop.
    result = await run_in_threadpool(verify_calculus, steps)
    if result.overall_status not in (OverallStatus.INCORRECT, OverallStatus.INCOMPLETE):
        return _calculus_response(result, None, LLMExplanation(explanation=_calculus_engine_message(result)), "ENGINE", None)

    d = await run_in_threadpool(_calculus_diagnosis, steps, result)
    template = LLMExplanation(
        explanation=f"{d.explanation} {d.evidence}".strip(),
        why_invalid=f"Rule: {d.expected_rule}.",
        how_to_avoid=d.hints[1],
        learning_tip=d.hints[0],
    )
    facts = _calculus_facts(steps, result, d)
    try:
        prose = await client.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=1)},
            ],
            role="text",
            schema_name="step_explanation",
            json_schema=LLM_JSON_SCHEMA,
            validate=LLMExplanation.model_validate,
        )
    except APIError as exc:
        return _calculus_response(result, d, template, "TEMPLATE", exc.code)
    if not consistent_with_facts(prose, facts):
        return _calculus_response(result, d, template, "TEMPLATE", "REJECTED_BY_GUARD")
    return _calculus_response(result, d, prose, "LLM", None)
