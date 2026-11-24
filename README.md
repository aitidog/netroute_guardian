# NetRoute Guardian — Enterprise Route Table Management & Change Analysis Platform

A full-stack web application designed to automate pre/post-change routing table verification with ServiceNow integration (Feature 1) and perform optimal prefix summarization across multi-vendor network devices (Feature 2).

## Architecture Overview

- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS (served by Nginx in Docker Compose, proxying `/api`)
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + APScheduler, managed with **`uv`**
- **Database**: PostgreSQL 16 (relational workflow & rule tables + JSONB route snapshots and reports)
- **Email Delivery**: Async SMTP (`aiosmtplib`) + Jinja2 HTML report templates, paired with **Mailpit** in Docker Compose so delivered emails can be inspected live at `http://localhost:8025`
- **Concurrency Model**:
  - **Device Collection (I/O-bound)**: `ConcurrentDeviceCollector` uses bounded `asyncio.Semaphore` + per-device timeout + partial-failure isolation across all CIs in a Change Request, offloading blocking I/O to worker threads.
  - **Comparison & Summarization Pipelines (CPU-bound)**: Pure, picklable single-responsibility pipelines offloaded via `PipelineExecutor` (`ProcessPoolExecutor`) to utilize multiple CPU cores without blocking the FastAPI event loop.
  - **Scheduler Concurrency Safety**: PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` guarantees idempotent T-1h pre-capture job claiming across replicas.

## Core Pipelines (Single Responsibility)

### Feature 1 — Comparison Pipeline (`backend/app/pipelines/comparison/`)
1. **`NormalizeStage`**: Canonicalize CIDRs and aggregate multi-path entries by `(VRF, Prefix)`.
2. **`DiffStage`**: Objective set/multiset diff producing `removed`, `added`, `changed`, and exact path deltas.
3. **`ImportanceClassifierStage`**: Pluggable rules — `LargePrefixRule` (`mask <= /20` removed/changed) and `PreSpecifiedRouteRule` (exact match against user-managed watchlist).
4. **`NetworkAnalysisStage`**: Pluggable analyzers:
   - `LpmFallbackAnalyzer`: Checks active post-change LPM parent coverage and egress consistency for removed prefixes.
   - `PathSelectionAnalyzer`: Lexicographic `(AD, Metric, PeerPriority)` primary vs backup path change detection, next-hop drift, redundancy deltas, and SD-WAN policy routing advisories.
   - `ImpactAssessmentAnalyzer`: Affected IP space and risk rating (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `PASS`).
5. **`ReportAssemblyStage`**: Executive summary, prioritized sections, human-readable explanations, and stage timing telemetry.

### Feature 2 — Route Summary Pipeline (`backend/app/pipelines/summary/`)
1. **`FilterNormalizeStage`**: Excludes `0.0.0.0/0` (and `::/0`), canonicalizes CIDRs, deduplicates per VRF.
2. **`PrefixCollapseStage`**: `O(N log N)` sorted monotonic stack retaining broadest existing covering prefixes and folding all covered sub-prefixes.
3. **`SupernetSuggestionStage`**: Optional adjacent CIDR aggregation suggestions via `ipaddress.collapse_addresses`.
4. **`SummaryFormatStage`**: Splits output into `summary_routes`, `remaining_routes`, and compression statistics.

## Quick Start (Docker Compose)

```bash
docker compose up --build
```

Once running:
- **Web UI**: http://localhost:3000
- **Backend OpenAPI Docs**: http://localhost:8000/docs
- **Mailpit Web Inbox (HTML Email Reports)**: http://localhost:8025

## Running Tests Locally

### Backend (`uv` + `pytest`)
```bash
cd backend
uv sync
uv run pytest -v
uv run ruff check app tests
```

### Frontend (`Vitest` + React Testing Library)
```bash
cd frontend
npm install
npm test
npm run build
```
