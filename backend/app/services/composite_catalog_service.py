"""Composite catalog router combining DBnomics with direct data connectors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
from app.config import Settings
from app.domain.analytics_protocols import CatalogSourceProtocol
from app.domain.connector_protocols import (
    ConnectorStatusItem,
    DataConnectorProtocol,
)
from app.models import (
    ChartSeries,
    Dataset,
    DatasetDetail,
    Provider,
    QueryRequest,
    SeriesPage,
)
from app.services.connectors import (
    FredConnector,
    MarketConnector,
    RbaConnector,
    build_default_sdmx_connectors,
    build_sdmx1_dynamic_connectors,
)
from app.services.dbnomics_service import DBnomicsService


class CompositeCatalogService(CatalogSourceProtocol):
    """Unified catalog service routing across DBnomics and custom connectors."""

    def __init__(
        self,
        dbnomics_service: DBnomicsService,
        connectors: Sequence[DataConnectorProtocol] | None = None,
    ) -> None:
        """Initialize the CompositeCatalogService.

        Args:
            dbnomics_service: Underlying DBnomicsService for global DBnomics catalogue.
            connectors: Optional list of custom statistical/financial connectors.
        """
        self._dbnomics = dbnomics_service
        self._connectors: dict[str, DataConnectorProtocol] = {}
        for connector in connectors or ():
            self.register_connector(connector)

    def register_connector(self, connector: DataConnectorProtocol) -> None:
        """Register or replace a pluggable data connector.

        Args:
            connector: DataConnectorProtocol implementation.
        """
        self._connectors[connector.provider_code.upper()] = connector

    def list_connector_statuses(self) -> list[ConnectorStatusItem]:
        """Return health and configuration status of all direct connectors."""
        statuses: list[ConnectorStatusItem] = []
        for connector in self._connectors.values():
            provider = connector.get_provider()
            configured = bool(getattr(connector, "is_configured", True))
            if getattr(connector, "is_dynamic_catalog", False):
                cached_fn = getattr(connector, "cached_dataset_count", None)
                ds_count = cached_fn() if callable(cached_fn) else 0
            else:
                ds_count = len(connector.list_datasets())
            statuses.append(
                ConnectorStatusItem(
                    provider_code=provider.code,
                    provider_name=provider.name,
                    source_type=connector.source_type,
                    requires_api_key=provider.requires_api_key,
                    configured=configured,
                    dataset_count=ds_count,
                )
            )
        return statuses

    def list_providers(self, source_type: str | None = None) -> list[Provider]:
        """Return merged list of direct connectors and DBnomics providers.

        Args:
            source_type: Optional connector source type filter
                ('dbnomics', 'sdmx', 'central_bank', 'financial').

        Returns:
            List of matching Provider objects.
        """
        custom_providers = [c.get_provider() for c in self._connectors.values()]
        try:
            upstream_providers = self._dbnomics.list_providers()
        except Exception:
            upstream_providers = []

        custom_codes = {p.code.upper() for p in custom_providers}
        merged = custom_providers + [
            p for p in upstream_providers if p.code.upper() not in custom_codes
        ]
        if not source_type or not source_type.strip():
            return merged
        normalized = source_type.strip().casefold()
        return [
            p for p in merged if (p.source_type or "dbnomics").casefold() == normalized
        ]

    def get_provider(self, provider_code: str) -> Provider:
        """Fetch Provider metadata from direct connectors or DBnomics."""
        connector = self._connectors.get(provider_code.upper())
        if connector is not None:
            return connector.get_provider()
        return self._dbnomics.get_provider(provider_code)

    def list_datasets(
        self,
        provider_code: str,
        search: str | None = None,
    ) -> list[Dataset]:
        """List datasets for a provider from direct connectors or DBnomics."""
        connector = self._connectors.get(provider_code.upper())
        if connector is not None:
            return connector.list_datasets(search=search)
        return self._dbnomics.list_datasets(provider_code, search=search)

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        """Fetch DatasetDetail from direct connectors or DBnomics."""
        connector = self._connectors.get(provider_code.upper())
        if connector is not None:
            return connector.get_dataset(dataset_code)
        return self._dbnomics.get_dataset(provider_code, dataset_code)

    def search_datasets(self, query: str, *, limit: int = 50) -> list[Dataset]:
        """Search datasets across both direct connectors and DBnomics."""
        normalized = query.strip()
        if not normalized:
            return []
        local_matches: list[Dataset] = []
        for connector in self._connectors.values():
            if getattr(connector, "is_dynamic_catalog", False):
                cached_fn = getattr(connector, "cached_dataset_count", None)
                if not callable(cached_fn) or cached_fn() == 0:
                    continue
            local_matches.extend(connector.list_datasets(search=normalized))
        remaining = max(0, limit - len(local_matches))
        if remaining == 0:
            return local_matches[:limit]
        try:
            upstream_matches = self._dbnomics.search_datasets(
                normalized, limit=remaining
            )
        except Exception:
            upstream_matches = []
        return (local_matches + upstream_matches)[:limit]

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
        """List series in a dataset from direct connectors or DBnomics."""
        connector = self._connectors.get(provider_code.upper())
        if connector is not None:
            return connector.list_series(
                dataset_code,
                search=search,
                dimensions=dimensions,
                offset=offset,
                limit=limit,
            )
        return self._dbnomics.list_series(
            provider_code,
            dataset_code,
            search=search,
            dimensions=dimensions,
            offset=offset,
            limit=limit,
        )

    def execute_query(self, query: QueryRequest) -> pd.DataFrame:
        """Execute observation query via direct connector or DBnomics."""
        connector = self._connectors.get(query.provider_code.upper())
        if connector is not None:
            return connector.fetch_observations(query)
        return self._dbnomics.execute_query(query)

    def build_chart_series(self, frame: pd.DataFrame) -> list[ChartSeries]:
        """Convert an observations DataFrame into ChartSeries objects."""
        return self._dbnomics.build_chart_series(frame)


def build_default_composite_catalog(settings: Settings) -> CompositeCatalogService:
    """Instantiate DBnomicsService and register all built-in data connectors."""
    dbnomics_service = DBnomicsService(settings)
    connectors: list[DataConnectorProtocol] = [
        *build_default_sdmx_connectors(),
        RbaConnector(),
        FredConnector(api_key=settings.fred_api_key),
        MarketConnector(),
        *build_sdmx1_dynamic_connectors(),
    ]
    return CompositeCatalogService(dbnomics_service, connectors=connectors)
