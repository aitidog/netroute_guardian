"""Async FastAPI v1 REST routes strictly following Route -> Service -> Repository separation.

Routes perform HTTP request/response handling only and never execute database queries directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import Response

from app.models.entities import utcnow
from app.repositories.bundle import RepositoryBundle, get_repositories
from app.schemas.dto import (
    AppSettingsRead,
    AppSettingsUpdate,
    ChangeRequestDetailRead,
    ChangeRequestRead,
    ComparisonReportDetailRead,
    ComparisonReportSummaryRead,
    DeviceCreate,
    DeviceRead,
    ImportantRouteCreate,
    ImportantRouteRead,
    ImportantRouteUpdate,
    MockServiceNowChangeCreate,
    MockServiceNowChangeRead,
    MockServiceNowChangeUpdate,
    RouteSummaryDeviceRequest,
    RouteSummaryResponse,
    RouteSummaryTextRequest,
    SchedulerStatusRead,
    TriggerCaptureResult,
)
from app.services.change_service import ChangeWorkflowService
from app.services.resource_services import (
    DeviceService,
    ImportantRouteService,
    SettingsService,
    SimulatorService,
)
from app.services.summary_service import RouteSummaryService

router = APIRouter()


def _get_change_service(request: Request) -> ChangeWorkflowService:
    return request.app.state.change_service


def _get_summary_service(request: Request) -> RouteSummaryService:
    return request.app.state.summary_service


def _get_important_route_service(request: Request) -> ImportantRouteService:
    return request.app.state.important_route_service


def _get_device_service(request: Request) -> DeviceService:
    return request.app.state.device_service


def _get_simulator_service(request: Request) -> SimulatorService:
    return request.app.state.simulator_service


def _get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings_service


# ---------------------------------------------------------------------------
# Feature 1: Change Requests & Workflow
# ---------------------------------------------------------------------------
@router.get("/changes", response_model=list[ChangeRequestRead], tags=["Changes"])
async def list_changes(
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> list[dict[str, Any]]:
    return await service.list_changes(repos)


@router.get("/changes/{change_id}", response_model=ChangeRequestDetailRead, tags=["Changes"])
async def get_change(
    change_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    return await service.get_change_detail(repos, change_id)


@router.delete(
    "/changes/{change_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Changes"],
)
async def delete_change(
    change_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> None:
    await service.delete_change(repos, change_id)


@router.post("/changes/sync", tags=["Changes"])
async def sync_servicenow_changes(
    request: Request,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    synced = await service.sync_from_servicenow(repos)
    request.app.state.scheduler_manager.last_sync_at = utcnow()
    return {"synced_count": len(synced), "chg_numbers": [c.chg_number for c in synced]}


@router.post(
    "/changes/{change_id}/trigger-pre-capture",
    response_model=TriggerCaptureResult,
    tags=["Changes"],
)
async def trigger_pre_capture(
    change_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    return await service.capture_pre_change(repos, change_id)


@router.post(
    "/changes/{change_id}/trigger-post-capture",
    response_model=TriggerCaptureResult,
    tags=["Changes"],
)
async def trigger_post_capture(
    change_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    return await service.capture_post_change_and_compare(repos, change_id)


# ---------------------------------------------------------------------------
# Feature 1: Comparison Reports & Ad-hoc CSV Comparison
# ---------------------------------------------------------------------------
@router.get("/reports", response_model=list[ComparisonReportSummaryRead], tags=["Reports"])
async def list_reports(
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> list[Any]:
    return await service.list_reports(repos)


@router.get("/reports/{report_id}", response_model=ComparisonReportDetailRead, tags=["Reports"])
async def get_report(
    report_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> Any:
    return await service.get_report(repos, report_id)


@router.get("/reports/{report_id}/export-csv", tags=["Reports"])
async def export_report_csv(
    report_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> Response:
    filename, content = await service.export_report_csv(repos, report_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/{report_id}/email-preview", tags=["Reports"])
async def preview_report_email(
    report_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, str]:
    return await service.preview_report_email(repos, report_id)


@router.post("/reports/{report_id}/resend-email", tags=["Reports"])
async def resend_report_email(
    report_id: int,
    recipient_email: str | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    return await service.resend_report_email(repos, report_id, recipient_email=recipient_email)


@router.post("/comparisons/adhoc", response_model=ComparisonReportDetailRead, tags=["Reports"])
async def adhoc_compare_files(
    before_file: UploadFile = File(...),
    after_file: UploadFile = File(...),
    device_label: str = Form("Uploaded Device"),
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> Any:
    before_text = (await before_file.read()).decode("utf-8-sig", errors="replace")
    after_text = (await after_file.read()).decode("utf-8-sig", errors="replace")
    return await service.compare_uploaded_texts(
        repos,
        before_text=before_text,
        after_text=after_text,
        device_label=device_label,
    )


@router.post("/comparisons/demo-csv", response_model=ComparisonReportDetailRead, tags=["Reports"])
async def compare_demo_csv(
    repos: RepositoryBundle = Depends(get_repositories),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> Any:
    return await service.compare_demo_csv(repos)


# ---------------------------------------------------------------------------
# Feature 1: Important Pre-Specified Routes CRUD
# ---------------------------------------------------------------------------
@router.get("/important-routes", response_model=list[ImportantRouteRead], tags=["Important Routes"])
async def list_important_routes(
    repos: RepositoryBundle = Depends(get_repositories),
    service: ImportantRouteService = Depends(_get_important_route_service),
) -> list[Any]:
    return await service.list_routes(repos)


@router.post(
    "/important-routes",
    response_model=ImportantRouteRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Important Routes"],
)
async def create_important_route(
    payload: ImportantRouteCreate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ImportantRouteService = Depends(_get_important_route_service),
) -> Any:
    return await service.create_route(repos, payload)


@router.put(
    "/important-routes/{route_id}",
    response_model=ImportantRouteRead,
    tags=["Important Routes"],
)
async def update_important_route(
    route_id: int,
    payload: ImportantRouteUpdate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ImportantRouteService = Depends(_get_important_route_service),
) -> Any:
    return await service.update_route(repos, route_id, payload)


@router.delete(
    "/important-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Important Routes"],
)
async def delete_important_route(
    route_id: int,
    repos: RepositoryBundle = Depends(get_repositories),
    service: ImportantRouteService = Depends(_get_important_route_service),
) -> None:
    await service.delete_route(repos, route_id)


# ---------------------------------------------------------------------------
# Feature 2: Route Summary
# ---------------------------------------------------------------------------
@router.post("/route-summary/device", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_device_routes(
    payload: RouteSummaryDeviceRequest,
    repos: RepositoryBundle = Depends(get_repositories),
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    return await service.summarize_by_device_query(
        repos,
        query=payload.query,
        include_supernet_suggestions=payload.include_supernet_suggestions,
    )


@router.post("/route-summary/text", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_text_routes(
    payload: RouteSummaryTextRequest,
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    return await service.summarize_raw_text(
        raw_text=payload.raw_text,
        source_label=payload.source_label,
        include_supernet_suggestions=payload.include_supernet_suggestions,
    )


@router.post("/route-summary/upload", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_uploaded_file(
    file: UploadFile = File(...),
    include_supernet_suggestions: bool = Form(False),
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    raw_text = (await file.read()).decode("utf-8-sig", errors="replace")
    return await service.summarize_raw_text(
        raw_text=raw_text,
        source_label=file.filename or "Uploaded File",
        include_supernet_suggestions=include_supernet_suggestions,
    )


@router.post("/route-summary/demo-csv", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_demo_csv(
    include_supernet_suggestions: bool = False,
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    return await service.summarize_demo_csv(include_supernet_suggestions=include_supernet_suggestions)


# ---------------------------------------------------------------------------
# Devices Inventory
# ---------------------------------------------------------------------------
@router.get("/devices", response_model=list[DeviceRead], tags=["Devices"])
async def list_devices(
    repos: RepositoryBundle = Depends(get_repositories),
    service: DeviceService = Depends(_get_device_service),
) -> list[Any]:
    return await service.list_devices(repos)


@router.post(
    "/devices",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Devices"],
)
async def create_device(
    payload: DeviceCreate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: DeviceService = Depends(_get_device_service),
) -> Any:
    return await service.create_device(repos, payload)


# ---------------------------------------------------------------------------
# ServiceNow Simulator & Inbound Webhook
# ---------------------------------------------------------------------------
@router.get(
    "/mock-servicenow/changes",
    response_model=list[MockServiceNowChangeRead],
    tags=["ServiceNow Simulator"],
)
async def list_mock_servicenow_changes(
    repos: RepositoryBundle = Depends(get_repositories),
    service: SimulatorService = Depends(_get_simulator_service),
) -> list[Any]:
    return await service.list_changes(repos)


@router.post(
    "/mock-servicenow/changes",
    response_model=MockServiceNowChangeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["ServiceNow Simulator"],
)
async def create_mock_servicenow_change(
    payload: MockServiceNowChangeCreate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: SimulatorService = Depends(_get_simulator_service),
) -> Any:
    return await service.create_change(repos, payload)


@router.put(
    "/mock-servicenow/changes/{record_id}",
    response_model=MockServiceNowChangeRead,
    tags=["ServiceNow Simulator"],
)
async def update_mock_servicenow_change(
    record_id: int,
    payload: MockServiceNowChangeUpdate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: SimulatorService = Depends(_get_simulator_service),
) -> Any:
    return await service.update_change(repos, record_id, payload)


@router.post("/integrations/servicenow/webhook", tags=["ServiceNow Simulator"])
async def servicenow_webhook(
    repos: RepositoryBundle = Depends(get_repositories),
    service: SimulatorService = Depends(_get_simulator_service),
) -> dict[str, Any]:
    return await service.handle_webhook(repos)


# ---------------------------------------------------------------------------
# Settings & Scheduler Status
# ---------------------------------------------------------------------------
@router.get("/settings", response_model=AppSettingsRead, tags=["Settings"])
async def get_app_settings(
    repos: RepositoryBundle = Depends(get_repositories),
    service: SettingsService = Depends(_get_settings_service),
) -> AppSettingsRead:
    return await service.get_settings(repos)


@router.put("/settings", response_model=AppSettingsRead, tags=["Settings"])
async def update_app_settings(
    payload: AppSettingsUpdate,
    repos: RepositoryBundle = Depends(get_repositories),
    service: SettingsService = Depends(_get_settings_service),
) -> AppSettingsRead:
    return await service.update_settings(repos, payload)


@router.get("/scheduler/status", response_model=SchedulerStatusRead, tags=["Scheduler"])
async def get_scheduler_status(
    request: Request,
    repos: RepositoryBundle = Depends(get_repositories),
    service: SettingsService = Depends(_get_settings_service),
) -> SchedulerStatusRead:
    return await service.get_scheduler_status(repos, request.app.state.scheduler_manager)


@router.post("/scheduler/dispatch-now", tags=["Scheduler"])
async def dispatch_scheduler_now(request: Request) -> dict[str, Any]:
    sched = request.app.state.scheduler_manager
    synced_count = await sched.run_sync_tick()
    processed_ids = await sched.run_dispatch_tick()
    return {
        "synced_count": synced_count,
        "dispatched_change_ids": processed_ids,
    }
