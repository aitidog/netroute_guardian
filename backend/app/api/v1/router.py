"""FastAPI v1 REST endpoints for route change tracking, comparison, summarization, and simulation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.adapters.devices.parsers import auto_parse_routing_text, parse_edgeconnect_csv
from app.core.database import get_db
from app.models.entities import (
    AppSetting,
    ChangeDeviceLink,
    ChangeRequest,
    ComparisonReport,
    Device,
    ImportantRoute,
    MockServiceNowChange,
    utcnow,
)
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
    SnapshotSummaryRead,
    TriggerCaptureResult,
)
from app.services.change_service import ChangeWorkflowService, get_int_setting
from app.services.summary_service import RouteSummaryService

router = APIRouter()

_RISK_ORDER = {"PASS": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}


def _get_change_service(request: Request) -> ChangeWorkflowService:
    return request.app.state.change_service


def _get_summary_service(request: Request) -> RouteSummaryService:
    return request.app.state.summary_service


def _serialize_change(change: ChangeRequest, include_detail: bool = False) -> dict[str, Any]:
    devices = [
        DeviceRead.model_validate(link.device) for link in change.device_links if link.device is not None
    ]
    pre_snaps = [s for s in change.snapshots if s.phase == "pre_change"]
    post_snaps = [s for s in change.snapshots if s.phase == "post_change"]
    reports = sorted(change.reports, key=lambda r: r.created_at, reverse=True)

    highest_risk: str | None = None
    for rep in reports:
        if highest_risk is None or _RISK_ORDER.get(rep.risk_level, 0) > _RISK_ORDER.get(highest_risk, 0):
            highest_risk = rep.risk_level

    base = {
        "id": change.id,
        "chg_number": change.chg_number,
        "title": change.title,
        "description": change.description,
        "scheduled_start": change.scheduled_start,
        "scheduled_end": change.scheduled_end,
        "capture_scheduled_at": change.capture_scheduled_at,
        "engineer_name": change.engineer_name,
        "engineer_email": change.engineer_email,
        "status": change.status,
        "sync_source": change.sync_source,
        "retry_count": change.retry_count,
        "last_error": change.last_error,
        "synced_at": change.synced_at,
        "updated_at": change.updated_at,
        "devices": devices,
        "pre_snapshot_count": len(pre_snaps),
        "post_snapshot_count": len(post_snaps),
        "report_count": len(reports),
        "highest_risk_level": highest_risk,
    }
    if include_detail:
        base["snapshots"] = [
            SnapshotSummaryRead.model_validate(s)
            for s in sorted(change.snapshots, key=lambda x: x.captured_at, reverse=True)
        ]
        base["reports"] = [ComparisonReportDetailRead.model_validate(r) for r in reports]
    return base


# ---------------------------------------------------------------------------
# Feature 1: Change Requests & Workflow
# ---------------------------------------------------------------------------
@router.get("/changes", response_model=list[ChangeRequestRead], tags=["Changes"])
def list_changes(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    stmt = (
        select(ChangeRequest)
        .options(
            selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device),
            selectinload(ChangeRequest.snapshots),
            selectinload(ChangeRequest.reports),
        )
        .order_by(ChangeRequest.scheduled_start.asc())
    )
    changes = db.scalars(stmt).all()
    return [_serialize_change(c, include_detail=False) for c in changes]


@router.get("/changes/{change_id}", response_model=ChangeRequestDetailRead, tags=["Changes"])
def get_change(change_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = (
        select(ChangeRequest)
        .options(
            selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device),
            selectinload(ChangeRequest.snapshots),
            selectinload(ChangeRequest.reports),
        )
        .where(ChangeRequest.id == change_id)
    )
    change = db.scalar(stmt)
    if change is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return _serialize_change(change, include_detail=True)


@router.post("/changes/sync", tags=["Changes"])
async def sync_servicenow_changes(
    request: Request,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    synced = await service.sync_from_servicenow(db)
    request.app.state.scheduler_manager.last_sync_at = utcnow()
    return {"synced_count": len(synced), "chg_numbers": [c.chg_number for c in synced]}


@router.post(
    "/changes/{change_id}/trigger-pre-capture",
    response_model=TriggerCaptureResult,
    tags=["Changes"],
)
async def trigger_pre_capture(
    change_id: int,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    try:
        return await service.capture_pre_change(db, change_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/changes/{change_id}/trigger-post-capture",
    response_model=TriggerCaptureResult,
    tags=["Changes"],
)
async def trigger_post_capture(
    change_id: int,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    try:
        result = await service.capture_post_change_and_compare(db, change_id)
        result["reports_generated"] = [
            ComparisonReportSummaryRead.model_validate(r) for r in result["reports_generated"]
        ]
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Feature 1: Comparison Reports & Ad-hoc CSV Comparison
# ---------------------------------------------------------------------------
@router.get("/reports", response_model=list[ComparisonReportSummaryRead], tags=["Reports"])
def list_reports(db: Session = Depends(get_db)) -> list[ComparisonReport]:
    stmt = select(ComparisonReport).order_by(ComparisonReport.created_at.desc()).limit(50)
    return list(db.scalars(stmt).all())


@router.get("/reports/{report_id}", response_model=ComparisonReportDetailRead, tags=["Reports"])
def get_report(report_id: int, db: Session = Depends(get_db)) -> ComparisonReport:
    report = db.get(ComparisonReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Comparison report not found")
    return report


@router.get("/reports/{report_id}/email-preview", tags=["Reports"])
def preview_report_email(
    report_id: int,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, str]:
    report = db.get(ComparisonReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Comparison report not found")

    chg = db.get(ChangeRequest, report.change_id) if report.change_id else None
    subject, html_body = service.email_sender.render_html(
        chg_number=chg.chg_number if chg else f"ADHOC-{report.id}",
        change_title=chg.title if chg else f"Ad-hoc Comparison ({report.device_label})",
        engineer_name=chg.engineer_name if chg else "Network Engineer",
        recipient_email=report.email_recipient or (chg.engineer_email if chg else "engineer@netops.local"),
        reports=[report.report_payload],
    )
    return {"subject": subject, "html": html_body}


@router.post("/reports/{report_id}/resend-email", tags=["Reports"])
async def resend_report_email(
    report_id: int,
    recipient_email: str | None = None,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    report = db.get(ComparisonReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Comparison report not found")

    chg = db.get(ChangeRequest, report.change_id) if report.change_id else None
    target_email = recipient_email or report.email_recipient or (chg.engineer_email if chg else None)
    if not target_email:
        raise HTTPException(status_code=400, detail="No recipient email address specified")

    delivery = await service.email_sender.send_comparison_report(
        chg_number=chg.chg_number if chg else f"ADHOC-{report.id}",
        change_title=chg.title if chg else f"Ad-hoc Comparison ({report.device_label})",
        engineer_name=chg.engineer_name if chg else "Network Engineer",
        recipient_email=target_email,
        reports=[report.report_payload],
    )
    report.email_recipient = target_email
    report.email_status = delivery.status
    report.email_error = delivery.error
    report.email_sent_at = utcnow() if delivery.status == "sent" else report.email_sent_at
    db.commit()
    return {
        "report_id": report.id,
        "recipient_email": target_email,
        "status": delivery.status,
        "error": delivery.error,
    }


@router.post("/comparisons/adhoc", response_model=ComparisonReportDetailRead, tags=["Reports"])
async def adhoc_compare_files(
    before_file: UploadFile = File(...),
    after_file: UploadFile = File(...),
    device_label: str = Form("Uploaded Device"),
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> ComparisonReport:
    before_text = (await before_file.read()).decode("utf-8-sig", errors="replace")
    after_text = (await after_file.read()).decode("utf-8-sig", errors="replace")
    try:
        before_routes = auto_parse_routing_text(before_text, label=device_label)
        after_routes = auto_parse_routing_text(after_text, label=device_label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not before_routes or not after_routes:
        raise HTTPException(
            status_code=400,
            detail="Both before and after files must contain at least one valid CIDR route",
        )

    return await service.run_adhoc_comparison(
        db,
        device_label=device_label,
        before_routes=before_routes,
        after_routes=after_routes,
    )


@router.post("/comparisons/demo-csv", response_model=ComparisonReportDetailRead, tags=["Reports"])
async def compare_demo_csv(
    request: Request,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> ComparisonReport:
    sample_dir = Path(request.app.state.settings.sample_data_dir)
    before_path = sample_dir / "subnetsExample_beforeChange.csv"
    after_path = sample_dir / "subnetsExample_afterChange.csv"
    if not before_path.exists() or not after_path.exists():
        raise HTTPException(status_code=404, detail="Demo CSV files not found on server")

    before_routes = parse_edgeconnect_csv(before_path.read_text(encoding="utf-8-sig"))
    after_routes = parse_edgeconnect_csv(after_path.read_text(encoding="utf-8-sig"))
    return await service.run_adhoc_comparison(
        db,
        device_label="uec-abc-prd01 (Sample CSV)",
        before_routes=before_routes,
        after_routes=after_routes,
    )


# ---------------------------------------------------------------------------
# Feature 1: Important Pre-Specified Routes CRUD
# ---------------------------------------------------------------------------
@router.get("/important-routes", response_model=list[ImportantRouteRead], tags=["Important Routes"])
def list_important_routes(db: Session = Depends(get_db)) -> list[ImportantRoute]:
    return list(db.scalars(select(ImportantRoute).order_by(ImportantRoute.created_at.asc())).all())


@router.post(
    "/important-routes",
    response_model=ImportantRouteRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Important Routes"],
)
def create_important_route(
    payload: ImportantRouteCreate,
    db: Session = Depends(get_db),
) -> ImportantRoute:
    rec = ImportantRoute(
        prefix=payload.prefix,
        description=payload.description,
        enabled=payload.enabled,
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Important route '{payload.prefix}' already exists",
        ) from exc
    db.refresh(rec)
    return rec


@router.put(
    "/important-routes/{route_id}",
    response_model=ImportantRouteRead,
    tags=["Important Routes"],
)
def update_important_route(
    route_id: int,
    payload: ImportantRouteUpdate,
    db: Session = Depends(get_db),
) -> ImportantRoute:
    rec = db.get(ImportantRoute, route_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Important route not found")

    if payload.prefix is not None:
        rec.prefix = payload.prefix
    if payload.description is not None:
        rec.description = payload.description
    if payload.enabled is not None:
        rec.enabled = payload.enabled

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Important route '{payload.prefix}' already exists",
        ) from exc
    db.refresh(rec)
    return rec


@router.delete(
    "/important-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Important Routes"],
)
def delete_important_route(route_id: int, db: Session = Depends(get_db)) -> None:
    rec = db.get(ImportantRoute, route_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Important route not found")
    db.delete(rec)
    db.commit()


# ---------------------------------------------------------------------------
# Feature 2: Route Summary
# ---------------------------------------------------------------------------
@router.post("/route-summary/device", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_device_routes(
    payload: RouteSummaryDeviceRequest,
    db: Session = Depends(get_db),
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    try:
        return await service.summarize_by_device_query(
            db,
            query=payload.query,
            include_supernet_suggestions=payload.include_supernet_suggestions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/route-summary/text", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_text_routes(
    payload: RouteSummaryTextRequest,
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    try:
        return await service.summarize_raw_text(
            raw_text=payload.raw_text,
            source_label=payload.source_label,
            include_supernet_suggestions=payload.include_supernet_suggestions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/route-summary/upload", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_uploaded_file(
    file: UploadFile = File(...),
    include_supernet_suggestions: bool = Form(False),
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    raw_text = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        return await service.summarize_raw_text(
            raw_text=raw_text,
            source_label=file.filename or "Uploaded File",
            include_supernet_suggestions=include_supernet_suggestions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/route-summary/demo-csv", response_model=RouteSummaryResponse, tags=["Route Summary"])
async def summarize_demo_csv(
    request: Request,
    include_supernet_suggestions: bool = False,
    service: RouteSummaryService = Depends(_get_summary_service),
) -> dict[str, Any]:
    after_path = Path(request.app.state.settings.sample_data_dir) / "subnetsExample_afterChange.csv"
    if not after_path.exists():
        raise HTTPException(status_code=404, detail="Demo CSV file not found on server")
    return await service.summarize_raw_text(
        raw_text=after_path.read_text(encoding="utf-8-sig"),
        source_label="subnetsExample_afterChange.csv",
        include_supernet_suggestions=include_supernet_suggestions,
    )


# ---------------------------------------------------------------------------
# Devices Inventory
# ---------------------------------------------------------------------------
@router.get("/devices", response_model=list[DeviceRead], tags=["Devices"])
def list_devices(db: Session = Depends(get_db)) -> list[Device]:
    return list(db.scalars(select(Device).order_by(Device.hostname.asc())).all())


@router.post(
    "/devices",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Devices"],
)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> Device:
    dev = Device(**payload.model_dump())
    db.add(dev)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Device with the same hostname or IP address already exists",
        ) from exc
    db.refresh(dev)
    return dev


# ---------------------------------------------------------------------------
# ServiceNow Simulator & Inbound Webhook
# ---------------------------------------------------------------------------
@router.get(
    "/mock-servicenow/changes",
    response_model=list[MockServiceNowChangeRead],
    tags=["ServiceNow Simulator"],
)
def list_mock_servicenow_changes(db: Session = Depends(get_db)) -> list[MockServiceNowChange]:
    return list(
        db.scalars(select(MockServiceNowChange).order_by(MockServiceNowChange.scheduled_start.asc())).all()
    )


@router.post(
    "/mock-servicenow/changes",
    response_model=MockServiceNowChangeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["ServiceNow Simulator"],
)
async def create_mock_servicenow_change(
    payload: MockServiceNowChangeCreate,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> MockServiceNowChange:
    chg_number = payload.chg_number or f"CHG{int(datetime.now(UTC).timestamp()) % 10000000:07d}"
    rec = MockServiceNowChange(
        chg_number=chg_number,
        title=payload.title,
        description=payload.description,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        engineer_name=payload.engineer_name,
        engineer_email=str(payload.engineer_email),
        state=payload.state,
        ci_device_ids=payload.ci_device_ids,
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"ServiceNow change '{chg_number}' already exists"
        ) from exc
    db.refresh(rec)
    # Trigger immediate sync so the platform reflects the new ServiceNow ticket right away.
    await service.sync_from_servicenow(db)
    return rec


@router.put(
    "/mock-servicenow/changes/{record_id}",
    response_model=MockServiceNowChangeRead,
    tags=["ServiceNow Simulator"],
)
async def update_mock_servicenow_change(
    record_id: int,
    payload: MockServiceNowChangeUpdate,
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> MockServiceNowChange:
    rec = db.get(MockServiceNowChange, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Simulated ServiceNow change not found")

    for field_name, val in payload.model_dump(exclude_unset=True).items():
        setattr(rec, field_name, str(val) if field_name == "engineer_email" and val else val)
    db.commit()
    db.refresh(rec)
    await service.sync_from_servicenow(db)
    return rec


@router.post("/integrations/servicenow/webhook", tags=["ServiceNow Simulator"])
async def servicenow_webhook(
    db: Session = Depends(get_db),
    service: ChangeWorkflowService = Depends(_get_change_service),
) -> dict[str, Any]:
    synced = await service.sync_from_servicenow(db)
    return {"status": "accepted", "synced_count": len(synced)}


# ---------------------------------------------------------------------------
# Settings & Scheduler Status
# ---------------------------------------------------------------------------
@router.get("/settings", response_model=AppSettingsRead, tags=["Settings"])
def get_app_settings(request: Request, db: Session = Depends(get_db)) -> AppSettingsRead:
    cfg = request.app.state.settings
    return AppSettingsRead(
        servicenow_mode=cfg.servicenow_mode,
        servicenow_window_hours=get_int_setting(db, "servicenow_window_hours", cfg.servicenow_window_hours),
        pre_capture_lead_minutes=get_int_setting(
            db, "pre_capture_lead_minutes", cfg.pre_capture_lead_minutes
        ),
        large_prefix_threshold=get_int_setting(
            db, "large_prefix_threshold", cfg.default_large_prefix_threshold
        ),
        max_concurrent_device_collections=cfg.max_concurrent_device_collections,
        pipeline_executor_mode=cfg.pipeline_executor_mode,
        pipeline_max_workers=cfg.pipeline_max_workers,
        mailpit_web_url=cfg.mailpit_web_url,
    )


@router.put("/settings", response_model=AppSettingsRead, tags=["Settings"])
def update_app_settings(
    payload: AppSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> AppSettingsRead:
    for key, val in payload.model_dump(exclude_unset=True).items():
        if val is None:
            continue
        rec = db.get(AppSetting, key)
        if rec is None:
            db.add(AppSetting(key=key, value=str(val)))
        else:
            rec.value = str(val)
    db.commit()
    return get_app_settings(request, db)


@router.get("/scheduler/status", response_model=SchedulerStatusRead, tags=["Scheduler"])
def get_scheduler_status(request: Request, db: Session = Depends(get_db)) -> SchedulerStatusRead:
    sched = request.app.state.scheduler_manager
    total_changes = db.scalar(select(func.count(ChangeRequest.id))) or 0
    pending_count = (
        db.scalar(select(func.count(ChangeRequest.id)).where(ChangeRequest.status == "synced")) or 0
    )
    next_due = db.scalar(
        select(func.min(ChangeRequest.capture_scheduled_at)).where(ChangeRequest.status == "synced")
    )
    return SchedulerStatusRead(
        running=sched.running,
        servicenow_mode=request.app.state.settings.servicenow_mode,
        last_sync_at=sched.last_sync_at,
        last_dispatch_at=sched.last_dispatch_at,
        synced_changes_count=int(total_changes),
        pending_pre_captures=int(pending_count),
        next_due_capture_at=next_due,
        jobs=sched.describe_jobs(),
    )


@router.post("/scheduler/dispatch-now", tags=["Scheduler"])
async def dispatch_scheduler_now(request: Request) -> dict[str, Any]:
    sched = request.app.state.scheduler_manager
    synced_count = await sched.run_sync_tick()
    processed_ids = await sched.run_dispatch_tick()
    return {
        "synced_count": synced_count,
        "dispatched_change_ids": processed_ids,
    }
