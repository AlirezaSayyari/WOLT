from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, FastAPI, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.application.engine_runtime import EngineRuntime
from app.application.operations_service import (
    DeviceService,
    EngineStateService,
    ListenerService,
)
from app.application.observability_service import (
    ObservabilityService,
    RetentionService,
    RetentionWorker,
)
from app.drivers import DriverRegistry
from app.infrastructure.crypto import CredentialCipher
from app.infrastructure.database import Database
from app.web.auth_routes import create_auth_router
from app.web.config import WebSettings
from app.web.operations_routes import create_operations_router
from app.web.observability_routes import create_observability_router
from app.application.identity_service import IdentityService
from app.web.identity_routes import create_identity_router
from app.infrastructure.host_agent import HostAgentClient
from app.infrastructure.email import SmtpMailer
from app.web.host_routes import create_host_router


API_PREFIX = "/api/v1"
class DatabaseHealth(Protocol):
    def is_ready(self) -> bool: ...

    def schema_is_ready(self) -> bool: ...

    def schema_revision(self) -> str | None: ...

    def owner_exists(self) -> bool: ...

    def dispose(self) -> None: ...


def _api_router(database: DatabaseHealth, settings: WebSettings) -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health/live", tags=["health"])
    def liveness() -> dict[str, str]:
        return {"status": "ok", "service": "wolt-web", "version": settings.version}

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
            "master_key_configured": bool(settings.master_key),
        }

    @router.get("/system/info", tags=["system"])
    def system_info() -> dict[str, str]:
        return {
            "name": "WOLT",
            "version": settings.version,
            "environment": settings.environment,
            "api_version": "v1",
            "commit_sha": settings.commit_sha,
            "build_date": settings.build_date,
            "schema_revision": database.schema_revision() or "unavailable",
        }

    return router


def create_app(
    settings: WebSettings | None = None,
    database: DatabaseHealth | None = None,
) -> FastAPI:
    resolved_settings = settings or WebSettings.from_env()
    resolved_database = database or Database(resolved_settings.database_url)
    runtime: EngineRuntime | None = None
    retention_worker: RetentionWorker | None = None

    if isinstance(resolved_database, Database):
        registry = DriverRegistry()
        cipher = (
            CredentialCipher(resolved_settings.master_key)
            if resolved_settings.master_key
            else None
        )
        device_service = DeviceService(resolved_database, registry, cipher)
        listener_service = ListenerService(resolved_database, registry)
        engine_service = EngineStateService(resolved_database)
        runtime = EngineRuntime(resolved_database, device_service, registry)
        observability_service = ObservabilityService(
            resolved_database,
            published_udp_start=resolved_settings.udp_published_start,
            published_udp_end=resolved_settings.udp_published_end,
        )
        retention_service = RetentionService(resolved_database)
        retention_worker = RetentionWorker(retention_service)
        identity_service = IdentityService(
            resolved_database,
            cipher,
            mailer=SmtpMailer(ca_file=resolved_settings.smtp_ca_file),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            if runtime is not None:
                runtime.start_from_desired_state()
            if retention_worker is not None:
                retention_worker.start()
            yield
        finally:
            if retention_worker is not None:
                retention_worker.stop()
            if runtime is not None:
                runtime.shutdown()
            resolved_database.dispose()

    docs_url = "/api/docs" if resolved_settings.environment != "production" else None
    app = FastAPI(
        title="WOLT Management API",
        version=resolved_settings.version,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_url else None,
        lifespan=lifespan,
    )
    app.include_router(_api_router(resolved_database, resolved_settings))
    app.include_router(
        create_auth_router(cast(Database, resolved_database), resolved_settings)
    )
    if runtime is not None:
        app.include_router(
            create_identity_router(
                service=identity_service,
                database=resolved_database,
                settings=resolved_settings,
            )
        )
        app.include_router(
            create_host_router(
                database=resolved_database,
                settings=resolved_settings,
                client=HostAgentClient(
                    resolved_settings.host_agent_socket,
                    resolved_settings.host_agent_token,
                ),
            )
        )
        app.include_router(
            create_operations_router(
                database=resolved_database,
                settings=resolved_settings,
                registry=registry,
                devices=device_service,
                listeners=listener_service,
                engine_state=engine_service,
                runtime=runtime,
            )
        )
        app.include_router(
            create_observability_router(
                database=resolved_database,
                settings=resolved_settings,
                observability=observability_service,
                retention=retention_service,
                runtime=runtime,
            )
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
