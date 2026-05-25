"""Application error hierarchy and FastAPI exception handlers.

Kept intentionally small in Phase 1. Domain modules raise subclasses of
``XPredictError`` and they are mapped to clean JSON responses here.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class XPredictError(Exception):
    """Base class for expected, mapped application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, detail: str | None = None, *, status_code: int | None = None) -> None:
        self.detail = detail or self.__doc__ or "Unexpected error"
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


class NotFoundError(XPredictError):
    """Resource not found."""

    status_code = 404
    code = "not_found"


class ConflictError(XPredictError):
    """Resource conflict."""

    status_code = 409
    code = "conflict"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(XPredictError)
    async def _handle_xpredict_error(_request: Request, exc: XPredictError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "detail": exc.detail}},
        )
