"""DuckDB implementation of the AnalyticsRepositoryProtocol."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from app.domain.analytics_models import (
    AnalyticsTransformRequest,
    CorrelationPair,
    StoredSeries,
    SyncRunSummary,
    WarehouseSummary,
)
from app.exceptions import InvalidAnalyticsQueryError
from app.models import DatasetDetail, Provider
from app.services.duckdb_mappers import (
    compute_correlations,
    extract_series_and_observations,
    query_stored_series,
    rows_to_records,
)
from app.services.duckdb_queries import (
    SCHEMA_STATEMENTS,
    UPSERT_DATASET_SQL,
    UPSERT_OBSERVATIONS_SQL,
    UPSERT_PROVIDER_SQL,
    UPSERT_SERIES_SQL,
    UPSERT_SYNC_RUN_SQL,
    build_transform_query,
    validate_readonly_sql,
)


class DuckDBAnalyticsRepository:
    """Embedded DuckDB repository managing the DBnomics star schema."""

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the DuckDB database file and create star-schema tables.

        Args:
            db_path: Path to the `.duckdb` database file or `:memory:`.
        """
        raw_str = str(db_path)
        if raw_str != ":memory:" and not Path(raw_str).is_absolute():
            project_root = Path(__file__).resolve().parents[3]
            self._db_path = str(project_root / raw_str)
        else:
            self._db_path = raw_str
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection.

        Args:
            read_only: Whether to open in read-only mode (ignored for `:memory:`).

        Returns:
            Active DuckDB connection.
        """
        if self._db_path == ":memory:":
            return duckdb.connect(":memory:")
        return duckdb.connect(self._db_path, read_only=read_only)

    def _ensure_schema(self) -> None:
        """Create star-schema tables and analytical views if they do not exist."""
        with self._connect() as conn:
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)

    def upsert_catalog_metadata(
        self,
        provider: Provider,
        dataset: DatasetDetail,
    ) -> None:
        """Upsert provider and dataset dimension rows.

        Args:
            provider: Provider metadata.
            dataset: DatasetDetail metadata including dimensions schema.
        """
        now_iso = datetime.now(UTC).isoformat()
        dimensions_json = json.dumps(
            [dim.model_dump() for dim in dataset.dimensions],
            ensure_ascii=False,
        )
        with self._connect() as conn:
            conn.execute(
                UPSERT_PROVIDER_SQL,
                [
                    provider.code,
                    provider.name,
                    provider.region,
                    provider.website,
                    now_iso,
                ],
            )
            conn.execute(
                UPSERT_DATASET_SQL,
                [
                    dataset.provider_code,
                    dataset.code,
                    dataset.name,
                    dataset.description,
                    dimensions_json,
                    now_iso,
                ],
            )

    def upsert_observations_frame(
        self,
        provider_code: str,
        dataset_code: str,
        frame: pd.DataFrame,
    ) -> tuple[int, int]:
        """Upsert series metadata and observation rows from a DBnomics DataFrame.

        Args:
            provider_code: DBnomics provider code.
            dataset_code: DBnomics dataset code.
            frame: Observations DataFrame returned by DBnomics.

        Returns:
            Tuple of (series_upserted_count, observations_upserted_count).
        """
        if frame.empty:
            return 0, 0

        now_iso = datetime.now(UTC).isoformat()
        series_rows, obs_rows = extract_series_and_observations(
            provider_code, dataset_code, frame, now_iso
        )
        with self._connect() as conn:
            if series_rows:
                conn.executemany(UPSERT_SERIES_SQL, series_rows)
            if obs_rows:
                conn.executemany(UPSERT_OBSERVATIONS_SQL, obs_rows)
        return len(series_rows), len(obs_rows)

    def record_sync_run(self, summary: SyncRunSummary) -> None:
        """Persist or update a synchronization audit record.

        Args:
            summary: SyncRunSummary instance.
        """
        with self._connect() as conn:
            conn.execute(
                UPSERT_SYNC_RUN_SQL,
                [
                    summary.run_id,
                    summary.provider_code,
                    summary.dataset_code,
                    summary.series_count,
                    summary.observations_upserted,
                    summary.status,
                    summary.error_detail,
                    summary.started_at,
                    summary.completed_at,
                ],
            )

    def get_warehouse_summary(self) -> WarehouseSummary:
        """Return overall warehouse counts, stored series list, and recent sync runs.

        Returns:
            WarehouseSummary model.
        """
        with self._connect() as conn:
            counts = conn.execute(
                "SELECT (SELECT COUNT(*) FROM dim_providers), "
                "(SELECT COUNT(*) FROM dim_datasets), "
                "(SELECT COUNT(*) FROM dim_series), "
                "(SELECT COUNT(*) FROM fact_observations)"
            ).fetchone() or (0, 0, 0, 0)
            series_list = query_stored_series(conn, None)
            sync_rows = conn.execute(
                "SELECT run_id, provider_code, dataset_code, series_count, "
                "observations_upserted, status, error_detail, "
                "CAST(started_at AS VARCHAR), CAST(completed_at AS VARCHAR) "
                "FROM sync_runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()

        recent_syncs = [
            SyncRunSummary(
                run_id=str(row[0]),
                provider_code=str(row[1]),
                dataset_code=str(row[2]),
                series_count=int(row[3]),
                observations_upserted=int(row[4]),
                status=str(row[5]),
                error_detail=str(row[6]) if row[6] is not None else None,
                started_at=str(row[7]),
                completed_at=str(row[8]) if row[8] is not None else None,
            )
            for row in sync_rows
        ]
        return WarehouseSummary(
            total_providers=int(counts[0]),
            total_datasets=int(counts[1]),
            total_series=int(counts[2]),
            total_observations=int(counts[3]),
            series=series_list,
            recent_syncs=recent_syncs,
        )

    def list_stored_series_by_ids(self, series_ids: list[str]) -> list[StoredSeries]:
        """Return StoredSeries metadata for the given series IDs.

        Args:
            series_ids: List of series identifiers.

        Returns:
            List of matching StoredSeries objects.
        """
        if not series_ids:
            return []
        with self._connect() as conn:
            return query_stored_series(conn, series_ids)

    def delete_series(self, series_id: str) -> bool:
        """Delete a stored series and its observations by series_id.

        Args:
            series_id: Full series identifier (provider/dataset/series).

        Returns:
            True if the series existed and was removed, False otherwise.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM dim_series WHERE series_id = ?", [series_id]
            ).fetchone()
            if existing is None:
                return False
            conn.execute(
                "DELETE FROM fact_observations WHERE series_id = ?", [series_id]
            )
            conn.execute("DELETE FROM dim_series WHERE series_id = ?", [series_id])
            return True

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
        sql, params = build_transform_query(request, max_rows)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            columns = [desc[0] for desc in (cursor.description or [])]
            records = rows_to_records(columns, cursor.fetchall())
            correlations = compute_correlations(conn, request, sql, params)
        return columns, records, correlations, sql

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
        validated_sql = validate_readonly_sql(sql)
        first_word = validated_sql.split(maxsplit=1)[0].upper()
        wrapped_sql = (
            f"SELECT * FROM ({validated_sql}) AS _q LIMIT {int(limit)}"
            if first_word in ("SELECT", "WITH")
            else validated_sql
        )
        try:
            with self._connect() as conn:
                cursor = conn.execute(wrapped_sql)
                columns = [desc[0] for desc in (cursor.description or [])]
                records = rows_to_records(columns, cursor.fetchall()[:limit])
        except duckdb.Error as error:
            raise InvalidAnalyticsQueryError(f"DuckDB SQL error: {error}") from error
        return columns, records, validated_sql
