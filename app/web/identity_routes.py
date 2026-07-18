import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, HttpUrl, SecretStr

from app.application.auth_service import AuthService, AuthenticatedUser
from app.application.identity_service import (
    IdentityConflictError,
    IdentityError,
    IdentityService,
    InvalidTokenError,
    SmtpInput,
)
from app.infrastructure.email import EmailDeliveryError
from app.web.auth_routes import LoginAttemptLimiter, SESSION_COOKIE
from app.web.config import WebSettings


class SmtpRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    security: str = Field(pattern=r"^(starttls|tls|none)$")
    from_email: EmailStr
    from_name: str = Field(min_length=1, max_length=120)
    public_base_url: HttpUrl
    username: str = Field(default="", max_length=320)
    password: SecretStr = Field(default=SecretStr(""), max_length=256)
    enabled: bool = True


class SmtpTestRequest(SmtpRequest):
    recipient: EmailStr


class InviteRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    role: str = Field(pattern=r"^(administrator|operator)$")


class UserUpdateRequest(BaseModel):
    role: str = Field(pattern=r"^(owner|administrator|operator)$")
    enabled: bool


class TokenPasswordRequest(BaseModel):
    token: SecretStr = Field(min_length=32, max_length=256)
    password: SecretStr = Field(min_length=12, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _smtp_input(payload: SmtpRequest) -> SmtpInput:
    return SmtpInput(
        host=payload.host.strip(), port=payload.port, security=payload.security,
        from_email=str(payload.from_email), from_name=payload.from_name.strip(),
        public_base_url=str(payload.public_base_url).rstrip("/"),
        username=payload.username.strip(), password=payload.password.get_secret_value(),
        enabled=payload.enabled,
    )


def _translate(exc: Exception) -> None:
    if isinstance(exc, IdentityConflictError):
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if isinstance(exc, InvalidTokenError):
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    if isinstance(exc, EmailDeliveryError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, IdentityError):
        code = 404 if exc.detail == "user_not_found" else 409 if exc.detail == "last_owner_required" else 503
        raise HTTPException(status_code=code, detail=exc.detail) from exc
    raise exc


def create_identity_router(
    *, service: IdentityService, database, settings: WebSettings
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    auth = AuthService(database, settings.session_hours)
    reset_limiter = LoginAttemptLimiter(limit=3, window_seconds=300)

    def require_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> AuthenticatedUser:
        user = auth.current_user(session_token) if session_token else None
        if user is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        return user

    def require_owner(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
        if user.role != "owner":
            raise HTTPException(status_code=403, detail="insufficient_permissions")
        return user

    @router.get("/users", tags=["identity"])
    def users(_user: AuthenticatedUser = Depends(require_owner)) -> list[dict]:
        return service.list_users()

    @router.post("/users/invitations", status_code=status.HTTP_201_CREATED, tags=["identity"])
    def invite(
        payload: InviteRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> dict:
        try:
            return service.invite_user(
                username=payload.username, email=str(payload.email), role=payload.role,
                actor_id=user.id, client_ip=_client_ip(request),
            )
        except Exception as exc:
            _translate(exc)

    @router.put("/users/{user_id}", status_code=204, tags=["identity"])
    def update_user(
        user_id: uuid.UUID, payload: UserUpdateRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> None:
        try:
            service.update_user(
                user_id, role=payload.role, enabled=payload.enabled,
                actor_id=user.id, client_ip=_client_ip(request),
            )
        except Exception as exc:
            _translate(exc)

    @router.post("/users/{user_id}/revoke-sessions", status_code=204, tags=["identity"])
    def revoke_sessions(
        user_id: uuid.UUID, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> None:
        try:
            service.revoke_sessions(user_id, actor_id=user.id, client_ip=_client_ip(request))
        except Exception as exc:
            _translate(exc)

    @router.get("/smtp", tags=["identity"])
    def smtp(_user: AuthenticatedUser = Depends(require_owner)) -> dict:
        try:
            return service.smtp_view()
        except Exception as exc:
            _translate(exc)

    @router.put("/smtp", tags=["identity"])
    def save_smtp(
        payload: SmtpRequest, request: Request,
        user: AuthenticatedUser = Depends(require_owner),
    ) -> dict:
        try:
            return service.save_smtp(
                _smtp_input(payload), actor_id=user.id, client_ip=_client_ip(request)
            )
        except Exception as exc:
            _translate(exc)

    @router.post("/smtp/test", status_code=204, tags=["identity"])
    def test_smtp(
        payload: SmtpTestRequest,
        _user: AuthenticatedUser = Depends(require_owner),
    ) -> None:
        try:
            service.test_smtp(_smtp_input(payload), str(payload.recipient))
        except Exception as exc:
            _translate(exc)

    @router.post("/auth/accept-invitation", status_code=204, tags=["authentication"])
    def accept_invitation(payload: TokenPasswordRequest, request: Request) -> None:
        try:
            service.accept_invitation(
                payload.token.get_secret_value(), payload.password.get_secret_value(),
                _client_ip(request),
            )
        except Exception as exc:
            _translate(exc)

    @router.post("/auth/password-reset/request", status_code=202, tags=["authentication"])
    def request_reset(payload: PasswordResetRequest, request: Request) -> dict[str, str]:
        client_ip = _client_ip(request)
        if not reset_limiter.allow(client_ip):
            return {"status": "accepted"}
        try:
            service.request_password_reset(str(payload.email), client_ip)
        except EmailDeliveryError:
            # The public response remains neutral to prevent account and SMTP discovery.
            pass
        return {"status": "accepted"}

    @router.post("/auth/password-reset/complete", status_code=204, tags=["authentication"])
    def complete_reset(payload: TokenPasswordRequest, request: Request) -> None:
        try:
            service.complete_password_reset(
                payload.token.get_secret_value(), payload.password.get_secret_value(),
                _client_ip(request),
            )
        except Exception as exc:
            _translate(exc)

    return router
