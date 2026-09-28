from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import Settings
from app.db import Database
from app.routes import api, pages

APP_DIR = Path(__file__).resolve().parent


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        app_settings.ensure_directories()
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
    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    application.include_router(pages.router)
    application.include_router(api.router)
    return application


app = create_app()
