"""Async repository for simulated external ServiceNow change tickets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.entities import MockServiceNowChange


class MockServiceNowRepository:
    """Encapsulates all async database access for ``mock_servicenow_changes``."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_all(self) -> list[MockServiceNowChange]:
        stmt = select(MockServiceNowChange).order_by(MockServiceNowChange.scheduled_start.asc())
        result = await self._db.scalars(stmt)
        return list(result.all())

    async def has_any(self) -> bool:
        return await self._db.scalar(select(MockServiceNowChange.id).limit(1)) is not None

    async def get_by_id(self, record_id: int) -> MockServiceNowChange | None:
        return await self._db.get(MockServiceNowChange, record_id)

    async def create(
        self,
        *,
        chg_number: str,
        title: str,
        description: str,
        scheduled_start: datetime,
        scheduled_end: datetime | None,
        engineer_name: str,
        engineer_email: str,
        state: str,
        ci_device_ids: list[int],
        commit: bool = True,
    ) -> MockServiceNowChange:
        rec = MockServiceNowChange(
            chg_number=chg_number,
            title=title,
            description=description,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            engineer_name=engineer_name,
            engineer_email=engineer_email,
            state=state,
            ci_device_ids=ci_device_ids,
        )
        self._db.add(rec)
        try:
            if commit:
                await self._db.commit()
                await self._db.refresh(rec)
            else:
                await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise ConflictError(f"ServiceNow change '{chg_number}' already exists") from exc
        return rec

    async def update(self, record_id: int, fields: dict[str, Any]) -> MockServiceNowChange:
        rec = await self._db.get(MockServiceNowChange, record_id)
        if rec is None:
            raise ResourceNotFoundError("Simulated ServiceNow change not found")
        for key, value in fields.items():
            setattr(rec, key, value)
        await self._db.commit()
        await self._db.refresh(rec)
        return rec

    async def mark_closed_by_chg_number(self, chg_number: str) -> None:
        rec = await self._db.scalar(
            select(MockServiceNowChange).where(MockServiceNowChange.chg_number == chg_number)
        )
        if rec is not None and rec.state != "closed":
            rec.state = "closed"
