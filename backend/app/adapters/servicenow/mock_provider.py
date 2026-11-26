"""Repository-backed ServiceNow simulator provider for standalone demonstrations."""

from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.servicenow.base import ServiceNowChangeDTO, ServiceNowProvider
from app.repositories.mock_snow_repo import MockServiceNowRepository


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class MockServiceNowProvider(ServiceNowProvider):
    """Reads simulated Change Requests via ``MockServiceNowRepository``."""

    def __init__(self, repo: MockServiceNowRepository) -> None:
        self._repo = repo

    @property
    def source_name(self) -> str:
        return "mock"

    async def fetch_scheduled_changes(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ServiceNowChangeDTO]:
        records = await self._repo.list_all()
        results: list[ServiceNowChangeDTO] = []
        ws = _ensure_utc(window_start)
        we = _ensure_utc(window_end)

        for rec in records:
            start_utc = _ensure_utc(rec.scheduled_start)
            # Include cancelled changes so already-synced platform jobs get cancelled.
            if rec.state == "cancelled" or (ws <= start_utc <= we):
                results.append(
                    ServiceNowChangeDTO(
                        chg_number=rec.chg_number,
                        title=rec.title,
                        description=rec.description,
                        scheduled_start=start_utc,
                        scheduled_end=(_ensure_utc(rec.scheduled_end) if rec.scheduled_end else None),
                        engineer_name=rec.engineer_name,
                        engineer_email=rec.engineer_email,
                        state=rec.state,
                        ci_device_ids=list(rec.ci_device_ids or []),
                    )
                )
        return results
