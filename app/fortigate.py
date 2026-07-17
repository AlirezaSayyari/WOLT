import ipaddress
import re
import socket
from dataclasses import dataclass

import paramiko

from app.config import INTERFACE_PATTERN, Settings


MAC_PATTERN = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")
ERROR_MARKERS = ("command fail", "parse error", "unknown action", "error", "failed")


class FortiGateError(RuntimeError):
    """A safe-to-log FortiGate operation failure."""


def build_wol_command(interface: str, mac_address: str, gateway_ip: str) -> str:
    if not INTERFACE_PATTERN.fullmatch(interface):
        raise ValueError("invalid FortiGate interface")
    if not MAC_PATTERN.fullmatch(mac_address):
        raise ValueError("invalid MAC address")
    try:
        normalized_ip = str(ipaddress.ip_address(gateway_ip))
    except ValueError as exc:
        raise ValueError("invalid gateway IP") from exc
    return f"execute wake-on-lan {interface} {mac_address} 2 9 {normalized_ip}"


@dataclass
class FortiGateClient:
    settings: Settings

    def execute_wol(self, interface: str, mac_address: str, gateway_ip: str) -> None:
        command = build_wol_command(interface, mac_address, gateway_ip)
        client = self._connect()
        try:
            self._execute_command(client, command)
        finally:
            client.close()

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        try:
            client.load_host_keys(self.settings.known_hosts_file)
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(
                hostname=self.settings.fortigate_host,
                port=self.settings.fortigate_ssh_port,
                username=self.settings.fortigate_username,
                password=self.settings.fortigate_password,
                timeout=self.settings.ssh_connect_timeout,
                banner_timeout=self.settings.ssh_connect_timeout,
                auth_timeout=self.settings.ssh_connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            return client
        except (OSError, paramiko.SSHException) as exc:
            client.close()
            raise FortiGateError(self._reason(exc)) from exc

    def _execute_command(self, client: paramiko.SSHClient, command: str) -> None:
        try:
            _stdin, stdout, stderr = client.exec_command(
                command, timeout=self.settings.ssh_command_timeout
            )
            status = stdout.channel.recv_exit_status()
            output = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
            if status != 0 or self._has_error(output):
                raise FortiGateError("command_failed")
        except (OSError, socket.timeout, paramiko.SSHException) as exc:
            raise FortiGateError(self._reason(exc)) from exc

    @staticmethod
    def _has_error(output: str) -> bool:
        lowered = output.lower()
        return any(marker in lowered for marker in ERROR_MARKERS)

    @staticmethod
    def _reason(exc: BaseException) -> str:
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return "ssh_timeout"
        if isinstance(exc, paramiko.AuthenticationException):
            return "ssh_authentication_failed"
        if isinstance(exc, paramiko.BadHostKeyException):
            return "host_key_verification_failed"
        return "ssh_connection_failed"
