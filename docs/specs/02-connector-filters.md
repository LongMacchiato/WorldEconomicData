# Technical Specification: Connector & Source-Type Filters (SDMX, DBnomics, Central Banks, Financial)

## 1. User Stories ("Who, What, Why")
- **US-01 (Connector Filter Bar in Catalogue Browser):** As an economic researcher, I want a connector filter bar (`All`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) with live provider counts in Section **01 Choose a provider**, so I can immediately filter between direct SDMX agencies (`SDMX_ABS`, `SDMX_BIS`, `SDMX1_*`), DBnomics providers, direct central bank connectors (`RBA`, `FRED`), and financial feeds (`YAHOO_FINANCE`).
- **US-02 (Connector Source Badges & Persisted Filter State):** As a user, I want each provider card to display a clear connector badge (`SDMX`, `DBnomics`, `Central Bank`, `Financial`) and persist my active connector filter in `localStorage` (`dbnomics-browser-state`).
- **US-03 (Connector Filter in Analytics Database Workbench):** As an analyst managing synced series in DuckDB, I want a connector filter bar in the **Analytics Database** tab so I can filter stored series by source connector (`All`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`).
- **US-04 (Server-Side `source_type` Filter on `/api/providers`):** As an API consumer, I want `GET /api/providers?source_type=sdmx|dbnomics|central_bank|financial` to support optional server-side filtering by connector source type.

---

## 2. Technical Constraints
- **Hardware & Runtime:** Native macOS Apple Silicon (`arm64`), Python 3.14 (`.venv`), Node.js 24 (`frontend/`).
- **Performance:** Instant client-side `useMemo` filtering across 120+ providers (< 2 ms) combined with text search (`providerSearch`).
- **UI & Accessibility (`impeccable` Standard — Rule 30):**
  - Apply `tabular-nums` to all filter badge counts.
  - Use accessible `aria-pressed` filter buttons and semantic `role="group"` filter toolbars.
  - Avoid card-in-card nesting; use clean, high-contrast neutral and blue pill controls matching the existing `zinc`/`blue` design system.

---

## 3. Data Schema & Types

### Frontend Types (`frontend/src/types.ts`)
```ts
export type ProviderSourceType = 'dbnomics' | 'sdmx' | 'central_bank' | 'financial'
export type ProviderSourceFilter = 'all' | ProviderSourceType

export interface Provider {
  code: string
  name: string
  region: string | null
  website: string | null
  source_type?: ProviderSourceType
  requires_api_key?: boolean
}
```

### Persisted Browser State (`frontend/src/App.tsx`)
```ts
interface PersistedBrowserState {
  providerCode: string | null
  providerSourceFilter: ProviderSourceFilter
  datasetCode: string | null
  dimensionSelections: DimensionSelections
  selectedSeriesCodes: string[]
  startPeriod: string
  endPeriod: string
}
```

---

## 4. Documentation & Support Impact
- **User Guide (`docs/user-guide/user-manual.md`):** Document the new Connector Filter bar (`All`, `SDMX`, `DBnomics`, `Central Banks`, `Financial`) in both the **Catalogue Browser** and **Analytics Database** tabs.
- **Support Runbook (`docs/support/troubleshooting.md`):** Add verification commands for `GET /api/providers?source_type=sdmx` and troubleshooting guidance if new `SDMX1_*` connectors do not appear until the backend `uvicorn` worker is reloaded.
- **Developer Docs (`README.md` & `CHANGELOG.md`):** Document the `?source_type=` query parameter on `GET /api/providers` and record the feature in `CHANGELOG.md`.
