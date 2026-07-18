import csv
import io
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, delete, func, or_, select, text

from app.application.operations_service import ResourceNotFoundError, _audit
from app.infrastructure.database.connection import Database
from app.infrastructure.database.models import (
    ApplicationSettings,
    AuditEvent,
    Device,
    ListenerMapping,
    User,
    UserSession,
    WakeEvent,
)


LOGGER = logging.getLogger("wolt.retention")
RETENTION_LOCK_KEY = 884_705_001


class UdpRangeOutsidePublishedError(RuntimeError):
    detail = "udp_range_outside_published_range"


class UdpRangeExcludesListenersError(RuntimeError):
    detail = "udp_range_excludes_existing_listeners"


class ObservabilityService:
    def __init__(
        self,
        database: Database,
        *,
        published_udp_start: int = 40000,
        published_udp_end: int = 40099,
    ) -> None:
        self.database = database
        self.published_udp_start = published_udp_start
        self.published_udp_end = published_udp_end

    def wake_events(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        result_code: str | None = None,
        mapping_id: uuid.UUID | None = None,
        device_id: uuid.UUID | None = None,
        query: str | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
    ) -> dict[str, Any]:
        filters = self._wake_filters(
            result_code=result_code,
            mapping_id=mapping_id,
            device_id=device_id,
            query=query,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
        )
        with self.database.session() as session:
            total = session.scalar(
                select(func.count()).select_from(WakeEvent).where(*filters)
            ) or 0
            rows = session.execute(
                select(WakeEvent, ListenerMapping.name, Device.name)
                .join(ListenerMapping, ListenerMapping.id == WakeEvent.mapping_id)
                .join(Device, Device.id == WakeEvent.device_id)
                .where(*filters)
                .order_by(WakeEvent.occurred_at.desc(), WakeEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "items": [
                    self._wake_view(event, mapping_name, device_name)
                    for event, mapping_name, device_name in rows
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": max(1, (total + page_size - 1) // page_size),
            }

    def wake_events_csv(self, **filters: Any) -> str:
        clauses = self._wake_filters(**filters)
        with self.database.session() as session:
            rows = session.execute(
                select(WakeEvent, ListenerMapping.name, Device.name)
                .join(ListenerMapping, ListenerMapping.id == WakeEvent.mapping_id)
                .join(Device, Device.id == WakeEvent.device_id)
                .where(*clauses)
                .order_by(WakeEvent.occurred_at.desc(), WakeEvent.id.desc())
                .limit(10_000)
            ).all()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "occurred_at",
                "result",
                "mac_address",
                "mapping",
                "device",
                "source_ip",
                "source_port",
                "duration_ms",
                "correlation_id",
            ]
        )
        for event, mapping_name, device_name in rows:
            writer.writerow(
                [
                    event.occurred_at.isoformat(),
                    self._csv_cell(event.result_code),
                    event.mac_address,
                    self._csv_cell(mapping_name),
                    self._csv_cell(device_name),
                    event.source_ip,
                    event.source_port,
                    event.duration_ms if event.duration_ms is not None else "",
                    str(event.correlation_id),
                ]
            )
        return stream.getvalue()

    def audit_events(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        action: str | None = None,
        object_type: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        clauses = []
        if action:
            clauses.append(AuditEvent.action == action)
        if object_type:
            clauses.append(AuditEvent.object_type == object_type)
        if query:
            pattern = f"%{query.strip()}%"
            clauses.append(
                or_(
                    AuditEvent.action.ilike(pattern),
                    AuditEvent.object_type.ilike(pattern),
                    AuditEvent.object_id.ilike(pattern),
                    AuditEvent.client_ip.ilike(pattern),
                    User.username.ilike(pattern),
                )
            )
        with self.database.session() as session:
            count_statement = (
                select(func.count())
                .select_from(AuditEvent)
                .outerjoin(User, User.id == AuditEvent.actor_user_id)
                .where(*clauses)
            )
            total = session.scalar(count_statement) or 0
            rows = session.execute(
                select(AuditEvent, User.username)
                .outerjoin(User, User.id == AuditEvent.actor_user_id)
                .where(*clauses)
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "items": [
                    {
                        "id": str(event.id),
                        "actor": username or "system",
                        "action": event.action,
                        "object_type": event.object_type,
                        "object_id": event.object_id,
                        "safe_changes": event.safe_changes,
                        "client_ip": event.client_ip,
                        "occurred_at": event.occurred_at,
                    }
                    for event, username in rows
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": max(1, (total + page_size - 1) // page_size),
            }

    def dashboard(self, hours: int = 24) -> dict[str, Any]:
        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)
        with self.database.session() as session:
            grouped = dict(
                session.execute(
                    select(WakeEvent.result_code, func.count())
                    .where(WakeEvent.occurred_at >= start)
                    .group_by(WakeEvent.result_code)
                ).all()
            )
            total = sum(grouped.values())
            successes = grouped.get("success", 0)
            rate_limited = grouped.get("rate_limited", 0)
            failures = total - successes - rate_limited
            series = []
            for index in range(hours):
                bucket_start = start + timedelta(hours=index)
                bucket_end = bucket_start + timedelta(hours=1)
                values = dict(
                    session.execute(
                        select(WakeEvent.result_code, func.count())
                        .where(
                            WakeEvent.occurred_at >= bucket_start,
                            WakeEvent.occurred_at < bucket_end,
                        )
                        .group_by(WakeEvent.result_code)
                    ).all()
                )
                bucket_total = sum(values.values())
                bucket_success = values.get("success", 0)
                bucket_limited = values.get("rate_limited", 0)
                series.append(
                    {
                        "start": bucket_start,
                        "success": bucket_success,
                        "rate_limited": bucket_limited,
                        "failed": bucket_total - bucket_success - bucket_limited,
                        "total": bucket_total,
                    }
                )
            recent_rows = session.execute(
                select(WakeEvent, ListenerMapping.name, Device.name)
                .join(ListenerMapping, ListenerMapping.id == WakeEvent.mapping_id)
                .join(Device, Device.id == WakeEvent.device_id)
                .order_by(WakeEvent.occurred_at.desc())
                .limit(8)
            ).all()
            healthy_devices = session.scalar(
                select(func.count()).select_from(Device).where(Device.health_status == "healthy")
            ) or 0
            total_devices = session.scalar(select(func.count()).select_from(Device)) or 0
        return {
            "period_hours": hours,
            "total_requests": total,
            "success": successes,
            "failed": failures,
            "rate_limited": rate_limited,
            "success_rate": round((successes / total) * 100, 1) if total else None,
            "healthy_devices": healthy_devices,
            "total_devices": total_devices,
            "series": series,
            "recent_events": [
                self._wake_view(event, mapping_name, device_name)
                for event, mapping_name, device_name in recent_rows
            ],
        }

    def settings(self) -> dict[str, Any]:
        with self.database.session() as session:
            settings = session.get(ApplicationSettings, 1)
            if settings is None:
                raise ResourceNotFoundError
            used_ports = session.scalar(
                select(func.count()).select_from(ListenerMapping)
            ) or 0
            return self._settings_view(settings, used_ports)

    def update_retention(
        self,
        *,
        wake_days: int,
        audit_days: int,
        rate_limit_seconds: int,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            settings = session.get(ApplicationSettings, 1)
            if settings is None:
                raise ResourceNotFoundError
            settings.wake_event_retention_days = wake_days
            settings.audit_event_retention_days = audit_days
            settings.rate_limit_seconds = rate_limit_seconds
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="settings.retention_updated",
                    object_type="application_settings",
                    object_id="1",
                    changes={
                        "wake_event_retention_days": wake_days,
                        "audit_event_retention_days": audit_days,
                        "rate_limit_seconds": rate_limit_seconds,
                    },
                    client_ip=client_ip,
                )
            )
            session.commit()
            used_ports = session.scalar(
                select(func.count()).select_from(ListenerMapping)
            ) or 0
            return self._settings_view(settings, used_ports)

    def update_udp_range(
        self,
        *,
        udp_start: int,
        udp_end: int,
        actor_id: uuid.UUID,
        client_ip: str,
    ) -> dict[str, Any]:
        if (
            udp_start < self.published_udp_start
            or udp_end > self.published_udp_end
        ):
            raise UdpRangeOutsidePublishedError
        with self.database.session() as session:
            settings = session.scalar(
                select(ApplicationSettings)
                .where(ApplicationSettings.id == 1)
                .with_for_update()
            )
            if settings is None:
                raise ResourceNotFoundError
            outside_count = session.scalar(
                select(func.count())
                .select_from(ListenerMapping)
                .where(
                    or_(
                        ListenerMapping.udp_port < udp_start,
                        ListenerMapping.udp_port > udp_end,
                    )
                )
            ) or 0
            if outside_count:
                raise UdpRangeExcludesListenersError
            previous = {
                "udp_port_start": settings.udp_port_start,
                "udp_port_end": settings.udp_port_end,
            }
            settings.udp_port_start = udp_start
            settings.udp_port_end = udp_end
            session.add(
                _audit(
                    actor_id=actor_id,
                    action="settings.udp_range_updated",
                    object_type="application_settings",
                    object_id="1",
                    changes={
                        "previous": previous,
                        "current": {
                            "udp_port_start": udp_start,
                            "udp_port_end": udp_end,
                        },
                    },
                    client_ip=client_ip,
                )
            )
            session.commit()
            used_ports = session.scalar(
                select(func.count()).select_from(ListenerMapping)
            ) or 0
            return self._settings_view(settings, used_ports)

    def _settings_view(
        self, settings: ApplicationSettings, used_ports: int
    ) -> dict[str, Any]:
        return {
            "udp_port_start": settings.udp_port_start,
            "udp_port_end": settings.udp_port_end,
            "udp_published_start": self.published_udp_start,
            "udp_published_end": self.published_udp_end,
            "udp_port_capacity": settings.udp_port_end - settings.udp_port_start + 1,
            "udp_ports_used": used_ports,
            "rate_limit_seconds": settings.rate_limit_seconds,
            "wake_event_retention_days": settings.wake_event_retention_days,
            "audit_event_retention_days": settings.audit_event_retention_days,
            "locale": settings.locale,
            "timezone": settings.timezone,
            "updated_at": settings.updated_at,
        }

    @staticmethod
    def _wake_filters(
        *,
        result_code: str | None = None,
        mapping_id: uuid.UUID | None = None,
        device_id: uuid.UUID | None = None,
        query: str | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
    ) -> list[Any]:
        filters = []
        if result_code:
            if result_code == "failed":
                filters.append(
                    WakeEvent.result_code.not_in(("success", "rate_limited"))
                )
            else:
                filters.append(WakeEvent.result_code == result_code)
        if mapping_id:
            filters.append(WakeEvent.mapping_id == mapping_id)
        if device_id:
            filters.append(WakeEvent.device_id == device_id)
        if query:
            pattern = f"%{query.strip()}%"
            filters.append(
                or_(
                    WakeEvent.mac_address.ilike(pattern),
                    WakeEvent.source_ip.ilike(pattern),
                    func.cast(WakeEvent.correlation_id, String).ilike(pattern),
                )
            )
        if occurred_after:
            filters.append(WakeEvent.occurred_at >= occurred_after)
        if occurred_before:
            filters.append(WakeEvent.occurred_at <= occurred_before)
        return filters

    @staticmethod
    def _wake_view(
        event: WakeEvent, mapping_name: str, device_name: str
    ) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "mapping_id": str(event.mapping_id),
            "mapping_name": mapping_name,
            "device_id": str(event.device_id),
            "device_name": device_name,
            "event_type": event.event_type,
            "mac_address": event.mac_address,
            "source_ip": event.source_ip,
            "source_port": event.source_port,
            "result_code": event.result_code,
            "duration_ms": event.duration_ms,
            "correlation_id": str(event.correlation_id),
            "occurred_at": event.occurred_at,
        }

    @staticmethod
    def _csv_cell(value: str) -> str:
        return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


class RetentionService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def cleanup(self) -> dict[str, int | bool]:
        now = datetime.now(UTC)
        with self.database.engine.connect() as connection:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": RETENTION_LOCK_KEY},
                ).scalar()
            )
            if not acquired:
                return {"acquired": False, "wake_events": 0, "audit_events": 0, "sessions": 0}
            connection.commit()
            try:
                with connection.begin():
                    settings = connection.execute(
                        select(
                            ApplicationSettings.wake_event_retention_days,
                            ApplicationSettings.audit_event_retention_days,
                        ).where(ApplicationSettings.id == 1)
                    ).one()
                    wake_result = connection.execute(
                        delete(WakeEvent).where(
                            WakeEvent.occurred_at
                            < now - timedelta(days=settings.wake_event_retention_days)
                        )
                    )
                    audit_result = connection.execute(
                        delete(AuditEvent).where(
                            AuditEvent.occurred_at
                            < now - timedelta(days=settings.audit_event_retention_days)
                        )
                    )
                    session_result = connection.execute(
                        delete(UserSession).where(UserSession.expires_at < now)
                    )
                return {
                    "acquired": True,
                    "wake_events": wake_result.rowcount or 0,
                    "audit_events": audit_result.rowcount or 0,
                    "sessions": session_result.rowcount or 0,
                }
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": RETENTION_LOCK_KEY},
                )
                connection.commit()


class RetentionWorker:
    def __init__(self, retention: RetentionService, interval_seconds: int = 3600) -> None:
        self.retention = retention
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="retention", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                result = self.retention.cleanup()
                LOGGER.info("event=retention_cleanup result=%s", result)
            except Exception as exc:
                LOGGER.error("event=retention_cleanup_failed reason=%s", type(exc).__name__)
