from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router, start_scheduler, stop_scheduler
from backend.core.config import ALLOWED_ORIGINS, BASE_DIR
from backend.core.logging import setup_logging

STATIC_DIR = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="AngadGPT Nexus", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()
