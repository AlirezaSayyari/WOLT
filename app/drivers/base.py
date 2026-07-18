from dataclasses import dataclass
from typing import Any, Protocol


class DriverValidationError(ValueError):
    pass


class DriverOperationError(RuntimeError):
    """Safe error category suitable for API responses and logs."""


@dataclass(frozen=True)
class ConnectionTestResult:
    status: str
    latency_ms: int


class DeviceDriver(Protocol):
    type_key: str

    def validate_configuration(self, configuration: dict[str, Any]) -> dict[str, Any]: ...

    def validate_credentials(self, credentials: dict[str, Any]) -> dict[str, str]: ...

    def validate_listener_parameters(self, parameters: dict[str, Any]) -> dict[str, str]: ...

    def test_connection(
        self, configuration: dict[str, Any], credentials: dict[str, Any]
    ) -> ConnectionTestResult: ...

    def execute_wake(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any],
        parameters: dict[str, Any],
        mac_address: str,
    ) -> None: ...
