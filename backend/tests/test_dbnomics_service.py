from typing import Any

import pandas as pd
import pytest
from app.config import Settings
from app.exceptions import ProviderNotFoundError, SeriesNotFoundError
from app.models import QueryRequest
from app.services.dbnomics_service import DBnomicsService


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def __call__(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self.calls.append((path, params))
        if path == "/providers":
            return {
                "providers": {
                    "docs": [
                        {
                            "code": "IMF",
                            "name": "International Monetary Fund",
                            "region": "World",
                            "website": "https://www.imf.org/",
                        },
                        {
                            "code": "ECB",
                            "name": "European Central Bank",
                            "region": "Europe",
                        },
                    ],
                    "num_found": 2,
                }
            }
        if path == "/datasets/IMF":
            return {
                "datasets": {
                    "docs": [
                        {
                            "code": "CPI",
                            "name": "Consumer Price Index",
                            "description": "Inflation prices",
                            "nb_series": 10,
                        },
                        {
                            "code": "WEO",
                            "name": "World Economic Outlook",
                            "nb_series": 5,
                        },
                    ],
                    "num_found": 2,
                }
            }
        if path == "/datasets/IMF/CPI":
            return {
                "datasets": {
                    "docs": [
                        {
                            "code": "CPI",
                            "name": "Consumer Price Index",
                            "description": "Inflation prices",
                            "nb_series": 10,
                            "dimensions_labels": {"FREQ": "Frequency"},
                            "dimensions_codes_order": ["FREQ"],
                            "dimensions_values_labels": {
                                "FREQ": {"A": "Annual", "M": "Monthly"}
                            },
                        }
                    ]
                }
            }
        if path == "/series/IMF/CPI":
            return {
                "series": {
                    "docs": [
                        {
                            "provider_code": "IMF",
                            "dataset_code": "CPI",
                            "series_code": "M.US.PCPI_IX",
                            "series_name": "Monthly - United States - CPI",
                            "dimensions": {"FREQ": "M", "REF_AREA": "US"},
                        }
                    ],
                    "num_found": 1,
                    "limit": params.get("limit") if params else 50,
                    "offset": params.get("offset") if params else 0,
                }
            }
        if path == "/search":
            return {
                "results": {
                    "docs": [
                        {
                            "provider_code": "IMF",
                            "code": "CPI",
                            "name": "Consumer Price Index",
                            "nb_series": 10,
                        }
                    ]
                }
            }
        raise AssertionError(f"Unexpected path: {path}")


@pytest.fixture
def fake_http() -> FakeHttp:
    return FakeHttp()


@pytest.fixture
def service(fake_http: FakeHttp) -> DBnomicsService:
    return DBnomicsService(
        Settings(metadata_cache_ttl_seconds=60),
        http_get=fake_http,
        fetch_series_fn=lambda _ids: pd.DataFrame(
            {
                "series_code": ["M.US.PCPI_IX", "M.US.PCPI_IX"],
                "series_name": ["US CPI", "US CPI"],
                "period": ["2020-01-01", "2020-02-01"],
                "value": [100.0, 101.5],
            }
        ),
    )


def test_list_providers_sorted_and_cached(
    service: DBnomicsService, fake_http: FakeHttp
) -> None:
    first = service.list_providers()
    second = service.list_providers()

    assert [provider.code for provider in first] == ["ECB", "IMF"]
    assert first == second
    assert len([call for call in fake_http.calls if call[0] == "/providers"]) == 1


def test_dataset_search_is_case_insensitive(
    service: DBnomicsService, fake_http: FakeHttp
) -> None:
    results = service.list_datasets("imf", "consumer")

    assert len(results) == 1
    assert results[0].code == "CPI"
    assert fake_http.calls[0][0] == "/providers"


def test_unknown_provider_raises(service: DBnomicsService) -> None:
    with pytest.raises(ProviderNotFoundError):
        service.list_datasets("UNKNOWN")


def test_get_dataset_parses_dimensions(service: DBnomicsService) -> None:
    detail = service.get_dataset("IMF", "CPI")

    assert detail.code == "CPI"
    assert detail.dimensions[0].code == "FREQ"
    assert detail.dimensions[0].values[0].code == "A"


def test_list_series_passes_dimension_filter(
    service: DBnomicsService, fake_http: FakeHttp
) -> None:
    page = service.list_series(
        "IMF",
        "CPI",
        dimensions={"FREQ": ["M"]},
        offset=0,
        limit=25,
    )

    assert page.num_found == 1
    assert page.items[0].series_code == "M.US.PCPI_IX"
    series_call = next(call for call in fake_http.calls if call[0] == "/series/IMF/CPI")
    assert series_call[1] is not None
    assert series_call[1]["dimensions"] == '{"FREQ":["M"]}'


def test_search_datasets(service: DBnomicsService) -> None:
    results = service.search_datasets("inflation")
    assert results[0].provider_code == "IMF"
    assert results[0].code == "CPI"


def test_execute_query_and_chart_series(service: DBnomicsService) -> None:
    frame = service.execute_query(
        QueryRequest(
            provider_code="IMF",
            dataset_code="CPI",
            series_codes=["M.US.PCPI_IX"],
        )
    )
    chart = service.build_chart_series(frame)

    assert len(frame) == 2
    assert chart[0].series_code == "M.US.PCPI_IX"
    assert chart[0].points[1].value == 101.5


def test_execute_query_maps_not_found() -> None:
    def failing_fetch(_ids: list[str]) -> pd.DataFrame:
        raise RuntimeError("series not found")

    service = DBnomicsService(
        Settings(),
        http_get=FakeHttp(),
        fetch_series_fn=failing_fetch,
    )

    with pytest.raises(SeriesNotFoundError):
        service.execute_query(
            QueryRequest(
                provider_code="IMF",
                dataset_code="CPI",
                series_codes=["MISSING"],
            )
        )
