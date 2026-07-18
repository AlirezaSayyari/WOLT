from typing import Any

from app.drivers.base import DeviceDriver, DriverValidationError
from app.drivers.fortigate_ssh import FortiGateSSHDriver


class DriverRegistry:
    def __init__(self) -> None:
        drivers: list[DeviceDriver] = [FortiGateSSHDriver()]
        self._drivers = {driver.type_key: driver for driver in drivers}

    def get(self, type_key: str) -> DeviceDriver:
        try:
            return self._drivers[type_key]
        except KeyError as exc:
            raise DriverValidationError("unsupported_driver_type") from exc

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type_key": "fortigate_ssh",
                "name": "FortiGate SSH",
                "configuration_fields": [
                    {"key": "host", "label": "Host or IP", "type": "text", "required": True},
                    {"key": "port", "label": "SSH port", "type": "number", "default": 22},
                    {"key": "host_key", "label": "Pinned SSH host key", "type": "textarea", "required": True},
                ],
                "credential_fields": [
                    {"key": "username", "label": "Username", "type": "text", "required": True},
                    {"key": "password", "label": "Password", "type": "password", "required": True},
                ],
                "listener_fields": [
                    {"key": "interface", "label": "Interface", "type": "text", "required": True},
                    {"key": "gateway_ip", "label": "Gateway / broadcast IP", "type": "text", "required": True},
                ],
            }
        ]
