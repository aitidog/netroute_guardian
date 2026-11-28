"""Async repository for point-in-time RouteSnapshot persistence."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import RouteSnapshot


class SnapshotRepository:
    """Encapsulates all async database access for ``route_snapshots``."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        device_id: int | None,
        change_id: int | None,
        device_label: str,
        phase: str,
        source_type: str,
        raw_entry_count: int,
        unique_prefix_count: int,
        routes_json: list[dict],
        commit: bool = False,
    ) -> RouteSnapshot:
        snap = RouteSnapshot(
            device_id=device_id,
            change_id=change_id,
            device_label=device_label,
            phase=phase,
            source_type=source_type,
            raw_entry_count=raw_entry_count,
            unique_prefix_count=unique_prefix_count,
            routes_json=routes_json,
        )
        self._db.add(snap)
        if commit:
            await self._db.commit()
            await self._db.refresh(snap)
        else:
            await self._db.flush()
        return snap

    async def get_latest_by_device_for_change(
        self,
        change_id: int,
        phase: str,
    ) -> dict[int, RouteSnapshot]:
        result = await self._db.scalars(
            select(RouteSnapshot)
            .where(RouteSnapshot.change_id == change_id, RouteSnapshot.phase == phase)
            .order_by(RouteSnapshot.captured_at.desc())
        )
        by_device: dict[int, RouteSnapshot] = {}
        for snap in result.all():
            if snap.device_id is not None and snap.device_id not in by_device:
                by_device[snap.device_id] = snap
        return by_device

    async def delete_by_change_id(self, change_id: int) -> None:
        await self._db.execute(delete(RouteSnapshot).where(RouteSnapshot.change_id == change_id))
