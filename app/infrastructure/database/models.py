import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


UUID = uuid.UUID


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_token_hash", "token_hash", unique=True),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_ip: Mapped[str] = mapped_column(String(45), nullable=False)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(TimestampMixin, Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    driver_type: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(String(120), nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ListenerMapping(TimestampMixin, Base):
    __tablename__ = "listener_mappings"
    __table_args__ = (UniqueConstraint("udp_port", name="uq_listener_mappings_udp_port"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    udp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_source_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    driver_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="inactive")
    last_error: Mapped[str | None] = mapped_column(String(160))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WakeEvent(Base):
    __tablename__ = "wake_events"
    __table_args__ = (
        Index("ix_wake_events_occurred_at", "occurred_at"),
        Index("ix_wake_events_result_code", "result_code"),
        Index("ix_wake_events_mapping_id", "mapping_id"),
        Index("ix_wake_events_device_id", "device_id"),
        Index("ix_wake_events_source_ip", "source_ip"),
        Index("ix_wake_events_correlation_id", "correlation_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mapping_id: Mapped[UUID] = mapped_column(
        ForeignKey("listener_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    mac_address: Mapped[str] = mapped_column(String(17), nullable=False)
    source_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    source_port: Mapped[int] = mapped_column(Integer, nullable=False)
    result_code: Mapped[str] = mapped_column(String(80), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_action", "action"),
        Index("ix_audit_events_object_type", "object_type"),
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(120))
    safe_changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    client_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApplicationSettings(Base):
    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    udp_port_start: Mapped[int] = mapped_column(Integer, nullable=False, default=40000)
    udp_port_end: Mapped[int] = mapped_column(Integer, nullable=False, default=40099)
    rate_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    wake_event_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    audit_event_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EngineState(Base):
    __tablename__ = "engine_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    desired_state: Mapped[str] = mapped_column(String(32), nullable=False, default="paused")
    observed_state: Mapped[str] = mapped_column(String(32), nullable=False, default="starting")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(160))
