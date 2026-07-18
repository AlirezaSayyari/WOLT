import logging
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.application.operations_service import DeviceService, ResourceConflictError
from app.drivers import DriverRegistry
from app.drivers.base import DriverOperationError
from app.infrastructure.crypto import CredentialCryptoError
from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import (
    ApplicationSettings,
    Device,
    EngineState,
    ListenerMapping,
    WakeEvent,
)
from app.parser import InvalidMagicPacketError, parse_magic_packet
from app.rate_limit import RateLimiter


LOGGER = logging.getLogger("wolt.engine")


@dataclass(frozen=True)
class RuntimeMapping:
    id: uuid.UUID
    device_id: uuid.UUID
    port: int
    allowed_source_ip: str
    driver_parameters: dict[str, Any]


@dataclass
class ManagedUDPListener:
    mapping: RuntimeMapping
    database: Database
    devices: DeviceService
    registry: DriverRegistry
    limiter: RateLimiter
    _socket: socket.socket
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    @classmethod
    def bind(
        cls,
        mapping: RuntimeMapping,
        database: Database,
        devices: DeviceService,
        registry: DriverRegistry,
        limiter: RateLimiter,
    ) -> "ManagedUDPListener":
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.bind(("0.0.0.0", mapping.port))
        return cls(mapping, database, devices, registry, limiter, sock)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"web-udp-{self.mapping.port}",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        LOGGER.info("event=listener_started listen_port=%s", self.mapping.port)
        while not self._stop.is_set():
            try:
                data, (source_ip, source_port) = self._socket.recvfrom(2048)
                self._handle(data, source_ip, source_port)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    LOGGER.error("event=listener_socket_error listen_port=%s", self.mapping.port)
            except Exception as exc:
                LOGGER.error(
                    "event=listener_request_error listen_port=%s reason=%s",
                    self.mapping.port,
                    type(exc).__name__,
                )
        LOGGER.info("event=listener_stopped listen_port=%s", self.mapping.port)

    def _handle(self, data: bytes, source_ip: str, source_port: int) -> None:
        if source_ip != self.mapping.allowed_source_ip:
            LOGGER.warning(
                "event=wol_request_rejected source_ip=%s listen_port=%s reason=source_not_allowed",
                source_ip,
                self.mapping.port,
            )
            return
        try:
            packet = parse_magic_packet(data)
        except InvalidMagicPacketError:
            LOGGER.warning(
                "event=wol_request_rejected source_ip=%s listen_port=%s reason=invalid_magic_packet",
                source_ip,
                self.mapping.port,
            )
            return

        started = time.monotonic()
        if not self.limiter.allow(self.mapping.port, packet.mac_address):
            self._record(
                packet.mac_address,
                source_ip,
                source_port,
                "rate_limited",
                started,
            )
            return
        try:
            driver_type, configuration, credentials = self.devices.runtime_material(
                self.mapping.device_id
            )
            self.registry.get(driver_type).execute_wake(
                configuration,
                credentials,
                self.mapping.driver_parameters,
                packet.mac_address,
            )
            result = "success"
        except (DriverOperationError, CredentialCryptoError, ResourceConflictError) as exc:
            result = str(exc) or "device_unavailable"
        self._record(packet.mac_address, source_ip, source_port, result, started)

    def _record(
        self,
        mac_address: str,
        source_ip: str,
        source_port: int,
        result: str,
        started: float,
    ) -> None:
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        with self.database.session() as session:
            session.add(
                WakeEvent(
                    mapping_id=self.mapping.id,
                    device_id=self.mapping.device_id,
                    event_type="wake_request",
                    mac_address=mac_address,
                    source_ip=source_ip,
                    source_port=source_port,
                    result_code=result,
                    duration_ms=duration_ms,
                )
            )
            session.commit()
        LOGGER.info(
            "event=wol_request_completed listen_port=%s destination_mac=%s result=%s duration_ms=%s",
            self.mapping.port,
            mac_address,
            result,
            duration_ms,
        )


class EngineRuntime:
    def __init__(
        self,
        database: Database,
        devices: DeviceService,
        registry: DriverRegistry,
    ) -> None:
        self.database = database
        self.devices = devices
        self.registry = registry
        self._listeners: dict[uuid.UUID, ManagedUDPListener] = {}
        self._lock = threading.RLock()

    def start_from_desired_state(self) -> None:
        with self.database.session() as session:
            state = session.get(EngineState, 1)
            desired = state.desired_state if state else "paused"
        if desired == "active":
            self.resume()
        else:
            self.pause()

    def resume(self) -> tuple[str, str | None]:
        with self._lock:
            self._close_all()
            with self.database.session() as session:
                rate_limit = session.get(ApplicationSettings, 1).rate_limit_seconds
                rows = session.execute(
                    select(ListenerMapping)
                    .join(Device, Device.id == ListenerMapping.device_id)
                    .where(
                        ListenerMapping.enabled.is_(True),
                        Device.enabled.is_(True),
                    )
                ).scalars().all()
            limiter = RateLimiter(rate_limit)
            failures = 0
            for row in rows:
                mapping = RuntimeMapping(
                    id=row.id,
                    device_id=row.device_id,
                    port=row.udp_port,
                    allowed_source_ip=row.allowed_source_ip,
                    driver_parameters=row.driver_parameters,
                )
                try:
                    driver_type, _configuration, _credentials = (
                        self.devices.runtime_material(row.device_id)
                    )
                    self.registry.get(driver_type).validate_listener_parameters(
                        row.driver_parameters
                    )
                    listener = ManagedUDPListener.bind(
                        mapping, self.database, self.devices, self.registry, limiter
                    )
                    listener.start()
                    self._listeners[row.id] = listener
                    self._set_mapping_status(row.id, "active", None)
                except (OSError, ResourceConflictError, CredentialCryptoError) as exc:
                    failures += 1
                    reason = "port_bind_failed" if isinstance(exc, OSError) else str(exc)
                    self._set_mapping_status(row.id, "error", reason)
            observed = "active" if failures == 0 else "degraded"
            error = None if failures == 0 else f"{failures}_listener_failures"
            self._heartbeat("active", observed, error)
            return observed, error

    def pause(self) -> None:
        with self._lock:
            self._close_all()
            with self.database.session() as session:
                session.execute(
                    update(ListenerMapping)
                    .where(ListenerMapping.status == "active")
                    .values(status="inactive", last_error=None)
                )
                session.commit()
            self._heartbeat("paused", "paused", None)

    def reconcile_if_active(self) -> None:
        with self.database.session() as session:
            state = session.get(EngineState, 1)
            active = state is not None and state.desired_state == "active"
        if active:
            self.resume()

    def shutdown(self) -> None:
        with self._lock:
            self._close_all()

    def _close_all(self) -> None:
        for listener in list(self._listeners.values()):
            listener.close()
        self._listeners.clear()

    def _set_mapping_status(
        self, mapping_id: uuid.UUID, status: str, error: str | None
    ) -> None:
        with self.database.session() as session:
            session.execute(
                update(ListenerMapping)
                .where(ListenerMapping.id == mapping_id)
                .values(status=status, last_error=error)
            )
            session.commit()

    def _heartbeat(
        self, desired: str, observed: str, error: str | None
    ) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            state = session.get(EngineState, 1)
            if state is not None:
                state.desired_state = desired
                state.observed_state = observed
                state.last_error = error
                state.heartbeat_at = now
                state.last_transition_at = now
                session.commit()
