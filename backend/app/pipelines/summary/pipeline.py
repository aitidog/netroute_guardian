"""Pipeline factory and top-level picklable entrypoint for Route Summarization."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.pipelines.base import PipelineRunner
from app.pipelines.summary.context import SummaryContext, SummaryInput
from app.pipelines.summary.stages import (
    FilterNormalizeStage,
    PrefixCollapseStage,
    SummaryFormatStage,
    SupernetSuggestionStage,
)


def build_summary_pipeline() -> PipelineRunner[SummaryContext]:
    """Assemble the 4-stage single-responsibility route summarization pipeline."""
    return PipelineRunner(
        stages=[
            FilterNormalizeStage(),
            PrefixCollapseStage(),
            SupernetSuggestionStage(),
            SummaryFormatStage(),
        ]
    )


def run_summary_pipeline(input_data: SummaryInput) -> dict[str, Any]:
    """Top-level pure picklable entrypoint safe for ProcessPoolExecutor execution."""
    runner = build_summary_pipeline()
    ctx = SummaryContext(input_data=input_data)
    final_ctx, traces = runner.run(ctx)
    payload = dict(final_ctx.result_payload)
    payload["pipeline_stages"] = [asdict(t) for t in traces]
    return payload
