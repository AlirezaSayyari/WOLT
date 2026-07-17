from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.fortigate import FortiGateClient, FortiGateError, build_wol_command


def test_builds_expected_command() -> None:
    command = build_wol_command(
        interface="demo-vlan-16",
        mac_address="02:AA:BB:CC:DD:16",
        gateway_ip="198.51.100.94",
    )
    assert command == (
        "execute wake-on-lan demo-vlan-16 "
        "02:AA:BB:CC:DD:16 2 9 198.51.100.94"
    )
    assert "40016" not in command


@pytest.mark.parametrize(
    ("interface", "mac", "gateway"),
    [
        ("bad interface", "02:AA:BB:CC:DD:16", "192.0.2.1"),
        ("vlan16", "02:aa:bb:cc:dd:16", "192.0.2.1"),
        ("vlan16", "02:AA:BB:CC:DD:16", "not-an-ip"),
    ],
)
def test_rejects_unsafe_command_values(interface: str, mac: str, gateway: str) -> None:
    with pytest.raises(ValueError):
        build_wol_command(interface, mac, gateway)


def test_executes_only_direct_command_and_closes_connection() -> None:
    settings = SimpleNamespace(ssh_command_timeout=10)
    client = Mock()
    stdout = Mock()
    stderr = Mock()
    stdout.channel.recv_exit_status.return_value = 0
    stdout.read.return_value = b""
    stderr.read.return_value = b""
    client.exec_command.return_value = (Mock(), stdout, stderr)
    fortigate = FortiGateClient(settings)  # type: ignore[arg-type]
    fortigate._connect = Mock(return_value=client)  # type: ignore[method-assign]

    fortigate.execute_wol("demo-vlan-16", "02:AA:BB:CC:DD:16", "198.51.100.94")

    client.exec_command.assert_called_once_with(
        "execute wake-on-lan demo-vlan-16 02:AA:BB:CC:DD:16 2 9 198.51.100.94",
        timeout=10,
    )
    assert not hasattr(client, "invoke_shell") or not client.invoke_shell.called
    client.close.assert_called_once()


def test_direct_command_failure_closes_connection() -> None:
    settings = SimpleNamespace(ssh_command_timeout=10)
    client = Mock()
    stdout = Mock()
    stderr = Mock()
    stdout.channel.recv_exit_status.return_value = 1
    stdout.read.return_value = b""
    stderr.read.return_value = b"command fail"
    client.exec_command.return_value = (Mock(), stdout, stderr)
    fortigate = FortiGateClient(settings)  # type: ignore[arg-type]
    fortigate._connect = Mock(return_value=client)  # type: ignore[method-assign]

    with pytest.raises(FortiGateError, match="command_failed"):
        fortigate.execute_wol("vlan16", "02:AA:BB:CC:DD:16", "198.51.100.94")

    client.close.assert_called_once()
