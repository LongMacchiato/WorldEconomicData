from typing import Any

import pandas as pd
import pytest
from app.api.routes import get_dbnomics_service
from app.exceptions import UpstreamUnavailableError
from app.main import app
from app.models import (
    ChartPoint,
    ChartSeries,
    Dataset,
    DatasetDetail,
    Dimension,
    DimensionCode,
    Provider,
    QueryRequest,
    SeriesPage,
    SeriesSummary,
)
from fastapi.testclient import TestClient


class FakeService:
    def __init__(self) -> None:
        self.frame = pd.DataFrame(
            {
                "series_code": ["M.US.PCPI_IX", "M.US.PCPI_IX", "M.US.PCPI_IX"],
                "series_name": ["US CPI", "US CPI", "US CPI"],
                "period": ["2020-01-01", "2020-02-01", "2020-03-01"],
                "value": [100.0, float("nan"), 102.0],
            }
        )
        self.last_search: str | None = None
        self.last_dimensions: dict[str, list[str]] | None = None

    def list_providers(self) -> list[Provider]:
        return [
            Provider(code="ECB", name="European Central Bank", region="Europe"),
            Provider(code="IMF", name="International Monetary Fund", region="World"),
        ]

    def get_provider(self, provider_code: str) -> Provider:
        for provider in self.list_providers():
            if provider.code.upper() == provider_code.upper():
                return provider
        raise KeyError(provider_code)

    def list_datasets(
        self, provider_code: str, search: str | None = None
    ) -> list[Dataset]:
        self.last_search = search
        return [
            Dataset(
                provider_code=provider_code.upper(),
                code="CPI",
                name="Consumer Price Index",
                description="Prices",
                nb_series=10,
            )
        ]

    def get_dataset(self, provider_code: str, dataset_code: str) -> DatasetDetail:
        return DatasetDetail(
            provider_code=provider_code.upper(),
            code=dataset_code,
            name="Consumer Price Index",
            dimensions=[
                Dimension(
                    code="FREQ",
                    label="Frequency",
                    values=[DimensionCode(code="M", label="Monthly")],
                )
            ],
        )

    def search_datasets(self, query: str, *, limit: int = 50) -> list[Dataset]:
        return [
            Dataset(
                provider_code="IMF",
                code="CPI",
                name=f"Match for {query}",
                nb_series=10,
            )
        ][:limit]

    def list_series(
        self,
        provider_code: str,
        dataset_code: str,
        *,
        search: str | None = None,
        dimensions: dict[str, list[str]] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> SeriesPage:
        self.last_search = search
        self.last_dimensions = dimensions
        return SeriesPage(
            items=[
                SeriesSummary(
                    provider_code=provider_code.upper(),
                    dataset_code=dataset_code,
                    series_code="M.US.PCPI_IX",
                    series_name="Monthly - United States - CPI",
                    dimensions={"FREQ": "M", "REF_AREA": "US"},
                )
            ],
            offset=offset,
            limit=limit or 50,
            num_found=1,
            has_next_page=False,
        )

    def execute_query(self, _query: QueryRequest) -> pd.DataFrame:
        return self.frame

    def build_chart_series(self, frame: pd.DataFrame) -> list[ChartSeries]:
        return [
            ChartSeries(
                series_code="M.US.PCPI_IX",
                series_name="US CPI",
                points=[
                    ChartPoint(
                        period=str(row["period"]), value=_nullable_float(row["value"])
                    )
                    for _, row in frame.iterrows()
                ],
            )
        ]


def _nullable_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    return float(value)


@pytest.fixture
def fake_service() -> FakeService:
    return FakeService()


@pytest.fixture
def client(fake_service: FakeService) -> TestClient:
    app.dependency_overrides[get_dbnomics_service] = lambda: fake_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def query_payload(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_code": "IMF",
        "dataset_code": "CPI",
        "series_codes": ["M.US.PCPI_IX"],
    }
    payload.update(updates)
    return payload


def test_health_and_providers(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}

    response = client.get("/api/providers")
    assert response.status_code == 200
    codes = [provider["code"] for provider in response.json()]
    assert codes == ["ECB", "IMF"]


def test_datasets_search_and_detail(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.get("/api/providers/imf/datasets?search=consumer")
    assert response.status_code == 200
    assert response.json()[0]["code"] == "CPI"
    assert fake_service.last_search == "consumer"

    detail = client.get("/api/providers/imf/datasets/CPI")
    assert detail.status_code == 200
    assert detail.json()["dimensions"][0]["code"] == "FREQ"


def test_search_endpoint(client: TestClient) -> None:
    response = client.get("/api/search?q=inflation")
    assert response.status_code == 200
    assert response.json()[0]["provider_code"] == "IMF"


def test_series_list_with_dimensions(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.get(
        "/api/providers/IMF/datasets/CPI/series",
        params={"dimensions": '{"FREQ":["M"]}', "limit": 25},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["series_code"] == "M.US.PCPI_IX"
    assert fake_service.last_dimensions == {"FREQ": ["M"]}


def test_preview_and_download(client: TestClient) -> None:
    preview = client.post(
        "/api/query/preview",
        json=query_payload(page=1, page_size=2),
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["total_rows"] == 3
    assert body["has_next_page"] is True
    assert len(body["rows"]) == 2
    assert body["chart_series"][0]["series_code"] == "M.US.PCPI_IX"
    assert body["rows"][1]["value"] is None

    csv_response = client.post(
        "/api/query/download?format=csv",
        json=query_payload(),
    )
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    assert "IMF_CPI.csv" in csv_response.headers["content-disposition"]
    assert "series_code" in csv_response.text

    json_response = client.post(
        "/api/query/download?format=json",
        json=query_payload(),
    )
    assert json_response.status_code == 200
    assert json_response.json()[0]["series_code"] == "M.US.PCPI_IX"


def test_upstream_error_mapping(client: TestClient, fake_service: FakeService) -> None:
    def failing_execute(_query: QueryRequest) -> pd.DataFrame:
        raise UpstreamUnavailableError("timeout")

    fake_service.execute_query = failing_execute  # type: ignore[method-assign]
    response = client.post("/api/query/preview", json=query_payload())
    assert response.status_code == 503
    assert response.json()["error"] == "upstream_unavailable"
