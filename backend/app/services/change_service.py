"""Core orchestration service for ServiceNow sync, concurrent capture, parallel diffing, and email."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.adapters.devices.base import NormalizedRoute
from app.adapters.devices.registry import ConcurrentDeviceCollector
from app.adapters.email.sender import EmailReportSender
from app.adapters.servicenow.base import ServiceNowProvider
from app.adapters.servicenow.mock_provider import MockServiceNowProvider
from app.adapters.servicenow.real_provider import RealServiceNowProvider
from app.core.concurrency import PipelineExecutor
from app.core.config import Settings
from app.models.entities import (
    AppSetting,
    ChangeDeviceLink,
    ChangeRequest,
    ComparisonReport,
    Device,
    ImportantRoute,
    RouteSnapshot,
    utcnow,
)
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def get_int_setting(db: Session, key: str, default: int) -> int:
    rec = db.get(AppSetting, key)
    if rec is None:
        return default
    try:
        return int(rec.value)
    except ValueError:
        return default


def build_servicenow_provider(db: Session, settings: Settings) -> ServiceNowProvider:
    if settings.servicenow_mode == "live":
        return RealServiceNowProvider(
            instance_url=settings.servicenow_instance_url,
            username=settings.servicenow_username,
            password=settings.servicenow_password,
        )
    return MockServiceNowProvider(db)


class ChangeWorkflowService:
    """Coordinates ServiceNow synchronization, concurrent device polling, and parallel diffing."""

    def __init__(
        self,
        *,
        settings: Settings,
        pipeline_executor: PipelineExecutor,
        email_sender: EmailReportSender | None = None,
        device_collector: ConcurrentDeviceCollector | None = None,
    ) -> None:
        self.settings = settings
        self.pipeline_executor = pipeline_executor
        self.email_sender = email_sender or EmailReportSender(settings)
        self.device_collector = device_collector or ConcurrentDeviceCollector(
            sample_data_dir=settings.sample_data_dir,
            max_concurrency=settings.max_concurrent_device_collections,
            timeout_seconds=settings.device_collection_timeout_seconds,
        )

    async def sync_from_servicenow(
        self,
        db: Session,
        provider: ServiceNowProvider | None = None,
    ) -> list[ChangeRequest]:
        """Poll ServiceNow for scheduled changes inside the configured window and upsert DB jobs."""
        active_provider = provider or build_servicenow_provider(db, self.settings)
        window_hours = get_int_setting(db, "servicenow_window_hours", self.settings.servicenow_window_hours)
        lead_minutes = get_int_setting(db, "pre_capture_lead_minutes", self.settings.pre_capture_lead_minutes)

        now = utcnow()
        window_start = now - timedelta(hours=2)
        window_end = now + timedelta(hours=window_hours)

        snow_changes = await active_provider.fetch_scheduled_changes(window_start, window_end)
        synced: list[ChangeRequest] = []

        for dto in snow_changes:
            start_utc = _ensure_utc(dto.scheduled_start)
            capture_at = start_utc - timedelta(minutes=lead_minutes)

            existing = db.scalar(
                select(ChangeRequest)
                .options(selectinload(ChangeRequest.device_links))
                .where(ChangeRequest.chg_number == dto.chg_number)
            )

            if existing is None:
                if dto.state == "cancelled":
                    continue
                change = ChangeRequest(
                    chg_number=dto.chg_number,
                    title=dto.title,
                    description=dto.description,
                    scheduled_start=start_utc,
                    scheduled_end=_ensure_utc(dto.scheduled_end) if dto.scheduled_end else None,
                    capture_scheduled_at=capture_at,
                    engineer_name=dto.engineer_name,
                    engineer_email=dto.engineer_email,
                    status="synced",
                    sync_source=active_provider.source_name,
                    synced_at=now,
                )
                db.add(change)
                db.flush()
            else:
                change = existing
                change.title = dto.title
                change.description = dto.description
                change.engineer_name = dto.engineer_name
                change.engineer_email = dto.engineer_email
                change.scheduled_end = _ensure_utc(dto.scheduled_end) if dto.scheduled_end else None
                change.synced_at = now

                if dto.state == "cancelled":
                    if change.status in ("synced", "failed"):
                        change.status = "cancelled"
                else:
                    # Reschedule T-1h capture whenever ServiceNow shifts start_date.
                    change.scheduled_start = start_utc
                    change.capture_scheduled_at = capture_at
                    if change.status == "cancelled":
                        change.status = "synced"

            # Resolve associated CIs by device ID or hostname
            resolved_ids = self._resolve_device_ids(db, dto.ci_device_ids, dto.ci_hostnames)
            if resolved_ids:
                current_ids = {link.device_id for link in change.device_links}
                if current_ids != set(resolved_ids):
                    change.device_links.clear()
                    db.flush()
                    for dev_id in resolved_ids:
                        db.add(ChangeDeviceLink(change_id=change.id, device_id=dev_id))

            synced.append(change)

        db.commit()
        return synced

    def _resolve_device_ids(
        self,
        db: Session,
        ci_device_ids: list[int],
        ci_hostnames: list[str],
    ) -> list[int]:
        ids: list[int] = []
        if ci_device_ids:
            found = db.scalars(select(Device.id).where(Device.id.in_(ci_device_ids))).all()
            ids.extend(found)
        if ci_hostnames:
            found_by_host = db.scalars(select(Device.id).where(Device.hostname.in_(ci_hostnames))).all()
            ids.extend(found_by_host)
        # Preserve order while deduplicating
        return list(dict.fromkeys(ids))

    async def capture_pre_change(self, db: Session, change_id: int) -> dict[str, Any]:
        """Collect pre-change routing tables concurrently across all CIs linked to a Change."""
        change = db.scalar(
            select(ChangeRequest)
            .options(selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device))
            .where(ChangeRequest.id == change_id)
        )
        if change is None:
            raise ValueError(f"Change request {change_id} not found")

        devices = [link.device for link in change.device_links if link.device is not None]
        if not devices:
            raise ValueError(f"Change request {change.chg_number} has no associated CI devices")

        change.status = "pre_capturing"
        change.last_error = None
        db.commit()

        outcome = await self.device_collector.collect_many(devices, phase="pre_change")

        for res in outcome.succeeded:
            snap = RouteSnapshot(
                device_id=res.device_id,
                change_id=change.id,
                device_label=res.hostname,
                phase="pre_change",
                source_type="collector",
                raw_entry_count=res.raw_entry_count,
                unique_prefix_count=res.unique_prefix_count,
                routes_json=[r.to_dict() for r in res.routes],
            )
            db.add(snap)

        if outcome.succeeded and not outcome.failed:
            change.status = "pre_captured"
            change.last_error = None
        elif outcome.succeeded and outcome.failed:
            change.status = "pre_captured"
            change.last_error = "Partial pre-capture failure: " + "; ".join(
                f"{f['hostname']} ({f['error']})" for f in outcome.failed
            )
        else:
            change.status = "failed"
            change.retry_count += 1
            change.last_error = "; ".join(f"{f['hostname']} ({f['error']})" for f in outcome.failed)

        db.commit()
        return {
            "change_id": change.id,
            "chg_number": change.chg_number,
            "phase": "pre_change",
            "succeeded_devices": [r.hostname for r in outcome.succeeded],
            "failed_devices": outcome.failed,
            "reports_generated": [],
            "email_status": None,
        }

    async def capture_post_change_and_compare(self, db: Session, change_id: int) -> dict[str, Any]:
        """Collect post-change routes concurrently, run parallel comparisons, and email the engineer."""
        change = db.scalar(
            select(ChangeRequest)
            .options(selectinload(ChangeRequest.device_links).selectinload(ChangeDeviceLink.device))
            .where(ChangeRequest.id == change_id)
        )
        if change is None:
            raise ValueError(f"Change request {change_id} not found")

        devices = [link.device for link in change.device_links if link.device is not None]
        if not devices:
            raise ValueError(f"Change request {change.chg_number} has no associated CI devices")

        # Locate latest pre-change snapshot per device
        pre_snaps_all = db.scalars(
            select(RouteSnapshot)
            .where(RouteSnapshot.change_id == change.id, RouteSnapshot.phase == "pre_change")
            .order_by(RouteSnapshot.captured_at.desc())
        ).all()
        pre_by_device: dict[int, RouteSnapshot] = {}
        for snap in pre_snaps_all:
            if snap.device_id is not None and snap.device_id not in pre_by_device:
                pre_by_device[snap.device_id] = snap

        if not pre_by_device:
            raise ValueError(
                f"No pre-change snapshots found for {change.chg_number}. "
                "Please wait for T-1h pre-capture or trigger pre-change capture first."
            )

        change.status = "post_capturing"
        db.commit()

        # Step 1: Concurrent I/O-bound device collection across all CIs
        outcome = await self.device_collector.collect_many(devices, phase="post_change")

        post_by_device: dict[int, RouteSnapshot] = {}
        for res in outcome.succeeded:
            snap = RouteSnapshot(
                device_id=res.device_id,
                change_id=change.id,
                device_label=res.hostname,
                phase="post_change",
                source_type="collector",
                raw_entry_count=res.raw_entry_count,
                unique_prefix_count=res.unique_prefix_count,
                routes_json=[r.to_dict() for r in res.routes],
            )
            db.add(snap)
            db.flush()
            if res.device_id is not None:
                post_by_device[res.device_id] = snap

        # Step 2: Parallel CPU-bound comparison pipelines via ProcessPoolExecutor / ThreadPoolExecutor
        important_prefixes = list(
            db.scalars(select(ImportantRoute.prefix).where(ImportantRoute.enabled.is_(True))).all()
        )
        large_threshold = get_int_setting(
            db, "large_prefix_threshold", self.settings.default_large_prefix_threshold
        )

        compare_pairs: list[tuple[Device, RouteSnapshot, RouteSnapshot]] = []
        pipeline_args: list[tuple[ComparisonInput]] = []
        for dev in devices:
            if dev.id in pre_by_device and dev.id in post_by_device:
                pre_snap = pre_by_device[dev.id]
                post_snap = post_by_device[dev.id]
                compare_pairs.append((dev, pre_snap, post_snap))
                pipeline_args.append(
                    (
                        ComparisonInput(
                            device_label=dev.hostname,
                            before_routes=pre_snap.routes_json,
                            after_routes=post_snap.routes_json,
                            important_prefixes=important_prefixes,
                            large_prefix_threshold=large_threshold,
                        ),
                    )
                )

        report_payloads = await self.pipeline_executor.run_batch(run_comparison_pipeline, pipeline_args)

        created_reports: list[ComparisonReport] = []
        for (dev, pre_snap, post_snap), payload in zip(compare_pairs, report_payloads, strict=True):
            rep = ComparisonReport(
                change_id=change.id,
                device_id=dev.id,
                device_label=dev.hostname,
                before_snapshot_id=pre_snap.id,
                after_snapshot_id=post_snap.id,
                risk_level=payload["risk_level"],
                summary_stats=payload["summary_stats"],
                report_payload=payload,
                email_recipient=change.engineer_email,
                email_status="pending",
            )
            db.add(rep)
            db.flush()
            created_reports.append(rep)

        # Step 3: Deliver consolidated HTML report email to the engineer's mailbox
        email_status = "skipped"
        if created_reports:
            delivery = await self.email_sender.send_comparison_report(
                chg_number=change.chg_number,
                change_title=change.title,
                engineer_name=change.engineer_name,
                recipient_email=change.engineer_email,
                reports=[r.report_payload for r in created_reports],
            )
            email_status = delivery.status
            sent_ts = utcnow() if delivery.status == "sent" else None
            for rep in created_reports:
                rep.email_status = delivery.status
                rep.email_error = delivery.error
                rep.email_sent_at = sent_ts

        change.status = "completed" if created_reports else "failed"
        if outcome.failed:
            change.last_error = "Post-capture device error(s): " + "; ".join(
                f"{f['hostname']} ({f['error']})" for f in outcome.failed
            )
        else:
            change.last_error = None
        db.commit()

        return {
            "change_id": change.id,
            "chg_number": change.chg_number,
            "phase": "post_change",
            "succeeded_devices": [r.hostname for r in outcome.succeeded],
            "failed_devices": outcome.failed,
            "reports_generated": created_reports,
            "email_status": email_status,
        }

    async def run_adhoc_comparison(
        self,
        db: Session,
        *,
        device_label: str,
        before_routes: list[NormalizedRoute],
        after_routes: list[NormalizedRoute],
    ) -> ComparisonReport:
        """Persist two ad-hoc snapshots and run the comparison pipeline off the event loop."""
        before_dicts = [r.to_dict() for r in before_routes]
        after_dicts = [r.to_dict() for r in after_routes]

        before_snap = RouteSnapshot(
            device_label=device_label,
            phase="adhoc",
            source_type="csv_upload",
            raw_entry_count=len(before_dicts),
            unique_prefix_count=len({(r["vrf"], r["prefix"]) for r in before_dicts}),
            routes_json=before_dicts,
        )
        after_snap = RouteSnapshot(
            device_label=device_label,
            phase="adhoc",
            source_type="csv_upload",
            raw_entry_count=len(after_dicts),
            unique_prefix_count=len({(r["vrf"], r["prefix"]) for r in after_dicts}),
            routes_json=after_dicts,
        )
        db.add_all([before_snap, after_snap])
        db.flush()

        important_prefixes = list(
            db.scalars(select(ImportantRoute.prefix).where(ImportantRoute.enabled.is_(True))).all()
        )
        large_threshold = get_int_setting(
            db, "large_prefix_threshold", self.settings.default_large_prefix_threshold
        )

        payload = await self.pipeline_executor.run(
            run_comparison_pipeline,
            ComparisonInput(
                device_label=device_label,
                before_routes=before_dicts,
                after_routes=after_dicts,
                important_prefixes=important_prefixes,
                large_prefix_threshold=large_threshold,
            ),
        )

        report = ComparisonReport(
            device_label=device_label,
            before_snapshot_id=before_snap.id,
            after_snapshot_id=after_snap.id,
            risk_level=payload["risk_level"],
            summary_stats=payload["summary_stats"],
            report_payload=payload,
            email_status="skipped",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def claim_due_pre_capture_ids(self, db: Session, now: datetime | None = None) -> list[int]:
        """Atomically claim Change Requests whose T-1h pre-capture window has arrived.

        Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` on PostgreSQL so multiple backend
        replicas cannot claim the same change simultaneously.
        """
        cutoff = _ensure_utc(now or utcnow())
        stmt = (
            select(ChangeRequest)
            .where(
                ChangeRequest.status == "synced",
                ChangeRequest.capture_scheduled_at <= cutoff,
            )
            .order_by(ChangeRequest.capture_scheduled_at.asc())
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        due_changes = list(db.scalars(stmt).all())
        claimed_ids: list[int] = []
        for chg in due_changes:
            chg.status = "pre_capturing"
            claimed_ids.append(chg.id)
        db.commit()
        return claimed_ids
