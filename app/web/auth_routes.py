import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.application.auth_service import (
    AuthService,
    AuthenticatedUser,
    AuthenticationResult,
    InvalidCredentialsError,
    SetupAlreadyCompletedError,
)
from app.infrastructure.database.connection import Database
from app.web.config import WebSettings


SESSION_COOKIE = "wolt_session"


class UserView(BaseModel):
    id: str
    username: str
    email: EmailStr
    role: str


class SetupOwnerRequest(BaseModel):
    bootstrap_token: SecretStr
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=128)


class RecoveryRequest(BaseModel):
    email: EmailStr
    recovery_code: SecretStr = Field(min_length=20, max_length=64)
    new_password: SecretStr = Field(min_length=12, max_length=128)


class AuthResponse(BaseModel):
    user: UserView
    recovery_code: str | None = None


class LoginAttemptLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 300) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return False
            attempts.append(now)
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_view(user: AuthenticatedUser) -> UserView:
    return UserView(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
    )


def _set_session_cookie(
    response: Response, result: AuthenticationResult, settings: WebSettings
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=result.session_token,
        max_age=settings.session_hours * 3600,
        path="/",
        secure=settings.session_secure,
        httponly=True,
        samesite="strict",
    )


def create_auth_router(database: Database, settings: WebSettings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    service = AuthService(database, settings.session_hours)
    limiter = LoginAttemptLimiter()
    bootstrap_limiter = LoginAttemptLimiter(limit=5, window_seconds=300)

    def require_user(
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> AuthenticatedUser:
        if not session_token:
            raise HTTPException(status_code=401, detail="authentication_required")
        user = service.current_user(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication_required")
        return user

    @router.post(
        "/setup/owner",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["setup"],
    )
    def create_owner(payload: SetupOwnerRequest, request: Request, response: Response) -> AuthResponse:
        key = _client_ip(request)
        if not bootstrap_limiter.allow(key):
            raise HTTPException(status_code=429, detail="too_many_setup_attempts")
        if not settings.bootstrap_token:
            raise HTTPException(status_code=503, detail="bootstrap_token_not_configured")
        if not hmac.compare_digest(
            payload.bootstrap_token.get_secret_value(), settings.bootstrap_token
        ):
            raise HTTPException(status_code=403, detail="invalid_bootstrap_token")
        try:
            result = service.create_owner(
                username=payload.username,
                email=str(payload.email),
                password=payload.password.get_secret_value(),
                client_ip=key,
            )
        except SetupAlreadyCompletedError as exc:
            raise HTTPException(status_code=409, detail="setup_already_completed") from exc
        bootstrap_limiter.clear(key)
        _set_session_cookie(response, result, settings)
        return AuthResponse(
            user=_user_view(result.user), recovery_code=result.recovery_code
        )

    @router.post("/auth/login", response_model=AuthResponse, tags=["authentication"])
    def login(payload: LoginRequest, request: Request, response: Response) -> AuthResponse:
        key = _client_ip(request)
        if not limiter.allow(key):
            raise HTTPException(status_code=429, detail="too_many_login_attempts")
        try:
            result = service.login(
                payload.identifier,
                payload.password.get_secret_value(),
                key,
            )
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=401, detail="invalid_credentials") from exc
        limiter.clear(key)
        _set_session_cookie(response, result, settings)
        return AuthResponse(user=_user_view(result.user))

    @router.get("/auth/me", response_model=UserView, tags=["authentication"])
    def current_user(user: AuthenticatedUser = Depends(require_user)) -> UserView:
        return _user_view(user)

    @router.post("/auth/logout", status_code=204, tags=["authentication"])
    def logout(
        request: Request,
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> Response:
        if session_token:
            service.logout(session_token, _client_ip(request))
        response = Response(status_code=204)
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=settings.session_secure,
            httponly=True,
            samesite="strict",
        )
        return response

    @router.post("/auth/recover", response_model=AuthResponse, tags=["authentication"])
    def recover(payload: RecoveryRequest, request: Request, response: Response) -> AuthResponse:
        key = _client_ip(request)
        if not limiter.allow(key):
            raise HTTPException(status_code=429, detail="too_many_recovery_attempts")
        try:
            result = service.recover_owner(
                email=str(payload.email),
                recovery_code=payload.recovery_code.get_secret_value().upper(),
                new_password=payload.new_password.get_secret_value(),
                client_ip=key,
            )
        except InvalidCredentialsError as exc:
            raise HTTPException(status_code=400, detail="invalid_recovery_credentials") from exc
        limiter.clear(key)
        _set_session_cookie(response, result, settings)
        return AuthResponse(
            user=_user_view(result.user), recovery_code=result.recovery_code
        )

    return router
