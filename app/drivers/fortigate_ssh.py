import base64
import hashlib
import ipaddress
import re
import socket
import time
from typing import Any

import paramiko
from paramiko.hostkeys import HostKeyEntry

from app.drivers.base import (
    ConnectionTestResult,
    DriverOperationError,
    DriverValidationError,
    HostKeyDiscoveryResult,
)
from app.fortigate import build_wol_command


HOST_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ERROR_MARKERS = ("command fail", "parse error", "unknown action", "error", "failed")
class FortiGateSSHDriver:
    type_key = "fortigate_ssh"

    def validate_configuration(self, configuration: dict[str, Any]) -> dict[str, Any]:
        target = self._validate_target(configuration)
        host_key = str(configuration.get("host_key", "")).strip()
        entry = HostKeyEntry.from_line(host_key)
        if entry is None or entry.key is None:
            raise DriverValidationError("invalid_or_missing_host_key")
        return {**target, "host_key": host_key}

    @staticmethod
    def _validate_target(configuration: dict[str, Any]) -> dict[str, Any]:
        host = str(configuration.get("host", "")).strip()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not HOST_PATTERN.fullmatch(host):
                raise DriverValidationError("invalid_device_host")
        try:
            port = int(configuration.get("port", 22))
            connect_timeout = float(configuration.get("connect_timeout", 5))
            command_timeout = float(configuration.get("command_timeout", 10))
        except (TypeError, ValueError) as exc:
            raise DriverValidationError("invalid_device_timeout_or_port") from exc
        if not 1 <= port <= 65535:
            raise DriverValidationError("invalid_device_port")
        if not 0.5 <= connect_timeout <= 60 or not 0.5 <= command_timeout <= 120:
            raise DriverValidationError("invalid_device_timeout")
        return {
            "host": host,
            "port": port,
            "connect_timeout": connect_timeout,
            "command_timeout": command_timeout,
        }

    def validate_credentials(self, credentials: dict[str, Any]) -> dict[str, str]:
        username = str(credentials.get("username", "")).strip()
        password = str(credentials.get("password", ""))
        if not username or len(username) > 128:
            raise DriverValidationError("invalid_device_username")
        if not password or len(password) > 512:
            raise DriverValidationError("invalid_device_password")
        return {"username": username, "password": password}

    def validate_listener_parameters(self, parameters: dict[str, Any]) -> dict[str, str]:
        interface = str(parameters.get("interface", "")).strip()
        if not INTERFACE_PATTERN.fullmatch(interface):
            raise DriverValidationError("invalid_fortigate_interface")
        gateway_ip = str(parameters.get("gateway_ip", "")).strip()
        try:
            gateway_ip = str(ipaddress.ip_address(gateway_ip))
        except ValueError as exc:
            raise DriverValidationError("invalid_gateway_ip") from exc
        return {"interface": interface, "gateway_ip": gateway_ip}

    def test_connection(
        self, configuration: dict[str, Any], credentials: dict[str, Any]
    ) -> ConnectionTestResult:
        config = self.validate_configuration(configuration)
        secret = self.validate_credentials(credentials)
        started = time.monotonic()
        client = self._connect(config, secret)
        client.close()
        return ConnectionTestResult(
            status="healthy", latency_ms=max(1, round((time.monotonic() - started) * 1000))
        )

    def discover_host_key(
        self, configuration: dict[str, Any], credentials: dict[str, Any]
    ) -> HostKeyDiscoveryResult:
        config = self._validate_target(configuration)
        secret = self.validate_credentials(credentials)
        host = str(config["host"])
        port = int(config["port"])
        timeout = float(config["connect_timeout"])
        started = time.monotonic()
        sock: socket.socket | None = None
        transport: paramiko.Transport | None = None
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = timeout
            transport.start_client(timeout=timeout)
            key = transport.get_remote_server_key()
            lookup_name = host if port == 22 else f"[{host}]:{port}"
            host_key = f"{lookup_name} {key.get_name()} {key.get_base64()}"
            fingerprint = "SHA256:" + base64.b64encode(
                hashlib.sha256(key.asbytes()).digest()
            ).decode("ascii").rstrip("=")
            try:
                transport.auth_password(
                    username=secret["username"],
                    password=secret["password"],
                    fallback=False,
                )
                authenticated = transport.is_authenticated()
                reason = None if authenticated else "ssh_authentication_failed"
            except paramiko.AuthenticationException:
                authenticated = False
                reason = "ssh_authentication_failed"
            latency = max(1, round((time.monotonic() - started) * 1000))
            return HostKeyDiscoveryResult(
                status="healthy" if authenticated else "unhealthy",
                latency_ms=latency,
                reason=reason,
                host_key=host_key,
                fingerprint=fingerprint,
                algorithm=key.get_name(),
                bits=key.get_bits(),
            )
        except (OSError, paramiko.SSHException) as exc:
            raise DriverOperationError(self._reason(exc)) from exc
        finally:
            if transport is not None:
                transport.close()
            elif sock is not None:
                sock.close()

    def execute_wake(
        self,
        configuration: dict[str, Any],
        credentials: dict[str, Any],
        parameters: dict[str, Any],
        mac_address: str,
    ) -> None:
        config = self.validate_configuration(configuration)
        secret = self.validate_credentials(credentials)
        listener = self.validate_listener_parameters(parameters)
        command = build_wol_command(
            listener["interface"], mac_address, listener["gateway_ip"]
        )
        client = self._connect(config, secret)
        try:
            _stdin, stdout, stderr = client.exec_command(
                command, timeout=config["command_timeout"]
            )
            status = stdout.channel.recv_exit_status()
            output = (stdout.read() + stderr.read()).decode("utf-8", errors="replace")
            if status != 0 or any(marker in output.lower() for marker in ERROR_MARKERS):
                raise DriverOperationError("command_failed")
        except (OSError, socket.timeout, paramiko.SSHException) as exc:
            raise DriverOperationError(self._reason(exc)) from exc
        finally:
            client.close()

    def _connect(
        self, configuration: dict[str, Any], credentials: dict[str, str]
    ) -> paramiko.SSHClient:
        entry = HostKeyEntry.from_line(str(configuration["host_key"]))
        if entry is None or entry.key is None:
            raise DriverOperationError("host_key_verification_failed")
        host = str(configuration["host"])
        port = int(configuration["port"])
        lookup_name = host if port == 22 else f"[{host}]:{port}"
        client = paramiko.SSHClient()
        client.get_host_keys().add(lookup_name, entry.key.get_name(), entry.key)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            client.connect(
                hostname=host,
                port=port,
                username=credentials["username"],
                password=credentials["password"],
                timeout=float(configuration["connect_timeout"]),
                banner_timeout=float(configuration["connect_timeout"]),
                auth_timeout=float(configuration["connect_timeout"]),
                look_for_keys=False,
                allow_agent=False,
            )
            return client
        except (OSError, paramiko.SSHException) as exc:
            client.close()
            raise DriverOperationError(self._reason(exc)) from exc

    @staticmethod
    def _reason(exc: BaseException) -> str:
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return "ssh_timeout"
        if isinstance(exc, paramiko.AuthenticationException):
            return "ssh_authentication_failed"
        if isinstance(exc, paramiko.BadHostKeyException):
            return "host_key_verification_failed"
        return "ssh_connection_failed"
