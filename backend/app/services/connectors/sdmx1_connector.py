"""Dynamic sdmx1 connector supporting all built-in SDMX statistical agencies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import RLock
from typing import Any, cast

import pandas as pd
import requests
import sdmx
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
)
from app.services.connectors.sdmx1_parsers import (
    Sdmx1StructureBundle,
    agency_kwargs,
    build_synthetic_series_from_dsd,
    datasets_from_message,
    extract_dimensions,
    is_http_not_found,
    mapping_get,
    parse_dataflow_catalog,
    to_flat_dataframe,
    to_public_dimensions,
    upstream_error_detail,
)
from app.services.connectors.sdmx1_registry import (
    ALL_AGENCIES_ID,
    SDMX1_PROVIDERS,
    Sdmx1ProviderDefinition,
)
from cachetools import TTLCache

DATAFLOW_REQUEST_PARAMS = {"detail": "allstubs", "references": "none"}
SdmxClientFactory = Callable[[str], Any]


def default_sdmx_client_factory(source_id: str) -> Any:
    """Create a default `sdmx.Client` instance for a registered source ID."""
    return sdmx.Client(source_id)


class Sdmx1DynamicConnector:
    """Dynamic `sdmx1` connector for browsing and querying SDMX dataflows."""

    is_dynamic_catalog: bool = True

    def __init__(
        self,
        definition: Sdmx1ProviderDefinition,
        *,
        client_factory: SdmxClientFactory = default_sdmx_client_factory,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Initialize the dynamic sdmx1 connector.

        Args:
            definition: Sdmx1ProviderDefinition metadata and overrides.
            client_factory: Factory returning an `sdmx.Client` instance.
            timeout_seconds: Upstream request timeout in seconds.
        """
        self._def = definition
        self._client_factory = client_factory
        self._timeout = timeout_seconds
        self._cache: TTLCache[tuple[str, str], Any] = TTLCache(maxsize=64, ttl=1800)
        self._lock = RLock()

    @property
    def provider_code(self) -> str:
        """Return uppercase provider code (`SDMX1_<ID>`)."""
        return self._def.provider_code

    @property
    def source_type(self) -> ProviderSourceType:
        """Return SDMX source type."""
        return ProviderSourceType.sdmx

    def cached_dataset_count(self) -> int:
        """Return number of cached dataflows without making network requests."""
        with self._lock:
            cached = self._cache.get(("dataflows", ""))
        return len(cached) if isinstance(cached, list) else 0

    def get_provider(self) -> Provider:
        """Return Provider metadata."""
        return Provider(
            code=self._def.provider_code,
            name=self._def.name,
            region="SDMX Network",
            website=self._def.base_url,
            source_type=ProviderSourceType.sdmx.value,
            requires_api_key=False,
        )

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List available SDMX dataflows with optional substring search."""
        datasets = cast(
            list[Dataset],
            self._cached(("dataflows", ""), self._load_dataflows),
        )
        if not search or not search.strip():
            return list(datasets)
        needle = search.strip().casefold()
        return [
            d
            for d in datasets
            if needle in d.code.casefold()
            or needle in d.name.casefold()
            or (d.description and needle in d.description.casefold())
        ]

    def get_dataset(self, dataset_code: str) -> DatasetDetail:
        """Return DatasetDetail and DSD dimensions for a dataflow."""
        bundle = self._get_structure_bundle(dataset_code)
        return DatasetDetail(
            provider_code=self.provider_code,
            code=dataset_code,
            name=f"{self._def.id} — {dataset_code}",
            description=self._def.description,
            nb_series=None,
            dimensions=to_public_dimensions(bundle.dimensions),
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
        """Synthesize selectable SDMX dimension-key series from the DSD."""
        bundle = self._get_structure_bundle(dataset_code)
        items = build_synthetic_series_from_dsd(
            self.provider_code,
            dataset_code,
            bundle.dimensions,
            search=search,
            dimensions=dimensions,
        )
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
        """Execute an SDMX observation query via `sdmx.Client.data`."""
        bundle = self._get_structure_bundle(query.dataset_code)
        raw_key = query.series_codes[0] if query.series_codes else ""
        key = "" if raw_key.upper() == "ALL" else raw_key
        params: dict[str, str] = {}
        if query.start_period:
            params["startPeriod"] = query.start_period
        if query.end_period:
            params["endPeriod"] = query.end_period
        try:
            message = self._client().data(
                query.dataset_code,
                key=key,
                dsd=bundle.dsd,
                params=params,
                timeout=self._timeout,
            )
            raw_df = to_flat_dataframe(sdmx.to_pandas(message))
        except (requests.Timeout, requests.ConnectionError) as error:
            raise UpstreamUnavailableError(
                f"Provider {self.provider_code} is unavailable"
            ) from error
        except Exception as error:
            raise UpstreamResponseError(
                f"Could not retrieve dataflow {query.dataset_code}: {error}"
            ) from error
        normalized = _normalize_sdmx1_dataframe(
            self.provider_code, query.dataset_code, raw_df
        )
        if normalized.empty:
            raise SeriesNotFoundError(
                f"No observations for {self.provider_code}/{query.dataset_code}"
            )
        return normalized

    def _client(self) -> Any:
        client = self._client_factory(self._def.id)
        if self._def.base_url:
            client.source.url = self._def.base_url
        return client

    def _cached(self, key: tuple[str, str], loader: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        value = loader()
        with self._lock:
            self._cache[key] = value
        return value

    def _load_dataflows(self) -> list[Dataset]:
        if not self._def.supports_catalog:
            return []
        try:
            return self._fetch_dataflows(self._def)
        except (requests.Timeout, requests.ConnectionError) as error:
            raise UpstreamUnavailableError(
                f"Provider {self.provider_code} is unavailable"
            ) from error
        except requests.HTTPError as error:
            if is_http_not_found(error) and self._def.agency_id is None:
                fallback = Sdmx1ProviderDefinition(
                    id=self._def.id,
                    provider_code=self._def.provider_code,
                    name=self._def.name,
                    description=self._def.description,
                    caveat=self._def.caveat,
                    base_url=self._def.base_url,
                    uses_lightweight_catalog=self._def.uses_lightweight_catalog,
                    agency_id=ALL_AGENCIES_ID,
                    supports_catalog=self._def.supports_catalog,
                )
                return self._fetch_dataflows(fallback)
            raise UpstreamResponseError(
                f"Invalid dataflow metadata from {self.provider_code}: "
                f"{upstream_error_detail(error)}"
            ) from error

    def _fetch_dataflows(self, provider: Sdmx1ProviderDefinition) -> list[Dataset]:
        client = self._client()
        if provider.uses_lightweight_catalog:
            req = client.dataflow(
                dry_run=True,
                params=DATAFLOW_REQUEST_PARAMS.copy(),
                **agency_kwargs(provider),
            )
            if req.headers.get("Accept") in (None, "*/*"):
                req.headers["Accept"] = "application/xml"
            resp = client.session.send(req, timeout=self._timeout)
            resp.raise_for_status()
            items = parse_dataflow_catalog(self.provider_code, resp.content)
        else:
            msg = client.dataflow(
                params=DATAFLOW_REQUEST_PARAMS.copy(),
                timeout=self._timeout,
                **agency_kwargs(provider),
            )
            items = datasets_from_message(self.provider_code, msg)
        return sorted(items, key=lambda d: (d.name.casefold(), d.code))

    def _get_structure_bundle(self, flow_id: str) -> Sdmx1StructureBundle:
        return cast(
            Sdmx1StructureBundle,
            self._cached(("structure", flow_id), lambda: self._load_structure(flow_id)),
        )

    def _load_structure(self, flow_id: str) -> Sdmx1StructureBundle:
        try:
            msg = self._client().dataflow(
                flow_id,
                params={"references": "all"},
                timeout=self._timeout,
                **agency_kwargs(self._def),
            )
            flow = mapping_get(getattr(msg, "dataflow", {}), flow_id)
            if flow is None:
                raise DatasetNotFoundError(
                    f"Dataflow {flow_id} not found for {self.provider_code}"
                )
            structure = getattr(flow, "structure", None)
            if structure is None:
                raise UpstreamResponseError(f"Dataflow {flow_id} has no DSD structure")
            dims = extract_dimensions(structure)
            return Sdmx1StructureBundle(dimensions=dims, dsd=structure)
        except (requests.Timeout, requests.ConnectionError) as error:
            raise UpstreamUnavailableError(
                f"Provider {self.provider_code} is unavailable"
            ) from error
        except DatasetNotFoundError, UpstreamResponseError:
            raise
        except Exception as error:
            raise UpstreamResponseError(
                f"Could not read DSD structure for {flow_id}: "
                f"{upstream_error_detail(error)}"
            ) from error


def _normalize_sdmx1_dataframe(
    provider_code: str, dataset_code: str, df: pd.DataFrame
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    cols = [str(c) for c in df.columns]
    time_col = next(
        (c for c in cols if c.upper() in {"TIME_PERIOD", "TIME", "PERIOD"}),
        cols[0],
    )
    value_col = next(
        (c for c in cols if c.upper() in {"VALUE", "OBS_VALUE"}),
        cols[-1],
    )
    dim_cols = [c for c in cols if c not in {time_col, value_col}]
    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        val = row.get(value_col)
        if val is None or pd.isna(val):
            continue
        try:
            num_val = float(val)
        except TypeError, ValueError:
            continue
        series_code = (
            ".".join(str(row.get(c, "")) for c in dim_cols if row.get(c) is not None)
            or "ALL"
        )
        records.append(
            {
                "provider_code": provider_code,
                "dataset_code": dataset_code,
                "series_code": series_code,
                "series_name": f"{dataset_code} ({series_code})",
                "period": str(row.get(time_col, "")),
                "value": num_val,
                "@frequency": str(row.get("FREQ") or "annual").lower(),
                "unit": str(row.get("UNIT_MEASURE") or "Value"),
            }
        )
    return pd.DataFrame(records)


def build_sdmx1_dynamic_connectors() -> list[Sdmx1DynamicConnector]:
    """Create dynamic sdmx1 connectors for all catalog-supporting sdmx1 sources."""
    return [
        Sdmx1DynamicConnector(defn) for defn in SDMX1_PROVIDERS if defn.supports_catalog
    ]
