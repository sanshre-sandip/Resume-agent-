import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from .config import settings
from .routers import resumes, research
from .database.session import engine
from .database.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Resume Creator API")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not create database tables (DB may be unavailable): %s", exc)
    yield
    logger.info("Shutting down AI Resume Creator API")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Resume Creator",
        description="Production-ready AI-powered resume generation platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(resumes.router)
    app.include_router(research.router)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
