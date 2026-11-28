"""Reproducible performance benchmark suite for device collection concurrency and core pipelines.

Measures real, uninstrumented wall-clock latency, peak heap memory, and concurrency scaling for:
1. Bounded async I/O device collection (``asyncio.Semaphore`` + per-device timeout)
2. Feature 1 Comparison Pipeline (5 stages across 4.4k..100k route entries)
3. Feature 2 Route Summary Pipeline (4 stages across 4.4k..100k route entries)
4. Multi-device CPU batch execution (``sync`` vs ``ProcessPoolExecutor``)

Usage:
    cd backend
    uv run python scripts/benchmark_performance.py --json-out /tmp/bench.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

# Ensure backend root is importable when run as a script
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.adapters.devices.parsers import parse_edgeconnect_csv  # noqa: E402
from app.core.concurrency import PipelineExecutor, gather_with_concurrency  # noqa: E402
from app.pipelines.comparison.context import ComparisonInput  # noqa: E402
from app.pipelines.comparison.pipeline import run_comparison_pipeline  # noqa: E402
from app.pipelines.summary.context import SummaryInput  # noqa: E402
from app.pipelines.summary.pipeline import run_summary_pipeline  # noqa: E402
from app.services.seed import DEFAULT_IMPORTANT_ROUTES  # noqa: E402
from scripts.generate_synthetic_sample_data import build_synthetic_csv_pair  # noqa: E402


def _generate_scaled_routes(total_entries: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate deterministic synthetic before/after route dicts at arbitrary entry scale."""
    before_csv, after_csv = build_synthetic_csv_pair()
    base_before = [r.to_dict() for r in parse_edgeconnect_csv(before_csv)]
    base_after = [r.to_dict() for r in parse_edgeconnect_csv(after_csv)]

    if total_entries <= len(base_before):
        return base_before, base_after

    before = list(base_before)
    after = list(base_after)
    needed = total_entries - len(before)
    idx = 0
    while needed > 0:
        first = 10 if (idx // 65536) % 2 == 0 else 172
        if first == 10:
            second = 1 + ((idx // 256) % 120)
        else:
            second = 16 + ((idx // 256) % 4)
        third = idx % 256
        prefix = f"{first}.{second}.{third}.0/24"
        entries = min(2, needed)
        for p in range(entries):
            row = {
                "prefix": prefix,
                "vrf": "default",
                "next_hop": "",
                "interface": "",
                "protocol": "unknown",
                "admin_distance": 15,
                "metric": 50 + p * 10,
                "peer_priority": 5 + p,
                "raw_metric": f"{50 + p * 10} (AD:15, PP:{5 + p})",
                "appliance": "uec-scale-bench",
            }
            before.append(row)
            after.append(row)
        needed -= entries
        idx += 1

    return before, after


def benchmark_scale_matrix(scales: list[int]) -> list[dict[str, Any]]:
    important = [p for p, _ in DEFAULT_IMPORTANT_ROUTES]
    rows: list[dict[str, Any]] = []
    for scale in scales:
        before_routes, after_routes = _generate_scaled_routes(scale)
        comp_input = ComparisonInput(
            device_label=f"bench-{scale}",
            before_routes=before_routes,
            after_routes=after_routes,
            important_prefixes=important,
            large_prefix_threshold=20,
        )
        summ_input = SummaryInput(
            source_label=f"bench-{scale}",
            routes=after_routes,
            include_supernet_suggestions=True,
        )

        # 1. Pure uninstrumented wall-clock timing (no tracemalloc distortion)
        t0 = time.perf_counter()
        comp_res = run_comparison_pipeline(comp_input)
        comp_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        summ_res = run_summary_pipeline(summ_input)
        summ_ms = (time.perf_counter() - t0) * 1000.0

        # 2. Separate peak-memory measurement pass with tracemalloc
        tracemalloc.start()
        run_comparison_pipeline(comp_input)
        _, comp_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        tracemalloc.start()
        run_summary_pipeline(summ_input)
        _, summ_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        rows.append(
            {
                "target_entries": scale,
                "actual_before_entries": len(before_routes),
                "unique_prefixes": comp_res["summary_stats"]["before_unique_prefixes"],
                "comparison_total_ms": round(comp_ms, 2),
                "comparison_stages_ms": {
                    s["name"]: s["duration_ms"] for s in comp_res["pipeline_stages"]
                },
                "comparison_peak_mb": round(comp_peak / (1024 * 1024), 2),
                "summary_total_ms": round(summ_ms, 2),
                "summary_stages_ms": {
                    s["name"]: s["duration_ms"] for s in summ_res["pipeline_stages"]
                },
                "summary_peak_mb": round(summ_peak / (1024 * 1024), 2),
                "summary_output_routes": summ_res["output_route_count"],
            }
        )
    return rows


async def benchmark_process_pool_batch(device_count: int = 8, route_scale: int = 20000) -> dict[str, Any]:
    before_routes, after_routes = _generate_scaled_routes(route_scale)
    important = [p for p, _ in DEFAULT_IMPORTANT_ROUTES]
    args_list = [
        (
            ComparisonInput(
                device_label=f"dev-{i:02d}",
                before_routes=before_routes,
                after_routes=after_routes,
                important_prefixes=important,
            ),
        )
        for i in range(device_count)
    ]

    sync_exec = PipelineExecutor(mode="sync", max_workers=1)
    sync_exec.start()
    t0 = time.perf_counter()
    await sync_exec.run_batch(run_comparison_pipeline, args_list)
    sync_ms = (time.perf_counter() - t0) * 1000.0
    sync_exec.shutdown()

    cpu_count = os.cpu_count() or 2
    worker_configs = [w for w in (2, 4) if w <= max(cpu_count, 2)]
    results: dict[str, Any] = {
        "device_count": device_count,
        "routes_per_device": len(before_routes),
        "sync_ms": round(sync_ms, 1),
        "process_pool": {},
    }

    for workers in worker_configs:
        proc_exec = PipelineExecutor(mode="process", max_workers=workers)
        proc_exec.start()
        await proc_exec.run(
            run_comparison_pipeline,
            ComparisonInput(device_label="warmup", before_routes=[], after_routes=[]),
        )
        t0 = time.perf_counter()
        await proc_exec.run_batch(run_comparison_pipeline, args_list)
        proc_ms = (time.perf_counter() - t0) * 1000.0
        proc_exec.shutdown()
        results["process_pool"][str(workers)] = {
            "total_ms": round(proc_ms, 1),
            "speedup_vs_sync": round(sync_ms / proc_ms, 2) if proc_ms > 0 else 0.0,
        }
    return results


async def benchmark_io_semaphore(device_count: int = 50, rtt_ms: float = 200.0) -> dict[str, Any]:
    """Compare serial vs asyncio.Semaphore(10) device polling under realistic network RTT."""
    rtt_sec = rtt_ms / 1000.0
    active = 0
    peak_active = 0

    async def fake_poll(dev_idx: int) -> int:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        try:
            await asyncio.sleep(rtt_sec)
            return dev_idx
        finally:
            active -= 1

    t0 = time.perf_counter()
    outcomes = await gather_with_concurrency(
        10,
        [fake_poll(i) for i in range(device_count)],
        timeout_seconds=5.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    serial_theoretical_ms = device_count * rtt_ms
    return {
        "device_count": device_count,
        "simulated_rtt_ms": rtt_ms,
        "max_concurrency": 10,
        "observed_peak_concurrency": peak_active,
        "succeeded": sum(1 for o in outcomes if not isinstance(o, BaseException)),
        "elapsed_ms": round(elapsed_ms, 1),
        "serial_equivalent_ms": round(serial_theoretical_ms, 1),
        "speedup_vs_serial": round(serial_theoretical_ms / elapsed_ms, 2),
    }


async def run_all(scales: list[int], batch_devices: int, batch_scale: int) -> dict[str, Any]:
    env_info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    return {
        "environment": env_info,
        "io_semaphore": await benchmark_io_semaphore(),
        "scale_matrix": benchmark_scale_matrix(scales),
        "process_pool_batch": await benchmark_process_pool_batch(
            device_count=batch_devices, route_scale=batch_scale
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run device collection concurrency and core pipeline performance benchmarks."
    )
    parser.add_argument(
        "--scales",
        default="4442,20000,50000,100000",
        help="Comma-separated route entry counts to benchmark",
    )
    parser.add_argument("--batch-devices", type=int, default=8)
    parser.add_argument("--batch-scale", type=int, default=20000)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    scales = [int(x.strip()) for x in args.scales.split(",") if x.strip()]
    report = asyncio.run(run_all(scales, args.batch_devices, args.batch_scale))
    serialized = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
