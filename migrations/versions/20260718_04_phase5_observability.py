"""Add Phase 5 observability query indexes."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260718_04"
down_revision: str | None = "20260717_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_wake_events_mapping_id", "wake_events", ["mapping_id"])
    op.create_index("ix_wake_events_device_id", "wake_events", ["device_id"])
    op.create_index("ix_wake_events_source_ip", "wake_events", ["source_ip"])
    op.create_index(
        "ix_wake_events_correlation_id", "wake_events", ["correlation_id"], unique=True
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_object_type", "audit_events", ["object_type"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_object_type", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_wake_events_correlation_id", table_name="wake_events")
    op.drop_index("ix_wake_events_source_ip", table_name="wake_events")
    op.drop_index("ix_wake_events_device_id", table_name="wake_events")
    op.drop_index("ix_wake_events_mapping_id", table_name="wake_events")
