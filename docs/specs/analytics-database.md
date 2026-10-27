# Specification: DBnomics Analytics Database & Workbench

## Overview

The **DBnomics Analytics Database & Workbench** extends the DBnomics Data Browser with an embedded **DuckDB** OLAP warehouse (`data/analytics.duckdb`) and an in-app Analytics Workbench UI. Users can curate series selections in the Catalogue Browser, incrementally sync them into a local star schema, and run cross-series transformations or custom read-only SQL queries.

## User Stories

- **US-1 (Curated Ingestion)**:
  - **Who**: Economic analyst / researcher
  - **What**: Sync selected DBnomics time series (along with provider, dataset, and dimension metadata) from the Catalogue Browser into a local DuckDB database.
  - **Why**: To build a persistent, reproducible macroeconomic dataset across multiple providers without re-fetching from upstream on every query.
- **US-2 (Incremental Upsert & Lineage)**:
  - **Who**: Data engineer
  - **What**: Upsert observations idempotently (`ON CONFLICT DO UPDATE`) and record sync history in `sync_runs`.
  - **Why**: So revised economic data releases update existing periods cleanly without creating duplicate rows, while preserving a full sync audit trail.
- **US-3 (Cross-Series Analytics & Transformations)**:
  - **Who**: Researcher
  - **What**: Select stored series across multiple providers/datasets and compute analytical transformations (`raw`, `yoy_pct`, `pop_pct`, `rebased_100`, `rolling_avg`) and pairwise correlation matrices directly in DuckDB.
  - **Why**: To compare heterogeneous series on a common scale and analyze co-movements.
- **US-4 (Safe Analytical SQL)**:
  - **Who**: Power user
  - **What**: Execute read-only DuckDB SQL queries (`SELECT` / `WITH` / `DESCRIBE` / `SUMMARIZE`) against the star schema or `v_series_observations` view and chart/inspect the results.
  - **Why**: To support flexible ad-hoc OLAP queries locally.
- **US-5 (In-App Gemini AI Assistant)**:
  - **Who**: Economic analyst
  - **What**: Ask natural-language prompts in the Analytics Workbench powered by `google-genai` (`gemini-3.8-flash` via the Interactions API) with function calling over DBnomics and DuckDB tools.
  - **Why**: To automate multi-step discovery, warehouse ingestion, transformations, and chart generation.
- **US-6 (Local DBnomics + DuckDB MCP Server)**:
  - **Who**: AI developer / researcher using Antigravity, Claude Desktop, or Cursor
  - **What**: Run `python -m app.mcp_server` (`FastMCP`) over `stdio`.
  - **Why**: To expose both upstream DBnomics catalogue tools and local DuckDB analytics warehouse tools to external MCP clients.

## Technical Constraints

- **Hardware & Runtime**: macOS (Apple Silicon / ARM64 compatible), Python 3.14 (`.venv`), Node.js 24 (`nvm`), embedded `duckdb`, `google-genai`, and `mcp`.
- **Performance Targets**:
  - Analytical transformations and joins across $\le 100{,}000$ stored observations execute in $< 150\text{ ms}$.
  - Default storage location: `data/analytics.duckdb` (configurable via `DBNOMICS_BROWSER_ANALYTICS_DB_PATH`).
- **Security & Data Sanitization**:
  - All repository DML and filtered queries use parameterized placeholders (`?`).
  - Custom SQL execution enforces read-only statements only (`SELECT`, `WITH`, `DESCRIBE`, `SUMMARIZE`, `EXPLAIN`) and rejects mutating or file/system commands (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `COPY`, `ATTACH`, `DETACH`, `PRAGMA`, `INSTALL`, `LOAD`, `CALL`, `EXPORT`, `IMPORT`).
  - AI tool-calling loops are bounded to at most 5 rounds per turn.
- **Modularity & Complexity**:
  - Domain models and repository protocols (`AnalyticsRepositoryProtocol`) are decoupled from FastAPI and DuckDB internals.
  - Every new module stays under 300 lines and cyclomatic complexity $\le 10$.

## Data Schema

### Tables

1. **`dim_providers`**
   - `provider_code VARCHAR PRIMARY KEY`
   - `provider_name VARCHAR NOT NULL`
   - `region VARCHAR`
   - `website VARCHAR`
   - `updated_at TIMESTAMPTZ NOT NULL`

2. **`dim_datasets`**
   - `provider_code VARCHAR NOT NULL`
   - `dataset_code VARCHAR NOT NULL`
   - `dataset_name VARCHAR NOT NULL`
   - `description VARCHAR`
   - `dimensions_schema JSON`
   - `updated_at TIMESTAMPTZ NOT NULL`
   - `PRIMARY KEY (provider_code, dataset_code)`

3. **`dim_series`**
   - `series_id VARCHAR PRIMARY KEY` (`{provider_code}/{dataset_code}/{series_code}`)
   - `provider_code VARCHAR NOT NULL`
   - `dataset_code VARCHAR NOT NULL`
   - `series_code VARCHAR NOT NULL`
   - `series_name VARCHAR NOT NULL`
   - `frequency VARCHAR`
   - `unit VARCHAR`
   - `dimensions JSON`
   - `last_synced_at TIMESTAMPTZ NOT NULL`

4. **`fact_observations`**
   - `series_id VARCHAR NOT NULL`
   - `period VARCHAR NOT NULL`
   - `period_start_date DATE`
   - `value DOUBLE`
   - `original_period VARCHAR`
   - `original_value VARCHAR`
   - `synced_at TIMESTAMPTZ NOT NULL`
   - `PRIMARY KEY (series_id, period)`

5. **`sync_runs`**
   - `run_id VARCHAR PRIMARY KEY`
   - `provider_code VARCHAR NOT NULL`
   - `dataset_code VARCHAR NOT NULL`
   - `series_count INTEGER NOT NULL`
   - `observations_upserted INTEGER NOT NULL`
   - `status VARCHAR NOT NULL` (`running` | `completed` | `failed`)
   - `error_detail VARCHAR`
   - `started_at TIMESTAMPTZ NOT NULL`
   - `completed_at TIMESTAMPTZ`

### Analytical View (`v_series_observations`)

Denormalized star-schema view joining `fact_observations`, `dim_series`, `dim_datasets`, and `dim_providers` for one-table SQL querying.

### Shared AI & MCP Tool Surface

Both the In-App Gemini Assistant (`POST /api/analytics/ai/chat`) and the Local MCP Server (`backend/app/mcp_server.py`) expose the same 7 tools:
1. `list_providers`
2. `search_datasets`
3. `list_series`
4. `sync_series_to_warehouse`
5. `get_warehouse_catalog`
6. `transform_warehouse_series`
7. `query_warehouse_sql`

