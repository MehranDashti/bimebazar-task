from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    InactiveAccountError,
    NotFoundError,
)

_ERROR_MESSAGES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthenticated",
    403: "Unauthorized",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Validation Exception",
    429: "Too Many Requests",
    500: "Unexpected Exception",
}


def _envelope(request: Request, code: int, message: str, error: dict) -> dict:
    """Build the standard failure envelope, attaching the request id when present."""
    body: dict = {"success": False, "code": code, "message": message, "error": error}
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        body["request_id"] = request_id
    return body


_DOMAIN_STATUS_MAP: dict[type, int] = {
    NotFoundError: 404,
    ConflictError: 409,
    AuthenticationError: 401,
    InactiveAccountError: 403,
}


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    status_code = _DOMAIN_STATUS_MAP.get(type(exc), 400)
    message = _ERROR_MESSAGES.get(status_code, "Something went wrong")
    return JSONResponse(
        status_code=status_code,
        content=_envelope(request, status_code, message, {"detail": exc.detail}),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = _ERROR_MESSAGES.get(exc.status_code, "Something went wrong")
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(request, exc.status_code, message, {"detail": exc.detail}),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"] if loc != "body")
        errors.setdefault(field, []).append(err["msg"])
    return JSONResponse(
        status_code=422,
        content=_envelope(request, 422, "Validation Exception", errors),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_envelope(
            request,
            500,
            "Unexpected Exception",
            {"detail": "An unexpected error occurred."},
        ),
    )
