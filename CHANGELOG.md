# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Unified `WorldEconomicData` Rebranding & Repository Rename:** Renamed application branding, package manifests (`pyproject.toml`, `frontend/package.json`), HTML metadata, local directory (`/Users/jasondavey/Projects/Tools/Data Acquisition/WorldEconomicData`), and GitHub repository (`LongMacchiato/WorldEconomicData`) from `DBnomics` to `WorldEconomicData`.
- **In-App Gemini & FRED API Key Configuration (`/api/analytics/ai/config` & `AiAssistantPanel.tsx`):** Added an in-app **API Keys & Model Configuration** drawer in the AI Economist Assistant with masked key status (`AIza...`), `.env` persistence (`0600` permissions), and immediate in-memory hot-reloading, plus an autonomous local catalog & DuckDB fallback agent (`ai_local_fallback.py`) when Gemini is unconfigured or unavailable.
- **Expanded Direct SDMX 2.1 / 3.0 Connectors (`sdmx_catalog_defs.py` & `sdmx1_registry.py`):** Added 6 new curated direct SDMX connectors — **Stats NZ (`SDMX_STATSNZ`)**, **Statistics Canada (`SDMX_STATCAN`)**, **Deutsche Bundesbank (`SDMX_BBK`)**, **Swiss Federal Statistical Office (`SDMX_BFS_CH`)**, **FAO (`SDMX_FAO`)**, and **World Bank WDI (`SDMX_WB_WDI`)** — alongside `SDMX_ABS`, `SDMX_BIS`, and 23 dynamic `SDMX1_*` agencies (including unlocked `SDMX1_BBK` on `https://api.statistiken.bundesbank.de/rest`), bringing total direct SDMX connectors to **31**.
- **Connector & Source-Type Filters (`ConnectorFilterBar` & `GET /api/providers?source_type=`):** Added interactive connector filter pills (`All Connectors`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) with live provider counts (`tabular-nums`) and connector source badges (`SDMX`, `DBnomics`, `Central Bank`, `Financial`) in both the **Catalogue Browser** and **Analytics Database** workbench, plus optional `?source_type=` server-side filtering on `GET /api/providers`.
- Embedded DuckDB analytics database (`data/analytics.duckdb`) with star-schema tables (`dim_providers`, `dim_datasets`, `dim_series`, `fact_observations`, `sync_runs`) and `v_series_observations` view.
- `/api/analytics/*` endpoints for syncing selected DBnomics series into DuckDB, browsing stored series, computing cross-series transformations (`raw`, `yoy_pct`, `pop_pct`, `rebased_100`, `rolling_avg`) and pairwise correlations, and executing safe read-only SQL queries.
- Frontend **Analytics Workbench** tab and **Sync to Analytics DB** action in the Catalogue Browser.
- In-App **AI Economist Assistant** (`POST /api/analytics/ai/chat` + `AiAssistantPanel.tsx`) powered by `google-genai` (`gemini-3.8-flash` Interactions API) with multi-step function calling over DBnomics and DuckDB tools.
- Local **DBnomics + DuckDB MCP Server** (`backend/app/mcp_server.py` using `FastMCP`) exposing 7 discovery, ingestion, transformation, and SQL tools over `stdio`.
- **Pluggable Data Connector Framework (`DataConnectorProtocol` & `CompositeCatalogService`)** merging 80+ DBnomics providers with direct statistical and financial connectors (`SDMX_*`, `SDMX1_*`, `RBA`, `FRED`, and `YAHOO_FINANCE`).
- **Macro Intelligence Dashboard (`MacroIntelligenceDashboard.tsx` & `/api/macro/*`)** featuring the Systemic Risk Scoreboard, AU vs. US Sovereign Yield Comparison, Trade Sensitivity & Commodity Correlation Matrix (`AUD/USD`, Iron Ore, Gold), and Local Apple Silicon MLX (`mlx-lm`) Executive Macro Briefs stored in DuckDB (`macro_briefs`).
