# User Manual: WorldEconomicData (SDMX, DBnomics, Central Banks & Macro Intelligence)

## 1. Overview
**WorldEconomicData** unifies **31 direct SDMX 2.1/3.0 & `sdmx1` agencies**, **80+ global DBnomics providers**, and **direct central-bank/financial connectors** (`SDMX_ABS`, `SDMX_BIS`, `SDMX_STATSNZ`, `SDMX_STATCAN`, `SDMX_BBK`, `SDMX_BFS_CH`, `SDMX_FAO`, `SDMX_WB_WDI`, 23 dynamic `SDMX1_*` agencies, `RBA`, `FRED`, `YAHOO_FINANCE`) inside a single DuckDB analytics warehouse (`data/analytics.duckdb`) and React workbench.

## 2. Workspace Modes

### 2.1 Catalogue Browser & Connector Filters
1. In Section **01 Choose a provider**, use the **Connector Filter Bar** (`All Connectors`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) to immediately isolate providers by connector ecosystem:
   - **SDMX:** 8 curated direct SDMX 2.1/3.0 connectors (`SDMX_ABS`, `SDMX_BIS`, `SDMX_STATSNZ`, `SDMX_STATCAN`, `SDMX_BBK`, `SDMX_BFS_CH`, `SDMX_FAO`, `SDMX_WB_WDI`) plus 23 dynamic `SDMX1_*` agencies (`SDMX1_ECB`, `SDMX1_ESTAT`, `SDMX1_IMF`, `SDMX1_OECD`, `SDMX1_BBK`, `SDMX1_INSEE`, `SDMX1_ISTAT`, `SDMX1_NB`, etc.).
   - **DBnomics:** Global DBnomics catalogue providers (`IMF`, `ECB`, `OECD`, `Eurostat`, `BIS`, etc.).
   - **Central Banks:** Direct central bank statistical APIs (`RBA`, `FRED`).
   - **Financial:** Live market feeds (`YAHOO_FINANCE`).
2. Combine the connector filter with the **Search providers** input to filter by name, code, or region. Your active connector filter is persisted in `localStorage`.
3. Choose a dataset (e.g., `RBA -> F1_1`, `SDMX_ABS -> ANA_AGG`, `SDMX_STATSNZ -> DF_CPI`, or `YAHOO_FINANCE -> COMMODITIES`).
4. Filter by dimensions or text search, select up to 10 series, preview interactive charts, export CSV/JSON, or click **Sync to Analytics DB** to persist observations into `data/analytics.duckdb`.

### 2.2 Analytics Database Workbench
1. Switch to **Analytics Database** in the top navigation bar.
2. Use the **Connector Filter Bar** (`All Connectors`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) above the **Stored Series & Transformations** list to filter synced DuckDB series by source connector.
3. Run cross-series transformations (`raw`, `yoy_pct`, `pop_pct`, `rebased_100`, `rolling_avg`) and inspect the automatic **Pearson Correlation Matrix**.
4. Query `v_series_observations` directly with read-only DuckDB SQL or use the **AI Economist Assistant** (`gemini-3.8-flash`).

### 2.3 Macro Intelligence (Systemic Risk & AI Briefs)
1. Switch to **Macro Intelligence** in the top navigation bar.
2. **Systemic Risk Scoreboard:** Displays 6 real-time macro and market metrics:
   - **RBA Cash Rate Target** (`RBA/F1_1/FIRMMCRT`)
   - **US 10Y-2Y Yield Spread** (`FRED/RATES/T10Y2Y` — flags `INVERTED` when $< 0\text{ bps}$)
   - **AU Trimmed Mean CPI YoY** (`RBA/G1/GCPIOCPMTMYP` — flags `ABOVE TARGET` when $> 3.0\%$)
   - **AUD/USD Spot** (`YAHOO_FINANCE/FX/AUDUSD`)
   - **Iron Ore 62% Fe CFR** (`YAHOO_FINANCE/COMMODITIES/IRON_ORE`)
   - **CBOE Volatility Index (VIX)** (`YAHOO_FINANCE/INDICES/VIX`)
3. **Sync Macro Bundle & Brief:** Click **Sync Macro Bundle & Brief** to pull the latest observations from all configured connectors into DuckDB and generate a dated **Executive AI Macro Brief** (`macro_briefs` table) using local Apple Silicon MLX (`mlx-lm` on `arm64`) with deterministic analytical synthesis fallback.

## 3. In-App API Key & Environment Configuration (`.env`)
You can configure your API keys either directly in the Web UI or via `.env`:
1. **In-App Configuration (Recommended):**
   - Switch to **Analytics & SQL Workbench** and click **Configure API Key** (or `API Key (...)`) in the top-right header of the **AI Economist Assistant** panel.
   - Paste your **Gemini API Key** (`AIza...`), choose your preferred model (`gemini-3.8-flash`, `gemini-4-argon`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`), and optionally enter your **FRED API Key**.
   - Click **Save & Apply** — keys are written to `.env` (`0600` permissions) and hot-reloaded in memory immediately without restarting the server.
2. **Manual `.env` Configuration:**
   - `FRED_API_KEY`: Enables live Federal Reserve (`FRED`) series ingestion.
   - `GEMINI_API_KEY`: Enables the Gemini 3.8 Interactions API Economist Assistant.
   - `DBNOMICS_BROWSER_HF_CACHE_DIR`: Central Hugging Face cache directory (`/Users/jasondavey/.cache/huggingface`).
