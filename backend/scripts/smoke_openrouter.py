"""Manual smoke test for the configured OpenRouter models (makes REAL, billable requests).

Run only after setting OPENROUTER_API_KEY and model names in backend/.env:
    .venv\\Scripts\\python scripts\\smoke_openrouter.py

Checks that the text model returns schema-valid JSON and that the vision model
can read one of the bundled handwritten samples. Never run by the test suites.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.explanation_service import explain  # noqa: E402
from app.services.image_service import prepare_image  # noqa: E402
from app.services.openrouter_client import get_openrouter_client  # noqa: E402
from app.services.vision_service import transcribe  # noqa: E402
from app.utils.errors import APIError  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "handwritten_samples" / "demo2_first_error.png"
EXPECTED = ["2x + 5 = 15", "2x = 15 - 5", "2x = 20", "x = 10"]


async def main() -> int:
    if settings.stub_ai:
        print("STEPCHECK_STUB_AI is enabled; unset it to test real models.")
        return 1
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not set (backend/.env).")
        return 1
    client = get_openrouter_client()
    ok = True

    print(f"Text model:     {settings.openrouter_text_model or '(not set)'}")
    try:
        result = await explain(EXPECTED, client)
        print(f"  source={result.source} ai_status={result.ai_status}")
        print(f"  explanation: {result.explanation[:160]}")
        ok &= result.source == "LLM"
    except APIError as exc:
        print(f"  FAILED: {exc.code} - {exc.message}")
        ok = False

    print(f"Vision model:   {settings.openrouter_vision_model or '(not set)'}")
    try:
        transcription = await transcribe(client, prepare_image(SAMPLE.read_bytes()))
        lines = [s.expression for s in transcription.steps]
        print(f"  lines: {lines}")
        print(f"  flagged for review: {[s.step_number for s in transcription.steps if s.needs_review]}")
        exact = [line.replace(" ", "") for line in lines] == [e.replace(" ", "") for e in EXPECTED]
        print(f"  exact transcription: {'yes' if exact else 'no (review the output above)'}")
    except APIError as exc:
        print(f"  FAILED: {exc.code} - {exc.message}")
        ok = False

    print(f"Fallback model: {settings.openrouter_fallback_model or '(not set)'}")
    print("RESULT:", "OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
