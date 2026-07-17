from app.infrastructure.database.base import Base
from app.infrastructure.database import models  # noqa: F401


def test_foundation_schema_contains_expected_tables() -> None:
    assert set(Base.metadata.tables) == {
        "application_settings",
        "audit_events",
        "device_credentials",
        "devices",
        "engine_state",
        "listener_mappings",
        "users",
        "wake_events",
    }


def test_listener_udp_port_has_unique_constraint() -> None:
    constraints = Base.metadata.tables["listener_mappings"].constraints
    assert any(constraint.name == "uq_listener_mappings_udp_port" for constraint in constraints)
