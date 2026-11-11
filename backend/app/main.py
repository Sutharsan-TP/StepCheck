"""StepCheck API entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import correct, explain, transcribe, verify
from app.config import settings
from app.utils.errors import APIError

logger = logging.getLogger("stepcheck")

API_PREFIX = "/api/v1"


def _error(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status, content=body)


def create_app() -> FastAPI:
    app = FastAPI(title="StepCheck API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
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
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")  # logged server-side only
        return _error(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    @app.get(f"{API_PREFIX}/health")
    def health() -> dict:
        return {"status": "healthy", "service": settings.service_name}

    app.include_router(verify.router, prefix=API_PREFIX)
    app.include_router(correct.router, prefix=API_PREFIX)
    app.include_router(transcribe.router, prefix=API_PREFIX)
    app.include_router(explain.router, prefix=API_PREFIX)
    return app


app = create_app()
