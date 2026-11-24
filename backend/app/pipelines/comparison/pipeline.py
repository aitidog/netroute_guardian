"""Pipeline factory and top-level picklable entrypoint for ProcessPoolExecutor execution."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.pipelines.base import PipelineRunner
from app.pipelines.comparison.analyzers import (
    ImpactAssessmentAnalyzer,
    LpmFallbackAnalyzer,
    PathSelectionAnalyzer,
)
from app.pipelines.comparison.context import ComparisonContext, ComparisonInput
from app.pipelines.comparison.rules import LargePrefixRule, PreSpecifiedRouteRule
from app.pipelines.comparison.stages import (
    DiffStage,
    ImportanceClassifierStage,
    NetworkAnalysisStage,
    NormalizeStage,
    ReportAssemblyStage,
)


def build_comparison_pipeline(
    *,
    important_prefixes: list[str],
    large_prefix_threshold: int = 20,
) -> PipelineRunner[ComparisonContext]:
    """Assemble the default 5-stage single-responsibility comparison pipeline."""
    return PipelineRunner(
        stages=[
            NormalizeStage(),
            DiffStage(),
            ImportanceClassifierStage(
                rules=[
                    LargePrefixRule(max_prefix_len=large_prefix_threshold),
                    PreSpecifiedRouteRule(prefixes=important_prefixes),
                ]
            ),
            NetworkAnalysisStage(
                analyzers=[
                    LpmFallbackAnalyzer(),
                    PathSelectionAnalyzer(),
                    ImpactAssessmentAnalyzer(),
                ]
            ),
            ReportAssemblyStage(),
        ]
    )


def run_comparison_pipeline(input_data: ComparisonInput) -> dict[str, Any]:
    """Top-level pure picklable entrypoint safe for multiprocessing ProcessPoolExecutor."""
    runner = build_comparison_pipeline(
        important_prefixes=input_data.important_prefixes,
        large_prefix_threshold=input_data.large_prefix_threshold,
    )
    ctx = ComparisonContext(input_data=input_data)
    final_ctx, traces = runner.run(ctx)
    payload = dict(final_ctx.report_payload)
    payload["pipeline_stages"] = [asdict(t) for t in traces]
    return payload
