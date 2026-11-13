"""StepCheck API entry point."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import correct, explain, transcribe, verify
from app.config import settings
from app.core.calculus.sandbox import get_sandbox
from app.services.rate_limiter import rate_limit
from app.utils.errors import APIError

logger = logging.getLogger("stepcheck")

API_PREFIX = "/api/v1"


def _error(
    status: int, code: str, message: str, details: list | None = None, headers: dict | None = None
) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body, headers=headers)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # Start the calculus worker in the background so the first calculus request
    # does not wait for SymPy to load; algebra requests never need it.
    threading.Thread(target=_warm_sandbox, daemon=True).start()
    yield
    get_sandbox().shutdown()


def _warm_sandbox() -> None:
    try:
        get_sandbox().warm_up()
    except Exception:  # it will be started on first use instead
        logger.exception("Calculus worker warm-up failed")


def create_app() -> FastAPI:
    app = FastAPI(title="StepCheck API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Retry-After"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in e.get("loc", ())[1:]), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _error(422, "INVALID_REQUEST", "The request is invalid.", details)

    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")  # logged server-side only
        return _error(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"service": settings.service_name, "health": f"{API_PREFIX}/health", "docs": "/docs"}

    @app.get(f"{API_PREFIX}/health")
    def health() -> dict:
        return {"status": "healthy", "service": settings.service_name}

    for router, bucket in (
        (verify.router, "verify"),
        (correct.router, "correct"),
        (transcribe.router, "transcribe"),
        (explain.router, "explain"),
    ):
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(rate_limit(bucket))])
    return app


app = create_app()
