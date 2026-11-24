"""Reusable, composable Pipeline framework with per-stage execution telemetry."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar

Ctx = TypeVar("Ctx")


@dataclass
class StageTrace:
    """Execution telemetry recorded for each stage in a pipeline run."""

    name: str
    description: str
    duration_ms: float
    details: dict = field(default_factory=dict)


class PipelineStage(ABC, Generic[Ctx]):
    """Abstract single-responsibility processing stage operating on a shared context."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short unique identifier for this stage."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable summary of this stage's single responsibility."""

    @abstractmethod
    def execute(self, ctx: Ctx) -> dict | None:
        """Transform or enrich ``ctx`` in place and optionally return trace details."""


class PipelineRunner(Generic[Ctx]):
    """Executes an ordered sequence of ``PipelineStage`` objects and records stage traces."""

    def __init__(self, stages: list[PipelineStage[Ctx]]) -> None:
        self._stages = list(stages)

    @property
    def stages(self) -> list[PipelineStage[Ctx]]:
        return list(self._stages)

    def run(self, ctx: Ctx) -> tuple[Ctx, list[StageTrace]]:
        traces: list[StageTrace] = []
        for stage in self._stages:
            t0 = time.perf_counter()
            details = stage.execute(ctx) or {}
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            traces.append(
                StageTrace(
                    name=stage.name,
                    description=stage.description,
                    duration_ms=elapsed_ms,
                    details=details,
                )
            )
        return ctx, traces
