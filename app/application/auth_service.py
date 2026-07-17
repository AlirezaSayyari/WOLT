import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import (
    ApplicationSettings,
    AuditEvent,
    RecoveryCode,
    User,
    UserSession,
)


class SetupAlreadyCompletedError(RuntimeError):
    pass


class InvalidCredentialsError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    username: str
    email: str
    role: str


@dataclass(frozen=True)
class AuthenticationResult:
    user: AuthenticatedUser
    session_token: str
    expires_at: datetime
    recovery_code: str | None = None


class AuthService:
    def __init__(self, database: Database, session_hours: int = 12) -> None:
        self.database = database
        self.session_lifetime = timedelta(hours=session_hours)
        self.password_hasher = PasswordHasher()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_user(user: User) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
        )

    @staticmethod
    def _new_recovery_code() -> str:
        raw = secrets.token_hex(12).upper()
        return "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))

    def _create_session(
        self, session: Session, user: User, client_ip: str
    ) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + self.session_lifetime
        session.add(
            UserSession(
                user_id=user.id,
                token_hash=self._token_hash(token),
                expires_at=expires_at,
                client_ip=client_ip,
            )
        )
        return token, expires_at

    def create_owner(
        self,
        *,
        username: str,
        email: str,
        password: str,
        client_ip: str,
    ) -> AuthenticationResult:
        with self.database.session() as session:
            session.execute(
                select(ApplicationSettings)
                .where(ApplicationSettings.id == 1)
                .with_for_update()
            ).scalar_one()
            if session.scalar(select(User.id).where(User.role == "owner")) is not None:
                raise SetupAlreadyCompletedError

            user = User(
                username=username.strip(),
                email=email.strip().lower(),
                password_hash=self.password_hasher.hash(password),
                role="owner",
                enabled=True,
                last_login_at=datetime.now(UTC),
            )
            session.add(user)
            session.flush()

            recovery_code = self._new_recovery_code()
            session.add(
                RecoveryCode(
                    user_id=user.id,
                    code_hash=self.password_hasher.hash(recovery_code),
                )
            )
            token, expires_at = self._create_session(session, user, client_ip)
            session.add(
                AuditEvent(
                    actor_user_id=user.id,
                    action="owner.created",
                    object_type="user",
                    object_id=str(user.id),
                    safe_changes={"role": "owner"},
                    client_ip=client_ip,
                )
            )
            session.commit()
            return AuthenticationResult(
                user=self._public_user(user),
                session_token=token,
                expires_at=expires_at,
                recovery_code=recovery_code,
            )

    def login(self, identifier: str, password: str, client_ip: str) -> AuthenticationResult:
        normalized = identifier.strip().lower()
        with self.database.session() as session:
            user = session.scalar(
                select(User).where(
                    User.enabled.is_(True),
                    or_(
                        func.lower(User.username) == normalized,
                        func.lower(User.email) == normalized,
                    ),
                )
            )
            if user is None or not self._verify(user.password_hash, password):
                raise InvalidCredentialsError
            if self.password_hasher.check_needs_rehash(user.password_hash):
                user.password_hash = self.password_hasher.hash(password)
            user.last_login_at = datetime.now(UTC)
            token, expires_at = self._create_session(session, user, client_ip)
            session.add(
                AuditEvent(
                    actor_user_id=user.id,
                    action="auth.login",
                    object_type="session",
                    object_id=None,
                    safe_changes={},
                    client_ip=client_ip,
                )
            )
            session.commit()
            return AuthenticationResult(self._public_user(user), token, expires_at)

    def current_user(self, token: str) -> AuthenticatedUser | None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            row = session.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(
                    UserSession.token_hash == self._token_hash(token),
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                    User.enabled.is_(True),
                )
            ).one_or_none()
            if row is None:
                return None
            return self._public_user(row[1])

    def logout(self, token: str, client_ip: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            stored = session.scalar(
                select(UserSession).where(
                    UserSession.token_hash == self._token_hash(token),
                    UserSession.revoked_at.is_(None),
                )
            )
            if stored is not None:
                stored.revoked_at = now
                session.add(
                    AuditEvent(
                        actor_user_id=stored.user_id,
                        action="auth.logout",
                        object_type="session",
                        object_id=str(stored.id),
                        safe_changes={},
                        client_ip=client_ip,
                    )
                )
                session.commit()

    def recover_owner(
        self,
        *,
        email: str,
        recovery_code: str,
        new_password: str,
        client_ip: str,
    ) -> AuthenticationResult:
        with self.database.session() as session:
            row = session.execute(
                select(User, RecoveryCode)
                .join(RecoveryCode, RecoveryCode.user_id == User.id)
                .where(
                    func.lower(User.email) == email.strip().lower(),
                    User.role == "owner",
                    User.enabled.is_(True),
                    RecoveryCode.used_at.is_(None),
                )
                .with_for_update()
            ).one_or_none()
            if row is None or not self._verify(row[1].code_hash, recovery_code):
                raise InvalidCredentialsError
            user, stored_code = row
            user.password_hash = self.password_hasher.hash(new_password)
            session.execute(
                update(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            replacement_code = self._new_recovery_code()
            stored_code.code_hash = self.password_hasher.hash(replacement_code)
            stored_code.created_at = datetime.now(UTC)
            stored_code.used_at = None
            token, expires_at = self._create_session(session, user, client_ip)
            session.add(
                AuditEvent(
                    actor_user_id=user.id,
                    action="auth.recovered",
                    object_type="user",
                    object_id=str(user.id),
                    safe_changes={"sessions_revoked": True},
                    client_ip=client_ip,
                )
            )
            session.commit()
            return AuthenticationResult(
                self._public_user(user), token, expires_at, replacement_code
            )

    def _verify(self, stored_hash: str, candidate: str) -> bool:
        try:
            return self.password_hasher.verify(stored_hash, candidate)
        except (InvalidHashError, VerifyMismatchError):
            return False
