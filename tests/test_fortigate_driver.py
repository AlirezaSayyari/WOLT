import paramiko
import pytest

from app.drivers.base import DriverValidationError
from app.drivers.fortigate_ssh import FortiGateSSHDriver


def host_key_line() -> str:
    key = paramiko.RSAKey.generate(1024)
    return f"192.0.2.30 {key.get_name()} {key.get_base64()}"


def test_fortigate_driver_normalizes_safe_configuration() -> None:
    driver = FortiGateSSHDriver()

    configuration = driver.validate_configuration(
        {"host": "192.0.2.30", "port": "22", "host_key": host_key_line()}
    )
    listener = driver.validate_listener_parameters(
        {"interface": "demo-vlan-16", "gateway_ip": "198.51.100.94"}
    )

    assert configuration["port"] == 22
    assert listener == {
        "interface": "demo-vlan-16",
        "gateway_ip": "198.51.100.94",
    }


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"interface": "bad interface", "gateway_ip": "198.51.100.1"}, "invalid_fortigate_interface"),
        ({"interface": "port1", "gateway_ip": "not-an-ip"}, "invalid_gateway_ip"),
    ],
)
def test_fortigate_driver_rejects_unsafe_listener_values(
    parameters: dict[str, str], message: str
) -> None:
    with pytest.raises(DriverValidationError, match=message):
        FortiGateSSHDriver().validate_listener_parameters(parameters)
