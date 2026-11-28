"""Async repository for synchronized ServiceNow ChangeRequest entities and CI links."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import ChangeDeviceLink, ChangeRequest


class ChangeRequestRepository:
    """Encapsulates all async database access for ``change_requests`` and ``change_device_links``."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_with_relations(self) -> list[ChangeRequest]:
        stmt = (
            select(ChangeRequest)
            .options(
                selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device),
                selectinload(ChangeRequest.snapshots),
                selectinload(ChangeRequest.reports),
            )
            .order_by(ChangeRequest.scheduled_start.asc())
        )
        result = await self._db.scalars(stmt)
        return list(result.all())

    async def get_with_relations(self, change_id: int) -> ChangeRequest | None:
        stmt = (
            select(ChangeRequest)
            .options(
                selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device),
                selectinload(ChangeRequest.snapshots),
                selectinload(ChangeRequest.reports),
            )
            .where(ChangeRequest.id == change_id)
        )
        return await self._db.scalar(stmt)

    async def get_by_id(self, change_id: int) -> ChangeRequest | None:
        return await self._db.get(ChangeRequest, change_id)

    async def get_with_devices(self, change_id: int) -> ChangeRequest | None:
        stmt = (
            select(ChangeRequest)
            .options(selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device))
            .where(ChangeRequest.id == change_id)
        )
        return await self._db.scalar(stmt)

    async def get_by_chg_number_with_links(self, chg_number: str) -> ChangeRequest | None:
        stmt = (
            select(ChangeRequest)
            .options(selectinload(ChangeRequest.device_links))
            .where(ChangeRequest.chg_number == chg_number)
        )
        return await self._db.scalar(stmt)

    async def create(
        self,
        *,
        chg_number: str,
        title: str,
        description: str,
        scheduled_start: datetime,
        scheduled_end: datetime | None,
        capture_scheduled_at: datetime,
        engineer_name: str,
        engineer_email: str,
        status: str,
        sync_source: str,
        synced_at: datetime,
    ) -> ChangeRequest:
        change = ChangeRequest(
            chg_number=chg_number,
            title=title,
            description=description,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            capture_scheduled_at=capture_scheduled_at,
            engineer_name=engineer_name,
            engineer_email=engineer_email,
            status=status,
            sync_source=sync_source,
            synced_at=synced_at,
        )
        self._db.add(change)
        await self._db.flush()
        # Ensure device_links relationship is initialized without lazy IO under AsyncSession
        await self._db.refresh(change, attribute_names=["device_links"])
        return change

    async def replace_device_links(self, change: ChangeRequest, device_ids: list[int]) -> None:
        current_ids = {link.device_id for link in change.device_links}
        if current_ids == set(device_ids):
            return
        change.device_links.clear()
        await self._db.flush()
        for dev_id in device_ids:
            self._db.add(ChangeDeviceLink(change_id=change.id, device_id=dev_id))

    async def save_status(
        self,
        change: ChangeRequest,
        *,
        status: str,
        last_error: str | None = None,
        increment_retry: bool = False,
    ) -> None:
        change.status = status
        change.last_error = last_error
        if increment_retry:
            change.retry_count += 1
        await self._db.commit()

    async def claim_due_pre_capture_ids(self, cutoff_utc: datetime) -> list[int]:
        """Atomically claim due T-1h Change Requests using FOR UPDATE SKIP LOCKED on PostgreSQL."""
        stmt = (
            select(ChangeRequest)
            .where(
                ChangeRequest.status == "synced",
                ChangeRequest.capture_scheduled_at <= cutoff_utc,
            )
            .order_by(ChangeRequest.capture_scheduled_at.asc())
        )
        conn = await self._db.connection()
        if conn.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        result = await self._db.scalars(stmt)
        due_changes = list(result.all())
        claimed_ids: list[int] = []
        for chg in due_changes:
            chg.status = "pre_capturing"
            claimed_ids.append(chg.id)
        await self._db.commit()
        return claimed_ids

    async def count_all(self) -> int:
        return int(await self._db.scalar(select(func.count(ChangeRequest.id))) or 0)

    async def count_by_status(self, status: str) -> int:
        return int(
            await self._db.scalar(select(func.count(ChangeRequest.id)).where(ChangeRequest.status == status))
            or 0
        )

    async def min_capture_scheduled_at_by_status(self, status: str) -> datetime | None:
        return await self._db.scalar(
            select(func.min(ChangeRequest.capture_scheduled_at)).where(ChangeRequest.status == status)
        )

    async def delete(self, change: ChangeRequest, *, commit: bool = False) -> None:
        await self._db.delete(change)
        if commit:
            await self._db.commit()
