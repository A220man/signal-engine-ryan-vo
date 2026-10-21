"""Signal Engine - Sheet Metal Unfold API."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.core.config import get_settings
from app.api import unfold

# Structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("starting_up", app=settings.APP_NAME, version=settings.APP_VERSION, env=settings.ENVIRONMENT)

    # Create upload directory
    import os
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    yield

    logger.info("shutting_down", app=settings.APP_NAME)


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Sheet-metal unfolding engine for CAD automation",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

    # Routes
    app.include_router(unfold.router)

    # Health
    @app.get("/health")
    async def health():
        return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    )