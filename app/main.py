from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import Settings
from app.db import Database
from app.routes import api, pages
from app.services.files import cleanup_expired_files

APP_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        app_settings.ensure_directories()
        cleanup_expired_files(
            (app_settings.uploads_dir, app_settings.results_dir), app_settings.file_ttl_hours
        )
        application.state.database.initialize()
        yield

    application = FastAPI(
        title="FlowForge API",
        version=__version__,
        description="Upload, clean, preview, and export tabular data with reusable recipes.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = Database(app_settings.database_path)
    application.state.templates = Jinja2Templates(directory=APP_DIR / "templates")

    @application.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.url.path == "/":
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' "
                "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
                "frame-ancestors 'none'",
            )
        return response

    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    application.include_router(pages.router)
    application.include_router(api.router)
    return application


app = create_app()
