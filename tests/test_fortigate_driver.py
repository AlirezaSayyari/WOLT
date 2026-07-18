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


def test_fortigate_driver_discovers_key_and_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    key = paramiko.RSAKey.generate(1024)

    class FakeSocket:
        def close(self) -> None:
            pass

    class FakeTransport:
        banner_timeout = 0.0

        def __init__(self, _sock: FakeSocket) -> None:
            self.authenticated = False

        def start_client(self, *, timeout: float) -> None:
            assert timeout == 5

        def get_remote_server_key(self) -> paramiko.PKey:
            return key

        def auth_password(self, *, username: str, password: str, fallback: bool) -> None:
            assert (username, password, fallback) == ("wol-service", "secret", False)
            self.authenticated = True

        def is_authenticated(self) -> bool:
            return self.authenticated

        def close(self) -> None:
            pass

    monkeypatch.setattr("socket.create_connection", lambda *_args, **_kwargs: FakeSocket())
    monkeypatch.setattr(paramiko, "Transport", FakeTransport)

    result = FortiGateSSHDriver().discover_host_key(
        {"host": "192.0.2.30", "port": 2222, "connect_timeout": 5},
        {"username": "wol-service", "password": "secret"},
    )

    assert result.status == "healthy"
    assert result.reason is None
    assert result.host_key.startswith("[192.0.2.30]:2222 ssh-rsa ")
    assert result.fingerprint.startswith("SHA256:")
    assert result.bits == 1024


def test_fortigate_driver_returns_discovered_key_when_authentication_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = paramiko.RSAKey.generate(1024)

    class FakeTransport:
        banner_timeout = 0.0

        def __init__(self, _sock: object) -> None:
            pass

        def start_client(self, *, timeout: float) -> None:
            pass

        def get_remote_server_key(self) -> paramiko.PKey:
            return key

        def auth_password(self, **_kwargs: object) -> None:
            raise paramiko.AuthenticationException

        def is_authenticated(self) -> bool:
            return False

        def close(self) -> None:
            pass

    monkeypatch.setattr("socket.create_connection", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(paramiko, "Transport", FakeTransport)

    result = FortiGateSSHDriver().discover_host_key(
        {"host": "192.0.2.30", "port": 22},
        {"username": "wol-service", "password": "wrong"},
    )

    assert result.status == "unhealthy"
    assert result.reason == "ssh_authentication_failed"
    assert result.host_key.startswith("192.0.2.30 ssh-rsa ")
