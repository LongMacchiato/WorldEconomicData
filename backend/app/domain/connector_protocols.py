"""Pluggable data connector protocols and macro intelligence domain models."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol

import pandas as pd
from app.models import Dataset, DatasetDetail, Provider, QueryRequest, SeriesPage
from pydantic import BaseModel, Field


class ProviderSourceType(StrEnum):
    """Classification of upstream data connector types."""

    dbnomics = "dbnomics"
    sdmx = "sdmx"
    central_bank = "central_bank"
    financial = "financial"


class SdmxEndpointConfig(BaseModel):
    """Configuration for a direct SDMX 2.1 or 3.0 REST API agency."""

    provider_code: str
    provider_name: str
    region: str
    website: str
    base_url: str
    agency_id: str
    sdmx_version: str = "2.1"


class DataConnectorProtocol(Protocol):
    """Protocol implemented by all custom statistical and financial data connectors."""

    @property
    def provider_code(self) -> str:
        """Unique uppercase provider code (e.g. 'SDMX_ABS', 'RBA', 'FRED')."""

    @property
    def source_type(self) -> ProviderSourceType:
        """Category of the data connector."""

    def get_provider(self) -> Provider:
        """Return Provider metadata for catalogue discovery."""

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List datasets exposed by this connector with optional search filter."""

    def get_dataset(self, dataset_code: str) -> DatasetDetail:
        """Return DatasetDetail including dimensions schema."""

    def list_series(
        self,
        dataset_code: str,
        *,
        search: str | None = None,
        dimensions: Mapping[str, list[str]] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> SeriesPage:
        """Return paginated SeriesPage for the given dataset and dimension filters."""

    def fetch_observations(self, query: QueryRequest) -> pd.DataFrame:
        """Fetch normalized time-series observations as a DataFrame."""


class ConnectorStatusItem(BaseModel):
    """Health and configuration status of a registered data connector."""

    provider_code: str
    provider_name: str
    source_type: ProviderSourceType
    requires_api_key: bool = False
    configured: bool = True
    dataset_count: int = 0


class MacroKpiMetric(BaseModel):
    """Single KPI metric for the Systemic Risk Scoreboard."""

    key: str
    label: str
    series_id: str
    value: float | None = None
    unit: str = "%"
    period: str | None = None
    previous_value: float | None = None
    delta: float | None = None
    status_badge: str | None = None


class MacroBriefRecord(BaseModel):
    """Persisted or generated AI Macro Intelligence Brief."""

    insight_date: str
    model_id: str
    summary: str
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class MacroDashboardStatus(BaseModel):
    """Complete payload for the Macro Intelligence Dashboard view."""

    internet_connected: bool
    connectors: list[ConnectorStatusItem] = Field(default_factory=list)
    kpis: list[MacroKpiMetric] = Field(default_factory=list)
    latest_brief: MacroBriefRecord | None = None
