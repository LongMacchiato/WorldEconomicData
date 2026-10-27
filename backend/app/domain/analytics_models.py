"""Domain models for the DuckDB analytics warehouse and workbench."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.models import (
    IDENTIFIER_PATTERN,
    SERIES_CODE_PATTERN,
    ChartSeries,
)
from pydantic import BaseModel, Field, field_validator, model_validator


class TransformationType(StrEnum):
    """Supported analytical time-series transformations."""

    raw = "raw"
    yoy_pct = "yoy_pct"
    pop_pct = "pop_pct"
    rebased_100 = "rebased_100"
    rolling_avg = "rolling_avg"


class SyncRequest(BaseModel):
    """Request payload for syncing selected DBnomics series into DuckDB.

    Attributes:
        provider_code: DBnomics provider identifier.
        dataset_code: DBnomics dataset identifier.
        series_codes: List of series codes to ingest.
        start_period: Optional lower bound period filter.
        end_period: Optional upper bound period filter.
    """

    provider_code: str
    dataset_code: str
    series_codes: list[str] = Field(min_length=1, max_length=25)
    start_period: str | None = None
    end_period: str | None = None

    @field_validator("provider_code", "dataset_code")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        """Validate provider or dataset identifier characters.

        Args:
            value: Raw identifier string.

        Returns:
            Normalized identifier string.
        """
        normalized = value.strip()
        if not IDENTIFIER_PATTERN.fullmatch(normalized):
            raise ValueError(
                "must contain only letters, numbers, '_', '-', '.', '@', '+', or '%'"
            )
        return normalized

    @field_validator("series_codes")
    @classmethod
    def validate_series_codes(cls, series_codes: list[str]) -> list[str]:
        """Deduplicate and validate series codes.

        Args:
            series_codes: Raw list of series codes.

        Returns:
            Deduplicated list of validated series codes.
        """
        normalized_codes: list[str] = []
        for code in series_codes:
            cleaned = code.strip()
            if not SERIES_CODE_PATTERN.fullmatch(cleaned):
                raise ValueError(f"invalid series code: {code!r}")
            if cleaned not in normalized_codes:
                normalized_codes.append(cleaned)
        if not normalized_codes:
            raise ValueError("series_codes must not be empty")
        return normalized_codes


class SyncRunSummary(BaseModel):
    """Audit summary of a single warehouse synchronization run."""

    run_id: str
    provider_code: str
    dataset_code: str
    series_count: int
    observations_upserted: int
    status: str
    error_detail: str | None = None
    started_at: str
    completed_at: str | None = None


class StoredSeries(BaseModel):
    """Metadata and observation coverage of a series stored in DuckDB."""

    series_id: str
    provider_code: str
    dataset_code: str
    series_code: str
    series_name: str
    frequency: str | None = None
    unit: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
    observation_count: int = 0
    min_period: str | None = None
    max_period: str | None = None
    last_synced_at: str


class WarehouseSummary(BaseModel):
    """Overview of the local DuckDB analytics warehouse."""

    total_providers: int
    total_datasets: int
    total_series: int
    total_observations: int
    series: list[StoredSeries] = Field(default_factory=list)
    recent_syncs: list[SyncRunSummary] = Field(default_factory=list)


class AnalyticsTransformRequest(BaseModel):
    """Request payload for running cross-series analytical transformations."""

    series_ids: list[str] = Field(min_length=1, max_length=15)
    transformation: TransformationType = TransformationType.raw
    rolling_window: int = Field(default=3, ge=2, le=60)
    start_period: str | None = None
    end_period: str | None = None

    @model_validator(mode="after")
    def validate_period_range(self) -> AnalyticsTransformRequest:
        """Ensure start_period is not after end_period."""
        if (
            self.start_period is not None
            and self.end_period is not None
            and self.start_period > self.end_period
        ):
            raise ValueError("start_period must not be after end_period")
        return self


class CorrelationPair(BaseModel):
    """Pairwise Pearson correlation between two stored series."""

    series_a: str
    series_b: str
    correlation: float | None = None
    overlapping_periods: int = 0


class AnalyticsQueryResult(BaseModel):
    """Result of an analytical transformation or custom SQL query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    chart_series: list[ChartSeries] = Field(default_factory=list)
    correlations: list[CorrelationPair] = Field(default_factory=list)
    total_rows: int
    executed_sql: str | None = None


class SqlQueryRequest(BaseModel):
    """Request payload for executing a read-only DuckDB SQL query."""

    sql: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=500, ge=1, le=5000)


class AiChatRequest(BaseModel):
    """Request payload for the In-App AI Economist Assistant."""

    prompt: str = Field(min_length=1, max_length=4000)
    previous_interaction_id: str | None = None


class AiToolCallRecord(BaseModel):
    """Summary of a tool executed by the AI Assistant during a turn."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str


class AiChatResponse(BaseModel):
    """Response returned by the In-App AI Economist Assistant."""

    reply: str
    interaction_id: str
    tool_calls: list[AiToolCallRecord] = Field(default_factory=list)
    query_result: AnalyticsQueryResult | None = None
    warehouse_updated: bool = False


class AiConfigStatus(BaseModel):
    """Masked API key and model configuration status for the UI."""

    gemini_key_configured: bool
    gemini_key_masked: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    fred_key_configured: bool = False
    fred_key_masked: str | None = None


class AiConfigUpdateRequest(BaseModel):
    """Request payload for updating API keys and Gemini model in `.env`."""

    gemini_api_key: str | None = None
    gemini_model: str | None = None
    fred_api_key: str | None = None
