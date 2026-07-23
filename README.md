# DBnomics Data Browser

A web application for discovering, filtering, previewing, and downloading public
economic time series from [DBnomics](https://db.nomics.world/). The React
interface uses a FastAPI backend that browses the DBnomics Web API catalogue and
fetches observations with the official Python
[`dbnomics`](https://pypi.org/project/dbnomics/) client.

## Architecture

```text
React + Vite  ->  FastAPI  ->  DBnomics Web API (catalogue)
                         \->  dbnomics.fetch_series (observations)
                         \->  TTL metadata cache
```

Provider, dataset, and series discovery use `https://api.db.nomics.world/v22`.
Observation queries call `fetch_series` and return tabular records plus
chart-ready series for preview and CSV or JSON download.

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

Start the API (from the repository root):

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
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

Open `http://localhost:5173`. The API documentation is available at
`http://localhost:8000/docs`.

Set `VITE_API_BASE_URL` when the API is hosted elsewhere. Backend settings use
the `DBNOMICS_BROWSER_` prefix; available limits and CORS defaults are defined in
`backend/app/config.py`.

## API

- `GET /health`
- `GET /api/providers`
- `GET /api/providers/{provider_code}`
- `GET /api/providers/{provider_code}/datasets?search=`
- `GET /api/providers/{provider_code}/datasets/{dataset_code}`
- `GET /api/search?q=`
- `GET /api/providers/{provider_code}/datasets/{dataset_code}/series`
- `POST /api/query/preview`
- `POST /api/query/download?format=csv|json`

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
