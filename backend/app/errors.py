"""Typed errors with one JSON shape: {"error": {"code": ..., "message": ...}}."""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(AppError):
    status = 404
    code = "not_found"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Conflict(AppError):
    """The action is not allowed in the current state (e.g. wrong order status)."""

    status = 409
    code = "conflict"


class InsufficientFunds(AppError):
    status = 409
    code = "insufficient_funds"


class LimitExceeded(AppError):
    status = 409
    code = "limit_exceeded"


class TooManyRequests(AppError):
    status = 429
    code = "too_many_requests"


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})
