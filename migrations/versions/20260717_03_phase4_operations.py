"""Add listener ingress policy for Phase 4 operations."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_03"
down_revision: str | None = "20260717_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listener_mappings",
        sa.Column(
            "allowed_source_ip",
            sa.String(45),
            nullable=False,
            server_default="127.0.0.1",
        ),
    )
    op.alter_column("listener_mappings", "allowed_source_ip", server_default=None)


def downgrade() -> None:
    op.drop_column("listener_mappings", "allowed_source_ip")
