"""Async repository for persisted ComparisonReport entities."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ComparisonReport


class ReportRepository:
    """Encapsulates all async database access for ``comparison_reports``."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_recent(self, limit: int = 50) -> list[ComparisonReport]:
        stmt = select(ComparisonReport).order_by(ComparisonReport.created_at.desc()).limit(limit)
        result = await self._db.scalars(stmt)
        return list(result.all())

    async def get_by_id(self, report_id: int) -> ComparisonReport | None:
        return await self._db.get(ComparisonReport, report_id)

    async def create(
        self,
        *,
        change_id: int | None = None,
        device_id: int | None = None,
        device_label: str,
        before_snapshot_id: int,
        after_snapshot_id: int,
        risk_level: str,
        summary_stats: dict,
        report_payload: dict,
        email_recipient: str | None = None,
        email_status: str = "skipped",
        commit: bool = False,
    ) -> ComparisonReport:
        report = ComparisonReport(
            change_id=change_id,
            device_id=device_id,
            device_label=device_label,
            before_snapshot_id=before_snapshot_id,
            after_snapshot_id=after_snapshot_id,
            risk_level=risk_level,
            summary_stats=summary_stats,
            report_payload=report_payload,
            email_recipient=email_recipient,
            email_status=email_status,
        )
        self._db.add(report)
        if commit:
            await self._db.commit()
            await self._db.refresh(report)
        else:
            await self._db.flush()
        return report

    async def update_email_delivery(
        self,
        reports: list[ComparisonReport],
        *,
        recipient: str | None = None,
        status: str,
        error: str | None,
        sent_at: datetime | None,
        commit: bool = True,
    ) -> None:
        for rep in reports:
            if recipient is not None:
                rep.email_recipient = recipient
            rep.email_status = status
            rep.email_error = error
            if sent_at is not None:
                rep.email_sent_at = sent_at
        if commit:
            await self._db.commit()
