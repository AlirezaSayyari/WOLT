"""Create the WOLT web foundation schema."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("driver_type", sa.String(80), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(32), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("udp_port_start", sa.Integer(), nullable=False),
        sa.Column("udp_port_end", sa.Integer(), nullable=False),
        sa.Column("rate_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("wake_event_retention_days", sa.Integer(), nullable=False),
        sa.Column("audit_event_retention_days", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "engine_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("desired_state", sa.String(32), nullable=False),
        sa.Column("observed_state", sa.String(32), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("last_transition_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(160)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "device_credentials",
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(120), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_table(
        "listener_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("udp_port", sa.Integer(), nullable=False),
        sa.Column("driver_parameters", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error", sa.String(160)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("udp_port", name="uq_listener_mappings_udp_port"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("object_type", sa.String(80), nullable=False),
        sa.Column("object_id", sa.String(120)),
        sa.Column("safe_changes", sa.JSON(), nullable=False),
        sa.Column("client_ip", sa.String(45), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_table(
        "wake_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mapping_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("mac_address", sa.String(17), nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=False),
        sa.Column("source_port", sa.Integer(), nullable=False),
        sa.Column("result_code", sa.String(80), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mapping_id"], ["listener_mappings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wake_events_occurred_at", "wake_events", ["occurred_at"])
    op.create_index("ix_wake_events_result_code", "wake_events", ["result_code"])

    settings_table = sa.table(
        "application_settings",
        sa.column("id", sa.Integer),
        sa.column("udp_port_start", sa.Integer),
        sa.column("udp_port_end", sa.Integer),
        sa.column("rate_limit_seconds", sa.Integer),
        sa.column("wake_event_retention_days", sa.Integer),
        sa.column("audit_event_retention_days", sa.Integer),
        sa.column("locale", sa.String),
        sa.column("timezone", sa.String),
    )
    op.bulk_insert(settings_table, [{
        "id": 1,
        "udp_port_start": 40000,
        "udp_port_end": 40099,
        "rate_limit_seconds": 30,
        "wake_event_retention_days": 90,
        "audit_event_retention_days": 365,
        "locale": "en",
        "timezone": "UTC",
    }])
    engine_table = sa.table(
        "engine_state",
        sa.column("id", sa.Integer),
        sa.column("desired_state", sa.String),
        sa.column("observed_state", sa.String),
    )
    op.bulk_insert(engine_table, [{"id": 1, "desired_state": "paused", "observed_state": "starting"}])


def downgrade() -> None:
    op.drop_index("ix_wake_events_result_code", table_name="wake_events")
    op.drop_index("ix_wake_events_occurred_at", table_name="wake_events")
    op.drop_table("wake_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("listener_mappings")
    op.drop_table("device_credentials")
    op.drop_table("engine_state")
    op.drop_table("application_settings")
    op.drop_table("devices")
    op.drop_table("users")
