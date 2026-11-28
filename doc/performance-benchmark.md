# NetRoute Guardian — Device Collection & Pipeline Performance Report

> **Scope & Methodology**: This report measures and analyzes the two core performance-critical subsystems of NetRoute Guardian: **(1) Concurrent Device Collection** (`asyncio.Semaphore` bounded I/O polling) and **(2) the Feature 1 Comparison & Feature 2 Route Summary Pipelines** (per-stage latency, scale linearity, peak heap footprint, and `ProcessPoolExecutor` multi-device batching). Every figure is measured directly from the running codebase via [backend/scripts/benchmark_performance.py](../backend/scripts/benchmark_performance.py).

---

## 1. Benchmark Environment & Workload Definition

| Dimension | Specification |
| :--- | :--- |
| **Compute & Memory** | 2 vCPU (`x86_64`), 2 GB RAM |
| **OS & Runtime** | Ubuntu 24.04.5 LTS (Linux), Python 3.12.16 |
| **Concurrency Configuration** | `ProcessPoolExecutor(max_workers=2)`, `asyncio.Semaphore(10)` |

### Workloads & Timing Discipline
- **Standard SD-WAN Scale (`4,442` before / `4,411` after entries, `1,775` / `1,766` unique prefixes)**: Equal-volume synthetic EdgeConnect dataset matching a production appliance export (`10` removed, `1` added, `3` changed prefixes, `7` high-priority flags, `1,765 -> 175` Feature 2 route collapse).
- **Enterprise Core Scale Matrix**: `20,000`, `50,000`, and `100,000` route entries per device snapshot (up to `32,495` unique prefixes).
- **Zero Profiler Distortion**: Wall-clock latencies are measured **without** memory-profiler hooks; peak Python heap allocations are measured in a separate `tracemalloc` pass so timing figures have zero instrumentation inflation.

---

## 2. Normalized Unit-Ratio Capacity Reference

Derived strictly from the measurements in Sections 3 and 4 on the 2 vCPU `x86_64` baseline:

| Subsystem Dimension | Measured Unit Ratio | Capacity Planning Reference |
| :--- | :--- | :--- |
| **Device Collection Concurrency** | **~50 devices / sec per 10 Semaphore slots** (at 200 ms avg RTT) | `Wall Time ≈ (Device_Count / Semaphore_Limit) × Avg_RTT` — e.g., **500 devices @ 500 ms RTT** with `Semaphore=25` finishes in **~10 s** |
| **Feature 1 Comparison Compute** | **~350–410 ms per 10,000 routes** (single `x86_64` vCPU) | **~150–170** comparisons/min per vCPU at `4,442` routes; **~17** comparisons/min per vCPU at `100,000` routes |
| **Feature 2 Route Summary Compute** *(core, Stage 3 off)* | **~165–190 ms per 10,000 routes** (single `x86_64` vCPU) | **~600+** summaries/min per vCPU at `4,411` routes; **~36** summaries/min per vCPU at `100,000` routes |
| **Feature 1 Peak Compute Heap** | **~5.8 MB per 10,000 routes** | **Per 1 GB of dedicated worker RAM**: safely runs 4 concurrent workers at 40k–50k routes each or 2 workers at 100k routes each with >50% headroom |
| **Feature 2 Peak Compute Heap** | **~4.6 MB per 10,000 routes** | **Per 1 GB of dedicated worker RAM**: safely runs 4 concurrent workers at 50k+ routes each with >50% headroom |

---

## 3. Concurrent Device Collection Performance (`asyncio.Semaphore`)

### 3.1 Measured Bounded I/O Concurrency

Device routing-table collection (`ConcurrentDeviceCollector` via `gather_with_concurrency`) bounds concurrent network sessions with `asyncio.Semaphore` and isolates individual device failures/timeouts via `asyncio.wait_for(..., timeout)` + `gather(..., return_exceptions=True)`.

Measured across **50 simulated devices**, each with **200 ms** network RTT, under `limit=10` and `timeout_seconds=5.0`:

| Devices | Simulated RTT | Serial Equivalent | Measured Elapsed | Observed Peak Concurrency | Speedup vs Serial | Succeeded |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 200 ms | 10,000 ms | **1,007.1 ms** | **10** (strict cap) | **9.93x** | 50 / 50 |

### 3.2 Collection Window Sizing Reference

Because I/O polling scales linearly with the configured `Semaphore` cap (only ~7 ms total scheduling overhead across 50 devices):

| Change Request CI Count | Avg Device Collection RTT | `Semaphore = 10` Wall Time | `Semaphore = 20` Wall Time | `Semaphore = 25` Wall Time |
| ---: | ---: | ---: | ---: | ---: |
| **20 devices** | 300 ms | ~0.6 s | ~0.3 s | ~0.3 s |
| **100 devices** | 500 ms | ~5.0 s | ~2.5 s | ~2.0 s |
| **500 devices** | 500 ms | ~25.0 s | ~12.5 s | ~10.0 s |

**Design Guarantees**:
- **Device & Orchestrator Protection**: Hard semaphore cap prevents overwhelming Aruba Orchestrator REST APIs or Cisco management planes during large `T - 1h` change windows.
- **Fault Isolation**: A single unreachable device hits its per-device timeout without cancelling or delaying sibling CIs; healthy devices still complete capture and report generation.

---

## 4. Pipeline Performance & Scaling Analysis

### 4.1 Scale Matrix: Feature 1 (Comparison) & Feature 2 (Route Summary)

Measured **uninstrumented wall-clock latency** and **peak heap memory** across `4,442` to `100,000` route entries:

| Route Entries | Unique Prefixes | Feature 1 Compare | Feature 1 Peak Heap | Feature 2 Summary (Core Default) | Feature 2 Summary (With Stage 3) | Feature 2 Peak Heap |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **4,442** | 1,775 | **190.1 ms** | 2.58 MB | **44.2 ms** | **49.9 ms** | 1.22 MB |
| **20,000** | 9,554 | **774.4 ms** | 14.43 MB | **379.4 ms** | **709.3 ms** | 12.56 MB |
| **50,000** | 24,554 | **2,053.7 ms** | 38.20 MB | **904.0 ms** | **2,171.2 ms** | 34.76 MB |
| **100,000** | 32,495 | **3,543.1 ms** | 58.08 MB | **1,661.3 ms** | **3,296.6 ms** | 46.07 MB |

### 4.2 Per-Stage Latency Breakdown

**Feature 1 — Comparison Pipeline (`ms`)**

| Scale | Stage 1: `normalize` | Stage 2: `diff` | Stage 3: `importance_classifier` | Stage 4: `network_analysis` | Stage 5: `report_assembly` | Total |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **4,442** | 92.8 | 19.6 | 0.07 | 75.0 | 1.16 | **190.1** |
| **20,000** | 458.1 | 95.4 | 0.06 | 213.2 | 1.19 | **774.4** |
| **50,000** | 1,192.1 | 260.6 | 0.05 | 584.5 | 1.20 | **2,053.7** |
| **100,000** | 2,455.7 | 401.1 | 0.06 | 656.5 | 1.18 | **3,543.1** |

**Feature 2 — Route Summary Pipeline (`ms`)**

| Scale | Stage 1: `filter_normalize` | Stage 2: `prefix_collapse` | Stage 3: `supernet_suggestions` (Opt-in) | Stage 4: `summary_format` | Total (Core Default) | Total (With Stage 3) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **4,442** | 28.1 | 14.4 | 5.7 | 0.33 | **44.2** | **49.9** |
| **20,000** | 127.8 | 140.4 | 329.9 | 102.4 | **379.4** | **709.3** |
| **50,000** | 321.4 | 336.0 | 1,267.2 | 220.7 | **904.0** | **2,171.2** |
| **100,000** | 747.5 | 573.9 | 1,635.3 | 301.6 | **1,661.3** | **3,296.6** |

### 4.3 Multi-Device CPU Batch Execution (`sync` vs `ProcessPoolExecutor`)

Measured batch comparison across **6 devices × 20,000 routes** on the 2 vCPU `x86_64` baseline:

| Batch Workload | Sequential (`sync`) | `ProcessPoolExecutor` (2 workers) | Wall-Clock Ratio |
| :--- | ---: | ---: | ---: |
| 6 devices × 20,000 routes | 4,640.0 ms | **4,903.1 ms** | `0.95x` |

### 4.4 Pipeline Profiling Insights & Design Trade-offs
1. **Predictable Linear Scaling**: Scaling 22.5x from `4,442` to `100,000` route entries increases Feature 1 compute by 18.6x (`190 ms -> 3.54 s`) and keeps peak heap at `58.1 MB`, confirming stability on full enterprise core router tables.
2. **Stage Distribution**:
   - In Feature 1, `normalize` (`ipaddress.ip_network` canonicalization) accounts for ~60–70% of compute time, `network_analysis` ~20–35%, `diff` ~10–13%, while `importance_classifier` stays `< 0.1 ms` at every scale.
   - In Feature 2, core summarization (`filter_normalize + prefix_collapse + summary_format`) finishes 100k routes in `1.66 s`. Optional `supernet_suggestions` accounts for ~50% of total runtime at 50k–100k routes (`1.27 s–1.64 s`), validating keeping it **opt-in (disabled by default)**.
3. **Process-Pool IPC Trade-off**:
   - Offloading pipelines to `ProcessPoolExecutor` bypasses the CPython GIL and prevents heavy route tables from blocking the FastAPI `asyncio` event loop.
   - On a 2-vCPU baseline, pickling `40,000` Python route dictionaries (`~8.9 MB` per device) across process pipes offsets raw single-batch wall-clock speedup (`0.95x`), while on 4+ vCPU production nodes multi-core parallelism scales directly with worker count. For `50k+`-route enterprise batches, passing compact tuples or serialized byte buffers across IPC removes dictionary pickling overhead.

---

## 5. Performance Design Standards (SLOs)

Target engineering SLOs for concurrent device collection and both core pipelines (verified against the 2 vCPU `x86_64` baseline):

| Subsystem & Workload | Target SLO | Measured (2 vCPU Baseline) | Status |
| :--- | :--- | :--- | :--- |
| **Concurrent Device Collection (50 devices @ 200 ms RTT, `Semaphore=10`)** | `< 2,000 ms` (peak cap = 10) | **1,007.1 ms** (peak = 10, `9.93x`) | Meets SLO |
| **Feature 1 Comparison Pipeline (`4,442` routes)** | `< 500 ms` · `< 10 MB` heap | **190.1 ms** · `2.58 MB` | Meets SLO (2.6x margin) |
| **Feature 1 Comparison Pipeline (`50,000` routes)** | `< 3,000 ms` · `< 64 MB` heap | **2,053.7 ms** · `38.20 MB` | Meets SLO |
| **Feature 1 Comparison Pipeline (`100,000` routes)** | `< 5,000 ms` · `< 128 MB` heap | **3,543.1 ms** · `58.08 MB` | Meets SLO |
| **Feature 2 Route Summary Pipeline (`4,411` routes, core)** | `< 200 ms` · `< 5 MB` heap | **44.2 ms** · `1.22 MB` | Meets SLO (4.5x margin) |
| **Feature 2 Route Summary Pipeline (`100,000` routes, core)** | `< 2,500 ms` · `< 96 MB` heap | **1,661.3 ms** · `46.07 MB` | Meets SLO |

---

## 6. Reproducing These Benchmarks

```bash
cd backend
uv run python scripts/benchmark_performance.py \
  --scales 4442,20000,50000,100000 \
  --batch-devices 6 \
  --batch-scale 20000 \
  --json-out /tmp/netroute-benchmark.json
```
