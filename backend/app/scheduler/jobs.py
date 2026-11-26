"""DB-driven APScheduler manager for ServiceNow sync and T-1h automatic pre-capture."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models.entities import utcnow
from app.repositories.bundle import RepositoryBundle
from app.services.change_service import ChangeWorkflowService

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Runs periodic ServiceNow polling and T-1h pre-change capture dispatch via repositories."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        change_service: ChangeWorkflowService,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.change_service = change_service
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self.last_sync_at: datetime | None = None
        self.last_dispatch_at: datetime | None = None

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self._scheduler.running:
            return

        self._scheduler.add_job(
            self.run_sync_tick,
            trigger="interval",
            seconds=self.settings.servicenow_sync_interval_seconds,
            id="servicenow_sync",
            name="ServiceNow Change Window Sync",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self.run_dispatch_tick,
            trigger="interval",
            seconds=self.settings.scheduler_dispatch_interval_seconds,
            id="pre_capture_dispatch",
            name="T-1h Pre-Change Route Capture Dispatch",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "APScheduler started (sync=%ds, dispatch=%ds)",
            self.settings.servicenow_sync_interval_seconds,
            self.settings.scheduler_dispatch_interval_seconds,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped")

    async def run_sync_tick(self) -> int:
        """Single ServiceNow sync cycle (also directly callable from tests)."""
        with self.session_factory() as db:
            repos = RepositoryBundle(db)
            synced = await self.change_service.sync_from_servicenow(repos)
            self.last_sync_at = utcnow()
            return len(synced)

    async def run_dispatch_tick(self) -> list[int]:
        """Claim due T-1h changes with FOR UPDATE SKIP LOCKED and execute pre-change captures."""
        with self.session_factory() as db:
            repos = RepositoryBundle(db)
            due_ids = await self.change_service.claim_due_pre_capture_ids(repos)

        processed: list[int] = []
        for chg_id in due_ids:
            try:
                with self.session_factory() as db:
                    repos = RepositoryBundle(db)
                    await self.change_service.capture_pre_change(repos, chg_id)
                processed.append(chg_id)
            except Exception as exc:
                logger.exception("Scheduled pre-capture failed for change_id=%d: %s", chg_id, exc)

        self.last_dispatch_at = utcnow()
        return processed

    def describe_jobs(self) -> list[dict[str, Any]]:
        if not self._scheduler.running:
            return []
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in self._scheduler.get_jobs()
        ]
