import pytest
from app.config import Settings
from app.services.dbnomics_service import DBnomicsService


@pytest.mark.live
def test_live_known_series_fetch() -> None:
    service = DBnomicsService(Settings())
    providers = service.list_providers()
    assert any(provider.code == "IMF" for provider in providers)

    datasets = service.list_datasets("IMF", "CPI")
    assert any(dataset.code == "CPI" for dataset in datasets)

    series_page = service.list_series("IMF", "CPI", limit=1)
    assert series_page.num_found > 0
    assert series_page.items
