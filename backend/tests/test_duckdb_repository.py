"""Unit tests for DuckDBAnalyticsRepository and SQL query builders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from app.domain.analytics_models import (
    AnalyticsTransformRequest,
    SyncRunSummary,
    TransformationType,
)
from app.exceptions import InvalidAnalyticsQueryError
from app.models import DatasetDetail, Dimension, DimensionCode, Provider
from app.services.duckdb_repository import DuckDBAnalyticsRepository


def _sample_provider() -> Provider:
    return Provider(
        code="IMF",
        name="International Monetary Fund",
        region="World",
        website="https://www.imf.org",
    )


def _sample_dataset() -> DatasetDetail:
    return DatasetDetail(
        provider_code="IMF",
        code="CPI",
        name="Consumer Price Index",
        description="Monthly CPI",
        nb_series=2,
        dimensions=[
            Dimension(
                code="REF_AREA",
                label="Reference Area",
                values=[
                    DimensionCode(code="US", label="United States"),
                    DimensionCode(code="EA", label="Euro Area"),
                ],
            )
        ],
    )


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series_code": "A.US.CPI",
                "series_name": "US CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "US",
                "period": "2021",
                "period_start_day": "2021-01-01",
                "value": 100.0,
            },
            {
                "series_code": "A.US.CPI",
                "series_name": "US CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "US",
                "period": "2022",
                "period_start_day": "2022-01-01",
                "value": 108.0,
            },
            {
                "series_code": "A.US.CPI",
                "series_name": "US CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "US",
                "period": "2023",
                "period_start_day": "2023-01-01",
                "value": 113.4,
            },
            {
                "series_code": "A.EA.CPI",
                "series_name": "Euro Area CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "EA",
                "period": "2021",
                "period_start_day": "2021-01-01",
                "value": 200.0,
            },
            {
                "series_code": "A.EA.CPI",
                "series_name": "Euro Area CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "EA",
                "period": "2022",
                "period_start_day": "2022-01-01",
                "value": 216.0,
            },
            {
                "series_code": "A.EA.CPI",
                "series_name": "Euro Area CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "EA",
                "period": "2023",
                "period_start_day": "2023-01-01",
                "value": 226.8,
            },
        ]
    )


def test_upsert_and_warehouse_summary(tmp_path: Path) -> None:
    repo = DuckDBAnalyticsRepository(tmp_path / "analytics.duckdb")
    repo.upsert_catalog_metadata(_sample_provider(), _sample_dataset())
    series_count, obs_count = repo.upsert_observations_frame(
        "IMF", "CPI", _sample_frame()
    )

    assert series_count == 2
    assert obs_count == 6

    # Re-syncing overlapping observation updates value without duplicating rows
    updated_frame = pd.DataFrame(
        [
            {
                "series_code": "A.US.CPI",
                "series_name": "US CPI Annual",
                "@frequency": "annual",
                "unit": "Index",
                "REF_AREA": "US",
                "period": "2023",
                "period_start_day": "2023-01-01",
                "value": 115.0,
            }
        ]
    )
    repo.upsert_observations_frame("IMF", "CPI", updated_frame)
    repo.record_sync_run(
        SyncRunSummary(
            run_id="run-1",
            provider_code="IMF",
            dataset_code="CPI",
            series_count=2,
            observations_upserted=6,
            status="completed",
            started_at="2026-10-18T00:00:00+00:00",
            completed_at="2026-10-18T00:00:01+00:00",
        )
    )

    summary = repo.get_warehouse_summary()
    assert summary.total_providers == 1
    assert summary.total_datasets == 1
    assert summary.total_series == 2
    assert summary.total_observations == 6
    assert len(summary.recent_syncs) == 1
    assert summary.recent_syncs[0].run_id == "run-1"

    _, rows, _ = repo.execute_readonly_sql(
        "SELECT value FROM v_series_observations "
        "WHERE series_id = 'IMF/CPI/A.US.CPI' AND period = '2023'",
        limit=10,
    )
    assert rows[0]["value"] == pytest.approx(115.0)


def test_transformations_and_correlations(tmp_path: Path) -> None:
    repo = DuckDBAnalyticsRepository(tmp_path / "analytics.duckdb")
    repo.upsert_catalog_metadata(_sample_provider(), _sample_dataset())
    repo.upsert_observations_frame("IMF", "CPI", _sample_frame())

    series_ids = ["IMF/CPI/A.US.CPI", "IMF/CPI/A.EA.CPI"]

    # Rebased to 100: 2021 should be 100.0, 2022 should be 108.0 for both series
    _, rebased_rows, correlations, _ = repo.execute_transform(
        AnalyticsTransformRequest(
            series_ids=series_ids,
            transformation=TransformationType.rebased_100,
        ),
        max_rows=100,
    )
    us_rebased = [
        r["transformed_value"]
        for r in rebased_rows
        if r["series_id"] == "IMF/CPI/A.US.CPI"
    ]
    assert us_rebased == pytest.approx([100.0, 108.0, 113.4])
    assert len(correlations) == 1
    assert correlations[0].correlation == pytest.approx(1.0)
    assert correlations[0].overlapping_periods == 3

    # YoY %: 2021 is None, 2022 is 8.0%, 2023 is 5.0%
    _, yoy_rows, _, _ = repo.execute_transform(
        AnalyticsTransformRequest(
            series_ids=["IMF/CPI/A.US.CPI"],
            transformation=TransformationType.yoy_pct,
        ),
        max_rows=100,
    )
    assert yoy_rows[0]["transformed_value"] is None
    assert yoy_rows[1]["transformed_value"] == pytest.approx(8.0)
    assert yoy_rows[2]["transformed_value"] == pytest.approx(5.0)

    # Delete series
    assert repo.delete_series("IMF/CPI/A.EA.CPI") is True
    assert repo.delete_series("IMF/CPI/NON_EXISTENT") is False
    assert repo.get_warehouse_summary().total_series == 1


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        "",
        "DROP TABLE dim_series",
        "DELETE FROM fact_observations",
        "SELECT * FROM dim_series; DROP TABLE dim_series",
        "COPY dim_series TO '/tmp/out.csv'",
        "ATTACH 'other.db' AS other",
        "PRAGMA database_list",
    ],
)
def test_readonly_sql_rejects_unsafe_queries(tmp_path: Path, unsafe_sql: str) -> None:
    repo = DuckDBAnalyticsRepository(tmp_path / "analytics.duckdb")
    with pytest.raises(InvalidAnalyticsQueryError):
        repo.execute_readonly_sql(unsafe_sql, limit=50)
