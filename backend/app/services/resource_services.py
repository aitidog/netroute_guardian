"""Domain services for Important Routes, Devices, ServiceNow Simulator, and Settings."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.exceptions import DomainValidationError
from app.models.entities import Device, ImportantRoute, MockServiceNowChange
from app.repositories.bundle import RepositoryBundle
from app.schemas.dto import (
    AppSettingsRead,
    AppSettingsUpdate,
    DeviceCreate,
    ImportantRouteCreate,
    ImportantRouteUpdate,
    MockServiceNowChangeCreate,
    MockServiceNowChangeUpdate,
    SchedulerStatusRead,
)
from app.services.change_service import ChangeWorkflowService


class ImportantRouteService:
    """Business service for CRUD management of pre-specified critical routes."""

    async def list_routes(self, repos: RepositoryBundle) -> list[ImportantRoute]:
        return await repos.important_routes.list_all()

    async def create_route(self, repos: RepositoryBundle, payload: ImportantRouteCreate) -> ImportantRoute:
        return await repos.important_routes.create(
            prefix=payload.prefix,
            description=payload.description,
            enabled=payload.enabled,
            commit=True,
        )

    async def update_route(
        self, repos: RepositoryBundle, route_id: int, payload: ImportantRouteUpdate
    ) -> ImportantRoute:
        return await repos.important_routes.update(
            route_id,
            prefix=payload.prefix,
            description=payload.description,
            enabled=payload.enabled,
        )

    async def delete_route(self, repos: RepositoryBundle, route_id: int) -> None:
        await repos.important_routes.delete(route_id)


class DeviceService:
    """Business service for managed network device inventory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def list_devices(self, repos: RepositoryBundle) -> list[Device]:
        return await repos.devices.list_all()

    async def create_device(self, repos: RepositoryBundle, payload: DeviceCreate) -> Device:
        if (
            self._settings is not None
            and self._settings.demo_disable_live_devices
            and payload.connection_mode == "live"
        ):
            raise DomainValidationError(
                "Live device creation is disabled in public demo mode; use connection_mode='mock'."
            )
        return await repos.devices.create(**payload.model_dump(), commit=True)


class SimulatorService:
    """Business service for simulated ServiceNow Change Requests and webhook sync."""

    def __init__(self, change_service: ChangeWorkflowService) -> None:
        self._change_service = change_service

    async def list_changes(self, repos: RepositoryBundle) -> list[MockServiceNowChange]:
        return await repos.mock_servicenow.list_all()

    async def create_change(
        self,
        repos: RepositoryBundle,
        payload: MockServiceNowChangeCreate,
    ) -> MockServiceNowChange:
        chg_number = payload.chg_number or f"CHG{int(datetime.now(UTC).timestamp()) % 10000000:07d}"
        rec = await repos.mock_servicenow.create(
            chg_number=chg_number,
            title=payload.title,
            description=payload.description,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            engineer_name=payload.engineer_name,
            engineer_email=str(payload.engineer_email),
            state=payload.state,
            ci_device_ids=payload.ci_device_ids,
            commit=True,
        )
        await self._change_service.sync_from_servicenow(repos)
        return rec

    async def update_change(
        self,
        repos: RepositoryBundle,
        record_id: int,
        payload: MockServiceNowChangeUpdate,
    ) -> MockServiceNowChange:
        fields: dict[str, Any] = {}
        for field_name, val in payload.model_dump(exclude_unset=True).items():
            fields[field_name] = str(val) if field_name == "engineer_email" and val else val
        rec = await repos.mock_servicenow.update(record_id, fields)
        await self._change_service.sync_from_servicenow(repos)
        return rec

    async def handle_webhook(self, repos: RepositoryBundle) -> dict[str, Any]:
        synced = await self._change_service.sync_from_servicenow(repos)
        return {"status": "accepted", "synced_count": len(synced)}


class SettingsService:
    """Business service for runtime configuration and scheduler observability."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def get_settings(self, repos: RepositoryBundle) -> AppSettingsRead:
        return AppSettingsRead(
            servicenow_mode=self._settings.servicenow_mode,
            servicenow_window_hours=await repos.settings.get_int(
                "servicenow_window_hours", self._settings.servicenow_window_hours
            ),
            pre_capture_lead_minutes=await repos.settings.get_int(
                "pre_capture_lead_minutes", self._settings.pre_capture_lead_minutes
            ),
            large_prefix_threshold=await repos.settings.get_int(
                "large_prefix_threshold", self._settings.default_large_prefix_threshold
            ),
            max_concurrent_device_collections=self._settings.max_concurrent_device_collections,
            pipeline_executor_mode=self._settings.pipeline_executor_mode,
            pipeline_max_workers=self._settings.pipeline_max_workers,
            mailpit_web_url=self._settings.mailpit_web_url,
        )

    async def update_settings(self, repos: RepositoryBundle, payload: AppSettingsUpdate) -> AppSettingsRead:
        updates = {
            key: str(val) for key, val in payload.model_dump(exclude_unset=True).items() if val is not None
        }
        if updates:
            await repos.settings.upsert_many(updates)
        return await self.get_settings(repos)

    async def get_scheduler_status(
        self, repos: RepositoryBundle, scheduler_manager: Any
    ) -> SchedulerStatusRead:
        total_changes = await repos.changes.count_all()
        pending_count = await repos.changes.count_by_status("synced")
        next_due = await repos.changes.min_capture_scheduled_at_by_status("synced")
        return SchedulerStatusRead(
            running=scheduler_manager.running,
            servicenow_mode=self._settings.servicenow_mode,
            last_sync_at=scheduler_manager.last_sync_at,
            last_dispatch_at=scheduler_manager.last_dispatch_at,
            synced_changes_count=total_changes,
            pending_pre_captures=pending_count,
            next_due_capture_at=next_due,
            jobs=scheduler_manager.describe_jobs(),
        )
