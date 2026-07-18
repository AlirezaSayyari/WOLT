import http.client
import json
import socket
from pathlib import Path
from typing import Any


class HostAgentError(RuntimeError):
    def __init__(self, detail: str, status: int = 503) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.socket_path))


class HostAgentClient:
    def __init__(self, socket_path: Path, token: str, timeout: float = 15) -> None:
        self.socket_path = socket_path
        self.token = token
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.token) and self.socket_path.exists()

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.token:
            raise HostAgentError("host_agent_not_configured")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        connection = UnixHTTPConnection(self.socket_path, self.timeout)
        try:
            connection.request(
                method, path, body=body,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read()
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (OSError, TimeoutError, http.client.HTTPException, json.JSONDecodeError) as exc:
            raise HostAgentError("host_agent_unavailable") from exc
        finally:
            connection.close()
        if not isinstance(value, dict):
            raise HostAgentError("host_agent_invalid_response")
        if response.status >= 400:
            raise HostAgentError(str(value.get("detail", "host_agent_request_failed")), response.status)
        return value
