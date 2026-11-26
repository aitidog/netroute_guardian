"""Scoped async Unit-of-Work bundle exposing all domain repositories over one AsyncSession."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.change_repo import ChangeRequestRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.important_route_repo import ImportantRouteRepository
from app.repositories.mock_snow_repo import MockServiceNowRepository
from app.repositories.report_repo import ReportRepository
from app.repositories.settings_repo import SettingsRepository
from app.repositories.snapshot_repo import SnapshotRepository


class RepositoryBundle:
    """Groups all async domain repositories under one transactional AsyncSession."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self.devices = DeviceRepository(db)
        self.important_routes = ImportantRouteRepository(db)
        self.settings = SettingsRepository(db)
        self.mock_servicenow = MockServiceNowRepository(db)
        self.changes = ChangeRequestRepository(db)
        self.snapshots = SnapshotRepository(db)
        self.reports = ReportRepository(db)

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()


async def get_repositories(
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[RepositoryBundle, None]:
    """FastAPI async dependency providing a request-scoped RepositoryBundle."""
    yield RepositoryBundle(db)
