from fastapi import APIRouter, Depends

from app.api.dependencies import resolve_steps
from app.api.schemas.explanation import ExplainRequest, ExplainResponse
from app.services.explanation_service import explain as explain_steps
from app.services.openrouter_client import OpenRouterClient, get_openrouter_client

router = APIRouter(tags=["explanation"])


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    request: ExplainRequest,
    client: OpenRouterClient = Depends(get_openrouter_client),
) -> ExplainResponse:
    steps = resolve_steps(request.verification_id, request.steps)
    return await explain_steps(steps, client)
