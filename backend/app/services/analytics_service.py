"""Domain service orchestrating DBnomics warehouse ingestion and analytical queries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.domain.analytics_models import (
    AnalyticsQueryResult,
    AnalyticsTransformRequest,
    SqlQueryRequest,
    SyncRequest,
    SyncRunSummary,
    WarehouseSummary,
)
from app.domain.analytics_protocols import (
    AnalyticsRepositoryProtocol,
    CatalogSourceProtocol,
)
from app.exceptions import SeriesNotFoundError
from app.models import ChartPoint, ChartSeries, QueryRequest
from app.services.duckdb_mappers import clean_float


class AnalyticsService:
    """Service coordinating DBnomics catalogue fetches with the DuckDB repository."""

    def __init__(
        self,
        settings: Settings,
        catalog_source: CatalogSourceProtocol,
        repository: AnalyticsRepositoryProtocol,
    ) -> None:
        """Initialize the AnalyticsService.

        Args:
            settings: Application Settings instance.
            catalog_source: Upstream DBnomics catalog/observations service.
            repository: Analytics warehouse repository implementation.
        """
        self._settings = settings
        self._catalog = catalog_source
        self._repository = repository

    def get_catalog_summary(self) -> WarehouseSummary:
        """Return overall warehouse counts, stored series list, and recent sync runs.

        Returns:
            WarehouseSummary model.
        """
        return self._repository.get_warehouse_summary()

    def sync_series(self, request: SyncRequest) -> SyncRunSummary:
        """Fetch selected series from DBnomics and upsert into the analytics warehouse.

        Args:
            request: SyncRequest specifying provider, dataset, and series codes.

        Returns:
            SyncRunSummary audit record for the completed sync run.
        """
        run_id = uuid.uuid4().hex[:12]
        started_at = datetime.now(UTC).isoformat()
        running_summary = SyncRunSummary(
            run_id=run_id,
            provider_code=request.provider_code,
            dataset_code=request.dataset_code,
            series_count=len(request.series_codes),
            observations_upserted=0,
            status="running",
            started_at=started_at,
        )
        self._repository.record_sync_run(running_summary)

        try:
            provider = self._catalog.get_provider(request.provider_code)
            dataset = self._catalog.get_dataset(
                request.provider_code, request.dataset_code
            )
            self._repository.upsert_catalog_metadata(provider, dataset)

            query_req = QueryRequest(
                provider_code=provider.code,
                dataset_code=dataset.code,
                series_codes=request.series_codes,
                start_period=request.start_period,
                end_period=request.end_period,
                page=1,
                page_size=self._settings.preview_default_page_size,
            )
            frame = self._catalog.execute_query(query_req)
            series_count, obs_count = self._repository.upsert_observations_frame(
                provider.code, dataset.code, frame
            )
            completed = SyncRunSummary(
                run_id=run_id,
                provider_code=provider.code,
                dataset_code=dataset.code,
                series_count=series_count or len(request.series_codes),
                observations_upserted=obs_count,
                status="completed",
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            self._repository.record_sync_run(completed)
            return completed
        except Exception as error:
            failed = SyncRunSummary(
                run_id=run_id,
                provider_code=request.provider_code,
                dataset_code=request.dataset_code,
                series_count=len(request.series_codes),
                observations_upserted=0,
                status="failed",
                error_detail=str(error),
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            self._repository.record_sync_run(failed)
            raise

    def delete_stored_series(self, series_id: str) -> None:
        """Delete a stored series and its observations from the warehouse.

        Args:
            series_id: Full series identifier (`provider/dataset/series`).

        Raises:
            SeriesNotFoundError: If the series is not present in the warehouse.
        """
        deleted = self._repository.delete_series(series_id)
        if not deleted:
            raise SeriesNotFoundError(
                f"Stored series {series_id!r} was not found in the analytics database"
            )

    def run_transformation(
        self,
        request: AnalyticsTransformRequest,
    ) -> AnalyticsQueryResult:
        """Execute a cross-series transformation and correlation analysis in DuckDB.

        Args:
            request: AnalyticsTransformRequest specifying series IDs and transform.

        Returns:
            AnalyticsQueryResult containing table rows, chart series, and correlations.
        """
        columns, rows, correlations, executed_sql = self._repository.execute_transform(
            request,
            max_rows=self._settings.analytics_max_query_rows,
        )
        chart_series = _build_chart_series_from_records(
            rows, value_col="transformed_value"
        )
        return AnalyticsQueryResult(
            columns=columns,
            rows=rows,
            chart_series=chart_series,
            correlations=correlations,
            total_rows=len(rows),
            executed_sql=executed_sql,
        )

    def run_sql_query(self, request: SqlQueryRequest) -> AnalyticsQueryResult:
        """Execute a validated read-only SQL query against the DuckDB warehouse.

        Args:
            request: SqlQueryRequest containing the SQL statement and row limit.

        Returns:
            AnalyticsQueryResult with columns, rows, and auto-detected chart series.
        """
        effective_limit = min(request.limit, self._settings.analytics_max_query_rows)
        columns, rows, executed_sql = self._repository.execute_readonly_sql(
            request.sql,
            limit=effective_limit,
        )
        value_col = (
            "transformed_value"
            if "transformed_value" in columns
            else ("value" if "value" in columns else None)
        )
        chart_series = (
            _build_chart_series_from_records(rows, value_col=value_col)
            if value_col and "period" in columns
            else []
        )
        return AnalyticsQueryResult(
            columns=columns,
            rows=rows,
            chart_series=chart_series,
            correlations=[],
            total_rows=len(rows),
            executed_sql=executed_sql,
        )


def _build_chart_series_from_records(
    records: list[dict[str, Any]],
    *,
    value_col: str,
) -> list[ChartSeries]:
    """Group tabular query records into ECharts-compatible ChartSeries objects."""
    if not records:
        return []

    grouped_points: dict[str, list[ChartPoint]] = {}
    series_names: dict[str, str] = {}
    for row in records:
        period = row.get("period")
        if period is None:
            continue
        code = str(row.get("series_id") or row.get("series_code") or "series")
        name = str(row.get("series_name") or row.get("series_id") or code)
        series_names.setdefault(code, name)
        grouped_points.setdefault(code, []).append(
            ChartPoint(
                period=str(period),
                value=clean_float(row.get(value_col)),
            )
        )

    return [
        ChartSeries(
            series_code=code,
            series_name=series_names.get(code, code),
            points=points,
        )
        for code, points in grouped_points.items()
    ]
