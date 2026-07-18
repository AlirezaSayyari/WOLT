import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.application.auth_service import AuthService
from app.infrastructure.crypto import CredentialCipher
from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import (
    AuditEvent,
    PasswordResetToken,
    SmtpSettings,
    User,
    UserInvitation,
    UserSession,
)
from app.infrastructure.email import SmtpConfiguration, SmtpMailer


class IdentityError(RuntimeError):
    detail = "identity_operation_failed"


class IdentityNotFoundError(IdentityError):
    detail = "user_not_found"


class IdentityConflictError(IdentityError):
    detail = "user_already_exists"


class LastOwnerError(IdentityError):
    detail = "last_owner_required"


class InvalidTokenError(IdentityError):
    detail = "invalid_or_expired_token"


class SmtpNotConfiguredError(IdentityError):
    detail = "smtp_not_configured"


class IdentityMasterKeyError(IdentityError):
    detail = "master_key_not_configured"


class InvitationNotAcceptedError(IdentityError):
    detail = "invitation_not_accepted"


@dataclass(frozen=True)
class SmtpInput:
    host: str
    port: int
    security: str
    from_email: str
    from_name: str
    public_base_url: str
    username: str
    password: str
    enabled: bool


def _audit(
    *, actor_id: uuid.UUID | None, action: str, object_id: str | None,
    changes: dict[str, Any], client_ip: str,
) -> AuditEvent:
    return AuditEvent(
        actor_user_id=actor_id,
        action=action,
        object_type="user" if action.startswith("user.") else "identity",
        object_id=object_id,
        safe_changes=changes,
        client_ip=client_ip,
    )


class IdentityService:
    def __init__(
        self,
        database: Database,
        cipher: CredentialCipher | None,
        mailer: SmtpMailer | None = None,
    ) -> None:
        self.database = database
        self.cipher = cipher
        self.mailer = mailer or SmtpMailer()
        self.password_hasher = PasswordHasher()

    @staticmethod
    def _token() -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        return raw, AuthService._token_hash(raw)

    def _require_cipher(self) -> CredentialCipher:
        if self.cipher is None:
            raise IdentityMasterKeyError
        return self.cipher

    def list_users(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        with self.database.session() as session:
            rows = session.execute(
                select(
                    User,
                    func.count(UserSession.id).filter(
                        UserSession.revoked_at.is_(None), UserSession.expires_at > now
                    ),
                )
                .outerjoin(UserSession, UserSession.user_id == User.id)
                .group_by(User.id)
                .order_by(User.created_at)
            ).all()
            pending_ids = set(
                session.scalars(
                    select(UserInvitation.user_id).where(
                        UserInvitation.accepted_at.is_(None),
                        UserInvitation.expires_at > now,
                    )
                )
            )
            return [
                {
                    "id": str(user.id), "username": user.username, "email": user.email,
                    "role": user.role, "enabled": user.enabled,
                    "status": "pending" if user.id in pending_ids else ("active" if user.enabled else "disabled"),
                    "active_sessions": int(session_count),
                    "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                    "created_at": user.created_at.isoformat(),
                }
                for user, session_count in rows
            ]

    def smtp_view(self) -> dict[str, Any]:
        with self.database.session() as session:
            stored = session.get(SmtpSettings, 1)
            if stored is None:
                return {"configured": False, "enabled": False}
            credentials = self._require_cipher().decrypt(stored.encrypted_credentials)
            return {
                "configured": True, "enabled": stored.enabled, "host": stored.host,
                "port": stored.port, "security": stored.security,
                "from_email": stored.from_email, "from_name": stored.from_name,
                "public_base_url": stored.public_base_url,
                "username": str(credentials.get("username", "")),
                "password_configured": bool(credentials.get("password")),
                "updated_at": stored.updated_at.isoformat(),
            }

    def test_smtp(self, values: SmtpInput, recipient: str) -> None:
        password = values.password
        if not password:
            with self.database.session() as session:
                stored = session.get(SmtpSettings, 1)
                if stored is not None:
                    password = str(
                        self._require_cipher().decrypt(stored.encrypted_credentials).get(
                            "password", ""
                        )
                    )
        configuration = SmtpConfiguration(
            host=values.host, port=values.port, security=values.security,
            username=values.username, password=password,
            from_email=values.from_email, from_name=values.from_name,
        )
        self.mailer.send(
            configuration, recipient=recipient,
            subject="WOLT SMTP test", text="Your WOLT email configuration is working.",
        )

    def save_smtp(
        self, values: SmtpInput, *, actor_id: uuid.UUID, client_ip: str
    ) -> dict[str, Any]:
        cipher = self._require_cipher()
        with self.database.session() as session:
            stored = session.get(SmtpSettings, 1)
            password = values.password
            if stored is not None and not password:
                password = str(cipher.decrypt(stored.encrypted_credentials).get("password", ""))
            encrypted = cipher.encrypt({"username": values.username, "password": password})
            if stored is None:
                stored = SmtpSettings(id=1)
                session.add(stored)
            stored.host = values.host
            stored.port = values.port
            stored.security = values.security
            stored.from_email = values.from_email
            stored.from_name = values.from_name
            stored.public_base_url = values.public_base_url.rstrip("/")
            stored.encrypted_credentials = encrypted
            stored.key_id = cipher.key_id
            stored.enabled = values.enabled
            session.add(_audit(
                actor_id=actor_id, action="identity.smtp_updated", object_id="1",
                changes={"host": values.host, "port": values.port, "security": values.security, "enabled": values.enabled},
                client_ip=client_ip,
            ))
            session.commit()
        return self.smtp_view()

    def _stored_smtp(self) -> tuple[SmtpSettings, SmtpConfiguration]:
        with self.database.session() as session:
            stored = session.get(SmtpSettings, 1)
            if stored is None or not stored.enabled:
                raise SmtpNotConfiguredError
            values = self._require_cipher().decrypt(stored.encrypted_credentials)
            config = SmtpConfiguration(
                host=stored.host, port=stored.port, security=stored.security,
                username=str(values.get("username", "")),
                password=str(values.get("password", "")),
                from_email=stored.from_email, from_name=stored.from_name,
            )
            session.expunge(stored)
            return stored, config

    def invite_user(
        self, *, username: str, email: str, role: str,
        actor_id: uuid.UUID, client_ip: str,
    ) -> dict[str, Any]:
        stored_smtp, smtp = self._stored_smtp()
        raw_token, token_hash = self._token()
        expires = datetime.now(UTC) + timedelta(hours=24)
        try:
            with self.database.session() as session:
                existing = session.scalars(
                    select(User).where(
                        or_(
                            func.lower(User.username) == username.strip().lower(),
                            func.lower(User.email) == email.strip().lower(),
                        )
                    )
                ).all()
                if any(user.password_hash is not None or user.enabled for user in existing):
                    raise IdentityConflictError
                for pending in existing:
                    session.delete(pending)
                session.flush()
                user = User(
                    username=username.strip(), email=email.strip().lower(),
                    password_hash=None, role=role, enabled=False,
                )
                session.add(user)
                session.flush()
                session.add(UserInvitation(
                    user_id=user.id, invited_by=actor_id,
                    token_hash=token_hash, expires_at=expires,
                ))
                session.add(_audit(
                    actor_id=actor_id, action="user.invited", object_id=str(user.id),
                    changes={"username": user.username, "email": user.email, "role": role},
                    client_ip=client_ip,
                ))
                session.commit()
                user_id = user.id
        except IntegrityError as exc:
            raise IdentityConflictError from exc
        link = f"{stored_smtp.public_base_url}/accept-invite?token={raw_token}"
        try:
            self.mailer.send(
                smtp, recipient=email, subject="You are invited to WOLT",
                text=(f"You were invited to WOLT as {role}.\n\nSet your password within 24 hours:\n{link}\n\nIf you did not expect this invitation, ignore this message."),
            )
        except Exception:
            with self.database.session() as session:
                failed_user = session.get(User, user_id)
                if failed_user is not None and not failed_user.enabled:
                    session.delete(failed_user)
                    session.commit()
            raise
        return {"id": str(user_id), "expires_at": expires.isoformat()}

    def accept_invitation(self, token: str, password: str, client_ip: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            invitation = session.scalar(
                select(UserInvitation).where(
                    UserInvitation.token_hash == AuthService._token_hash(token),
                    UserInvitation.accepted_at.is_(None), UserInvitation.expires_at > now,
                ).with_for_update()
            )
            if invitation is None:
                raise InvalidTokenError
            user = session.get(User, invitation.user_id)
            if user is None:
                raise InvalidTokenError
            user.password_hash = self.password_hasher.hash(password)
            user.enabled = True
            invitation.accepted_at = now
            session.add(_audit(
                actor_id=user.id, action="user.invitation_accepted", object_id=str(user.id),
                changes={"role": user.role}, client_ip=client_ip,
            ))
            session.commit()

    def update_user(
        self, user_id: uuid.UUID, *, role: str, enabled: bool,
        actor_id: uuid.UUID, client_ip: str,
    ) -> None:
        with self.database.session() as session:
            user = session.get(User, user_id)
            if user is None:
                raise IdentityNotFoundError
            if enabled and user.password_hash is None:
                raise InvitationNotAcceptedError
            if user.role == "owner" and (role != "owner" or not enabled):
                owner_count = session.scalar(
                    select(func.count()).select_from(User).where(
                        User.role == "owner", User.enabled.is_(True)
                    )
                ) or 0
                if owner_count <= 1:
                    raise LastOwnerError
            changes = {"role": [user.role, role], "enabled": [user.enabled, enabled]}
            user.role = role
            user.enabled = enabled
            if not enabled:
                session.execute(
                    update(UserSession).where(
                        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
                    ).values(revoked_at=datetime.now(UTC))
                )
            session.add(_audit(
                actor_id=actor_id, action="user.updated", object_id=str(user.id),
                changes=changes, client_ip=client_ip,
            ))
            session.commit()

    def revoke_sessions(
        self, user_id: uuid.UUID, *, actor_id: uuid.UUID, client_ip: str
    ) -> None:
        with self.database.session() as session:
            if session.get(User, user_id) is None:
                raise IdentityNotFoundError
            result = session.execute(
                update(UserSession).where(
                    UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
                ).values(revoked_at=datetime.now(UTC))
            )
            session.add(_audit(
                actor_id=actor_id, action="user.sessions_revoked", object_id=str(user_id),
                changes={"count": result.rowcount}, client_ip=client_ip,
            ))
            session.commit()

    def request_password_reset(self, email: str, client_ip: str) -> None:
        try:
            stored_smtp, smtp = self._stored_smtp()
        except SmtpNotConfiguredError:
            return
        with self.database.session() as session:
            user = session.scalar(select(User).where(
                func.lower(User.email) == email.strip().lower(), User.enabled.is_(True)
            ))
            if user is None or user.password_hash is None:
                return
            now = datetime.now(UTC)
            session.execute(update(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
            ).values(used_at=now))
            raw_token, token_hash = self._token()
            session.add(PasswordResetToken(
                user_id=user.id, token_hash=token_hash,
                expires_at=now + timedelta(minutes=30),
            ))
            session.add(_audit(
                actor_id=None, action="identity.password_reset_requested", object_id=str(user.id),
                changes={}, client_ip=client_ip,
            ))
            session.commit()
        link = f"{stored_smtp.public_base_url}/reset-password?token={raw_token}"
        self.mailer.send(
            smtp, recipient=user.email, subject="Reset your WOLT password",
            text=f"Use this one-time link within 30 minutes:\n{link}\n\nIf you did not request this reset, ignore this message.",
        )

    def complete_password_reset(self, token: str, password: str, client_ip: str) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            reset = session.scalar(select(PasswordResetToken).where(
                PasswordResetToken.token_hash == AuthService._token_hash(token),
                PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now,
            ).with_for_update())
            if reset is None:
                raise InvalidTokenError
            user = session.get(User, reset.user_id)
            if user is None or not user.enabled:
                raise InvalidTokenError
            user.password_hash = self.password_hasher.hash(password)
            reset.used_at = now
            session.execute(update(UserSession).where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
            ).values(revoked_at=now))
            session.add(_audit(
                actor_id=user.id, action="identity.password_reset_completed", object_id=str(user.id),
                changes={"sessions_revoked": True}, client_ip=client_ip,
            ))
            session.commit()
