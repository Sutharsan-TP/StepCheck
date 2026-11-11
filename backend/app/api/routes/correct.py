from fastapi import APIRouter

from app.api.schemas.correction import CorrectRequest, CorrectResponse
from app.core.correction_engine import InvalidProgress, correct_full, correct_guided
from app.services import progress_token
from app.services.verification_store import LookupStatus, verification_store
from app.utils.errors import APIError

router = APIRouter(tags=["correction"])


def _steps_for(request: CorrectRequest) -> list[str]:
    if request.steps is not None:
        return list(request.steps)
    lookup = verification_store.get(str(request.verification_id))
    if lookup.status is LookupStatus.EXPIRED:
        raise APIError(
            410,
            "VERIFICATION_EXPIRED",
            "This verification has expired. Submit the steps again (or send them directly in 'steps').",
        )
    if lookup.status is LookupStatus.NOT_FOUND:
        raise APIError(
            404,
            "VERIFICATION_NOT_FOUND",
            "No verification exists with this id. It may have been cleared by a server restart; "
            "submit the steps again.",
        )
    return list(lookup.entry.steps)


@router.post("/correct", response_model=CorrectResponse)
def correct(request: CorrectRequest) -> CorrectResponse:
    steps = _steps_for(request)
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
