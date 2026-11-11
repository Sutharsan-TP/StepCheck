from fastapi import APIRouter

from app.api.schemas.verification import VerifyRequest, VerifyResponse
from app.core.first_error_detector import verify_steps
from app.services.verification_store import verification_store

router = APIRouter(tags=["verification"])


@router.post("/verify", response_model=VerifyResponse)
def verify(request: VerifyRequest) -> VerifyResponse:
    # Sync handler: SymPy work runs in FastAPI's threadpool, not the event loop.
    result = verify_steps(request.steps)
    verification_id = verification_store.save(request.steps, result)
    return VerifyResponse.from_result(result, request.request_id, verification_id)
