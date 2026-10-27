"""Generic SDMX 2.1 / 3.0 REST CSV connector for national & international agencies."""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from typing import Any

import httpx
import pandas as pd
from app.domain.connector_protocols import ProviderSourceType, SdmxEndpointConfig
from app.exceptions import (
    DatasetNotFoundError,
    SeriesNotFoundError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from app.models import (
    Dataset,
    DatasetDetail,
    Dimension,
    DimensionCode,
    Provider,
    QueryRequest,
    SeriesPage,
)
from app.services.connectors.sdmx_catalog_defs import (
    ABS_DATASETS,
    BBK_DATASETS,
    BFS_CH_DATASETS,
    BIS_DATASETS,
    DEFAULT_SDMX_ENDPOINTS,
    FAO_DATASETS,
    STATCAN_DATASETS,
    STATSNZ_DATASETS,
    WB_WDI_DATASETS,
    SdmxDatasetSpec,
)
from app.services.connectors.sdmx_csv_helpers import (
    extract_dimension_columns,
    extract_series_summaries,
    normalize_sdmx_observations,
)

__all__ = [
    "ABS_DATASETS",
    "BBK_DATASETS",
    "BFS_CH_DATASETS",
    "BIS_DATASETS",
    "DEFAULT_SDMX_ENDPOINTS",
    "FAO_DATASETS",
    "STATCAN_DATASETS",
    "STATSNZ_DATASETS",
    "WB_WDI_DATASETS",
    "SdmxConnector",
    "SdmxDatasetSpec",
    "build_default_sdmx_connectors",
]

TextFetchFn = Callable[[str, Mapping[str, Any]], str]


class SdmxConnector:
    """Direct SDMX REST CSV connector implementing DataConnectorProtocol."""

    def __init__(
        self,
        config: SdmxEndpointConfig,
        datasets: tuple[SdmxDatasetSpec, ...],
        *,
        text_fetcher: TextFetchFn | None = None,
        timeout_seconds: float = 25.0,
    ) -> None:
        """Initialize the SDMX connector.

        Args:
            config: SDMX endpoint configuration.
            datasets: Curated SDMX dataflow specifications.
            text_fetcher: Optional HTTP text fetcher override for unit testing.
            timeout_seconds: Request timeout in seconds.
        """
        self._config = config
        self._datasets = {spec.code.upper(): spec for spec in datasets}
        self._fetch_text = text_fetcher or self._default_fetch_text
        self._timeout = timeout_seconds

    @property
    def provider_code(self) -> str:
        """Return uppercase provider code."""
        return self._config.provider_code

    @property
    def source_type(self) -> ProviderSourceType:
        """Return SDMX source type."""
        return ProviderSourceType.sdmx

    def get_provider(self) -> Provider:
        """Return Provider metadata."""
        return Provider(
            code=self._config.provider_code,
            name=self._config.provider_name,
            region=self._config.region,
            website=self._config.website,
            source_type=ProviderSourceType.sdmx.value,
            requires_api_key=False,
        )

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List available SDMX dataflows with optional substring search."""
        items = [
            Dataset(
                provider_code=self.provider_code,
                code=spec.code,
                name=spec.name,
                description=spec.description,
            )
            for spec in self._datasets.values()
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
        """Return DatasetDetail and inferred dimensions for an SDMX dataflow."""
        spec = self._get_spec(dataset_code)
        df = self._load_sdmx_frame(spec, last_n=5)
        dim_cols = extract_dimension_columns(df)
        dimensions = [
            Dimension(
                code=col,
                label=col,
                values=[
                    DimensionCode(code=str(val), label=str(val))
                    for val in sorted(df[col].dropna().astype(str).unique())[:40]
                ],
            )
            for col in dim_cols
        ]
        return DatasetDetail(
            provider_code=self.provider_code,
            code=spec.code,
            name=spec.name,
            description=spec.description,
            nb_series=None,
            dimensions=dimensions,
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
        """List distinct series inside an SDMX dataflow."""
        spec = self._get_spec(dataset_code)
        df = self._load_sdmx_frame(spec, last_n=2)
        summaries = extract_series_summaries(
            self.provider_code, spec.code, df, search=search, dimensions=dimensions
        )
        page_limit = limit or 50
        sliced = summaries[offset : offset + page_limit]
        return SeriesPage(
            items=sliced,
            offset=offset,
            limit=page_limit,
            num_found=len(summaries),
            has_next_page=offset + len(sliced) < len(summaries),
        )

    def fetch_observations(self, query: QueryRequest) -> pd.DataFrame:
        """Fetch and normalize SDMX observations for selected series codes."""
        spec = self._get_spec(query.dataset_code)
        df = self._load_sdmx_frame(spec, last_n=40)
        normalized = normalize_sdmx_observations(
            self.provider_code,
            spec.code,
            df,
            selected_codes=set(query.series_codes),
        )
        if normalized.empty:
            raise SeriesNotFoundError(
                f"No observations matched {query.series_codes} in {spec.code}"
            )
        if query.start_period:
            normalized = normalized[
                normalized["period"].astype(str) >= query.start_period
            ]
        if query.end_period:
            normalized = normalized[
                normalized["period"].astype(str) <= query.end_period
            ]
        return normalized.reset_index(drop=True)

    def _get_spec(self, dataset_code: str) -> SdmxDatasetSpec:
        spec = self._datasets.get(dataset_code.upper())
        if spec is None:
            raise DatasetNotFoundError(
                f"SDMX dataset {self.provider_code}/{dataset_code} not found"
            )
        return spec

    def _load_sdmx_frame(self, spec: SdmxDatasetSpec, *, last_n: int) -> pd.DataFrame:
        url = (
            f"{self._config.base_url.rstrip('/')}/data/"
            f"{spec.dataflow_ref}/{spec.key_filter}"
        )
        csv_text = self._fetch_text(url, {"format": "csv", "lastNObservations": last_n})
        try:
            df = pd.read_csv(io.StringIO(csv_text), low_memory=False)
        except Exception as error:
            raise UpstreamResponseError(f"Invalid SDMX CSV payload: {error}") from error
        df.columns = [str(c).strip() for c in df.columns]
        return df

    def _default_fetch_text(self, url: str, params: Mapping[str, Any]) -> str:
        try:
            response = httpx.get(
                url,
                params=dict(params),
                headers={"Accept": "text/csv"},
                timeout=self._timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as error:
            raise UpstreamUnavailableError(f"SDMX request failed: {error}") from error


def build_default_sdmx_connectors() -> list[SdmxConnector]:
    """Create the default direct SDMX connectors across national & global agencies."""
    return [
        SdmxConnector(config=config, datasets=datasets)
        for config, datasets in DEFAULT_SDMX_ENDPOINTS
    ]
