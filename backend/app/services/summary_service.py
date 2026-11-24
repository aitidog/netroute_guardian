"""Feature 2 service: device lookup by IP/hostname and route summarization pipeline execution."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.devices.parsers import auto_parse_routing_text
from app.adapters.devices.registry import build_device_collector
from app.core.concurrency import PipelineExecutor
from app.core.config import Settings
from app.models.entities import Device
from app.pipelines.summary.context import SummaryInput
from app.pipelines.summary.pipeline import run_summary_pipeline


class RouteSummaryService:
    """Executes Feature 2 route summarization from live/mock devices or uploaded files."""

    def __init__(self, *, settings: Settings, pipeline_executor: PipelineExecutor) -> None:
        self.settings = settings
        self.pipeline_executor = pipeline_executor

    async def summarize_by_device_query(
        self,
        db: Session,
        *,
        query: str,
        include_supernet_suggestions: bool = False,
    ) -> dict[str, Any]:
        """Resolve a device by IP address or hostname, fetch its routing table, and summarize."""
        cleaned = query.strip()
        device = db.scalar(
            select(Device).where(
                or_(
                    func.lower(Device.hostname) == cleaned.lower(),
                    Device.ip_address == cleaned,
                )
            )
        )
        if device is None:
            raise ValueError(
                f"Device '{cleaned}' not found in inventory (searched by hostname and IP address)"
            )

        collector = build_device_collector(device, self.settings.sample_data_dir)
        fetched = await collector.collect_routes(phase="adhoc")

        return await self.pipeline_executor.run(
            run_summary_pipeline,
            SummaryInput(
                source_label=device.hostname,
                device_type=device.device_type,
                device_ip=device.ip_address,
                routes=[r.to_dict() for r in fetched.routes],
                include_supernet_suggestions=include_supernet_suggestions,
            ),
        )

    async def summarize_raw_text(
        self,
        *,
        raw_text: str,
        source_label: str = "Uploaded Routing Table",
        include_supernet_suggestions: bool = False,
    ) -> dict[str, Any]:
        """Parse uploaded CSV / Cisco CLI / plain CIDR text and run the summarization pipeline."""
        routes = auto_parse_routing_text(raw_text, label=source_label)
        if not routes:
            raise ValueError("No valid CIDR routes could be parsed from the provided input")

        return await self.pipeline_executor.run(
            run_summary_pipeline,
            SummaryInput(
                source_label=source_label,
                routes=[r.to_dict() for r in routes],
                include_supernet_suggestions=include_supernet_suggestions,
            ),
        )
