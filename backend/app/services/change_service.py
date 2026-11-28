"""Service layer for ServiceNow sync, concurrent capture, parallel diffing, reports, and email."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.adapters.devices.base import NormalizedRoute
from app.adapters.devices.parsers import auto_parse_routing_text, parse_edgeconnect_csv
from app.adapters.devices.registry import ConcurrentDeviceCollector
from app.adapters.email.csv_exporter import format_comparison_reports_csv, sanitize_filename_token
from app.adapters.email.sender import EmailReportSender
from app.adapters.servicenow.base import ServiceNowProvider
from app.adapters.servicenow.mock_provider import MockServiceNowProvider
from app.adapters.servicenow.real_provider import RealServiceNowProvider
from app.core.concurrency import PipelineExecutor
from app.core.config import Settings
from app.core.exceptions import DomainValidationError, ResourceNotFoundError
from app.models.entities import ChangeRequest, ComparisonReport, utcnow
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline
from app.repositories.bundle import RepositoryBundle
from app.schemas.dto import (
    ComparisonReportDetailRead,
    ComparisonReportSummaryRead,
    DeviceRead,
    SnapshotSummaryRead,
)

logger = logging.getLogger(__name__)

_RISK_ORDER = {"PASS": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_servicenow_provider(repos: RepositoryBundle, settings: Settings) -> ServiceNowProvider:
    if settings.servicenow_mode == "live":
        return RealServiceNowProvider(
            instance_url=settings.servicenow_instance_url,
            username=settings.servicenow_username,
            password=settings.servicenow_password,
        )
    return MockServiceNowProvider(repos.mock_servicenow)


def serialize_change(change: ChangeRequest, *, include_detail: bool = False) -> dict[str, Any]:
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

    base: dict[str, Any] = {
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


class ChangeWorkflowService:
    """Coordinates ServiceNow synchronization, concurrent device polling, and parallel diffing.

    All persistence is strictly delegated to ``RepositoryBundle`` with zero direct DB calls.
    """

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

    async def list_changes(self, repos: RepositoryBundle) -> list[dict[str, Any]]:
        changes = await repos.changes.list_with_relations()
        return [serialize_change(c, include_detail=False) for c in changes]

    async def get_change_detail(self, repos: RepositoryBundle, change_id: int) -> dict[str, Any]:
        change = await repos.changes.get_with_relations(change_id)
        if change is None:
            raise ResourceNotFoundError("Change request not found")
        return serialize_change(change, include_detail=True)

    async def delete_change(self, repos: RepositoryBundle, change_id: int) -> None:
        """Delete a completed change request along with its linked reports and snapshots."""
        change = await repos.changes.get_by_id(change_id)
        if change is None:
            raise ResourceNotFoundError("Change request not found")
        if change.status != "completed":
            raise DomainValidationError(
                f"Only completed change requests can be deleted (current status: '{change.status}')"
            )

        # Delete reports before snapshots to satisfy snapshot foreign keys, then remove the change.
        await repos.reports.delete_by_change_id(change.id)
        await repos.snapshots.delete_by_change_id(change.id)
        if change.sync_source == "mock":
            await repos.mock_servicenow.mark_closed_by_chg_number(change.chg_number)
        await repos.changes.delete(change, commit=False)
        await repos.commit()

    async def sync_from_servicenow(
        self,
        repos: RepositoryBundle,
        provider: ServiceNowProvider | None = None,
    ) -> list[ChangeRequest]:
        """Poll ServiceNow for scheduled changes inside the configured window and upsert DB jobs."""
        active_provider = provider or build_servicenow_provider(repos, self.settings)
        window_hours = await repos.settings.get_int(
            "servicenow_window_hours", self.settings.servicenow_window_hours
        )
        lead_minutes = await repos.settings.get_int(
            "pre_capture_lead_minutes", self.settings.pre_capture_lead_minutes
        )

        now = utcnow()
        window_start = now - timedelta(hours=2)
        window_end = now + timedelta(hours=window_hours)

        snow_changes = await active_provider.fetch_scheduled_changes(window_start, window_end)
        synced: list[ChangeRequest] = []

        for dto in snow_changes:
            start_utc = _ensure_utc(dto.scheduled_start)
            capture_at = start_utc - timedelta(minutes=lead_minutes)
            existing = await repos.changes.get_by_chg_number_with_links(dto.chg_number)

            if existing is None:
                if dto.state in ("cancelled", "closed"):
                    continue
                change = await repos.changes.create(
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
                    change.scheduled_start = start_utc
                    change.capture_scheduled_at = capture_at
                    if change.status == "cancelled":
                        change.status = "synced"

            resolved_ids = await self._resolve_device_ids(repos, dto.ci_device_ids, dto.ci_hostnames)
            if resolved_ids:
                await repos.changes.replace_device_links(change, resolved_ids)

            synced.append(change)

        await repos.commit()
        return synced

    async def _resolve_device_ids(
        self,
        repos: RepositoryBundle,
        ci_device_ids: list[int],
        ci_hostnames: list[str],
    ) -> list[int]:
        ids: list[int] = []
        if ci_device_ids:
            ids.extend(await repos.devices.find_ids_by_ids(ci_device_ids))
        if ci_hostnames:
            ids.extend(await repos.devices.find_ids_by_hostnames(ci_hostnames))
        return list(dict.fromkeys(ids))

    async def capture_pre_change(self, repos: RepositoryBundle, change_id: int) -> dict[str, Any]:
        """Collect pre-change routing tables concurrently across all CIs linked to a Change."""
        change = await repos.changes.get_with_devices(change_id)
        if change is None:
            raise DomainValidationError(f"Change request {change_id} not found")

        devices = [link.device for link in change.device_links if link.device is not None]
        if not devices:
            raise DomainValidationError(f"Change request {change.chg_number} has no associated CI devices")

        await repos.changes.save_status(change, status="pre_capturing", last_error=None)

        outcome = await self.device_collector.collect_many(devices, phase="pre_change")

        for res in outcome.succeeded:
            await repos.snapshots.create(
                device_id=res.device_id,
                change_id=change.id,
                device_label=res.hostname,
                phase="pre_change",
                source_type="collector",
                raw_entry_count=res.raw_entry_count,
                unique_prefix_count=res.unique_prefix_count,
                routes_json=[r.to_dict() for r in res.routes],
            )

        if outcome.succeeded and not outcome.failed:
            await repos.changes.save_status(change, status="pre_captured", last_error=None)
        elif outcome.succeeded and outcome.failed:
            err = "Partial pre-capture failure: " + "; ".join(
                f"{f['hostname']} ({f['error']})" for f in outcome.failed
            )
            await repos.changes.save_status(change, status="pre_captured", last_error=err)
        else:
            err = "; ".join(f"{f['hostname']} ({f['error']})" for f in outcome.failed)
            await repos.changes.save_status(change, status="failed", last_error=err, increment_retry=True)

        return {
            "change_id": change.id,
            "chg_number": change.chg_number,
            "phase": "pre_change",
            "succeeded_devices": [r.hostname for r in outcome.succeeded],
            "failed_devices": outcome.failed,
            "reports_generated": [],
            "email_status": None,
        }

    async def capture_post_change_and_compare(
        self, repos: RepositoryBundle, change_id: int
    ) -> dict[str, Any]:
        """Collect post-change routes concurrently, run parallel comparisons, and email engineer."""
        change = await repos.changes.get_with_devices(change_id)
        if change is None:
            raise DomainValidationError(f"Change request {change_id} not found")

        devices = [link.device for link in change.device_links if link.device is not None]
        if not devices:
            raise DomainValidationError(f"Change request {change.chg_number} has no associated CI devices")

        pre_by_device = await repos.snapshots.get_latest_by_device_for_change(change.id, phase="pre_change")
        if not pre_by_device:
            raise DomainValidationError(
                f"No pre-change snapshots found for {change.chg_number}. "
                "Please wait for T-1h pre-capture or trigger pre-change capture first."
            )

        await repos.changes.save_status(change, status="post_capturing", last_error=change.last_error)

        outcome = await self.device_collector.collect_many(devices, phase="post_change")

        post_by_device = {}
        for res in outcome.succeeded:
            snap = await repos.snapshots.create(
                device_id=res.device_id,
                change_id=change.id,
                device_label=res.hostname,
                phase="post_change",
                source_type="collector",
                raw_entry_count=res.raw_entry_count,
                unique_prefix_count=res.unique_prefix_count,
                routes_json=[r.to_dict() for r in res.routes],
            )
            if res.device_id is not None:
                post_by_device[res.device_id] = snap

        important_prefixes = await repos.important_routes.list_enabled_prefixes()
        large_threshold = await repos.settings.get_int(
            "large_prefix_threshold", self.settings.default_large_prefix_threshold
        )

        compare_pairs = []
        pipeline_args = []
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
            rep = await repos.reports.create(
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
            created_reports.append(rep)

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
            await repos.reports.update_email_delivery(
                created_reports,
                status=delivery.status,
                error=delivery.error,
                sent_at=utcnow() if delivery.status == "sent" else None,
                commit=False,
            )

        err_msg = (
            "Post-capture device error(s): "
            + "; ".join(f"{f['hostname']} ({f['error']})" for f in outcome.failed)
            if outcome.failed
            else None
        )
        await repos.changes.save_status(
            change,
            status="completed" if created_reports else "failed",
            last_error=err_msg,
        )

        return {
            "change_id": change.id,
            "chg_number": change.chg_number,
            "phase": "post_change",
            "succeeded_devices": [r.hostname for r in outcome.succeeded],
            "failed_devices": outcome.failed,
            "reports_generated": [ComparisonReportSummaryRead.model_validate(r) for r in created_reports],
            "email_status": email_status,
        }

    async def list_reports(self, repos: RepositoryBundle) -> list[ComparisonReport]:
        return await repos.reports.list_recent(limit=50)

    async def get_report(self, repos: RepositoryBundle, report_id: int) -> ComparisonReport:
        report = await repos.reports.get_by_id(report_id)
        if report is None:
            raise ResourceNotFoundError("Comparison report not found")
        return report

    async def export_report_csv(self, repos: RepositoryBundle, report_id: int) -> tuple[str, bytes]:
        report = await self.get_report(repos, report_id)
        csv_text = format_comparison_reports_csv([report.report_payload])
        filename = f"route-comparison-{sanitize_filename_token(report.device_label)}-{report.id}.csv"
        return filename, ("\ufeff" + csv_text).encode("utf-8")

    async def preview_report_email(self, repos: RepositoryBundle, report_id: int) -> dict[str, str]:
        report = await self.get_report(repos, report_id)
        chg = await repos.changes.get_by_id(report.change_id) if report.change_id else None
        subject, html_body = self.email_sender.render_html(
            chg_number=chg.chg_number if chg else f"ADHOC-{report.id}",
            change_title=chg.title if chg else f"Ad-hoc Comparison ({report.device_label})",
            engineer_name=chg.engineer_name if chg else "Network Engineer",
            recipient_email=report.email_recipient
            or (chg.engineer_email if chg else "engineer@netops.local"),
            reports=[report.report_payload],
        )
        return {"subject": subject, "html": html_body}

    async def resend_report_email(
        self,
        repos: RepositoryBundle,
        report_id: int,
        *,
        recipient_email: str | None = None,
    ) -> dict[str, Any]:
        report = await self.get_report(repos, report_id)
        chg = await repos.changes.get_by_id(report.change_id) if report.change_id else None
        target_email = recipient_email or report.email_recipient or (chg.engineer_email if chg else None)
        if not target_email:
            raise DomainValidationError("No recipient email address specified")

        delivery = await self.email_sender.send_comparison_report(
            chg_number=chg.chg_number if chg else f"ADHOC-{report.id}",
            change_title=chg.title if chg else f"Ad-hoc Comparison ({report.device_label})",
            engineer_name=chg.engineer_name if chg else "Network Engineer",
            recipient_email=target_email,
            reports=[report.report_payload],
        )
        await repos.reports.update_email_delivery(
            [report],
            recipient=target_email,
            status=delivery.status,
            error=delivery.error,
            sent_at=utcnow() if delivery.status == "sent" else None,
            commit=True,
        )
        return {
            "report_id": report.id,
            "recipient_email": target_email,
            "status": delivery.status,
            "error": delivery.error,
        }

    async def compare_uploaded_texts(
        self,
        repos: RepositoryBundle,
        *,
        before_text: str,
        after_text: str,
        device_label: str,
    ) -> ComparisonReport:
        try:
            before_routes = auto_parse_routing_text(before_text, label=device_label)
            after_routes = auto_parse_routing_text(after_text, label=device_label)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        if not before_routes or not after_routes:
            raise DomainValidationError(
                "Both before and after files must contain at least one valid CIDR route"
            )
        return await self.run_adhoc_comparison(
            repos,
            device_label=device_label,
            before_routes=before_routes,
            after_routes=after_routes,
        )

    async def compare_demo_csv(self, repos: RepositoryBundle) -> ComparisonReport:
        sample_dir = Path(self.settings.sample_data_dir)
        before_path = sample_dir / "subnetsExample_beforeChange.csv"
        after_path = sample_dir / "subnetsExample_afterChange.csv"
        if not before_path.exists() or not after_path.exists():
            raise ResourceNotFoundError("Demo CSV files not found on server")

        before_routes = parse_edgeconnect_csv(before_path.read_text(encoding="utf-8-sig"))
        after_routes = parse_edgeconnect_csv(after_path.read_text(encoding="utf-8-sig"))
        return await self.run_adhoc_comparison(
            repos,
            device_label="uec-abc-prd01 (Sample CSV)",
            before_routes=before_routes,
            after_routes=after_routes,
        )

    async def run_adhoc_comparison(
        self,
        repos: RepositoryBundle,
        *,
        device_label: str,
        before_routes: list[NormalizedRoute],
        after_routes: list[NormalizedRoute],
    ) -> ComparisonReport:
        """Persist two ad-hoc snapshots and run the comparison pipeline off the event loop."""
        before_dicts = [r.to_dict() for r in before_routes]
        after_dicts = [r.to_dict() for r in after_routes]

        before_snap = await repos.snapshots.create(
            device_id=None,
            change_id=None,
            device_label=device_label,
            phase="adhoc",
            source_type="csv_upload",
            raw_entry_count=len(before_dicts),
            unique_prefix_count=len({(r["vrf"], r["prefix"]) for r in before_dicts}),
            routes_json=before_dicts,
        )
        after_snap = await repos.snapshots.create(
            device_id=None,
            change_id=None,
            device_label=device_label,
            phase="adhoc",
            source_type="csv_upload",
            raw_entry_count=len(after_dicts),
            unique_prefix_count=len({(r["vrf"], r["prefix"]) for r in after_dicts}),
            routes_json=after_dicts,
        )

        important_prefixes = await repos.important_routes.list_enabled_prefixes()
        large_threshold = await repos.settings.get_int(
            "large_prefix_threshold", self.settings.default_large_prefix_threshold
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

        return await repos.reports.create(
            device_label=device_label,
            before_snapshot_id=before_snap.id,
            after_snapshot_id=after_snap.id,
            risk_level=payload["risk_level"],
            summary_stats=payload["summary_stats"],
            report_payload=payload,
            email_status="skipped",
            commit=True,
        )

    async def claim_due_pre_capture_ids(
        self,
        repos: RepositoryBundle,
        now: datetime | None = None,
    ) -> list[int]:
        cutoff = _ensure_utc(now or utcnow())
        return await repos.changes.claim_due_pre_capture_ids(cutoff)
