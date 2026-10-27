# WorldEconomicData

A unified macroeconomic, statistical, and financial intelligence platform for
discovering, filtering, previewing, and analyzing public economic time series
from **31 Direct SDMX 2.1/3.0 & `sdmx1` agencies**, **80+ [DBnomics](https://db.nomics.world/) providers**,
and direct central-bank/market connectors (`RBA`, `FRED`, `YAHOO_FINANCE`), with
an embedded DuckDB star-schema warehouse and AI Economist Assistant.

## Architecture

```text
React + Vite  ->  FastAPI  ->  DBnomics Web API (catalogue)
                          \->  Direct Connectors (SDMX 2.1/3.0, sdmx1, RBA, FRED, Yahoo Finance)
                          \->  dbnomics.fetch_series (observations)
                          \->  TTL metadata cache
                          \->  Embedded DuckDB star-schema warehouse (data/analytics.duckdb)
```

Provider, dataset, and series discovery use `https://api.db.nomics.world/v22` alongside
direct SDMX and central-bank connectors. The frontend provides a **Connector Filter Bar**
(`All Connectors`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) in both the
**Catalogue Browser** and **Analytics Database** tabs.

## Prerequisites

- Python 3.14
- NVM with Node.js 24

## Setup

Create the Python virtual environment and install the pinned dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Install the frontend dependencies through the repository's Node environment.
From the **repository root**:

```bash
nvm use
npm --prefix frontend ci
```

Or from `frontend/`:

```bash
nvm use
npm ci
```

## Run locally

From the repository root, start both servers with:

```bash
./start.sh
```

Or run them manually in separate terminals.

Start the API on port **8001** (from the repository root). Port 8000 is commonly
occupied by other local services (e.g. Docker containers):

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8001
```

In another terminal, start the frontend from the repository root:

```bash
nvm use
npm --prefix frontend run dev
```

Or from `frontend/`:

```bash
nvm use
npm run dev
```

Open `http://localhost:5173`. In dev, the frontend proxies `/api` to the backend
on port 8001, so CORS is not required. The API documentation is available at
`http://localhost:8001/docs`.

Set `VITE_API_BASE_URL` when the API is hosted elsewhere. Backend settings use
the `DBNOMICS_BROWSER_` prefix (including `DBNOMICS_BROWSER_ANALYTICS_DB_PATH`
and `DBNOMICS_BROWSER_ANALYTICS_MAX_QUERY_ROWS`); see `.env.example` and
`backend/app/config.py`.

## API

### Catalogue & Preview
- `GET /health`
- `GET /api/providers?source_type=` (optional `source_type` filter: `sdmx`, `dbnomics`, `central_bank`, `financial`)
- `GET /api/providers/{provider_code}`
- `GET /api/providers/{provider_code}/datasets?search=`
- `GET /api/providers/{provider_code}/datasets/{dataset_code}`
- `GET /api/search?q=`
- `GET /api/providers/{provider_code}/datasets/{dataset_code}/series`
- `POST /api/query/preview`
- `POST /api/query/download?format=csv|json`

### DuckDB Analytics Warehouse & AI Economist Assistant
- `GET /api/analytics/catalog` — warehouse counts, stored series list, and recent sync runs
- `POST /api/analytics/sync` — sync selected DBnomics series into DuckDB
- `DELETE /api/analytics/series/{series_id}` — remove a stored series and its observations
- `POST /api/analytics/transform` — compute cross-series transformations (`raw`, `yoy_pct`, `pop_pct`, `rebased_100`, `rolling_avg`) and pairwise Pearson correlations
- `POST /api/analytics/sql` — execute validated read-only DuckDB SQL queries against `v_series_observations`
- `POST /api/analytics/ai/chat` — Gemini 3.8 Flash (`google-genai` Interactions API) assistant with automatic multi-step function calling across DBnomics and DuckDB (set `GEMINI_API_KEY` or `DBNOMICS_BROWSER_GEMINI_API_KEY` in `.env`)

### Direct Connectors & Macro Intelligence (`/api/macro/*`)
- `GET /api/macro/status` — Systemic Risk Scoreboard KPIs, registered direct connectors (`SDMX_ABS`, `SDMX_BIS`, `SDMX1_*`, `RBA`, `FRED`, `YAHOO_FINANCE`), and latest AI Macro Brief
- `POST /api/macro/refresh` — syncs core RBA, FRED, and Yahoo Finance macro/market series into DuckDB and generates a fresh Daily Macro Brief via local Apple Silicon `mlx-lm` (`Meta-Llama-3.1-8B-Instruct-4bit`) or rule synthesis
- `GET /api/macro/insights` — returns the latest persisted `ai_insights` record
- `GET /api/macro/connectors` — lists all registered `DataConnectorProtocol` plugins and their configuration status

## Local Model Context Protocol (MCP) Server

The repository includes a built-in stdio MCP server (`backend/app/mcp_server.py`) exposing 7 DBnomics & DuckDB tools (`list_providers`, `search_datasets`, `list_series`, `sync_series_to_warehouse`, `get_warehouse_catalog`, `transform_warehouse_series`, `query_warehouse_sql`) for external MCP clients (Antigravity, Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "world-economic-data": {
      "command": "/ABSOLUTE/PATH/TO/WorldEconomicData/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "/ABSOLUTE/PATH/TO/WorldEconomicData/backend"
      }
    }
  }
}
```

Example preview request:

```json
{
  "provider_code": "IMF",
  "dataset_code": "CPI",
  "series_codes": ["M.US.PCPI_IX"],
  "start_period": "2020-01-01",
  "end_period": "2024-12-31",
  "page": 1,
  "page_size": 25
}
```

Keep series selections focused; the API caps how many series can be fetched in
one request.

## Quality checks

Backend:

```bash
.venv/bin/python -m ruff format --check backend
.venv/bin/python -m ruff check backend
.venv/bin/python -m mypy backend/app
.venv/bin/python -m pytest backend/tests
```

Live DBnomics harness (network required; excluded from the default suite):

```bash
.venv/bin/python -m pytest backend/tests/live -m live
```

Frontend:

```bash
nvm use
npm --prefix frontend run format:check
npm --prefix frontend run lint
npm --prefix frontend run check
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

The unit and browser tests mock DBnomics responses, so routine test runs do not
depend on the external API.
