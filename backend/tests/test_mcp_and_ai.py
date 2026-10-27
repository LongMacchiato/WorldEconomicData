"""Unit and API integration tests for the MCP server and Gemini AI Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from app.api.analytics_routes import get_ai_assistant_service, get_analytics_service
from app.config import Settings
from app.main import app
from app.mcp_server import create_mcp_server
from app.models import (
    Dataset,
    DatasetDetail,
    Provider,
    QueryRequest,
    SeriesPage,
    SeriesSummary,
)
from app.services.ai_assistant_service import AIAssistantService
from app.services.ai_tools import AnalyticsToolDispatcher
from app.services.analytics_service import AnalyticsService
from app.services.duckdb_repository import DuckDBAnalyticsRepository
from fastapi.testclient import TestClient


class FakeFullCatalogSource:
    """Mock catalog source implementing all CatalogSourceProtocol methods."""

    def list_providers(self) -> list[Provider]:
        return [
            Provider(code="IMF", name="International Monetary Fund", region="World"),
            Provider(code="OECD", name="OECD", region="World"),
        ]

    def list_datasets(
        self, provider_code: str, search: str | None = None
    ) -> list[Dataset]:
        return [
            Dataset(
                provider_code=provider_code,
                code="CPI",
                name=f"Consumer Price Index ({search or 'all'})",
                nb_series=2,
            )
        ]

    def search_datasets(self, query: str, limit: int = 25) -> list[Dataset]:
        return [
            Dataset(
                provider_code="IMF",
                code="CPI",
                name=f"Consumer Price Index ({query})",
                nb_series=2,
            )
        ][:limit]

    def list_series(
        self,
        provider_code: str,
        dataset_code: str,
        dimensions: dict[str, list[str]] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SeriesPage:
        items = [
            SeriesSummary(
                provider_code=provider_code,
                dataset_code=dataset_code,
                series_code="A.US.CPI",
                series_name="US CPI Headline",
                dimensions={"REF_AREA": "US"},
            ),
            SeriesSummary(
                provider_code=provider_code,
                dataset_code=dataset_code,
                series_code="A.EA.CPI",
                series_name="Euro Area CPI Headline",
                dimensions={"REF_AREA": "EA"},
            ),
        ]
        return SeriesPage(
            items=items[:limit],
            offset=offset,
            limit=limit,
            num_found=len(items),
            has_next_page=False,
        )

    def get_provider(self, provider_code: str) -> Provider:
        return Provider(code=provider_code, name="International Monetary Fund")

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        return DatasetDetail(
            provider_code=provider_code,
            code=dataset_code,
            name="Consumer Price Index",
        )

    def execute_query(self, query: QueryRequest) -> pd.DataFrame:
        rows = []
        for s_code in query.series_codes:
            for period, val in [("2022", 100.0), ("2023", 106.0), ("2024", 112.36)]:
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


@dataclass
class FakeInteractionStep:
    """Mock step inside a Gemini Interaction response."""

    type: str
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class FakeInteractionResponse:
    """Mock Gemini Interaction object returned by client.interactions.create."""

    id: str
    status: str
    output_text: str | None = None
    steps: list[FakeInteractionStep] = field(default_factory=list)


class FakeInteractionsNamespace:
    """Mock client.interactions namespace returning scripted turns."""

    def __init__(self, responses: list[FakeInteractionResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeInteractionResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeGenAIClient:
    """Mock GenAI client implementing GenAIClientProtocol."""

    def __init__(self, responses: list[FakeInteractionResponse]) -> None:
        self._interactions = FakeInteractionsNamespace(responses)

    @property
    def interactions(self) -> FakeInteractionsNamespace:
        return self._interactions


def test_dispatcher_all_seven_tools_and_mcp_server(tmp_path: Path) -> None:
    db_path = tmp_path / "mcp_test.duckdb"
    repo = DuckDBAnalyticsRepository(db_path)
    catalog = FakeFullCatalogSource()
    analytics_service = AnalyticsService(
        settings=Settings(analytics_db_path=str(db_path)),
        catalog_source=catalog,
        repository=repo,
    )
    dispatcher = AnalyticsToolDispatcher(catalog, analytics_service)

    p_res, _ = dispatcher.dispatch("list_providers", {"search": "imf"})
    assert len(p_res["providers"]) == 1

    d_res, _ = dispatcher.dispatch("search_datasets", {"query": "inflation"})
    assert len(d_res["datasets"]) == 1

    s_res, _ = dispatcher.dispatch(
        "list_series", {"provider_code": "IMF", "dataset_code": "CPI"}
    )
    assert s_res["num_found"] == 2

    sync_res, _ = dispatcher.dispatch(
        "sync_series_to_warehouse",
        {
            "provider_code": "IMF",
            "dataset_code": "CPI",
            "series_codes": ["A.US.CPI", "A.EA.CPI"],
        },
    )
    assert sync_res["status"] == "completed"
    assert dispatcher.warehouse_updated is True

    cat_res, _ = dispatcher.dispatch("get_warehouse_catalog", {})
    assert cat_res["total_series"] == 2

    tf_res, _ = dispatcher.dispatch(
        "transform_warehouse_series",
        {
            "series_ids": ["IMF/CPI/A.US.CPI", "IMF/CPI/A.EA.CPI"],
            "transformation": "yoy_pct",
        },
    )
    assert tf_res["total_rows"] == 6
    assert dispatcher.latest_query_result is not None

    sql_res, _ = dispatcher.dispatch(
        "query_warehouse_sql",
        {"sql": "SELECT series_id, period, value FROM v_series_observations"},
    )
    assert sql_res["total_rows"] == 6

    unknown_res, _ = dispatcher.dispatch("non_existent_tool", {})
    assert "error" in unknown_res

    mcp = create_mcp_server(
        catalog_source=catalog,
        analytics_service=analytics_service,
    )
    assert mcp.name == "dbnomics-analytics-warehouse"


def test_ai_chat_endpoint_executes_tools_and_returns_query_result(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ai_test.duckdb"
    repo = DuckDBAnalyticsRepository(db_path)
    catalog = FakeFullCatalogSource()
    settings = Settings(
        analytics_db_path=str(db_path),
        gemini_api_key="test-key-not-real",
        gemini_model="gemini-3.8-flash",
    )
    analytics_service = AnalyticsService(
        settings=settings,
        catalog_source=catalog,
        repository=repo,
    )
    fake_client = FakeGenAIClient(
        responses=[
            FakeInteractionResponse(
                id="inter_1",
                status="requires_action",
                steps=[
                    FakeInteractionStep(
                        type="function_call",
                        id="call_sync_1",
                        name="sync_series_to_warehouse",
                        arguments={
                            "provider_code": "IMF",
                            "dataset_code": "CPI",
                            "series_codes": ["A.US.CPI", "A.EA.CPI"],
                        },
                    ),
                    FakeInteractionStep(
                        type="function_call",
                        id="call_tf_2",
                        name="transform_warehouse_series",
                        arguments={
                            "series_ids": ["IMF/CPI/A.US.CPI", "IMF/CPI/A.EA.CPI"],
                            "transformation": "yoy_pct",
                        },
                    ),
                ],
            ),
            FakeInteractionResponse(
                id="inter_2",
                status="completed",
                output_text=(
                    "Synced IMF/CPI series and computed YoY % inflation. "
                    "Both series rose 6.0% in 2023 and 2024."
                ),
            ),
        ]
    )
    ai_service = AIAssistantService(
        settings=settings,
        catalog_source=catalog,
        analytics_service=analytics_service,
        genai_client=fake_client,
    )
    app.dependency_overrides[get_analytics_service] = lambda: analytics_service
    app.dependency_overrides[get_ai_assistant_service] = lambda: ai_service
    client = TestClient(app)

    try:
        res = client.post(
            "/api/analytics/ai/chat",
            json={"prompt": "Sync US and Euro Area CPI and compare YoY inflation"},
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["interaction_id"] == "inter_2"
        assert "6.0%" in payload["reply"]
        assert payload["warehouse_updated"] is True
        assert len(payload["tool_calls"]) == 2
        assert payload["tool_calls"][0]["name"] == "sync_series_to_warehouse"
        assert payload["tool_calls"][1]["name"] == "transform_warehouse_series"
        assert payload["query_result"] is not None
        assert len(payload["query_result"]["chart_series"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_ai_chat_missing_api_key_returns_503(tmp_path: Path) -> None:
    db_path = tmp_path / "ai_no_key.duckdb"
    repo = DuckDBAnalyticsRepository(db_path)
    catalog = FakeFullCatalogSource()
    settings = Settings(analytics_db_path=str(db_path), gemini_api_key=None)
    analytics_service = AnalyticsService(
        settings=settings,
        catalog_source=catalog,
        repository=repo,
    )
    ai_service = AIAssistantService(
        settings=settings,
        catalog_source=catalog,
        analytics_service=analytics_service,
        genai_client=None,
    )
    app.dependency_overrides[get_ai_assistant_service] = lambda: ai_service
    client = TestClient(app)
    try:
        res = client.post(
            "/api/analytics/ai/chat",
            json={"prompt": "Show warehouse catalog"},
        )
        assert res.status_code == 503
        assert "GEMINI_API_KEY" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()
