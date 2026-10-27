"""SQL DDL, parameterized query builders, and SQL safety validators for DuckDB."""

from __future__ import annotations

import re

from app.domain.analytics_models import AnalyticsTransformRequest, TransformationType
from app.exceptions import InvalidAnalyticsQueryError

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS dim_providers (
        provider_code VARCHAR PRIMARY KEY,
        provider_name VARCHAR NOT NULL,
        region VARCHAR,
        website VARCHAR,
        updated_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_datasets (
        provider_code VARCHAR NOT NULL,
        dataset_code VARCHAR NOT NULL,
        dataset_name VARCHAR NOT NULL,
        description VARCHAR,
        dimensions_schema JSON,
        updated_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (provider_code, dataset_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_series (
        series_id VARCHAR PRIMARY KEY,
        provider_code VARCHAR NOT NULL,
        dataset_code VARCHAR NOT NULL,
        series_code VARCHAR NOT NULL,
        series_name VARCHAR NOT NULL,
        frequency VARCHAR,
        unit VARCHAR,
        dimensions JSON,
        last_synced_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_observations (
        series_id VARCHAR NOT NULL,
        period VARCHAR NOT NULL,
        period_start_date DATE,
        value DOUBLE,
        original_period VARCHAR,
        original_value VARCHAR,
        synced_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (series_id, period)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_runs (
        run_id VARCHAR PRIMARY KEY,
        provider_code VARCHAR NOT NULL,
        dataset_code VARCHAR NOT NULL,
        series_count INTEGER NOT NULL,
        observations_upserted INTEGER NOT NULL,
        status VARCHAR NOT NULL,
        error_detail VARCHAR,
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_insights (
        insight_date DATE PRIMARY KEY,
        model_id VARCHAR NOT NULL,
        summary TEXT NOT NULL,
        metrics_snapshot JSON NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE OR REPLACE VIEW v_series_observations AS
    SELECT
        f.series_id, s.provider_code, p.provider_name, s.dataset_code, d.dataset_name,
        s.series_code, s.series_name, s.frequency, s.unit, s.dimensions,
        f.period, f.period_start_date, f.value
    FROM fact_observations f
    JOIN dim_series s ON f.series_id = s.series_id
    LEFT JOIN dim_datasets d
        ON s.provider_code = d.provider_code AND s.dataset_code = d.dataset_code
    LEFT JOIN dim_providers p ON s.provider_code = p.provider_code
    """,
)

ALLOWED_SQL_PREFIXES = ("SELECT", "WITH", "DESCRIBE", "SUMMARIZE", "EXPLAIN")
FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|"
    r"COPY|ATTACH|DETACH|PRAGMA|INSTALL|LOAD|CALL|EXPORT|IMPORT|"
    r"SET|RESET|VACUUM|CHECKPOINT|read_csv|read_parquet|read_json|glob"
    r")\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    """Validate that a user-supplied SQL query is a single read-only statement.

    Args:
        sql: Raw SQL query string.

    Returns:
        Normalized SQL query string without trailing semicolon.

    Raises:
        InvalidAnalyticsQueryError: If the SQL statement is empty, contains multiple
            statements, or includes forbidden keywords.
    """
    cleaned = re.sub(r"--[^\n]*", " ", sql)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL).strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if not cleaned:
        raise InvalidAnalyticsQueryError("SQL query must not be empty")
    if ";" in cleaned:
        raise InvalidAnalyticsQueryError("Only a single SQL statement is allowed")

    first_token = cleaned.split(maxsplit=1)[0].upper()
    if first_token not in ALLOWED_SQL_PREFIXES:
        raise InvalidAnalyticsQueryError(
            "Only read-only SELECT, WITH, DESCRIBE, or SUMMARIZE queries are permitted"
        )
    if FORBIDDEN_SQL_PATTERN.search(cleaned):
        raise InvalidAnalyticsQueryError(
            "Query contains forbidden DDL, DML, or filesystem keywords"
        )
    return cleaned


def build_transform_expression(
    transformation: TransformationType,
    rolling_window: int,
) -> str:
    """Build the DuckDB SQL window expression for the requested transformation.

    Args:
        transformation: Selected TransformationType enum.
        rolling_window: Window size for rolling average.

    Returns:
        SQL expression computing `transformed_value`.
    """
    if transformation is TransformationType.raw:
        return "value"
    if transformation is TransformationType.pop_pct:
        prev = "LAG(value, 1) OVER (PARTITION BY series_id ORDER BY period)"
        return (
            f"CASE WHEN {prev} IS NULL OR {prev} = 0 THEN NULL "
            f"ELSE ((value - {prev}) / ABS({prev})) * 100.0 END"
        )
    if transformation is TransformationType.yoy_pct:
        part = "OVER (PARTITION BY series_id ORDER BY period)"
        lag_expr = (
            "CASE UPPER(COALESCE(frequency, '')) "
            f"WHEN 'M' THEN LAG(value, 12) {part} "
            f"WHEN 'MONTHLY' THEN LAG(value, 12) {part} "
            f"WHEN 'Q' THEN LAG(value, 4) {part} "
            f"WHEN 'QUARTERLY' THEN LAG(value, 4) {part} "
            f"ELSE LAG(value, 1) {part} END"
        )
        return (
            f"CASE WHEN ({lag_expr}) IS NULL OR ({lag_expr}) = 0 THEN NULL "
            f"ELSE ((value - ({lag_expr})) / ABS({lag_expr})) * 100.0 END"
        )
    if transformation is TransformationType.rebased_100:
        base = (
            "FIRST_VALUE(value IGNORE NULLS) OVER ("
            "PARTITION BY series_id ORDER BY period "
            "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)"
        )
        return (
            f"CASE WHEN {base} IS NULL OR {base} = 0 THEN NULL "
            f"ELSE (value / {base}) * 100.0 END"
        )
    window_preceding = max(1, int(rolling_window) - 1)
    return (
        f"AVG(value) OVER (PARTITION BY series_id ORDER BY period "
        f"ROWS BETWEEN {window_preceding} PRECEDING AND CURRENT ROW)"
    )


def build_transform_query(
    request: AnalyticsTransformRequest,
    max_rows: int,
) -> tuple[str, list[object]]:
    """Construct a parameterized SQL query and parameter list for transformations.

    Args:
        request: AnalyticsTransformRequest parameters.
        max_rows: Row cap for result set.

    Returns:
        Tuple of (parameterized_sql, parameter_values).
    """
    placeholders = ", ".join("?" for _ in request.series_ids)
    params: list[object] = list(request.series_ids)
    where_clauses = [f"series_id IN ({placeholders})"]
    if request.start_period:
        where_clauses.append("period >= ?")
        params.append(request.start_period)
    if request.end_period:
        where_clauses.append("period <= ?")
        params.append(request.end_period)

    expr = build_transform_expression(request.transformation, request.rolling_window)
    where_sql = " AND ".join(where_clauses)
    sql = (
        "WITH filtered AS (\n"
        "    SELECT series_id, provider_code, dataset_code, series_code, series_name,\n"
        "           frequency, unit, period, value\n"
        "    FROM v_series_observations\n"
        f"    WHERE {where_sql}\n"
        ")\n"
        "SELECT\n"
        "    series_id,\n"
        "    provider_code,\n"
        "    dataset_code,\n"
        "    series_code,\n"
        "    series_name,\n"
        "    period,\n"
        "    value AS raw_value,\n"
        f"    ROUND({expr}, 6) AS transformed_value\n"
        "FROM filtered\n"
        "ORDER BY period ASC, series_id ASC\n"
        f"LIMIT {int(max_rows)}"
    )
    return sql, params


UPSERT_PROVIDER_SQL = """
INSERT INTO dim_providers (provider_code, provider_name, region, website, updated_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (provider_code) DO UPDATE SET
    provider_name = EXCLUDED.provider_name,
    region = EXCLUDED.region,
    website = EXCLUDED.website,
    updated_at = EXCLUDED.updated_at
"""

UPSERT_DATASET_SQL = """
INSERT INTO dim_datasets (
    provider_code, dataset_code, dataset_name,
    description, dimensions_schema, updated_at
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (provider_code, dataset_code) DO UPDATE SET
    dataset_name = EXCLUDED.dataset_name,
    description = EXCLUDED.description,
    dimensions_schema = EXCLUDED.dimensions_schema,
    updated_at = EXCLUDED.updated_at
"""

UPSERT_SERIES_SQL = """
INSERT INTO dim_series (
    series_id, provider_code, dataset_code, series_code,
    series_name, frequency, unit, dimensions, last_synced_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (series_id) DO UPDATE SET
    series_name = EXCLUDED.series_name,
    frequency = COALESCE(EXCLUDED.frequency, dim_series.frequency),
    unit = COALESCE(EXCLUDED.unit, dim_series.unit),
    dimensions = EXCLUDED.dimensions,
    last_synced_at = EXCLUDED.last_synced_at
"""

UPSERT_OBSERVATIONS_SQL = """
INSERT INTO fact_observations (
    series_id, period, period_start_date, value,
    original_period, original_value, synced_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (series_id, period) DO UPDATE SET
    period_start_date = EXCLUDED.period_start_date,
    value = EXCLUDED.value,
    original_period = EXCLUDED.original_period,
    original_value = EXCLUDED.original_value,
    synced_at = EXCLUDED.synced_at
"""

UPSERT_SYNC_RUN_SQL = """
INSERT INTO sync_runs (
    run_id, provider_code, dataset_code, series_count,
    observations_upserted, status, error_detail, started_at, completed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (run_id) DO UPDATE SET
    series_count = EXCLUDED.series_count,
    observations_upserted = EXCLUDED.observations_upserted,
    status = EXCLUDED.status,
    error_detail = EXCLUDED.error_detail,
    completed_at = EXCLUDED.completed_at
"""

UPSERT_AI_INSIGHT_SQL = """
INSERT INTO ai_insights (
    insight_date, model_id, summary, metrics_snapshot, created_at
)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (insight_date) DO UPDATE SET
    model_id = EXCLUDED.model_id,
    summary = EXCLUDED.summary,
    metrics_snapshot = EXCLUDED.metrics_snapshot,
    created_at = EXCLUDED.created_at
"""
