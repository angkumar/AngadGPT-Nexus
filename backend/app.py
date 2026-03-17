from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router, start_scheduler
from backend.core.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="AngadGPT Nexus")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"] ,
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    try:
        app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
    except RuntimeError:
        # Frontend not built yet
        pass

    @app.on_event("startup")
    async def _startup() -> None:
        start_scheduler()

    return app


app = create_app()

