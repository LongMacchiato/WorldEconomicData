"""Direct Federal Reserve Economic Data (FRED) API connector."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd
from app.domain.connector_protocols import ProviderSourceType
from app.exceptions import (
    DatasetNotFoundError,
    SeriesNotFoundError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from app.models import (
    Dataset,
    DatasetDetail,
    Provider,
    QueryRequest,
    SeriesPage,
    SeriesSummary,
)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


@dataclass(frozen=True)
class FredDatasetSpec:
    """Curated grouping of FRED macro-economic and yield series."""

    code: str
    name: str
    description: str
    series: Mapping[str, tuple[str, str, str]]


FRED_DATASETS: dict[str, FredDatasetSpec] = {
    "RATES": FredDatasetSpec(
        code="RATES",
        name="US Treasury Yields & Yield Curve Spreads",
        description="Constant maturity US Treasury yields and recession curve spreads.",
        series={
            "T10Y2Y": (
                "10-Year Minus 2-Year Treasury Yield Spread",
                "Percent",
                "daily",
            ),
            "GS10": (
                "10-Year Treasury Constant Maturity Rate (Monthly)",
                "Percent",
                "monthly",
            ),
            "DGS10": (
                "10-Year Treasury Constant Maturity Rate (Daily)",
                "Percent",
                "daily",
            ),
            "DGS2": (
                "2-Year Treasury Constant Maturity Rate (Daily)",
                "Percent",
                "daily",
            ),
            "FEDFUNDS": ("Effective Federal Funds Rate", "Percent", "monthly"),
        },
    ),
    "MONETARY": FredDatasetSpec(
        code="MONETARY",
        name="Federal Reserve Balance Sheet & Liquidity",
        description="Fed total assets, M2 money stock, and reserve balances.",
        series={
            "WALCL": (
                "Assets: Total Assets (Less Eliminations from Consolidation)",
                "Millions of USD",
                "weekly",
            ),
            "M2SL": ("M2 Money Stock", "Billions of USD", "monthly"),
        },
    ),
    "MACRO": FredDatasetSpec(
        code="MACRO",
        name="US Core Macro Indicators (Inflation, GDP & Labor)",
        description="US CPI, Core PCE, Real GDP, and Unemployment Rate.",
        series={
            "CPIAUCSL": (
                "Consumer Price Index for All Urban Consumers",
                "Index",
                "monthly",
            ),
            "UNRATE": ("US Civilian Unemployment Rate", "Percent", "monthly"),
            "GDPC1": (
                "Real Gross Domestic Product",
                "Billions of Chained 2017 Dollars",
                "quarterly",
            ),
        },
    ),
}

JsonFetchFn = Callable[[str, Mapping[str, Any]], dict[str, Any]]


class FredConnector:
    """Direct St. Louis Fed (FRED) REST API connector."""

    def __init__(
        self,
        api_key: str | None,
        *,
        json_fetcher: JsonFetchFn | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        """Initialize the FRED connector.

        Args:
            api_key: St. Louis Fed API key (`FRED_API_KEY`).
            json_fetcher: Optional HTTP JSON fetcher override for testing.
            timeout_seconds: Request timeout in seconds.
        """
        self._api_key = (api_key or "").strip() or None
        self._fetch_json = json_fetcher or self._default_fetch_json
        self._timeout = timeout_seconds

    @property
    def provider_code(self) -> str:
        """Return FRED provider code."""
        return "FRED"

    @property
    def source_type(self) -> ProviderSourceType:
        """Return central_bank source type."""
        return ProviderSourceType.central_bank

    @property
    def is_configured(self) -> bool:
        """Return True if a valid FRED API key is configured."""
        return bool(self._api_key and self._api_key != "your_fred_api_key_here")

    def get_provider(self) -> Provider:
        """Return Provider metadata for FRED."""
        return Provider(
            code="FRED",
            name="Federal Reserve Economic Data (Direct St. Louis Fed API)",
            region="United States",
            website="https://fred.stlouisfed.org",
            source_type=ProviderSourceType.central_bank.value,
            requires_api_key=True,
        )

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List curated FRED dataset groupings."""
        items = [
            Dataset(
                provider_code=self.provider_code,
                code=spec.code,
                name=spec.name,
                description=spec.description,
                nb_series=len(spec.series),
            )
            for spec in FRED_DATASETS.values()
        ]
        if not search or not search.strip():
            return items
        needle = search.strip().casefold()
        return [
            d
            for d in items
            if needle in d.code.casefold()
            or needle in d.name.casefold()
            or (d.description and needle in d.description.casefold())
        ]

    def get_dataset(self, dataset_code: str) -> DatasetDetail:
        """Return DatasetDetail for a FRED dataset grouping."""
        spec = self._get_spec(dataset_code)
        return DatasetDetail(
            provider_code=self.provider_code,
            code=spec.code,
            name=spec.name,
            description=spec.description,
            nb_series=len(spec.series),
            dimensions=[],
        )

    def list_series(
        self,
        dataset_code: str,
        *,
        search: str | None = None,
        dimensions: Mapping[str, list[str]] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> SeriesPage:
        """List series in a FRED dataset grouping."""
        _ = dimensions
        spec = self._get_spec(dataset_code)
        items = [
            SeriesSummary(
                provider_code=self.provider_code,
                dataset_code=spec.code,
                series_code=code,
                series_name=meta[0],
                dimensions={"unit": meta[1], "frequency": meta[2]},
            )
            for code, meta in spec.series.items()
        ]
        if search and search.strip():
            needle = search.strip().casefold()
            items = [
                s
                for s in items
                if needle in s.series_code.casefold()
                or needle in s.series_name.casefold()
            ]
        page_limit = limit or 50
        sliced = items[offset : offset + page_limit]
        return SeriesPage(
            items=sliced,
            offset=offset,
            limit=page_limit,
            num_found=len(items),
            has_next_page=offset + len(sliced) < len(items),
        )

    def fetch_observations(self, query: QueryRequest) -> pd.DataFrame:
        """Fetch real-time observations from FRED API for selected series codes."""
        if not self.is_configured:
            raise UpstreamUnavailableError(
                "FRED_API_KEY is not configured in .env. "
                "Set FRED_API_KEY to fetch live FRED series."
            )
        spec = self._get_spec(query.dataset_code)
        records: list[dict[str, Any]] = []
        for series_code in query.series_codes:
            meta = spec.series.get(series_code.upper(), (series_code, "Units", "daily"))
            params: dict[str, Any] = {
                "series_id": series_code.upper(),
                "api_key": self._api_key,
                "file_type": "json",
            }
            if query.start_period:
                params["observation_start"] = query.start_period
            if query.end_period:
                params["observation_end"] = query.end_period
            payload = self._fetch_json(FRED_OBSERVATIONS_URL, params)
            for obs in payload.get("observations") or []:
                raw_val = obs.get("value")
                if raw_val in (None, ".", ""):
                    continue
                try:
                    numeric_val = float(raw_val)
                except TypeError, ValueError:
                    continue
                records.append(
                    {
                        "provider_code": self.provider_code,
                        "dataset_code": spec.code,
                        "series_code": series_code.upper(),
                        "series_name": meta[0],
                        "period": str(obs.get("date") or ""),
                        "value": numeric_val,
                        "@frequency": meta[2],
                        "unit": meta[1],
                    }
                )
        if not records:
            raise SeriesNotFoundError(
                f"No FRED observations returned for {query.series_codes}"
            )
        return pd.DataFrame(records)

    def _get_spec(self, dataset_code: str) -> FredDatasetSpec:
        spec = FRED_DATASETS.get(dataset_code.upper())
        if spec is None:
            raise DatasetNotFoundError(f"FRED dataset {dataset_code!r} was not found")
        return spec

    def _default_fetch_json(
        self, url: str, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            response = httpx.get(url, params=dict(params), timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise UpstreamResponseError("FRED API returned non-object JSON")
            return data
        except httpx.HTTPError as error:
            raise UpstreamUnavailableError(
                f"FRED API request failed: {error}"
            ) from error
