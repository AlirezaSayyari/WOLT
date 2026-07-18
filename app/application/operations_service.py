import ipaddress
import socket
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.drivers import DriverRegistry
from app.drivers.base import DriverOperationError, DriverValidationError
from app.infrastructure.crypto import CredentialCipher, CredentialCryptoError
from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import (
    ApplicationSettings,
    AuditEvent,
    Device,
    DeviceCredential,
    EngineState,
    ListenerMapping,
    WakeEvent,
)


class OperationsError(RuntimeError):
    detail = "operations_error"


class ResourceNotFoundError(OperationsError):
    detail = "resource_not_found"


class ResourceConflictError(OperationsError):
    detail = "resource_conflict"


class ResourceInUseError(OperationsError):
    detail = "resource_in_use"


class StaleVersionError(OperationsError):
    detail = "stale_listener_version"


class MasterKeyRequiredError(OperationsError):
    detail = "master_key_not_configured"


def _audit(
    *,
    actor_id: uuid.UUID,
    action: str,
    object_type: str,
    object_id: str,
    changes: dict[str, Any],
    client_ip: str,
) -> AuditEvent:
    return AuditEvent(
        actor_user_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        safe_changes=changes,
        client_ip=client_ip,
    )


class DeviceService:
    def __init__(
        self,
        database: Database,
        registry: DriverRegistry,
        cipher: CredentialCipher | None,
    ) -> None:
        self.database = database
        self.registry = registry
        self.cipher = cipher

    def list(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(
                    Device,
                    func.count(ListenerMapping.id),
                    func.count(DeviceCredential.device_id),
                )
                .outerjoin(ListenerMapping, ListenerMapping.device_id == Device.id)
                .outerjoin(DeviceCredential, DeviceCredential.device_id == Device.id)
                .group_by(Device.id)
                .order_by(Device.name)
            ).all()
            return [self._view(device, listeners, bool(credentials)) for device, listeners, credentials in rows]

    def get(self, device_id: uuid.UUID) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.execute(
                select(
                    Device,
                    func.count(ListenerMapping.id),
                    func.count(DeviceCredential.device_id),
                )
                .outerjoin(ListenerMapping, ListenerMapping.device_id == Device.id)
                .outerjoin(DeviceCredential, DeviceCredential.device_id == Device.id)
                .where(Device.id == device_id)
                .group_by(Device.id)
            ).one_or_none()
            if row is None:
                raise ResourceNotFoundError
            return self._view(row[0], row[1], bool(row[2]))

    def create(
        self,
        *,
        name: str,
        driver_type: str,
        configuration: dict[str, Any],
        credentials: dict[str, Any],
        enabled: bool,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        cipher = self._require_cipher()
        driver = self.registry.get(driver_type)
        config = driver.validate_configuration(configuration)
        secret = driver.validate_credentials(credentials)
        device = Device(
            name=name.strip(),
            driver_type=driver_type,
            configuration=config,
            enabled=enabled,
            health_status="unknown",
        )
        if not device.name:
            raise DriverValidationError("device_name_required")
        with self.database.session() as session:
            try:
                session.add(device)
                session.flush()
                session.add(
                    DeviceCredential(
                        device_id=device.id,
                        encrypted_payload=cipher.encrypt(secret),
                        key_id=cipher.key_id,
                    )
                )
                session.add(
                    _audit(
                        actor_id=actor_id,
                        action="device.created",
                        object_type="device",
                        object_id=str(device.id),
                        changes={"name": device.name, "driver_type": driver_type, "enabled": enabled},
                        client_ip=client_ip,
                    )
                )
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ResourceConflictError from exc
        return self.get(device.id)

    def discover_host_key(
        self,
        *,
        driver_type: str,
        configuration: dict[str, Any],
        credentials: dict[str, Any],
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        driver = self.registry.get(driver_type)
        try:
            result = driver.discover_host_key(configuration, credentials)
        except DriverOperationError as exc:
            with self.database.session() as session:
                session.add(
                    _audit(
                        actor_id=actor_id,
                        action="device.host_key_discovery_tested",
                        object_type="device_candidate",
                        object_id="pending",
                        changes={"status": "unhealthy", "reason": str(exc)},
                        client_ip=client_ip,
                    )
                )
                session.commit()
            raise
        with self.database.session() as session:
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="device.host_key_discovery_tested",
                    object_type="device_candidate",
                    object_id="pending",
                    changes={
                        "status": result.status,
                        "reason": result.reason,
                        "algorithm": result.algorithm,
                        "fingerprint": result.fingerprint,
                    },
                    client_ip=client_ip,
                )
            )
            session.commit()
        return {
            "status": result.status,
            "latency_ms": result.latency_ms,
            "reason": result.reason,
            "host_key": result.host_key,
            "fingerprint": result.fingerprint,
            "algorithm": result.algorithm,
            "bits": result.bits,
        }

    def update(
        self,
        device_id: uuid.UUID,
        *,
        name: str,
        configuration: dict[str, Any],
        credentials: dict[str, Any] | None,
        enabled: bool,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            device = session.get(Device, device_id)
            if device is None:
                raise ResourceNotFoundError
            driver = self.registry.get(device.driver_type)
            device.name = name.strip()
            if not device.name:
                raise DriverValidationError("device_name_required")
            device.configuration = driver.validate_configuration(configuration)
            device.enabled = enabled
            if not enabled:
                device.health_status = "disabled"
            if credentials is not None:
                cipher = self._require_cipher()
                secret = driver.validate_credentials(credentials)
                stored = session.get(DeviceCredential, device_id)
                if stored is None:
                    stored = DeviceCredential(device_id=device_id)
                    session.add(stored)
                stored.encrypted_payload = cipher.encrypt(secret)
                stored.key_id = cipher.key_id
                stored.rotated_at = datetime.now(UTC)
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="device.updated",
                    object_type="device",
                    object_id=str(device.id),
                    changes={"name": device.name, "enabled": enabled, "credential_replaced": credentials is not None},
                    client_ip=client_ip,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ResourceConflictError from exc
        return self.get(device_id)

    def delete(
        self, device_id: uuid.UUID, *, actor_id: uuid.UUID, client_ip: str
    ) -> None:
        with self.database.session() as session:
            device = session.get(Device, device_id)
            if device is None:
                raise ResourceNotFoundError
            listener_count = session.scalar(
                select(func.count()).select_from(ListenerMapping).where(ListenerMapping.device_id == device_id)
            )
            if listener_count:
                raise ResourceInUseError
            name = device.name
            session.delete(device)
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="device.deleted",
                    object_type="device",
                    object_id=str(device_id),
                    changes={"name": name},
                    client_ip=client_ip,
                )
            )
            session.commit()

    def test_connection(
        self, device_id: uuid.UUID, *, actor_id: uuid.UUID, client_ip: str
    ) -> dict[str, Any]:
        with self.database.session() as session:
            device = session.get(Device, device_id)
            credential = session.get(DeviceCredential, device_id)
            if device is None:
                raise ResourceNotFoundError
            if credential is None:
                raise ResourceConflictError
            try:
                secret = self._decrypt(credential)
                result = self.registry.get(device.driver_type).test_connection(
                    device.configuration, secret
                )
                device.health_status = result.status
                safe_result = {"status": result.status, "latency_ms": result.latency_ms, "reason": None}
            except (DriverOperationError, CredentialCryptoError) as exc:
                reason = str(exc)
                device.health_status = "unhealthy"
                safe_result = {"status": "unhealthy", "latency_ms": None, "reason": reason}
            device.last_checked_at = datetime.now(UTC)
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="device.connection_tested",
                    object_type="device",
                    object_id=str(device.id),
                    changes={"status": safe_result["status"], "reason": safe_result["reason"]},
                    client_ip=client_ip,
                )
            )
            session.commit()
            return safe_result

    def runtime_material(self, device_id: uuid.UUID) -> tuple[str, dict[str, Any], dict[str, Any]]:
        with self.database.session() as session:
            device = session.get(Device, device_id)
            credential = session.get(DeviceCredential, device_id)
            if device is None or credential is None or not device.enabled:
                raise ResourceConflictError
            return device.driver_type, device.configuration, self._decrypt(credential)

    def _decrypt(self, credential: DeviceCredential) -> dict[str, Any]:
        cipher = self._require_cipher()
        if credential.key_id != cipher.key_id:
            raise CredentialCryptoError("credential_key_mismatch")
        return cipher.decrypt(credential.encrypted_payload)

    def _require_cipher(self) -> CredentialCipher:
        if self.cipher is None:
            raise MasterKeyRequiredError
        return self.cipher

    @staticmethod
    def _view(
        device: Device, listener_count: int, credential_configured: bool
    ) -> dict[str, Any]:
        return {
            "id": str(device.id),
            "name": device.name,
            "driver_type": device.driver_type,
            "configuration": device.configuration,
            "enabled": device.enabled,
            "health_status": device.health_status,
            "last_checked_at": device.last_checked_at,
            "listener_count": listener_count,
            "credential_configured": credential_configured,
            "created_at": device.created_at,
        }


class ListenerService:
    def __init__(self, database: Database, registry: DriverRegistry) -> None:
        self.database = database
        self.registry = registry

    def list(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(ListenerMapping, Device.name, Device.driver_type)
                .join(Device, Device.id == ListenerMapping.device_id)
                .order_by(ListenerMapping.udp_port)
            ).all()
            return [self._view(mapping, device_name, driver_type) for mapping, device_name, driver_type in rows]

    def create(
        self,
        *,
        device_id: uuid.UUID,
        name: str,
        description: str | None,
        udp_port: int | None,
        allowed_source_ip: str,
        driver_parameters: dict[str, Any],
        enabled: bool,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        source = self._source_ip(allowed_source_ip)
        with self.database.session() as session:
            settings = session.execute(
                select(ApplicationSettings).where(ApplicationSettings.id == 1).with_for_update()
            ).scalar_one()
            device = session.get(Device, device_id)
            if device is None:
                raise ResourceNotFoundError
            if enabled and not device.enabled:
                raise ResourceConflictError
            parameters = self.registry.get(device.driver_type).validate_listener_parameters(driver_parameters)
            port = udp_port if udp_port is not None else self._allocate_port(session, settings)
            self._validate_port(session, settings, port)
            if not self._port_available(port):
                raise ResourceConflictError
            mapping = ListenerMapping(
                device_id=device_id,
                name=name.strip(),
                description=(description or "").strip() or None,
                udp_port=port,
                allowed_source_ip=source,
                driver_parameters=parameters,
                enabled=enabled,
                status="inactive",
            )
            if not mapping.name:
                raise DriverValidationError("listener_name_required")
            session.add(mapping)
            try:
                session.flush()
                session.add(
                    _audit(
                        actor_id=actor_id,
                        action="listener.created",
                        object_type="listener",
                        object_id=str(mapping.id),
                        changes={"name": mapping.name, "udp_port": port, "enabled": enabled},
                        client_ip=client_ip,
                    )
                )
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ResourceConflictError from exc
        return self.get(mapping.id)

    def get(self, mapping_id: uuid.UUID) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.execute(
                select(ListenerMapping, Device.name, Device.driver_type)
                .join(Device, Device.id == ListenerMapping.device_id)
                .where(ListenerMapping.id == mapping_id)
            ).one_or_none()
            if row is None:
                raise ResourceNotFoundError
            return self._view(row[0], row[1], row[2])

    def update(
        self,
        mapping_id: uuid.UUID,
        *,
        version: int,
        device_id: uuid.UUID,
        name: str,
        description: str | None,
        udp_port: int,
        allowed_source_ip: str,
        driver_parameters: dict[str, Any],
        enabled: bool,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        source = self._source_ip(allowed_source_ip)
        with self.database.session() as session:
            mapping = session.execute(
                select(ListenerMapping).where(ListenerMapping.id == mapping_id).with_for_update()
            ).scalar_one_or_none()
            if mapping is None:
                raise ResourceNotFoundError
            if mapping.version != version:
                raise StaleVersionError
            settings = session.get(ApplicationSettings, 1)
            device = session.get(Device, device_id)
            if settings is None or device is None:
                raise ResourceNotFoundError
            if enabled and not device.enabled:
                raise ResourceConflictError
            parameters = self.registry.get(device.driver_type).validate_listener_parameters(driver_parameters)
            self._validate_port(session, settings, udp_port, exclude_id=mapping_id)
            if udp_port != mapping.udp_port and not self._port_available(udp_port):
                raise ResourceConflictError
            mapping.device_id = device_id
            mapping.name = name.strip()
            mapping.description = (description or "").strip() or None
            mapping.udp_port = udp_port
            mapping.allowed_source_ip = source
            mapping.driver_parameters = parameters
            mapping.enabled = enabled
            mapping.status = "inactive"
            mapping.last_error = None
            mapping.version += 1
            if not mapping.name:
                raise DriverValidationError("listener_name_required")
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="listener.updated",
                    object_type="listener",
                    object_id=str(mapping.id),
                    changes={"name": mapping.name, "udp_port": udp_port, "enabled": enabled, "version": mapping.version},
                    client_ip=client_ip,
                )
            )
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ResourceConflictError from exc
        return self.get(mapping_id)

    def delete(
        self, mapping_id: uuid.UUID, *, actor_id: uuid.UUID, client_ip: str
    ) -> None:
        with self.database.session() as session:
            mapping = session.get(ListenerMapping, mapping_id)
            if mapping is None:
                raise ResourceNotFoundError
            event_count = session.scalar(
                select(func.count()).select_from(WakeEvent).where(WakeEvent.mapping_id == mapping_id)
            )
            if event_count:
                raise ResourceInUseError
            name = mapping.name
            port = mapping.udp_port
            session.delete(mapping)
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="listener.deleted",
                    object_type="listener",
                    object_id=str(mapping_id),
                    changes={"name": name, "udp_port": port},
                    client_ip=client_ip,
                )
            )
            session.commit()

    @staticmethod
    def _source_ip(value: str) -> str:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError as exc:
            raise DriverValidationError("invalid_allowed_source_ip") from exc

    @staticmethod
    def _allocate_port(session: Any, settings: ApplicationSettings) -> int:
        used = set(session.scalars(select(ListenerMapping.udp_port)).all())
        for port in range(settings.udp_port_start, settings.udp_port_end + 1):
            if port not in used and ListenerService._port_available(port):
                return port
        raise ResourceConflictError

    @staticmethod
    def _validate_port(
        session: Any,
        settings: ApplicationSettings,
        port: int,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if not settings.udp_port_start <= port <= settings.udp_port_end:
            raise DriverValidationError("udp_port_outside_allowed_range")
        statement = select(ListenerMapping.id).where(ListenerMapping.udp_port == port)
        if exclude_id is not None:
            statement = statement.where(ListenerMapping.id != exclude_id)
        if session.scalar(statement) is not None:
            raise ResourceConflictError

    @staticmethod
    def _port_available(port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False
        finally:
            sock.close()

    @staticmethod
    def _view(mapping: ListenerMapping, device_name: str, driver_type: str) -> dict[str, Any]:
        return {
            "id": str(mapping.id),
            "device_id": str(mapping.device_id),
            "device_name": device_name,
            "driver_type": driver_type,
            "name": mapping.name,
            "description": mapping.description,
            "udp_port": mapping.udp_port,
            "allowed_source_ip": mapping.allowed_source_ip,
            "driver_parameters": mapping.driver_parameters,
            "enabled": mapping.enabled,
            "status": mapping.status,
            "last_error": mapping.last_error,
            "version": mapping.version,
            "created_at": mapping.created_at,
            "updated_at": mapping.updated_at,
        }


class EngineStateService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self) -> dict[str, Any]:
        with self.database.session() as session:
            state = session.get(EngineState, 1)
            if state is None:
                raise ResourceNotFoundError
            active_count = session.scalar(
                select(func.count()).select_from(ListenerMapping).where(ListenerMapping.status == "active")
            )
            enabled_count = session.scalar(
                select(func.count()).select_from(ListenerMapping).where(ListenerMapping.enabled.is_(True))
            )
            return {
                "desired_state": state.desired_state,
                "observed_state": state.observed_state,
                "heartbeat_at": state.heartbeat_at,
                "last_transition_at": state.last_transition_at,
                "last_error": state.last_error,
                "active_listeners": active_count,
                "enabled_listeners": enabled_count,
            }

    def transition(
        self,
        desired_state: str,
        *,
        observed_state: str,
        last_error: str | None,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            state = session.get(EngineState, 1)
            if state is None:
                raise ResourceNotFoundError
            state.desired_state = desired_state
            state.observed_state = observed_state
            state.last_error = last_error
            state.last_transition_at = datetime.now(UTC)
            state.heartbeat_at = datetime.now(UTC)
            session.add(
                _audit(
                    actor_id=actor_id,
                    action=f"engine.{desired_state}",
                    object_type="engine",
                    object_id="1",
                    changes={"observed_state": observed_state, "last_error": last_error},
                    client_ip=client_ip,
                )
            )
            session.commit()
        return self.get()
