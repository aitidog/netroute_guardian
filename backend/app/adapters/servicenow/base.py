"""Abstract ServiceNow provider contract and normalized change DTO."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ServiceNowChangeDTO:
    """Normalized Change Request fetched from ServiceNow (live or simulated)."""

    chg_number: str
    title: str
    description: str
    scheduled_start: datetime
    scheduled_end: datetime | None
    engineer_name: str
    engineer_email: str
    state: str  # scheduled | implement | closed | cancelled
    ci_device_ids: list[int] = field(default_factory=list)
    ci_hostnames: list[str] = field(default_factory=list)


class ServiceNowProvider(ABC):
    """Pluggable interface for retrieving scheduled network changes from ServiceNow."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier of this provider implementation (e.g. 'mock' or 'live')."""

    @abstractmethod
    async def fetch_scheduled_changes(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ServiceNowChangeDTO]:
        """Return network Change Requests scheduled within [window_start, window_end]."""
