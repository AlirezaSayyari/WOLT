from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.infrastructure.database import Database
from app.web.auth_routes import create_auth_router
from app.web.config import WebSettings


API_PREFIX = "/api/v1"
VERSION = "0.2.0-dev"


class DatabaseHealth(Protocol):
    def is_ready(self) -> bool: ...

    def schema_is_ready(self) -> bool: ...

    def owner_exists(self) -> bool: ...

    def dispose(self) -> None: ...


def _api_router(database: DatabaseHealth, settings: WebSettings) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        return {"status": "ok", "service": "wolt-web", "version": VERSION}

    @router.get("/health/ready", tags=["health"])
    def readiness() -> Response:
        if not database.is_ready():
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "unavailable"},
            )
        if not database.schema_is_ready():
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "database": "migration_required"},
            )
        return JSONResponse(content={"status": "ready", "database": "ready"})

    @router.get("/setup/status", tags=["setup"])
    def setup_status() -> dict[str, object]:
        database_ready = database.is_ready()
        schema_ready = database_ready and database.schema_is_ready()
        owner_exists = schema_ready and database.owner_exists()
        return {
            "database_ready": database_ready,
            "schema_ready": schema_ready,
            "setup_required": not owner_exists,
            "bootstrap_configured": bool(settings.bootstrap_token),
        }

    @router.get("/system/info", tags=["system"])
    def system_info() -> dict[str, str]:
        return {
            "name": "WOLT",
            "version": VERSION,
            "environment": settings.environment,
            "api_version": "v1",
        }

    return router


def create_app(
    settings: WebSettings | None = None,
    database: DatabaseHealth | None = None,
) -> FastAPI:
    resolved_settings = settings or WebSettings.from_env()
    resolved_database = database or Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        resolved_database.dispose()

    docs_url = "/api/docs" if resolved_settings.environment != "production" else None
    app = FastAPI(
        title="WOLT Management API",
        version=VERSION,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_url else None,
        lifespan=lifespan,
    )
    app.include_router(_api_router(resolved_database, resolved_settings))
    app.include_router(
        create_auth_router(cast(Database, resolved_database), resolved_settings)
    )

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    static_dir = resolved_settings.static_dir
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        requested = (static_dir / path).resolve()
        try:
            requested.relative_to(static_dir.resolve())
        except ValueError:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        if path and requested.is_file():
            return FileResponse(requested)
        index = Path(static_dir) / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Web assets are not installed"},
        )

    return app
