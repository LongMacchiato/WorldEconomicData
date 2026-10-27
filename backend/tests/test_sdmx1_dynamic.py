"""Unit tests for dynamic sdmx1 provider registry, XML parser, and connector."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from app.config import Settings
from app.domain.analytics_models import AiConfigUpdateRequest
from app.models import QueryRequest
from app.services.connectors.sdmx1_connector import (
    Sdmx1DynamicConnector,
    build_sdmx1_dynamic_connectors,
)
from app.services.connectors.sdmx1_parsers import parse_dataflow_catalog
from app.services.connectors.sdmx1_registry import get_sdmx1_provider
from app.services.env_config_service import (
    get_ai_config_status,
    mask_secret,
    update_env_config,
)

SAMPLE_DATAFLOW_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<mes:Structure xmlns:mes="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
               xmlns:str="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
               xmlns:com="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <mes:Structures>
    <str:Dataflows>
      <str:Dataflow id="EXR" agencyID="ECB" version="1.0">
        <com:Name xml:lang="en">Exchange Rates</com:Name>
      </str:Dataflow>
      <str:Dataflow id="ICP" agencyID="ECB" version="1.0">
        <com:Name xml:lang="en">Indices of Consumer Prices</com:Name>
      </str:Dataflow>
    </str:Dataflows>
  </mes:Structures>
</mes:Structure>
"""


class FakeSdmxClient:
    """Fake sdmx.Client for deterministic unit testing."""

    def __init__(self) -> None:
        self.source = SimpleNamespace(url="https://example.org/sdmx")

    def dataflow(
        self,
        flow_id: str | None = None,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> Any:
        _ = (params, timeout, kwargs)
        if flow_id is None:
            return SimpleNamespace(
                dataflow={
                    "EXR": SimpleNamespace(
                        id="EXR",
                        name="Exchange Rates",
                        description="ECB FX reference rates",
                    )
                }
            )
        codes = [
            SimpleNamespace(id="USD", name="US Dollar"),
            SimpleNamespace(id="AUD", name="Australian Dollar"),
        ]
        freq_dim = SimpleNamespace(
            id="FREQ",
            name="Frequency",
            local_representation=SimpleNamespace(
                enumerated=SimpleNamespace(
                    items=[SimpleNamespace(id="D", name="Daily")]
                )
            ),
        )
        curr_dim = SimpleNamespace(
            id="CURRENCY",
            name="Currency",
            local_representation=SimpleNamespace(
                enumerated=SimpleNamespace(items=codes)
            ),
        )
        time_dim = SimpleNamespace(
            id="TIME_PERIOD",
            name="Time period",
            local_representation=None,
        )
        dsd = SimpleNamespace(
            dimensions=SimpleNamespace(components=[freq_dim, curr_dim, time_dim])
        )
        return SimpleNamespace(
            dataflow={"EXR": SimpleNamespace(id="EXR", structure=dsd)}
        )

    def data(self, flow_id: str, **kwargs: Any) -> Any:
        _ = (flow_id, kwargs)
        return "FAKE_SDMX_MESSAGE"


def test_sdmx1_registry_and_xml_catalog_parser() -> None:
    ecb = get_sdmx1_provider("ECB")
    assert ecb.provider_code == "SDMX1_ECB"
    assert ecb.supports_catalog

    datasets = parse_dataflow_catalog("SDMX1_ECB", SAMPLE_DATAFLOW_XML)
    assert len(datasets) == 2
    assert datasets[0].code == "EXR"
    assert datasets[0].name == "Exchange Rates"

    connectors = build_sdmx1_dynamic_connectors()
    codes = {c.provider_code for c in connectors}
    assert "SDMX1_ECB" in codes
    assert "SDMX1_ESTAT" in codes
    assert "SDMX1_OECD" in codes


def test_sdmx1_dynamic_connector_structure_and_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defn = get_sdmx1_provider("ECB")
    connector = Sdmx1DynamicConnector(
        defn, client_factory=lambda _sid: FakeSdmxClient()
    )
    assert connector.cached_dataset_count() == 0

    datasets = connector.list_datasets(search="Exchange")
    assert len(datasets) == 1
    assert connector.cached_dataset_count() == 1

    detail = connector.get_dataset("EXR")
    assert [d.code for d in detail.dimensions] == ["FREQ", "CURRENCY"]

    series = connector.list_series("EXR", dimensions={"CURRENCY": ["AUD"]})
    assert series.num_found >= 1
    assert ".AUD" in series.items[0].series_code

    monkeypatch.setattr(
        "sdmx.to_pandas",
        lambda _msg: pd.DataFrame(
            {
                "FREQ": ["D", "D"],
                "CURRENCY": ["AUD", "AUD"],
                "TIME_PERIOD": ["2026-10-20", "2026-10-21"],
                "value": [1.54, 1.55],
            }
        ),
    )
    df = connector.fetch_observations(
        QueryRequest(
            provider_code="SDMX1_ECB",
            dataset_code="EXR",
            series_codes=["D.AUD"],
        )
    )
    assert len(df) == 2
    assert float(df.iloc[-1]["value"]) == pytest.approx(1.55)


def test_env_config_service_masking_and_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert mask_secret(None) is None
    assert mask_secret("AIzaSyTestKey123456789") == "AIza...6789"

    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nGEMINI_API_KEY=old_key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "old_key")

    update_env_config(
        AiConfigUpdateRequest(
            gemini_api_key="AIzaSyNewSecretKey9999",
            gemini_model="gemini-4-argon",
            fred_api_key="fred1234567890",
        ),
        env_path=env_file,
    )
    saved = env_file.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=AIzaSyNewSecretKey9999" in saved
    assert "DBNOMICS_BROWSER_GEMINI_MODEL=gemini-4-argon" in saved
    assert "FRED_API_KEY=fred1234567890" in saved

    status = get_ai_config_status(
        Settings(
            gemini_api_key="AIzaSyNewSecretKey9999",
            gemini_model="gemini-4-argon",
            fred_api_key="fred1234567890",
        )
    )
    assert status.gemini_key_configured is True
    assert status.gemini_key_masked == "AIza...9999"
    assert status.gemini_model == "gemini-4-argon"
    assert status.fred_key_masked == "fred...7890"
