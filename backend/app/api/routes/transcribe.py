from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.schemas.transcription import TranscriptionResponse
from app.services.image_service import prepare_image, read_upload
from app.services.openrouter_client import OpenRouterClient, get_openrouter_client
from app.services.vision_service import transcribe as transcribe_image

router = APIRouter(tags=["transcription"])


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    client: OpenRouterClient = Depends(get_openrouter_client),
) -> TranscriptionResponse:
    data = await read_upload(file)
    image = await run_in_threadpool(prepare_image, data)
    del data  # keep the raw upload in memory no longer than needed
    return await transcribe_image(client, image)
