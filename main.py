from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exception_handler import (
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.core.response import ok
from app.db.session import AsyncSessionLocal, check_db, create_tables
from app.workers.expiry_worker import start_expiry_scheduler, stop_expiry_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    # In production, schema is owned by Alembic migrations — don't create_all on boot.
    if not settings.PRODUCTION:
        await create_tables()
    start_expiry_scheduler(
        session_factory=AsyncSessionLocal,
        interval_seconds=settings.EXPIRY_SWEEP_INTERVAL_SECONDS,
    )
    yield
    stop_expiry_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.PRODUCTION else None,
        redoc_url="/redoc" if not settings.PRODUCTION else None,
        openapi_url="/openapi.json" if not settings.PRODUCTION else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(api_router)

    @app.get("/health", tags=["Health"], include_in_schema=not settings.PRODUCTION)
    async def health():
        db_ok = await check_db()
        return ok(
            {
                "status": "ok" if db_ok else "degraded",
                "version": settings.APP_VERSION,
                "database": "up" if db_ok else "down",
            }
        )

    return app


app = create_app()
