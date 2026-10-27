"""Protocol interfaces for analytics persistence and upstream catalogue access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

import pandas as pd
from app.domain.analytics_models import (
    AnalyticsTransformRequest,
    CorrelationPair,
    StoredSeries,
    SyncRunSummary,
    WarehouseSummary,
)
from app.models import Dataset, DatasetDetail, Provider, QueryRequest, SeriesPage


class CatalogSourceProtocol(Protocol):
    """Protocol for fetching DBnomics metadata and series observations."""

    def list_providers(self) -> list[Provider]:
        """List all DBnomics providers."""

    def get_provider(self, provider_code: str) -> Provider:
        """Fetch provider metadata by code.

        Args:
            provider_code: DBnomics provider code.

        Returns:
            Provider metadata object.
        """

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        """Fetch dataset detail and dimensions by provider and dataset code.

        Args:
            provider_code: DBnomics provider code.
            dataset_code: DBnomics dataset code.

        Returns:
            DatasetDetail metadata object.
        """

    def list_datasets(
        self, provider_code: str, search: str | None = None
    ) -> list[Dataset]:
        """List datasets for a specific provider with optional substring search."""

    def search_datasets(self, query: str, *, limit: int = 50) -> list[Dataset]:
        """Search datasets across DBnomics providers."""

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
        """List series in a dataset with optional text and dimension filters."""

    def execute_query(self, query: QueryRequest) -> pd.DataFrame:
        """Fetch observations for a query request.

        Args:
            query: QueryRequest specifying provider, dataset, and series codes.

        Returns:
            Pandas DataFrame containing series observations.
        """


class AnalyticsRepositoryProtocol(Protocol):
    """Protocol for persisting and querying DBnomics data in the analytics warehouse."""

    def upsert_catalog_metadata(
        self,
        provider: Provider,
        dataset: DatasetDetail,
    ) -> None:
        """Upsert provider and dataset dimension rows.

        Args:
            provider: Provider metadata.
            dataset: Dataset metadata including dimension schema.
        """

    def upsert_observations_frame(
        self,
        provider_code: str,
        dataset_code: str,
        frame: pd.DataFrame,
    ) -> tuple[int, int]:
        """Upsert series dimension metadata and observation facts from a DataFrame.

        Args:
            provider_code: DBnomics provider code.
            dataset_code: DBnomics dataset code.
            frame: DataFrame returned by DBnomics fetch_series.

        Returns:
            Tuple of (distinct_series_upserted, observation_rows_upserted).
        """

    def record_sync_run(self, summary: SyncRunSummary) -> None:
        """Persist or update a synchronization audit record.

        Args:
            summary: SyncRunSummary model.
        """

    def get_warehouse_summary(self) -> WarehouseSummary:
        """Return overall warehouse counts, stored series list, and recent sync runs.

        Returns:
            WarehouseSummary model.
        """

    def delete_series(self, series_id: str) -> bool:
        """Delete a stored series and its observations by series_id.

        Args:
            series_id: Full series identifier (provider/dataset/series).

        Returns:
            True if the series existed and was removed, False otherwise.
        """

    def execute_transform(
        self,
        request: AnalyticsTransformRequest,
        max_rows: int,
    ) -> tuple[list[str], list[dict[str, Any]], list[CorrelationPair], str]:
        """Run an analytical window transformation and compute correlations.

        Args:
            request: Transformation parameters and selected series IDs.
            max_rows: Maximum rows to return.

        Returns:
            Tuple of (columns, records, correlations, executed_sql).
        """

    def list_stored_series_by_ids(self, series_ids: list[str]) -> list[StoredSeries]:
        """Return StoredSeries metadata for the given series IDs.

        Args:
            series_ids: List of series identifiers.

        Returns:
            List of matching StoredSeries objects.
        """

    def execute_readonly_sql(
        self,
        sql: str,
        limit: int,
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        """Validate and execute a read-only SQL query against DuckDB.

        Args:
            sql: Raw SQL query string.
            limit: Row cap to enforce.

        Returns:
            Tuple of (columns, records, executed_sql).
        """
