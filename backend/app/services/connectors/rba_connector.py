"""Direct Reserve Bank of Australia (RBA) statistical tables CSV connector."""

from __future__ import annotations

import io
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


@dataclass(frozen=True)
class RbaTableSpec:
    """RBA statistical CSV table specification."""

    code: str
    name: str
    description: str
    url: str
    frequency: str
    series_labels: Mapping[str, str]


RBA_TABLES: dict[str, RbaTableSpec] = {
    "F1_1": RbaTableSpec(
        code="F1_1",
        name="Interest Rates and Yields - Money Market (F1.1)",
        description=(
            "RBA Cash Rate Target, Interbank Overnight Rate, and Bank Accepted Bills."
        ),
        url="https://www.rba.gov.au/statistics/tables/csv/f1.1-data.csv",
        frequency="monthly",
        series_labels={
            "FIRMMCRT": "Cash Rate Target (%)",
            "FIRMMCRI": "Interbank Overnight Cash Rate (%)",
            "FIRMMBAB30": "30-Day Bank Accepted Bills (%)",
            "FIRMMBAB90": "90-Day Bank Accepted Bills (%)",
            "FIRMMBAB180": "180-Day Bank Accepted Bills (%)",
        },
    ),
    "G1": RbaTableSpec(
        code="G1",
        name="Consumer Price Inflation (G1)",
        description=(
            "Headline CPI, RBA Trimmed Mean CPI, and Weighted Median Inflation."
        ),
        url="https://www.rba.gov.au/statistics/tables/csv/g1-data.csv",
        frequency="quarterly",
        series_labels={
            "GCPIOCPMTMYP": "Year-ended Trimmed Mean Inflation (%)",
            "GCPIOCPMTMQP": "Quarterly Trimmed Mean Inflation (%)",
            "GCPIOCPMWMYP": "Year-ended Weighted Median Inflation (%)",
            "GCPIAGYP": "Year-ended All Groups CPI Inflation (%)",
            "GCPIAGQP": "Quarterly All Groups CPI Inflation (%)",
            "GCPITIYP": "Year-ended Tradables Inflation (%)",
            "GCPINTIYP": "Year-ended Non-Tradables Inflation (%)",
        },
    ),
}

CsvFetchFn = Callable[[str], str]


class RbaConnector:
    """Direct RBA CSV connector implementing DataConnectorProtocol."""

    def __init__(
        self,
        *,
        csv_fetcher: CsvFetchFn | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        """Initialize the RBA connector.

        Args:
            csv_fetcher: Optional CSV HTTP fetcher override for testing.
            timeout_seconds: HTTP timeout in seconds.
        """
        self._fetch_csv = csv_fetcher or self._default_fetch_csv
        self._timeout = timeout_seconds

    @property
    def provider_code(self) -> str:
        """Return RBA provider code."""
        return "RBA"

    @property
    def source_type(self) -> ProviderSourceType:
        """Return central_bank source type."""
        return ProviderSourceType.central_bank

    def get_provider(self) -> Provider:
        """Return RBA Provider metadata."""
        return Provider(
            code="RBA",
            name="Reserve Bank of Australia (Direct Statistical Tables)",
            region="Australia",
            website="https://www.rba.gov.au/statistics/tables/",
            source_type=ProviderSourceType.central_bank.value,
            requires_api_key=False,
        )

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List available RBA statistical tables."""
        items = [
            Dataset(
                provider_code=self.provider_code,
                code=spec.code,
                name=spec.name,
                description=spec.description,
                nb_series=len(spec.series_labels),
            )
            for spec in RBA_TABLES.values()
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
        """Return DatasetDetail for an RBA statistical table."""
        spec = self._get_spec(dataset_code)
        return DatasetDetail(
            provider_code=self.provider_code,
            code=spec.code,
            name=spec.name,
            description=spec.description,
            nb_series=len(spec.series_labels),
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
        """List curated and discovered series in an RBA table."""
        _ = dimensions
        spec = self._get_spec(dataset_code)
        items = [
            SeriesSummary(
                provider_code=self.provider_code,
                dataset_code=spec.code,
                series_code=code,
                series_name=label,
                dimensions={"frequency": spec.frequency, "unit": "Percent"},
            )
            for code, label in spec.series_labels.items()
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
        """Fetch and parse RBA CSV observations for the requested series."""
        spec = self._get_spec(query.dataset_code)
        csv_text = self._fetch_csv(spec.url)
        frame = _parse_rba_csv(
            csv_text,
            spec=spec,
            selected_codes=set(query.series_codes),
        )
        if frame.empty:
            raise SeriesNotFoundError(
                f"No RBA observations found for {query.series_codes} in {spec.code}"
            )
        if query.start_period:
            frame = frame[frame["period"].astype(str) >= query.start_period]
        if query.end_period:
            frame = frame[frame["period"].astype(str) <= query.end_period]
        return frame.reset_index(drop=True)

    def _get_spec(self, dataset_code: str) -> RbaTableSpec:
        spec = RBA_TABLES.get(dataset_code.upper())
        if spec is None:
            raise DatasetNotFoundError(f"RBA dataset {dataset_code!r} was not found")
        return spec

    def _default_fetch_csv(self, url: str) -> str:
        try:
            response = httpx.get(url, timeout=self._timeout, follow_redirects=True)
            response.raise_for_status()
            return response.content.decode("utf-8", errors="replace")
        except httpx.HTTPError as error:
            raise UpstreamUnavailableError(f"RBA CSV fetch failed: {error}") from error


def _parse_rba_csv(
    csv_text: str,
    *,
    spec: RbaTableSpec,
    selected_codes: set[str],
) -> pd.DataFrame:
    lines = csv_text.splitlines()
    header_idx = 0
    for idx, line in enumerate(lines[:20]):
        if line.startswith("Series ID"):
            header_idx = idx
            break
    try:
        df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    except Exception as error:
        raise UpstreamResponseError(f"Failed to parse RBA CSV: {error}") from error

    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    records: list[dict[str, Any]] = []
    target_cols = [c for c in df.columns[1:] if c in selected_codes]
    if not target_cols:
        return pd.DataFrame()

    for _, row in df.iterrows():
        dt = pd.to_datetime(str(row[date_col]), format="%d/%m/%Y", errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(str(row[date_col]), dayfirst=True, errors="coerce")
        if pd.isna(dt):
            continue
        period_str = dt.strftime("%Y-%m-%d")
        for col in target_cols:
            try:
                numeric_val = float(row[col])
            except TypeError, ValueError:
                continue
            if pd.isna(numeric_val):
                continue
            records.append(
                {
                    "provider_code": "RBA",
                    "dataset_code": spec.code,
                    "series_code": col,
                    "series_name": spec.series_labels.get(col, col),
                    "period": period_str,
                    "value": numeric_val,
                    "@frequency": spec.frequency,
                    "unit": "Percent",
                }
            )
    return pd.DataFrame(records)
