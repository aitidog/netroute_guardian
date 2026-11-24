"""Concurrency tests verifying bounded device polling and multi-process pipeline execution."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.adapters.devices.base import DeviceCollector, DeviceFetchResult, NormalizedRoute
from app.adapters.devices.registry import ConcurrentDeviceCollector
from app.core.concurrency import PipelineExecutor, gather_with_concurrency
from app.models.entities import Device
from app.pipelines.comparison.context import ComparisonInput
from app.pipelines.comparison.pipeline import run_comparison_pipeline
from app.pipelines.summary.context import SummaryInput
from app.pipelines.summary.pipeline import run_summary_pipeline


class _SlowTrackingCollector(DeviceCollector):
    """Fake device collector that tracks peak concurrency and optionally fails or times out."""

    def __init__(
        self,
        device: Device,
        *,
        delay: float,
        tracker: dict[str, int],
        should_fail: bool = False,
    ) -> None:
        self.device = device
        self.delay = delay
        self.tracker = tracker
        self.should_fail = should_fail

    async def collect_routes(self, phase="adhoc") -> DeviceFetchResult:
        self.tracker["active"] += 1
        self.tracker["peak"] = max(self.tracker["peak"], self.tracker["active"])
        try:
            await asyncio.sleep(self.delay)
            if self.should_fail:
                raise ConnectionError(f"Simulated SSH unreachable on {self.device.hostname}")
            return DeviceFetchResult(
                device_id=self.device.id,
                hostname=self.device.hostname,
                ip_address=self.device.ip_address,
                device_type=self.device.device_type,
                routes=[NormalizedRoute(prefix="10.0.0.0/24")],
                raw_entry_count=1,
                unique_prefix_count=1,
            )
        finally:
            self.tracker["active"] -= 1


@pytest.mark.asyncio
async def test_concurrent_device_collection_enforces_semaphore_and_isolates_failures():
    devices = [
        Device(
            id=i,
            hostname=f"dev-{i:02d}",
            ip_address=f"10.10.0.{i}",
            device_type="cisco_nexus",
        )
        for i in range(1, 9)
    ]
    tracker = {"active": 0, "peak": 0}

    def factory(dev: Device, _sample_dir: str) -> DeviceCollector:
        # dev-03 fails; dev-06 hangs past the timeout; others succeed quickly
        if dev.id == 3:
            return _SlowTrackingCollector(dev, delay=0.05, tracker=tracker, should_fail=True)
        if dev.id == 6:
            return _SlowTrackingCollector(dev, delay=1.0, tracker=tracker)
        return _SlowTrackingCollector(dev, delay=0.05, tracker=tracker)

    collector = ConcurrentDeviceCollector(
        sample_data_dir="",
        max_concurrency=3,
        timeout_seconds=0.25,
    )

    t0 = time.perf_counter()
    outcome = await collector.collect_many(devices, phase="pre_change", collector_factory=factory)
    elapsed = time.perf_counter() - t0

    assert tracker["peak"] <= 3
    assert tracker["peak"] >= 2  # proved genuine concurrency
    assert elapsed < 0.7  # bounded parallelism ran much faster than sequential
    assert len(outcome.succeeded) == 6
    assert len(outcome.failed) == 2
    failed_hosts = {f["hostname"] for f in outcome.failed}
    assert failed_hosts == {"dev-03", "dev-06"}


@pytest.mark.asyncio
async def test_gather_with_concurrency_caps_inflight_tasks():
    active = 0
    peak = 0

    async def work(idx: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.03)
        active -= 1
        return idx * 2

    results = await gather_with_concurrency(2, [work(i) for i in range(6)])
    assert results == [0, 2, 4, 6, 8, 10]
    assert peak == 2


@pytest.mark.asyncio
async def test_pipeline_executor_process_pool_parallel_batch():
    """Verify pipelines are 100% picklable and execute cleanly in real ProcessPoolExecutor workers."""
    executor = PipelineExecutor(mode="process", max_workers=2)
    executor.start()
    try:
        items = [
            (
                ComparisonInput(
                    device_label=f"parallel-dev-{i}",
                    before_routes=[
                        {"prefix": f"10.{i}.0.0/16", "vrf": "default", "metric": 50, "admin_distance": 15}
                    ],
                    after_routes=[
                        {"prefix": f"10.{i}.0.0/16", "vrf": "default", "metric": 150, "admin_distance": 15}
                    ],
                    important_prefixes=[],
                ),
            )
            for i in range(4)
        ]
        results = await executor.run_batch(run_comparison_pipeline, items)
        assert len(results) == 4
        assert [r["device_label"] for r in results] == [f"parallel-dev-{i}" for i in range(4)]
        assert all(r["risk_level"] == "CRITICAL" for r in results)

        summary_res = await executor.run(
            run_summary_pipeline,
            SummaryInput(
                source_label="mp-summary",
                routes=[{"prefix": "10.1.0.0/16"}, {"prefix": "10.1.2.0/24"}],
            ),
        )
        assert summary_res["summary_route_count"] == 1
        assert summary_res["covered_route_count"] == 1
    finally:
        executor.shutdown()
