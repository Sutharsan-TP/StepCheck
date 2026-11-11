from fastapi import APIRouter

from app.api.schemas.correction import CorrectRequest, CorrectResponse
from app.core.correction_engine import correct_full, correct_guided
from app.services.verification_store import verification_store
from app.utils.errors import APIError

router = APIRouter(tags=["correction"])


@router.post("/correct", response_model=CorrectResponse)
def correct(request: CorrectRequest) -> CorrectResponse:
    steps = request.steps
    if steps is None:
        steps = verification_store.get(request.verification_id)
        if steps is None:
            raise APIError(
                404,
                "VERIFICATION_NOT_FOUND",
                "This verification has expired or does not exist. Submit the steps again.",
            )
    if request.mode == "FULL":
        return CorrectResponse.from_full(correct_full(steps))
    return CorrectResponse.from_guided(
        correct_guided(steps, request.progress, request.attempt, request.hint_level)
    )
