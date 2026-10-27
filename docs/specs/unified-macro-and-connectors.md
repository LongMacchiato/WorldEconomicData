# Specification: WorldEconomicData Rebrand & In-App API Key Configuration

## 1. User Stories ("Who, What, Why")
- **US-01 (In-App Gemini API Key Configuration)**: As an economist or analyst using the AI Economist Assistant, I want to enter, validate, and save my Google Gemini API Key (`GEMINI_API_KEY`) and preferred model (`gemini-3.8-flash` / `gemini-4-argon` / `gemini-3.5-flash-lite`) directly in the Web UI (and optionally my `FRED_API_KEY`) so that I can activate live Gemini 3.8 Interactions API tool-calling immediately without manually editing `.env` or restarting the backend server.
- **US-02 (Masked Status & Hot-Reload)**: As a user, I want the UI to show whether my `GEMINI_API_KEY` and `FRED_API_KEY` are currently configured (with a masked preview such as `AIza...7x9Q`, never exposing the full secret in plaintext GET responses) and hot-reload the running `AIAssistantService` and `FredConnector` instances as soon as I save.
- **US-03 (Unified `WorldEconomicData` Application, Folder & GitHub Rename)**: As the project owner, I want the application UI, metadata (`pyproject.toml`, `package.json`, `index.html`, `main.py`, `mcp_server.py`), local folder (`/Users/jasondavey/Projects/Tools/Data Acquisition/WorldEconomicData`), and GitHub repository (`LongMacchiato/WorldEconomicData`) unified under the name **WorldEconomicData**.

## 2. Technical Constraints & Security
- **Hardware / Runtime**: macOS on Apple Silicon (`arm64`), FastAPI + Pydantic Settings backend, React 19 + TypeScript + Tailwind CSS v4 frontend.
- **Secret Storage (Rule 39 & 41)**:
  - Keys are persisted strictly to the untracked `/Users/jasondavey/Projects/Tools/Data Acquisition/DBnomics/.env` file (`0600` permissions) and updated in-memory in `os.environ` + cached FastAPI singletons (`get_settings.cache_clear()`, `get_ai_assistant_service.cache_clear()`, `get_dbnomics_service.cache_clear()`, `get_composite_catalog_service.cache_clear()`).
  - `GET /api/analytics/ai/config` never returns raw secret values—only `gemini_key_configured: bool`, `gemini_key_masked: str | None`, `gemini_model: str`, `fred_key_configured: bool`, and `fred_key_masked: str | None`.
  - No API keys or tokens are ever logged.

## 3. Data Schema
### `AiConfigStatus` (`GET /api/analytics/ai/config`)
```json
{
  "gemini_key_configured": true,
  "gemini_key_masked": "AIza...9xYz",
  "gemini_model": "gemini-3.8-flash",
  "fred_key_configured": false,
  "fred_key_masked": null
}
```

### `AiConfigUpdateRequest` (`PUT /api/analytics/ai/config`)
```json
{
  "gemini_api_key": "AIzaSy...",
  "gemini_model": "gemini-3.8-flash",
  "fred_api_key": "optional_32_char_fred_key"
}
```

## 4. Documentation & Support Impact
- **User Guide**: Update [`docs/user-guide/user-manual.md`](file:///Users/jasondavey/Projects/Tools/Data%20Acquisition/DBnomics/docs/user-guide/user-manual.md) with instructions for configuring `GEMINI_API_KEY` and `FRED_API_KEY` via the in-app **API Key Settings** panel in the AI Economist Assistant (and header settings modal).
- **Support & Troubleshooting**: Update [`docs/support/troubleshooting.md`](file:///Users/jasondavey/Projects/Tools/Data%20Acquisition/DBnomics/docs/support/troubleshooting.md) with verification steps for `GET /api/analytics/ai/config` and troubleshooting invalid/non-`AIza` keys.
