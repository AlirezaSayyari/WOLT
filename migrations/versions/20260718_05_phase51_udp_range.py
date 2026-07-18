"""Add database constraints for the configurable active UDP range."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260718_05"
down_revision: str | None = "20260718_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_application_settings_udp_start",
        "application_settings",
        "udp_port_start BETWEEN 1024 AND 65535",
    )
    op.create_check_constraint(
        "ck_application_settings_udp_end",
        "application_settings",
        "udp_port_end BETWEEN udp_port_start AND 65535",
    )
    op.create_check_constraint(
        "ck_application_settings_udp_width",
        "application_settings",
        "udp_port_end - udp_port_start + 1 <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_application_settings_udp_width",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_udp_end",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_udp_start",
        "application_settings",
        type_="check",
    )
