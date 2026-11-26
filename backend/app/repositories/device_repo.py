"""Repository for managed network Device (CI) persistence."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.models.entities import Device


class DeviceRepository:
    """Encapsulates all database access for ``devices``."""

    def __init__(self, db: Session) -> None:
        self._db = db

    async def list_all(self) -> list[Device]:
        return list(self._db.scalars(select(Device).order_by(Device.hostname.asc())).all())

    async def get_by_id(self, device_id: int) -> Device | None:
        return self._db.get(Device, device_id)

    async def get_by_hostname(self, hostname: str) -> Device | None:
        return self._db.scalar(select(Device).where(Device.hostname == hostname))

    async def get_by_hostname_or_ip(self, query: str) -> Device | None:
        cleaned = query.strip()
        return self._db.scalar(
            select(Device).where(
                or_(
                    func.lower(Device.hostname) == cleaned.lower(),
                    Device.ip_address == cleaned,
                )
            )
        )

    async def find_ids_by_ids(self, device_ids: list[int]) -> list[int]:
        if not device_ids:
            return []
        return list(self._db.scalars(select(Device.id).where(Device.id.in_(device_ids))).all())

    async def find_ids_by_hostnames(self, hostnames: list[str]) -> list[int]:
        if not hostnames:
            return []
        return list(self._db.scalars(select(Device.id).where(Device.hostname.in_(hostnames))).all())

    async def create(
        self,
        *,
        hostname: str,
        ip_address: str,
        device_type: str,
        connection_mode: str = "mock",
        location: str = "",
        description: str = "",
        config_json: dict | None = None,
        commit: bool = True,
    ) -> Device:
        device = Device(
            hostname=hostname,
            ip_address=ip_address,
            device_type=device_type,
            connection_mode=connection_mode,
            location=location,
            description=description,
            config_json=config_json or {},
        )
        self._db.add(device)
        try:
            if commit:
                self._db.commit()
                self._db.refresh(device)
            else:
                self._db.flush()
        except IntegrityError as exc:
            self._db.rollback()
            raise ConflictError("Device with the same hostname or IP address already exists") from exc
        return device
