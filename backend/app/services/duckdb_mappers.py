"""DataFrame and DuckDB row mapping helpers for the analytics warehouse."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any

import duckdb
import pandas as pd
from app.domain.analytics_models import (
    AnalyticsTransformRequest,
    CorrelationPair,
    StoredSeries,
)

RESERVED_OBSERVATION_COLUMNS = frozenset(
    {
        "provider_code",
        "dataset_code",
        "dataset_name",
        "series_code",
        "series_name",
        "period",
        "period_start_day",
        "value",
        "original_period",
        "original_value",
        "indexed_at",
        "@frequency",
        "frequency",
        "unit",
        "UNIT",
        "FREQ",
    }
)


def extract_series_and_observations(
    provider_code: str,
    dataset_code: str,
    frame: pd.DataFrame,
    now_iso: str,
) -> tuple[list[list[Any]], list[list[Any]]]:
    """Extract normalized dimension and observation parameter lists from a DataFrame.

    Args:
        provider_code: DBnomics provider code.
        dataset_code: DBnomics dataset code.
        frame: Observations DataFrame returned by DBnomics.
        now_iso: ISO-8601 UTC timestamp string.

    Returns:
        Tuple of (series_rows, observation_rows) ready for parameterized executemany.
    """
    series_map: dict[str, list[Any]] = {}
    obs_map: dict[tuple[str, str], list[Any]] = {}
    dim_cols = [c for c in frame.columns if str(c) not in RESERVED_OBSERVATION_COLUMNS]

    for row in frame.to_dict(orient="records"):
        s_code = str(row.get("series_code") or row.get("series") or "").strip()
        period = str(row.get("period") or row.get("original_period") or "").strip()
        if not s_code or not period:
            continue
        series_id = f"{provider_code}/{dataset_code}/{s_code}"
        if series_id not in series_map:
            series_map[series_id] = _build_series_row(
                series_id, provider_code, dataset_code, s_code, row, dim_cols, now_iso
            )
        obs_map[(series_id, period)] = _build_obs_row(series_id, period, row, now_iso)
    return list(series_map.values()), list(obs_map.values())


def _build_series_row(
    series_id: str,
    provider_code: str,
    dataset_code: str,
    series_code: str,
    row: dict[Any, Any],
    dim_cols: list[Any],
    now_iso: str,
) -> list[Any]:
    """Build a single dim_series parameter row."""
    s_name = str(row.get("series_name") or series_code)
    freq = clean_optional_str(
        row.get("@frequency") or row.get("frequency") or row.get("FREQ")
    )
    unit = clean_optional_str(row.get("unit") or row.get("UNIT"))
    dims = {
        str(col): str(row[col])
        for col in dim_cols
        if clean_optional_str(row.get(col)) is not None
    }
    return [
        series_id,
        provider_code,
        dataset_code,
        series_code,
        s_name,
        freq,
        unit,
        json.dumps(dims, ensure_ascii=False),
        now_iso,
    ]


def _build_obs_row(
    series_id: str,
    period: str,
    row: dict[Any, Any],
    now_iso: str,
) -> list[Any]:
    """Build a single fact_observations parameter row."""
    start_day = parse_period_date(row.get("period_start_day") or period)
    val = clean_float(row.get("value"))
    orig_period = clean_optional_str(row.get("original_period")) or period
    orig_val = clean_optional_str(row.get("original_value"))
    return [series_id, period, start_day, val, orig_period, orig_val, now_iso]


def query_stored_series(
    conn: duckdb.DuckDBPyConnection,
    series_ids: list[str] | None,
) -> list[StoredSeries]:
    """Query stored series metadata and observation statistics.

    Args:
        conn: Active DuckDB connection.
        series_ids: Optional filter of series_id values.

    Returns:
        List of StoredSeries objects ordered by provider, dataset, and series code.
    """
    where_clause = ""
    params: list[Any] = []
    if series_ids:
        placeholders = ", ".join("?" for _ in series_ids)
        where_clause = f"WHERE s.series_id IN ({placeholders})"
        params = list(series_ids)
    rows = conn.execute(
        f"""
        SELECT
            s.series_id, s.provider_code, s.dataset_code, s.series_code, s.series_name,
            s.frequency, s.unit, CAST(s.dimensions AS VARCHAR),
            COUNT(f.period) AS obs_count,
            MIN(f.period) AS min_period,
            MAX(f.period) AS max_period,
            CAST(s.last_synced_at AS VARCHAR)
        FROM dim_series s
        LEFT JOIN fact_observations f ON s.series_id = f.series_id
        {where_clause}
        GROUP BY s.series_id, s.provider_code, s.dataset_code, s.series_code,
                 s.series_name, s.frequency, s.unit, s.dimensions, s.last_synced_at
        ORDER BY s.provider_code ASC, s.dataset_code ASC, s.series_code ASC
        """,
        params,
    ).fetchall()
    return [
        StoredSeries(
            series_id=str(r[0]),
            provider_code=str(r[1]),
            dataset_code=str(r[2]),
            series_code=str(r[3]),
            series_name=str(r[4]),
            frequency=str(r[5]) if r[5] is not None else None,
            unit=str(r[6]) if r[6] is not None else None,
            dimensions=json.loads(r[7]) if r[7] else {},
            observation_count=int(r[8] or 0),
            min_period=str(r[9]) if r[9] is not None else None,
            max_period=str(r[10]) if r[10] is not None else None,
            last_synced_at=str(r[11]),
        )
        for r in rows
    ]


def compute_correlations(
    conn: duckdb.DuckDBPyConnection,
    request: AnalyticsTransformRequest,
    transform_sql: str,
    params: list[object],
) -> list[CorrelationPair]:
    """Compute pairwise Pearson correlations on transformed values in DuckDB.

    Args:
        conn: Active DuckDB connection.
        request: AnalyticsTransformRequest parameters.
        transform_sql: Parameterized transformation SQL query.
        params: Query parameter list.

    Returns:
        List of CorrelationPair results.
    """
    if len(request.series_ids) < 2:
        return []
    corr_sql = (
        f"WITH t AS ({transform_sql})\n"
        "SELECT a.series_id, b.series_id, "
        "ROUND(CORR(a.transformed_value, b.transformed_value), 4) AS corr_val, "
        "COUNT(*) AS overlap\n"
        "FROM t a JOIN t b ON a.period = b.period AND a.series_id < b.series_id\n"
        "WHERE a.transformed_value IS NOT NULL AND b.transformed_value IS NOT NULL\n"
        "GROUP BY a.series_id, b.series_id\n"
        "ORDER BY a.series_id, b.series_id"
    )
    rows = conn.execute(corr_sql, params).fetchall()
    return [
        CorrelationPair(
            series_a=str(r[0]),
            series_b=str(r[1]),
            correlation=clean_float(r[2]),
            overlapping_periods=int(r[3] or 0),
        )
        for r in rows
    ]


def rows_to_records(
    columns: list[str],
    rows: list[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Convert DuckDB result tuples into JSON-safe dictionaries."""
    return [
        {col: json_safe(val) for col, val in zip(columns, row, strict=False)}
        for row in rows
    ]


def json_safe(value: Any) -> Any:
    """Convert dates, timestamps, and NaNs into JSON-serializable primitives."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def clean_float(value: Any) -> float | None:
    """Safely convert numeric values to Python float or None."""
    if value is None or value is pd.NA:
        return None
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return None if (math.isnan(numeric) or math.isinf(numeric)) else numeric


def clean_optional_str(value: Any) -> str | None:
    """Return stripped non-empty string or None."""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text if text and text.upper() != "NA" else None


def parse_period_date(value: Any) -> str | None:
    """Extract YYYY-MM-DD date string when available."""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = clean_optional_str(value)
    if text and len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None
