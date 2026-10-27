"""API integration tests for /api/analytics/* endpoints."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from app.api.analytics_routes import get_analytics_service
from app.config import Settings
from app.exceptions import UpstreamUnavailableError
from app.main import app
from app.models import DatasetDetail, Dimension, DimensionCode, Provider, QueryRequest
from app.services.analytics_service import AnalyticsService
from app.services.duckdb_repository import DuckDBAnalyticsRepository
from fastapi.testclient import TestClient


class FakeCatalogSource:
    """Mock catalog source implementing CatalogSourceProtocol."""

    def __init__(self, *, fail_upstream: bool = False) -> None:
        self.fail_upstream = fail_upstream

    def get_provider(self, provider_code: str) -> Provider:
        if self.fail_upstream:
            raise UpstreamUnavailableError("Upstream DBnomics down")
        return Provider(
            code=provider_code,
            name="International Monetary Fund",
            region="World",
            website="https://www.imf.org",
        )

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        return DatasetDetail(
            provider_code=provider_code,
            code=dataset_code,
            name="Consumer Price Index",
            description="CPI Headline",
            nb_series=2,
            dimensions=[
                Dimension(
                    code="REF_AREA",
                    label="Reference Area",
                    values=[DimensionCode(code="US", label="United States")],
                )
            ],
        )

    def execute_query(self, query: QueryRequest) -> pd.DataFrame:
        rows = []
        for s_code in query.series_codes:
            for period, val in [("2022", 100.0), ("2023", 108.0), ("2024", 113.4)]:
                rows.append(
                    {
                        "series_code": s_code,
                        "series_name": f"Series {s_code}",
                        "@frequency": "annual",
                        "unit": "Index",
                        "REF_AREA": "US",
                        "period": period,
                        "period_start_day": f"{period}-01-01",
                        "value": val,
                    }
                )
        return pd.DataFrame(rows)


def _create_client(
    tmp_path: Path,
    *,
    fail_upstream: bool = False,
) -> tuple[TestClient, DuckDBAnalyticsRepository]:
    repo = DuckDBAnalyticsRepository(tmp_path / "test_api.duckdb")
    service = AnalyticsService(
        settings=Settings(analytics_db_path=str(tmp_path / "test_api.duckdb")),
        catalog_source=FakeCatalogSource(fail_upstream=fail_upstream),
        repository=repo,
    )
    app.dependency_overrides[get_analytics_service] = lambda: service
    return TestClient(app), repo


def test_sync_catalog_transform_sql_and_delete(tmp_path: Path) -> None:
    client, _ = _create_client(tmp_path)
    try:
        # 1. Sync two series into DuckDB
        sync_res = client.post(
            "/api/analytics/sync",
            json={
                "provider_code": "IMF",
                "dataset_code": "CPI",
                "series_codes": ["A.US.CPI", "A.EA.CPI"],
            },
        )
        assert sync_res.status_code == 200
        sync_payload = sync_res.json()
        assert sync_payload["status"] == "completed"
        assert sync_payload["series_count"] == 2
        assert sync_payload["observations_upserted"] == 6

        # 2. Fetch catalog summary
        catalog_res = client.get("/api/analytics/catalog")
        assert catalog_res.status_code == 200
        catalog = catalog_res.json()
        assert catalog["total_providers"] == 1
        assert catalog["total_datasets"] == 1
        assert catalog["total_series"] == 2
        assert catalog["total_observations"] == 6

        # 3. Run YoY % transformation
        transform_res = client.post(
            "/api/analytics/transform",
            json={
                "series_ids": ["IMF/CPI/A.US.CPI", "IMF/CPI/A.EA.CPI"],
                "transformation": "yoy_pct",
                "rolling_window": 3,
            },
        )
        assert transform_res.status_code == 200
        transform_data = transform_res.json()
        assert len(transform_data["chart_series"]) == 2
        assert len(transform_data["correlations"]) == 1
        assert transform_data["correlations"][0]["correlation"] == pytest.approx(1.0)

        # 4. Run custom read-only SQL query
        sql_res = client.post(
            "/api/analytics/sql",
            json={
                "sql": (
                    "SELECT series_id, period, value "
                    "FROM v_series_observations ORDER BY period DESC"
                ),
                "limit": 10,
            },
        )
        assert sql_res.status_code == 200
        sql_data = sql_res.json()
        assert sql_data["total_rows"] == 6
        assert len(sql_data["chart_series"]) == 2

        # 5. Delete one series
        del_res = client.delete("/api/analytics/series/IMF/CPI/A.EA.CPI")
        assert del_res.status_code == 200
        assert client.get("/api/analytics/catalog").json()["total_series"] == 1
    finally:
        app.dependency_overrides.clear()


def test_sync_failure_records_failed_run_and_returns_503(tmp_path: Path) -> None:
    client, repo = _create_client(tmp_path, fail_upstream=True)
    try:
        res = client.post(
            "/api/analytics/sync",
            json={
                "provider_code": "IMF",
                "dataset_code": "CPI",
                "series_codes": ["A.US.CPI"],
            },
        )
        assert res.status_code == 503
        summary = repo.get_warehouse_summary()
        assert len(summary.recent_syncs) == 1
        assert summary.recent_syncs[0].status == "failed"
    finally:
        app.dependency_overrides.clear()


def test_sql_endpoint_rejects_unsafe_statement_with_422(tmp_path: Path) -> None:
    client, _ = _create_client(tmp_path)
    try:
        res = client.post(
            "/api/analytics/sql",
            json={"sql": "DROP TABLE fact_observations", "limit": 10},
        )
        assert res.status_code == 422
        assert res.json()["error"] == "invalid_analytics_query"
    finally:
        app.dependency_overrides.clear()
