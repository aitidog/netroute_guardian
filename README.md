# NetRoute Guardian — Enterprise Route Table Management & Change Analysis Platform

A full-stack web application designed to automate pre/post-change routing table verification with ServiceNow integration (**Feature 1**) and perform optimal prefix summarization across multi-vendor network devices (**Feature 2**).

> **Documentation**:
> - [System Architecture & Deployment Design](doc/architecture.md)
> - [Pipeline Design, Algorithms, Extensibility & Configurable Conditions](doc/pipeline-design.md)

---

## Architecture Overview

- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS (served by Nginx in Docker Compose, proxying `/api`)
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.0 + APScheduler, managed with **`uv`**
- **Database**: PostgreSQL 16 (relational workflow & rule tables + JSONB route snapshots and reports)
- **Email Delivery**: Async SMTP (`aiosmtplib`) + Jinja2 HTML report templates, paired with **Mailpit** in Docker Compose so delivered emails can be inspected live at `http://localhost:8025`
- **Concurrency Model**:
  - **Device Collection (I/O-bound)**: `ConcurrentDeviceCollector` uses bounded `asyncio.Semaphore` + per-device timeout + partial-failure isolation across all CIs in a Change Request, offloading blocking I/O and parsing to worker threads.
  - **Comparison & Summarization Pipelines (CPU-bound)**: Pure, picklable single-responsibility pipelines offloaded via `PipelineExecutor` (`ProcessPoolExecutor`) to utilize multiple CPU cores without blocking the FastAPI event loop.
  - **Scheduler Concurrency Safety**: PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` guarantees idempotent `T - 1h` pre-capture job claiming across replicas.

---

## Core Pipelines (Single Responsibility)

### Feature 1 — Comparison Pipeline (`backend/app/pipelines/comparison/`)
1. **`NormalizeStage`**: Canonicalize CIDRs and aggregate multi-path entries by `(VRF, Prefix)`.
2. **`DiffStage`**: Objective set/multiset diff producing `removed`, `added`, `changed`, and exact path deltas.
3. **`ImportanceClassifierStage`**: Pluggable rules — `LargePrefixRule` (`mask <= /20` removed/changed) and `PreSpecifiedRouteRule` (exact match against user-managed watchlist).
4. **`NetworkAnalysisStage`**: Pluggable analyzers:
   - `LpmFallbackAnalyzer`: Checks active post-change LPM parent coverage and egress consistency for removed prefixes.
   - `PathSelectionAnalyzer`: Lexicographic `(AD, Metric, PeerPriority)` primary vs. backup path change detection, next-hop drift, redundancy deltas, and SD-WAN policy routing advisories.
   - `ImpactAssessmentAnalyzer`: Affected IP space and risk rating (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `PASS`).
5. **`ReportAssemblyStage`**: Executive summary, prioritized sections, human-readable explanations, and stage timing telemetry.

### Feature 2 — Route Summary Pipeline (`backend/app/pipelines/summary/`)
1. **`FilterNormalizeStage`**: Excludes `0.0.0.0/0` (and `::/0`), canonicalizes CIDRs, deduplicates per VRF.
2. **`PrefixCollapseStage`**: Sorted monotonic stack retaining broadest existing covering prefixes and folding all covered sub-prefixes.
3. **`SupernetSuggestionStage`**: Optional adjacent CIDR aggregation suggestions via `ipaddress.collapse_addresses`.
4. **`SummaryFormatStage`**: Splits output into `summary_routes`, `remaining_routes`, and compression statistics.

---

## Preparing Sample Data (`backend/sample_data/`)

> **Why isn't sample CSV data committed to Git?**  
> Real network routing exports often contain sensitive internal IP plans and topology details, so `backend/sample_data/*.csv` is excluded via `.gitignore`. Before running the EdgeConnect CSV demo or full backend integration tests, place your sample CSV files locally as described below.

### 1. Target Directory & Expected Filenames

Place the two routing table CSV files in **`backend/sample_data/`**:

```text
backend/
└── sample_data/
    ├── .gitkeep
    ├── subnetsExample_beforeChange.csv   # Pre-change routing table snapshot
    └── subnetsExample_afterChange.csv    # Post-change routing table snapshot (also used by Feature 2 demo)
```

| File Path | Used By |
| :--- | :--- |
| `backend/sample_data/subnetsExample_beforeChange.csv` | EdgeConnect demo device `uec-abc-prd01` (`pre_change` phase), `/api/v1/comparisons/demo-csv`, and `pytest` EdgeConnect fixtures |
| `backend/sample_data/subnetsExample_afterChange.csv` | EdgeConnect demo device `uec-abc-prd01` (`post_change` & `adhoc` phases), `/api/v1/comparisons/demo-csv`, `/api/v1/route-summary/demo-csv`, and `pytest` |

*(Optional)* If you run via Docker Compose and prefer not to rebuild the image when swapping CSV files, you can bind-mount a host directory to `/app/sample_data` on the `backend` service or override `SAMPLE_DATA_DIR`.

### 2. CSV Format Specification (Aruba EdgeConnect / Silver Peak Export Format)

- **Encoding**: UTF-8 (with or without UTF-8 BOM — the parser automatically strips `\ufeff`).
- **Delimiter**: Standard RFC 4180 comma-separated values (`.csv`). Cells containing commas (such as `"50 (AD:15, PP:7)"`) **must** be enclosed in double quotes.
- **Multi-path support**: Multiple rows may share the same `Subnet/Mask` (representing ECMP or primary/backup paths with different metrics, ADs, or next-hops).

| Column Header | Required | Accepted Header Aliases | Format & Semantics |
| :--- | :---: | :--- | :--- |
| `Appliance` | Optional | `Device` | Source appliance hostname (e.g. `uec-abc-prd01`). |
| `Subnet/Mask` | **Yes** | `Prefix`, `Subnet`, `Network` | Valid IPv4 or IPv6 CIDR notation (e.g. `10.127.0.0/16`, `0.0.0.0/0`). Non-strict host bits are canonicalized automatically. |
| `Next Hop` | Optional | `NextHop` | Next-hop IP address (e.g. `10.162.183.217`). Leave empty for SD-WAN fabric overlay routes. |
| `Interface` | Optional | — | Outgoing interface name (e.g. `lan0`, `twan0`, `wan0`). Leave empty for SD-WAN fabric overlay routes. |
| `Metric` | Optional | — | Numeric metric or EdgeConnect string: `<metric>`, `<metric> (AD:<ad>)`, or `"<metric> (AD:<ad>, PP:<pp>)"`. Lower `(AD, Metric, PP)` indicates higher route preference. |
| `VRF` | Optional | `Segment` | Routing table / VRF isolation domain. Defaults to `default` when omitted. |

#### Minimal Synthetic Example

If you do not have real EdgeConnect Orchestrator exports, you can create minimal test CSVs immediately:

**`backend/sample_data/subnetsExample_beforeChange.csv`**
```csv
Appliance,Subnet/Mask,Next Hop,Interface,Metric
uec-abc-prd01,0.0.0.0/0,10.162.183.217,lan0,50 (AD:1)
uec-abc-prd01,0.0.0.0/0,194.20.1.5,twan0,52 (AD:251)
uec-abc-prd01,10.127.0.0/16,,,"50 (AD:15, PP:7)"
uec-abc-prd01,10.127.0.0/16,,,150 (AD:15)
uec-abc-prd01,10.132.0.0/14,,,50 (AD:15)
uec-abc-prd01,10.76.12.0/23,,,50 (AD:15)
uec-abc-prd01,10.64.0.0/12,,,50 (AD:15)
uec-abc-prd01,10.1.0.0/16,,,50 (AD:15)
uec-abc-prd01,10.1.1.0/24,,,50 (AD:15)
```

**`backend/sample_data/subnetsExample_afterChange.csv`**
```csv
Appliance,Subnet/Mask,Next Hop,Interface,Metric
uec-abc-prd01,0.0.0.0/0,10.162.183.217,lan0,50 (AD:1)
uec-abc-prd01,0.0.0.0/0,194.20.1.1,twan0,52 (AD:251)
uec-abc-prd01,10.127.0.0/16,,,150 (AD:15)
uec-abc-prd01,10.127.0.0/16,,,200 (AD:15)
uec-abc-prd01,10.64.0.0/12,,,50 (AD:15)
uec-abc-prd01,10.1.0.0/16,,,50 (AD:15)
uec-abc-prd01,10.1.1.0/24,,,50 (AD:15)
uec-abc-prd01,10.156.43.128/25,,,50 (AD:15)
```

### 3. Other Supported Input Formats (Ad-hoc Upload & Paste)

In addition to EdgeConnect CSV exports, the **Ad-hoc CSV Compare** and **Route Summary** pages automatically detect and parse:
- **Cisco Nexus (`NX-OS`)**: Raw `show ip route vrf all` CLI output (including VRF headers and multi-path `*via` entries).
- **Cisco Router (`IOS` / `IOS-XE`)**: Raw `show ip route` CLI output (including connected routes and indented ECMP continuation lines).
- **Plain CIDR List**: One CIDR prefix per line (comments starting with `#` are ignored), useful for quick Feature 2 route summarization tests.

*(Note: The built-in simulated Cisco Nexus `nx-dc1-core01` and Cisco Router `rtr-hq-wan01` devices use self-contained synthetic CLI fixtures in `backend/app/adapters/devices/mock_fixtures.py` and work immediately even without CSV files.)*

---

## Quick Start (Docker Compose)

1. Place your sample CSV files in `backend/sample_data/` (see section above).
2. Start the full 4-container stack:

```bash
docker compose up --build
```

Once running:
- **Web UI**: http://localhost:3000
- **Backend OpenAPI Docs**: http://localhost:8000/docs
- **Mailpit Web Inbox (HTML Email Reports)**: http://localhost:8025

---

## Running Tests Locally

### Backend (`uv` + `pytest` + `ruff`)
```bash
cd backend
uv sync
uv run pytest -v
uv run ruff check app tests
```

> **Note**: Tests that assert exact prefix counts against the reference EdgeConnect CSV datasets require the full `subnetsExample_beforeChange.csv` and `subnetsExample_afterChange.csv` files to be present in `backend/sample_data/`.

### Frontend (`Vitest` + React Testing Library)
```bash
cd frontend
npm install
npm test
npm run build
```
