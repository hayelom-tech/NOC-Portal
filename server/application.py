from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from server.controllers.auth import router as auth_router
from server.controllers.content import router as content_router
from server.controllers.incidents import router as incidents_router
from server.controllers.pages import router as pages_router
from server.controllers.shifts import router as shifts_router
from server.controllers.uploads import router as uploads_router
from server.controllers.users import router as users_router
from server.lifecycle import lifespan
from server.middleware import install_middleware


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_app() -> FastAPI:
    app = FastAPI(
        title="NOC Shift Portal API",
        version="1.0.0",
        docs_url="/api-docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=10000)
    install_middleware(app)
    for router in (
        auth_router,
        users_router,
        shifts_router,
        content_router,
        incidents_router,
        uploads_router,
        pages_router,
    ):
        app.include_router(router)
    app.mount("/assets", StaticFiles(directory=str(PROJECT_ROOT / "ui" / "assets")), name="assets")
    app.mount("/docs", StaticFiles(directory=str(PROJECT_ROOT / "docs")), name="documents")
    return app
