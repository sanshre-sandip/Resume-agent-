import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from .config import settings
from .routers import auth, resumes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Resume Creator API")
    yield
    logger.info("Shutting down AI Resume Creator API")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nhyapu Craft",
        description="Create, edit, and export professional resumes.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(resumes.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Pydantic v2 errors include rejected input; never echo credentials back to clients.
        safe_errors = []
        for error in exc.errors():
            safe_error = dict(error)
            if any(str(part).lower() in {"api_key", "password", "current_password", "new_password"} for part in error.get("loc", ())):
                safe_error.pop("input", None)
            safe_errors.append(safe_error)
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(safe_errors)})

    static_dir = Path(__file__).resolve().parents[2] / "frontend" / "static"
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(static_dir / "index.html")

    @app.get("/workspace", include_in_schema=False)
    def workspace(request: Request):
        try:
            auth.get_current_user(request)
        except HTTPException:
            return RedirectResponse("/login?next=%2Fworkspace", status_code=303)
        return FileResponse(static_dir / "workspace.html")

    @app.get("/login", include_in_schema=False)
    @app.get("/register", include_in_schema=False)
    @app.get("/forgot-password", include_in_schema=False)
    @app.get("/reset-password", include_in_schema=False)
    def authentication_page():
        return FileResponse(static_dir / "auth.html")

    @app.get("/account", include_in_schema=False)
    def account_page(request: Request):
        try:
            auth.get_current_user(request)
        except HTTPException:
            return RedirectResponse("/login?next=%2Faccount", status_code=303)
        return FileResponse(static_dir / "account.html")

    @app.get("/privacy", include_in_schema=False)
    def privacy_page():
        return FileResponse(static_dir / "privacy.html")

    @app.get("/terms", include_in_schema=False)
    def terms_page():
        return FileResponse(static_dir / "terms.html")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.middleware("http")
    async def validate_request_origin(request, call_next):
        origin = request.headers.get("origin")
        if origin and request.method not in {"GET", "HEAD", "OPTIONS"}:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host", ""):
                return JSONResponse(status_code=403, content={"detail": "Cross-site requests are not allowed."})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'; "
            "frame-ancestors 'self'; frame-src 'self'; img-src 'self' data: blob:; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self'; "
            "connect-src 'self'"
        )
        # CSP frame-ancestors is the authoritative framing policy. Strip any
        # redundant XFO header added by a surrounding ASGI middleware.
        if "x-frame-options" in response.headers:
            del response.headers["x-frame-options"]
        if settings.app_env.lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
