from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast
from urllib.parse import quote

import httpx
import pandas as pd
from app.config import Settings
from app.exceptions import (
    DatasetNotFoundError,
    ProviderNotFoundError,
    ResultLimitExceededError,
    SeriesNotFoundError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from app.models import (
    ChartPoint,
    ChartSeries,
    Dataset,
    DatasetDetail,
    Dimension,
    DimensionCode,
    Provider,
    QueryRequest,
    SeriesPage,
    SeriesSummary,
)
from cachetools import TTLCache
from dbnomics import fetch_series

HttpGet = Callable[[str, Mapping[str, Any] | None], dict[str, Any]]
FetchSeriesFn = Callable[..., pd.DataFrame]


class DBnomicsService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_get: HttpGet | None = None,
        fetch_series_fn: FetchSeriesFn | None = None,
    ) -> None:
        self._settings = settings
        self._http_get = http_get or self._default_http_get
        self._fetch_series: FetchSeriesFn = fetch_series_fn or cast(
            FetchSeriesFn, fetch_series
        )
        self._cache: TTLCache[str, Any] = TTLCache(
            maxsize=settings.metadata_cache_max_size,
            ttl=settings.metadata_cache_ttl_seconds,
        )

    def list_providers(self) -> list[Provider]:
        cache_key = "providers"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cast(list[Provider], cached)

        providers: list[Provider] = []
        offset = 0
        page_limit = self._settings.providers_page_limit
        while True:
            payload = self._http_get(
                "/providers",
                {"limit": page_limit, "offset": offset},
            )
            page = payload.get("providers") or {}
            docs = page.get("docs") or []
            for document in docs:
                providers.append(
                    Provider(
                        code=str(document["code"]),
                        name=str(document.get("name") or document["code"]),
                        region=_optional_str(document.get("region")),
                        website=_optional_str(document.get("website")),
                    )
                )
            num_found = int(page.get("num_found") or len(providers))
            offset += len(docs)
            if offset >= num_found or not docs:
                break

        providers.sort(key=lambda provider: provider.code.lower())
        self._cache[cache_key] = providers
        return providers

    def get_provider(self, provider_code: str) -> Provider:
        providers = self.list_providers()
        for provider in providers:
            if provider.code.upper() == provider_code.upper():
                return provider
        raise ProviderNotFoundError(f"Provider {provider_code!r} was not found")

    def list_datasets(
        self,
        provider_code: str,
        search: str | None = None,
    ) -> list[Dataset]:
        provider = self.get_provider(provider_code)
        cache_key = f"datasets:{provider.code.upper()}"
        cached = self._cache.get(cache_key)
        if cached is None:
            datasets = self._fetch_all_datasets(provider.code)
            self._cache[cache_key] = datasets
        else:
            datasets = cast(list[Dataset], cached)

        if not search or not search.strip():
            return datasets

        needle = search.strip().casefold()
        return [
            dataset
            for dataset in datasets
            if needle in dataset.code.casefold()
            or needle in dataset.name.casefold()
            or (dataset.description and needle in dataset.description.casefold())
        ]

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        provider = self.get_provider(provider_code)
        cache_key = f"dataset:{provider.code.upper()}:{dataset_code}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cast(DatasetDetail, cached)

        payload = self._http_get(
            f"/datasets/{quote(provider.code, safe='')}/{quote(dataset_code, safe='')}",
            None,
        )
        docs = (payload.get("datasets") or {}).get("docs") or []
        if not docs:
            raise DatasetNotFoundError(
                f"Dataset {provider.code}/{dataset_code} was not found"
            )
        document = docs[0]
        detail = DatasetDetail(
            provider_code=provider.code,
            code=str(document.get("code") or dataset_code),
            name=str(document.get("name") or dataset_code),
            description=_optional_str(document.get("description")),
            nb_series=_optional_int(document.get("nb_series")),
            dimensions=_parse_dimensions(document),
        )
        self._cache[cache_key] = detail
        return detail

    def search_datasets(self, query: str, *, limit: int = 50) -> list[Dataset]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        payload = self._http_get(
            "/search",
            {"q": normalized_query, "limit": limit, "offset": 0},
        )
        docs = (payload.get("results") or {}).get("docs") or []
        datasets: list[Dataset] = []
        for document in docs:
            provider_code = document.get("provider_code")
            if not provider_code:
                continue
            datasets.append(
                Dataset(
                    provider_code=str(provider_code),
                    code=str(document.get("code") or ""),
                    name=str(document.get("name") or document.get("code") or ""),
                    description=_optional_str(document.get("description")),
                    nb_series=_optional_int(document.get("nb_series")),
                )
            )
        return datasets

    def list_series(
        self,
        provider_code: str,
        dataset_code: str,
        *,
        search: str | None = None,
        dimensions: Mapping[str, list[str]] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> SeriesPage:
        dataset = self.get_dataset(provider_code, dataset_code)
        page_limit = limit or self._settings.series_page_limit
        if page_limit > self._settings.series_max_page_limit:
            raise ResultLimitExceededError(
                "Series page limit cannot exceed "
                f"{self._settings.series_max_page_limit}"
            )

        params: dict[str, Any] = {
            "limit": page_limit,
            "offset": offset,
            "observations": 0,
        }
        if search and search.strip():
            params["q"] = search.strip()
        if dimensions:
            cleaned = {key: values for key, values in dimensions.items() if values}
            if cleaned:
                params["dimensions"] = json.dumps(cleaned, separators=(",", ":"))

        payload = self._http_get(
            (
                f"/series/{quote(dataset.provider_code, safe='')}/"
                f"{quote(dataset.code, safe='')}"
            ),
            params,
        )
        page = payload.get("series") or {}
        docs = page.get("docs") or []
        items = [
            SeriesSummary(
                provider_code=str(
                    document.get("provider_code") or dataset.provider_code
                ),
                dataset_code=str(document.get("dataset_code") or dataset.code),
                series_code=str(document["series_code"]),
                series_name=str(document.get("series_name") or document["series_code"]),
                dimensions={
                    str(key): str(value)
                    for key, value in (document.get("dimensions") or {}).items()
                },
            )
            for document in docs
        ]
        num_found = int(page.get("num_found") or len(items))
        return SeriesPage(
            items=items,
            offset=offset,
            limit=page_limit,
            num_found=num_found,
            has_next_page=offset + len(items) < num_found,
        )

    def execute_query(self, query: QueryRequest) -> pd.DataFrame:
        series_ids = [
            f"{query.provider_code}/{query.dataset_code}/{series_code}"
            for series_code in query.series_codes
        ]
        try:
            frame = self._fetch_series(series_ids)
        except Exception as error:
            message = str(error)
            if "404" in message or "not found" in message.casefold():
                raise SeriesNotFoundError(message) from error
            raise UpstreamResponseError(
                f"Failed to fetch series observations: {message}"
            ) from error

        if not isinstance(frame, pd.DataFrame):
            raise UpstreamResponseError("DBnomics client did not return a DataFrame")

        if frame.empty:
            return frame

        filtered = frame
        if "period" in filtered.columns:
            if query.start_period:
                filtered = filtered[
                    filtered["period"].astype(str) >= query.start_period
                ]
            if query.end_period:
                filtered = filtered[filtered["period"].astype(str) <= query.end_period]

        return filtered.reset_index(drop=True)

    def build_chart_series(self, frame: pd.DataFrame) -> list[ChartSeries]:
        if frame.empty:
            return []

        series_code_column = _first_present(
            frame.columns, ("series_code", "series", "code")
        )
        series_name_column = _first_present(
            frame.columns, ("series_name", "series_code", "series")
        )
        period_column = _first_present(frame.columns, ("period", "original_period"))
        value_column = _first_present(frame.columns, ("value", "original_value"))

        if period_column is None or value_column is None:
            return []

        chart_series: list[ChartSeries] = []
        if series_code_column is None:
            points = [
                ChartPoint(
                    period=str(row[period_column]),
                    value=_to_float(row[value_column]),
                )
                for _, row in frame.iterrows()
            ]
            chart_series.append(
                ChartSeries(series_code="series", series_name="series", points=points)
            )
            return chart_series

        for series_code, group in frame.groupby(series_code_column, sort=False):
            series_name = str(series_code)
            if series_name_column is not None:
                first_name = group[series_name_column].iloc[0]
                if first_name is not None and not (
                    isinstance(first_name, float) and pd.isna(first_name)
                ):
                    series_name = str(first_name)
            points = [
                ChartPoint(
                    period=str(row[period_column]),
                    value=_to_float(row[value_column]),
                )
                for _, row in group.iterrows()
            ]
            chart_series.append(
                ChartSeries(
                    series_code=str(series_code),
                    series_name=series_name,
                    points=points,
                )
            )
        return chart_series

    def _fetch_all_datasets(self, provider_code: str) -> list[Dataset]:
        datasets: list[Dataset] = []
        offset = 0
        page_limit = self._settings.datasets_page_limit
        while True:
            payload = self._http_get(
                f"/datasets/{quote(provider_code, safe='')}",
                {"limit": page_limit, "offset": offset},
            )
            page = payload.get("datasets") or {}
            docs = page.get("docs") or []
            for document in docs:
                datasets.append(
                    Dataset(
                        provider_code=provider_code,
                        code=str(document["code"]),
                        name=str(document.get("name") or document["code"]),
                        description=_optional_str(document.get("description")),
                        nb_series=_optional_int(document.get("nb_series")),
                    )
                )
            num_found = int(page.get("num_found") or len(datasets))
            offset += len(docs)
            if offset >= num_found or not docs:
                break
        return datasets

    def _default_http_get(
        self,
        path: str,
        params: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{self._settings.api_base_url.rstrip('/')}{path}"
        try:
            response = httpx.get(
                url,
                params=dict(params) if params else None,
                timeout=self._settings.upstream_timeout_seconds,
                follow_redirects=True,
            )
        except httpx.TimeoutException as error:
            raise UpstreamUnavailableError(
                f"DBnomics API timed out for {path}"
            ) from error
        except httpx.HTTPError as error:
            raise UpstreamUnavailableError(
                f"DBnomics API unavailable for {path}: {error}"
            ) from error

        if response.status_code == 404:
            raise DatasetNotFoundError(f"Resource not found: {path}")
        if response.status_code >= 500:
            raise UpstreamUnavailableError(
                f"DBnomics API error {response.status_code} for {path}"
            )
        if response.status_code >= 400:
            raise UpstreamResponseError(
                f"DBnomics API rejected request {path}: {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise UpstreamResponseError(
                f"DBnomics API returned invalid JSON for {path}"
            ) from error
        if not isinstance(payload, dict):
            raise UpstreamResponseError(
                f"DBnomics API returned unexpected payload for {path}"
            )
        return payload


def _parse_dimensions(document: Mapping[str, Any]) -> list[Dimension]:
    labels = document.get("dimensions_labels") or {}
    values_labels = document.get("dimensions_values_labels") or {}
    order = document.get("dimensions_codes_order") or list(labels.keys())
    dimensions: list[Dimension] = []
    for dimension_code in order:
        code = str(dimension_code)
        label = str(labels.get(code) or code)
        raw_values = values_labels.get(code) or {}
        values = [
            DimensionCode(code=str(value_code), label=str(value_label))
            for value_code, value_label in raw_values.items()
        ]
        values.sort(key=lambda item: item.code.lower())
        dimensions.append(Dimension(code=code, label=label, values=values))
    return dimensions


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _first_present(columns: Any, candidates: tuple[str, ...]) -> str | None:
    column_names = {str(column) for column in columns}
    for candidate in candidates:
        if candidate in column_names:
            return candidate
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None
