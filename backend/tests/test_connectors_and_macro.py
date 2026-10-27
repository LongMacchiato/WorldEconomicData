"""Unit and integration tests for pluggable connectors and Macro Intelligence API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from app.api.macro_routes import get_composite_catalog_service, get_mlx_macro_service
from app.config import Settings
from app.domain.connector_protocols import SdmxEndpointConfig
from app.exceptions import (
    DatasetNotFoundError,
    SeriesNotFoundError,
    UpstreamUnavailableError,
)
from app.main import app
from app.models import Provider, QueryRequest
from app.services.analytics_service import AnalyticsService
from app.services.composite_catalog_service import CompositeCatalogService
from app.services.connectors.fred_connector import FredConnector
from app.services.connectors.market_connector import MarketConnector
from app.services.connectors.rba_connector import RbaConnector
from app.services.connectors.sdmx_connector import (
    ABS_DATASETS,
    SdmxConnector,
    build_default_sdmx_connectors,
)
from app.services.duckdb_repository import DuckDBAnalyticsRepository
from app.services.mlx_macro_service import MlxMacroService
from fastapi.testclient import TestClient

SAMPLE_ABS_CSV = (
    "DATAFLOW,MEASURE,DATA_ITEM,TSEST,REGION,FREQ,TIME_PERIOD,OBS_VALUE,UNIT_MEASURE\n"
    "ABS:ANA_AGG(1.0.0),M1,GPM,20,AUS,Q,2026-Q1,0.4,PCT\n"
    "ABS:ANA_AGG(1.0.0),M1,GPM,20,AUS,Q,2026-Q2,0.6,PCT\n"
    "ABS:ANA_AGG(1.0.0),M3,GPM_PCA,10,AUS,Q,2026-Q2,26500,AUD\n"
)

SAMPLE_RBA_F1_CSV = (
    "F1.1 INTEREST RATES AND YIELDS - MONEY MARKET\n"
    "Title,Cash Rate Target,90-day bill\n"
    "Series ID,FIRMMCRT,FIRMMBAB90\n"
    "31/08/2026,4.35,4.41\n"
    "30/09/2026,4.36,4.42\n"
)

SAMPLE_RBA_G1_CSV = (
    "G1 CONSUMER PRICE INFLATION\n"
    "Series ID,GCPIOCPMTMYP,GCPIAGYP\n"
    "31/03/2026,3.5,3.7\n"
    "30/06/2026,3.6,3.8\n"
)


class DummyDBnomicsService:
    """Minimal stub for DBnomicsService."""

    def list_providers(self) -> list[Provider]:
        return [
            Provider(code="IMF", name="International Monetary Fund", region="World")
        ]

    def get_provider(self, provider_code: str) -> Provider:
        return Provider(code=provider_code, name="IMF")

    def list_datasets(self, provider_code: str, search: str | None = None) -> list[Any]:
        _ = (provider_code, search)
        return []

    def search_datasets(self, query: str, *, limit: int = 50) -> list[Any]:
        _ = (query, limit)
        return []

    def build_chart_series(self, frame: pd.DataFrame) -> list[Any]:
        _ = frame
        return []


def _make_sdmx_abs_connector() -> SdmxConnector:
    return SdmxConnector(
        config=SdmxEndpointConfig(
            provider_code="SDMX_ABS",
            provider_name="Australian Bureau of Statistics (Direct SDMX 3.0)",
            region="Australia",
            website="https://www.abs.gov.au",
            base_url="https://data.api.abs.gov.au/rest",
            agency_id="ABS",
            sdmx_version="3.0",
        ),
        datasets=ABS_DATASETS,
        text_fetcher=lambda _url, _params: SAMPLE_ABS_CSV,
    )


def test_default_sdmx_connectors_registry() -> None:
    connectors = build_default_sdmx_connectors()
    codes = [c.provider_code for c in connectors]
    assert codes == [
        "SDMX_ABS",
        "SDMX_BIS",
        "SDMX_STATSNZ",
        "SDMX_STATCAN",
        "SDMX_BBK",
        "SDMX_BFS_CH",
        "SDMX_FAO",
        "SDMX_WB_WDI",
    ]
    for connector in connectors:
        assert connector.get_provider().source_type == "sdmx"
        assert len(connector.list_datasets()) >= 2


def test_sdmx_connector_discovery_and_observations() -> None:
    connector = _make_sdmx_abs_connector()
    assert connector.get_provider().source_type == "sdmx"
    assert len(connector.list_datasets(search="GDP")) == 1

    detail = connector.get_dataset("ANA_AGG")
    dim_codes = [d.code for d in detail.dimensions]
    assert "MEASURE" in dim_codes
    assert "TSEST" in dim_codes

    series_page = connector.list_series("ANA_AGG", dimensions={"TSEST": ["20"]})
    assert series_page.num_found == 1
    assert series_page.items[0].series_code == "M1.GPM.20.AUS.Q"

    df = connector.fetch_observations(
        QueryRequest(
            provider_code="SDMX_ABS",
            dataset_code="ANA_AGG",
            series_codes=["M1.GPM.20.AUS.Q"],
            start_period="2026-Q2",
        )
    )
    assert len(df) == 1
    assert float(df.iloc[0]["value"]) == pytest.approx(0.6)

    with pytest.raises(DatasetNotFoundError):
        connector.get_dataset("UNKNOWN")
    with pytest.raises(SeriesNotFoundError):
        connector.fetch_observations(
            QueryRequest(
                provider_code="SDMX_ABS",
                dataset_code="ANA_AGG",
                series_codes=["NON_EXISTENT"],
            )
        )


def test_rba_fred_and_market_connectors() -> None:
    rba = RbaConnector(
        csv_fetcher=lambda url: (
            SAMPLE_RBA_F1_CSV if "f1.1" in url else SAMPLE_RBA_G1_CSV
        )
    )
    rba_df = rba.fetch_observations(
        QueryRequest(
            provider_code="RBA",
            dataset_code="F1_1",
            series_codes=["FIRMMCRT"],
        )
    )
    assert len(rba_df) == 2
    assert float(rba_df.iloc[-1]["value"]) == pytest.approx(4.36)

    unconfigured_fred = FredConnector(api_key=None)
    assert not unconfigured_fred.is_configured
    with pytest.raises(UpstreamUnavailableError):
        unconfigured_fred.fetch_observations(
            QueryRequest(
                provider_code="FRED",
                dataset_code="RATES",
                series_codes=["T10Y2Y"],
            )
        )

    configured_fred = FredConnector(
        api_key="test_fred_key",
        json_fetcher=lambda _u, _p: {
            "observations": [
                {"date": "2026-09-01", "value": "."},
                {"date": "2026-10-01", "value": "-0.12"},
            ]
        },
    )
    fred_df = configured_fred.fetch_observations(
        QueryRequest(
            provider_code="FRED",
            dataset_code="RATES",
            series_codes=["T10Y2Y"],
        )
    )
    assert len(fred_df) == 1
    assert float(fred_df.iloc[0]["value"]) == pytest.approx(-0.12)

    market = MarketConnector(
        history_fetcher=lambda _sym: pd.DataFrame(
            {"Close": [0.695, 0.703]}, index=["2026-10-20", "2026-10-21"]
        )
    )
    mkt_df = market.fetch_observations(
        QueryRequest(
            provider_code="YAHOO_FINANCE",
            dataset_code="FX",
            series_codes=["AUDUSD"],
        )
    )
    assert len(mkt_df) == 2
    assert float(mkt_df.iloc[-1]["value"]) == pytest.approx(0.703)


def test_macro_dashboard_routes_and_warehouse_sync(tmp_path: Path) -> None:
    db_file = tmp_path / "macro_test.duckdb"
    settings = Settings(analytics_db_path=str(db_file), fred_api_key="test_key")

    rba = RbaConnector(
        csv_fetcher=lambda url: (
            SAMPLE_RBA_F1_CSV if "f1.1" in url else SAMPLE_RBA_G1_CSV
        )
    )
    fred = FredConnector(
        api_key="test_key",
        json_fetcher=lambda _u, _p: {
            "observations": [
                {"date": "2026-09-01", "value": "-0.20"},
                {"date": "2026-10-01", "value": "-0.15"},
            ]
        },
    )
    market = MarketConnector(
        history_fetcher=lambda _sym: pd.DataFrame(
            {"Close": [100.0, 102.5]}, index=["2026-10-20", "2026-10-21"]
        )
    )
    catalog = CompositeCatalogService(
        DummyDBnomicsService(),  # type: ignore[arg-type]
        connectors=[_make_sdmx_abs_connector(), rba, fred, market],
    )
    repo = DuckDBAnalyticsRepository(db_file)
    analytics = AnalyticsService(
        settings=settings, catalog_source=catalog, repository=repo
    )
    macro_service = MlxMacroService(
        settings=settings, catalog=catalog, analytics=analytics
    )

    app.dependency_overrides[get_composite_catalog_service] = lambda: catalog
    app.dependency_overrides[get_mlx_macro_service] = lambda: macro_service
    try:
        with TestClient(app) as client:
            conn_res = client.get("/api/macro/connectors")
            assert conn_res.status_code == 200
            assert len(conn_res.json()) == 4

            refresh_res = client.post("/api/macro/refresh")
            assert refresh_res.status_code == 200
            body = refresh_res.json()
            kpis = {k["key"]: k for k in body["kpis"]}
            assert kpis["cash_rate"]["value"] == pytest.approx(4.36)
            assert kpis["yield_curve"]["status_badge"] == "INVERTED"
            assert kpis["trimmed_cpi"]["status_badge"] == "ABOVE TARGET"
            assert body["latest_brief"]["summary"]

            insight_res = client.get("/api/macro/insights")
            assert insight_res.status_code == 200
            assert insight_res.json()["insight_date"]
    finally:
        app.dependency_overrides.clear()
