"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _csv(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    service_name: str = "stepcheck-api"
    cors_origins: list[str] = field(
        default_factory=lambda: _csv("CORS_ORIGINS", "http://localhost:3000")
    )
    max_steps: int = int(os.getenv("MAX_STEPS", "30"))
    # OpenRouter (used from Milestone 2; read here so config lives in one place)
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_vision_model: str = os.getenv("OPENROUTER_VISION_MODEL", "")
    openrouter_text_model: str = os.getenv("OPENROUTER_TEXT_MODEL", "")
    openrouter_fallback_model: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "")


settings = Settings()
