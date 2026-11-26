"""Feature 2 service: device lookup via repository and route summarization pipeline execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.devices.parsers import auto_parse_routing_text
from app.adapters.devices.registry import build_device_collector
from app.core.concurrency import PipelineExecutor
from app.core.config import Settings
from app.core.exceptions import DomainValidationError, ResourceNotFoundError
from app.pipelines.summary.context import SummaryInput
from app.pipelines.summary.pipeline import run_summary_pipeline
from app.repositories.bundle import RepositoryBundle


class RouteSummaryService:
    """Executes Feature 2 route summarization from live/mock devices or uploaded files."""

    def __init__(self, *, settings: Settings, pipeline_executor: PipelineExecutor) -> None:
        self.settings = settings
        self.pipeline_executor = pipeline_executor

    async def summarize_by_device_query(
        self,
        repos: RepositoryBundle,
        *,
        query: str,
        include_supernet_suggestions: bool = False,
    ) -> dict[str, Any]:
        """Resolve a device by IP address or hostname via repository, fetch routes, and summarize."""
        cleaned = query.strip()
        device = await repos.devices.get_by_hostname_or_ip(cleaned)
        if device is None:
            raise ResourceNotFoundError(
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
        try:
            routes = auto_parse_routing_text(raw_text, label=source_label)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        if not routes:
            raise DomainValidationError("No valid CIDR routes could be parsed from the provided input")

        return await self.pipeline_executor.run(
            run_summary_pipeline,
            SummaryInput(
                source_label=source_label,
                routes=[r.to_dict() for r in routes],
                include_supernet_suggestions=include_supernet_suggestions,
            ),
        )

    async def summarize_demo_csv(
        self,
        *,
        include_supernet_suggestions: bool = False,
    ) -> dict[str, Any]:
        """Run Feature 2 summarization against the configured sample after-change CSV."""
        after_path = Path(self.settings.sample_data_dir) / "subnetsExample_afterChange.csv"
        if not after_path.exists():
            raise ResourceNotFoundError("Demo CSV file not found on server")
        return await self.summarize_raw_text(
            raw_text=after_path.read_text(encoding="utf-8-sig"),
            source_label="subnetsExample_afterChange.csv",
            include_supernet_suggestions=include_supernet_suggestions,
        )
