import re
from enum import StrEnum
from typing import Any

from app.config import get_settings
from pydantic import BaseModel, Field, field_validator, model_validator

# DBnomics codes commonly include '@' (OECD) and '.' (series masks).
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_@.+%-]+$")
SERIES_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_@.+%-]+$")


class Provider(BaseModel):
    code: str
    name: str
    region: str | None = None
    website: str | None = None
    source_type: str = "dbnomics"
    requires_api_key: bool = False


class Dataset(BaseModel):
    provider_code: str
    code: str
    name: str
    description: str | None = None
    nb_series: int | None = None


class DimensionCode(BaseModel):
    code: str
    label: str


class Dimension(BaseModel):
    code: str
    label: str
    values: list[DimensionCode] = Field(default_factory=list)


class DatasetDetail(BaseModel):
    provider_code: str
    code: str
    name: str
    description: str | None = None
    nb_series: int | None = None
    dimensions: list[Dimension] = Field(default_factory=list)


class SeriesSummary(BaseModel):
    provider_code: str
    dataset_code: str
    series_code: str
    series_name: str
    dimensions: dict[str, str] = Field(default_factory=dict)


class SeriesPage(BaseModel):
    items: list[SeriesSummary]
    offset: int
    limit: int
    num_found: int
    has_next_page: bool


class ChartPoint(BaseModel):
    period: str
    value: float | None = None


class ChartSeries(BaseModel):
    series_code: str
    series_name: str
    points: list[ChartPoint]


class QueryRequest(BaseModel):
    provider_code: str
    dataset_code: str
    series_codes: list[str] = Field(min_length=1)
    start_period: str | None = None
    end_period: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default_factory=lambda: get_settings().preview_default_page_size,
        ge=1,
    )

    @field_validator("provider_code", "dataset_code")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized_value = value.strip()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "must contain only letters, numbers, '_', '-', '.', '@', '+', or '%'"
            )
        return normalized_value

    @field_validator("series_codes")
    @classmethod
    def validate_series_codes(cls, series_codes: list[str]) -> list[str]:
        settings = get_settings()
        if len(series_codes) > settings.max_selected_series:
            raise ValueError(
                f"at most {settings.max_selected_series} series may be selected"
            )
        normalized_codes: list[str] = []
        for series_code in series_codes:
            normalized_code = series_code.strip()
            if not SERIES_CODE_PATTERN.fullmatch(normalized_code):
                raise ValueError(f"invalid series code: {series_code!r}")
            if normalized_code not in normalized_codes:
                normalized_codes.append(normalized_code)
        if not normalized_codes:
            raise ValueError("series_codes must not be empty")
        return normalized_codes

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        maximum_page_size = get_settings().preview_max_page_size
        if value > maximum_page_size:
            raise ValueError(f"page_size must not exceed {maximum_page_size}")
        return value

    @model_validator(mode="after")
    def validate_period_range(self) -> QueryRequest:
        if (
            self.start_period is not None
            and self.end_period is not None
            and self.start_period > self.end_period
        ):
            raise ValueError("start_period must not be after end_period")
        return self


class PreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    chart_series: list[ChartSeries]
    page: int
    page_size: int
    total_rows: int
    has_next_page: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str


class DownloadFormat(StrEnum):
    csv = "csv"
    json = "json"
