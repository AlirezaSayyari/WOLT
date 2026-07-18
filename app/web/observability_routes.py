import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.application.auth_service import AuthService, AuthenticatedUser
from app.application.engine_runtime import EngineRuntime
from app.application.observability_service import (
    ObservabilityService,
    RetentionService,
    UdpRangeExcludesListenersError,
    UdpRangeOutsidePublishedError,
)
from app.infrastructure.database.connection import Database
from app.web.auth_routes import SESSION_COOKIE
from app.web.config import WebSettings


class RetentionSettingsRequest(BaseModel):
    wake_event_retention_days: int = Field(ge=1, le=3650)
    audit_event_retention_days: int = Field(ge=30, le=3650)
    rate_limit_seconds: int = Field(ge=0, le=3600)


class UdpRangeRequest(BaseModel):
    udp_port_start: int = Field(ge=1024, le=65535)
    udp_port_end: int = Field(ge=1024, le=65535)

    @model_validator(mode="after")
    def validate_range(self) -> "UdpRangeRequest":
        if self.udp_port_start > self.udp_port_end:
            raise ValueError("udp_range_start_after_end")
        if self.udp_port_end - self.udp_port_start + 1 > 100:
            raise ValueError("udp_range_too_wide")
        return self


def create_observability_router(
    *,
    database: Database,
    settings: WebSettings,
    observability: ObservabilityService,
    retention: RetentionService,
    runtime: EngineRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    auth = AuthService(database, settings.session_hours)

    def require_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> AuthenticatedUser:
        if not session_token:
            raise HTTPException(status_code=401, detail="authentication_required")
        user = auth.current_user(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        return user

    def require_admin(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
        if user.role not in {"owner", "administrator"}:
            raise HTTPException(status_code=403, detail="insufficient_permissions")
        return user

    @router.get("/dashboard", tags=["observability"])
    def dashboard(
        hours: int = Query(default=24, ge=1, le=168),
        _user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        return observability.dashboard(hours)

    @router.get("/events", tags=["observability"])
    def events(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        result_code: str | None = Query(default=None, max_length=80),
        mapping_id: uuid.UUID | None = None,
        device_id: uuid.UUID | None = None,
        query: str | None = Query(default=None, max_length=120),
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        _user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        return observability.wake_events(
            page=page,
            page_size=page_size,
            result_code=result_code,
            mapping_id=mapping_id,
            device_id=device_id,
            query=query,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )

    @router.get("/events/export.csv", tags=["observability"])
    def export_events(
        result_code: str | None = Query(default=None, max_length=80),
        mapping_id: uuid.UUID | None = None,
        device_id: uuid.UUID | None = None,
        query: str | None = Query(default=None, max_length=120),
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        _user: AuthenticatedUser = Depends(require_user),
    ) -> Response:
        csv_content = observability.wake_events_csv(
            result_code=result_code,
            mapping_id=mapping_id,
            device_id=device_id,
            query=query,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
        return Response(
            content="\ufeff" + csv_content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="wolt-events.csv"'},
        )

    @router.get("/audit", tags=["audit"])
    def audit(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        action: str | None = Query(default=None, max_length=120),
        object_type: str | None = Query(default=None, max_length=80),
        query: str | None = Query(default=None, max_length=120),
        _user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        return observability.audit_events(
            page=page,
            page_size=page_size,
            action=action,
            object_type=object_type,
            query=query,
        )

    @router.get("/settings", tags=["settings"])
    def get_settings(
        _user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        return observability.settings()

    @router.put("/settings/retention", tags=["settings"])
    def update_settings(
        payload: RetentionSettingsRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        result = observability.update_retention(
            wake_days=payload.wake_event_retention_days,
            audit_days=payload.audit_event_retention_days,
            rate_limit_seconds=payload.rate_limit_seconds,
            actor_id=user.id,
            client_ip=request.client.host if request.client else "unknown",
        )
        runtime.reconcile_if_active()
        return result

    @router.put("/settings/udp-range", tags=["settings"])
    def update_udp_range(
        payload: UdpRangeRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            result = observability.update_udp_range(
                udp_start=payload.udp_port_start,
                udp_end=payload.udp_port_end,
                actor_id=user.id,
                client_ip=request.client.host if request.client else "unknown",
            )
        except UdpRangeOutsidePublishedError as exc:
            raise HTTPException(status_code=422, detail=exc.detail) from exc
        except UdpRangeExcludesListenersError as exc:
            raise HTTPException(status_code=409, detail=exc.detail) from exc
        runtime.reconcile_if_active()
        return result

    @router.post("/settings/retention/run", tags=["settings"])
    def run_retention(
        _user: AuthenticatedUser = Depends(require_admin),
    ) -> dict[str, int | bool]:
        return retention.cleanup()

    return router
