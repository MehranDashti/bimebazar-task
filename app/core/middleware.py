import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        request.state.request_id = request_id

        logger.info(
            f"[{request_id}] --> {request.method} {request.url.path} "
            f"client={request.client.host if request.client else 'unknown'}"
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(f"[{request_id}] UNHANDLED EXCEPTION: {exc}", exc_info=True)
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"[{request_id}] <-- {request.method} {request.url.path} "
            f"status={response.status_code} duration={duration_ms:.2f}ms"
        )

        response.headers["X-Request-ID"] = request_id
        return response
