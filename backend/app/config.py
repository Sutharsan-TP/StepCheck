"""Environment-based configuration."""

from __future__ import annotations

import os
import secrets
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
    # Signs guided-correction progress tokens. If unset, a random per-process secret
    # is used, so tokens (like stored verifications) do not survive a restart.
    progress_token_secret: str = field(
        default_factory=lambda: os.getenv("PROGRESS_TOKEN_SECRET") or secrets.token_hex(32)
    )
    # Per-client requests per minute (in-memory, per process).
    rate_limits_per_minute: dict[str, int] = field(
        default_factory=lambda: {
            "transcribe": int(os.getenv("RATE_LIMIT_TRANSCRIBE_PER_MINUTE", "10")),
            "explain": int(os.getenv("RATE_LIMIT_EXPLAIN_PER_MINUTE", "30")),
            "verify": int(os.getenv("RATE_LIMIT_VERIFY_PER_MINUTE", "120")),
            "correct": int(os.getenv("RATE_LIMIT_CORRECT_PER_MINUTE", "120")),
        }
    )
    # Only behind a trusted reverse proxy (e.g. Render): use X-Forwarded-For for client IPs.
    trust_proxy: bool = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")
    # Local demos / end-to-end tests only: answer AI requests with a deterministic offline stub.
    stub_ai: bool = os.getenv("STEPCHECK_STUB_AI", "false").lower() in ("1", "true", "yes")
    # OpenRouter. Model names are configuration only; none are hardcoded or assumed
    # to be free or vision-capable.
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_vision_model: str = os.getenv("OPENROUTER_VISION_MODEL", "")
    openrouter_text_model: str = os.getenv("OPENROUTER_TEXT_MODEL", "")
    openrouter_fallback_model: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_timeout_seconds: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30"))
    openrouter_max_retries: int = int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))
    openrouter_app_title: str = os.getenv("OPENROUTER_APP_TITLE", "StepCheck")
    openrouter_app_url: str = os.getenv("OPENROUTER_APP_URL", "")


settings = Settings()
