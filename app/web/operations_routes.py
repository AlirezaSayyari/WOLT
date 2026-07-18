import uuid
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.application.auth_service import AuthService, AuthenticatedUser
from app.application.engine_runtime import EngineRuntime
from app.application.operations_service import (
    DeviceService,
    EngineStateService,
    ListenerService,
    MasterKeyRequiredError,
    OperationsError,
    ResourceConflictError,
    ResourceInUseError,
    ResourceNotFoundError,
    StaleVersionError,
)
from app.drivers import DriverRegistry
from app.drivers.base import DriverValidationError
from app.infrastructure.database.connection import Database
from app.web.auth_routes import SESSION_COOKIE
from app.web.config import WebSettings


class DeviceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    driver_type: str = Field(min_length=1, max_length=80)
    configuration: dict[str, Any]
    credentials: dict[str, Any]
    enabled: bool = True


class DeviceUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    configuration: dict[str, Any]
    credentials: dict[str, Any] | None = None
    enabled: bool = True


class ListenerCreateRequest(BaseModel):
    device_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    udp_port: int | None = Field(default=None, ge=1, le=65535)
    allowed_source_ip: str = Field(min_length=2, max_length=45)
    driver_parameters: dict[str, Any]
    enabled: bool = False


class ListenerUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    device_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    udp_port: int = Field(ge=1, le=65535)
    allowed_source_ip: str = Field(min_length=2, max_length=45)
    driver_parameters: dict[str, Any]
    enabled: bool = False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _translate_error(exc: Exception) -> None:
    if isinstance(exc, ResourceNotFoundError):
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    if isinstance(exc, (ResourceConflictError, ResourceInUseError, StaleVersionError)):
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if isinstance(exc, MasterKeyRequiredError):
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    if isinstance(exc, DriverValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, OperationsError):
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    raise exc


def create_operations_router(
    *,
    database: Database,
    settings: WebSettings,
    registry: DriverRegistry,
    devices: DeviceService,
    listeners: ListenerService,
    engine_state: EngineStateService,
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

    @router.get("/drivers", tags=["devices"])
    def driver_schemas(_user: AuthenticatedUser = Depends(require_user)) -> list[dict[str, Any]]:
        return registry.schemas()

    @router.get("/devices", tags=["devices"])
    def list_devices(_user: AuthenticatedUser = Depends(require_user)) -> list[dict[str, Any]]:
        return devices.list()

    @router.post("/devices", status_code=status.HTTP_201_CREATED, tags=["devices"])
    def create_device(
        payload: DeviceCreateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        try:
            result = devices.create(
                name=payload.name,
                driver_type=payload.driver_type,
                configuration=payload.configuration,
                credentials=payload.credentials,
                enabled=payload.enabled,
                actor_id=user.id,
                client_ip=_client_ip(request),
            )
            runtime.reconcile_if_active()
            return result
        except Exception as exc:
            _translate_error(exc)

    @router.put("/devices/{device_id}", tags=["devices"])
    def update_device(
        device_id: uuid.UUID,
        payload: DeviceUpdateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        try:
            result = devices.update(
                device_id,
                name=payload.name,
                configuration=payload.configuration,
                credentials=payload.credentials,
                enabled=payload.enabled,
                actor_id=user.id,
                client_ip=_client_ip(request),
            )
            runtime.reconcile_if_active()
            return result
        except Exception as exc:
            _translate_error(exc)

    @router.delete("/devices/{device_id}", status_code=204, tags=["devices"])
    def delete_device(
        device_id: uuid.UUID,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> None:
        try:
            devices.delete(device_id, actor_id=user.id, client_ip=_client_ip(request))
        except Exception as exc:
            _translate_error(exc)

    @router.post("/devices/{device_id}/test", tags=["devices"])
    def test_device(
        device_id: uuid.UUID,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        try:
            return devices.test_connection(
                device_id, actor_id=user.id, client_ip=_client_ip(request)
            )
        except Exception as exc:
            _translate_error(exc)

    @router.get("/listeners", tags=["listeners"])
    def list_listeners(_user: AuthenticatedUser = Depends(require_user)) -> list[dict[str, Any]]:
        return listeners.list()

    @router.post("/listeners", status_code=status.HTTP_201_CREATED, tags=["listeners"])
    def create_listener(
        payload: ListenerCreateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        try:
            result = listeners.create(
                device_id=payload.device_id,
                name=payload.name,
                description=payload.description,
                udp_port=payload.udp_port,
                allowed_source_ip=payload.allowed_source_ip,
                driver_parameters=payload.driver_parameters,
                enabled=payload.enabled,
                actor_id=user.id,
                client_ip=_client_ip(request),
            )
            runtime.reconcile_if_active()
            return result
        except Exception as exc:
            _translate_error(exc)

    @router.put("/listeners/{listener_id}", tags=["listeners"])
    def update_listener(
        listener_id: uuid.UUID,
        payload: ListenerUpdateRequest,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        try:
            result = listeners.update(
                listener_id,
                version=payload.version,
                device_id=payload.device_id,
                name=payload.name,
                description=payload.description,
                udp_port=payload.udp_port,
                allowed_source_ip=payload.allowed_source_ip,
                driver_parameters=payload.driver_parameters,
                enabled=payload.enabled,
                actor_id=user.id,
                client_ip=_client_ip(request),
            )
            runtime.reconcile_if_active()
            return result
        except Exception as exc:
            _translate_error(exc)

    @router.delete("/listeners/{listener_id}", status_code=204, tags=["listeners"])
    def delete_listener(
        listener_id: uuid.UUID,
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> None:
        try:
            listeners.delete(
                listener_id, actor_id=user.id, client_ip=_client_ip(request)
            )
            runtime.reconcile_if_active()
        except Exception as exc:
            _translate_error(exc)

    @router.get("/engine", tags=["engine"])
    def get_engine(_user: AuthenticatedUser = Depends(require_user)) -> dict[str, Any]:
        return engine_state.get()

    @router.post("/engine/resume", tags=["engine"])
    def resume_engine(
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        observed, error = runtime.resume()
        return engine_state.transition(
            "active",
            observed_state=observed,
            last_error=error,
            actor_id=user.id,
            client_ip=_client_ip(request),
        )

    @router.post("/engine/pause", tags=["engine"])
    def pause_engine(
        request: Request,
        user: AuthenticatedUser = Depends(require_user),
    ) -> dict[str, Any]:
        runtime.pause()
        return engine_state.transition(
            "paused",
            observed_state="paused",
            last_error=None,
            actor_id=user.id,
            client_ip=_client_ip(request),
        )

    return router
