import uuid
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.auth_service import AuthService, AuthenticatedUser
from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import ApplicationSettings, AuditEvent
from app.infrastructure.host_agent import HostAgentClient, HostAgentError
from app.web.auth_routes import SESSION_COOKIE
from app.web.config import WebSettings


class NetworkRequest(BaseModel):
    source_ip: str = Field(min_length=2, max_length=45)
    udp_start: int = Field(ge=1024, le=65535)
    udp_end: int = Field(ge=1024, le=65535)


class UpgradeRequest(BaseModel):
    version: str = Field(min_length=1, max_length=80)


def create_host_router(
    *, database: Database, settings: WebSettings, client: HostAgentClient
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/host", tags=["host"])
    auth = AuthService(database, settings.session_hours)

    def require_owner(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> AuthenticatedUser:
        user = auth.current_user(session_token) if session_token else None
        if user is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        if user.role != "owner":
            raise HTTPException(status_code=403, detail="insufficient_permissions")
        return user

    def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return client.request(method, path, payload)
        except HostAgentError as exc:
            code = exc.status if 400 <= exc.status < 600 else 503
            raise HTTPException(status_code=code, detail=exc.detail) from exc

    def audit(
        *, user_id: uuid.UUID, action: str, changes: dict[str, Any], request: Request
    ) -> None:
        with database.session() as session:
            session.add(AuditEvent(
                actor_user_id=user_id, action=action, object_type="host",
                object_id="local", safe_changes=changes,
                client_ip=request.client.host if request.client else "unknown",
            ))
            session.commit()

    @router.get("/status")
    def status(_user: AuthenticatedUser = Depends(require_owner)) -> dict[str, Any]:
        return call("GET", "/v1/status")

    @router.get("/releases")
    def releases(_user: AuthenticatedUser = Depends(require_owner)) -> dict[str, Any]:
        return call("GET", "/v1/releases")

    @router.get("/jobs/{job_id}")
    def job(job_id: uuid.UUID, _user: AuthenticatedUser = Depends(require_owner)) -> dict[str, Any]:
        return call("GET", f"/v1/jobs/{job_id}")

    @router.post("/firewall/preview")
    def preview(payload: NetworkRequest, _user: AuthenticatedUser = Depends(require_owner)) -> dict[str, Any]:
        return call("POST", "/v1/firewall/preview", payload.model_dump())

    @router.post("/firewall/apply")
    def apply_firewall(
        payload: NetworkRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> dict[str, Any]:
        result = call("POST", "/v1/firewall/apply", payload.model_dump())
        audit(user_id=user.id, action="host.firewall_applied", changes=payload.model_dump(), request=request)
        return result

    @router.post("/deployment")
    def deployment(
        payload: NetworkRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> dict[str, Any]:
        with database.session() as session:
            active = session.get(ApplicationSettings, 1)
            if active is not None and not (
                payload.udp_start <= active.udp_port_start
                and payload.udp_end >= active.udp_port_end
            ):
                raise HTTPException(
                    status_code=422,
                    detail="published_range_excludes_active_range",
                )
        result = call("POST", "/v1/deployment", payload.model_dump())
        audit(user_id=user.id, action="host.deployment_started", changes={**payload.model_dump(), **result}, request=request)
        return result

    @router.post("/upgrade")
    def upgrade(
        payload: UpgradeRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> dict[str, Any]:
        result = call("POST", "/v1/upgrade", payload.model_dump())
        audit(user_id=user.id, action="host.upgrade_started", changes={"version": payload.version, **result}, request=request)
        return result

    @router.post("/rollback")
    def rollback(
        request: Request, user: AuthenticatedUser = Depends(require_owner),
    ) -> dict[str, Any]:
        result = call("POST", "/v1/rollback", {})
        audit(user_id=user.id, action="host.rollback_started", changes=result, request=request)
        return result

    return router
