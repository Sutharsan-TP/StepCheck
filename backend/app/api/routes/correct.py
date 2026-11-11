from fastapi import APIRouter

from app.api.dependencies import resolve_steps
from app.api.schemas.correction import CorrectRequest, CorrectResponse
from app.core.correction_engine import InvalidProgress, correct_full, correct_guided
from app.services import progress_token
from app.utils.errors import APIError

router = APIRouter(tags=["correction"])


@router.post("/correct", response_model=CorrectResponse)
def correct(request: CorrectRequest) -> CorrectResponse:
    steps = resolve_steps(request.verification_id, request.steps)
    if request.mode == "FULL":
        return CorrectResponse.from_full(correct_full(steps))

    if request.progress and not progress_token.is_valid(request.progress_token, steps, request.progress):
        raise APIError(
            422,
            "PROGRESS_TOKEN_INVALID",
            "The submitted progress was not issued by StepCheck for this solution. Restart guided correction.",
        )
    try:
        guided = correct_guided(steps, request.progress, request.attempt, request.hint_level)
    except InvalidProgress as exc:
        raise APIError(422, "INVALID_PROGRESS", exc.message) from None
    return CorrectResponse.from_guided(guided, progress_token.sign(steps, guided.progress))
