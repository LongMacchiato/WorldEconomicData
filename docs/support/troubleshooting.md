# Troubleshooting & Operational Runbook

## 1. Health & Verification Checks

Run these checks to verify backend, connector filters, and DuckDB warehouse health:

```bash
# 1. Core API health
curl -s http://localhost:8001/health

# 2. Verify Connector Source-Type Filtering on /api/providers
curl -s "http://localhost:8001/api/providers?source_type=sdmx" | python3 -m json.tool
curl -s "http://localhost:8001/api/providers?source_type=central_bank" | python3 -m json.tool

# 3. Direct Connector Registry & Macro Scoreboard status
curl -s http://localhost:8001/api/macro/status | python3 -m json.tool

# 4. DuckDB Analytics Warehouse summary
curl -s http://localhost:8001/api/analytics/catalog | python3 -m json.tool
```

---

## 2. Troubleshooting Matrix (`Symptom -> Root Cause -> Resolution`)

| Symptom / Error Message | Root Cause | Resolution Steps |
| :--- | :--- | :--- |
| **"No providers match your current connector filter or search."** | A specific connector filter (`SDMX`, `Central Banks`, `Financial`, `DBnomics`) is active while searching for a provider from a different connector category. | Click **All Connectors** in the Connector Filter Bar (Section `01 Choose a provider`) or clear the search input. |
| **`FRED_API_KEY is not configured in .env`** (or `FRED` badge shows `Key Needed`) | `FRED_API_KEY` is missing or empty in `/Users/jasondavey/Projects/Tools/Data Acquisition/WorldEconomicData/.env`. | 1. Configure via the in-app **API Keys & Model Configuration** drawer in the AI Economist Assistant, or add `FRED_API_KEY=<your_32_char_key>` to `.env`.<br>2. Click **Sync Macro Bundle & Brief**. |
| **`PermissionError: [Errno 1] Operation not permitted: '~/.cache/huggingface'`** | macOS sandbox or directory permissions block writes to the user-global Hugging Face cache. | Automatically handled by `MlxMacroService`, which sets `HF_HOME` to `/Users/jasondavey/.cache/huggingface` (configurable via `DBNOMICS_BROWSER_HF_CACHE_DIR`). |
| **`Macro Intelligence` charts show "Click Sync Macro Bundle & Brief"** | Fresh DuckDB database does not yet contain the core RBA/Yahoo Finance/FRED series. | Click **Sync Macro Bundle & Brief** in the top-right of the **Macro Intelligence** tab (or `POST /api/macro/refresh`). |
| **Address already in use (`Port 8001`)** | An existing `uvicorn` process is already bound to port `8001`. | Check `lsof -i :8001` and restart via `./start.sh` or `uvicorn app.main:app --app-dir backend --reload --port 8001`. |
