import csv
import io
import json
import math
from collections.abc import Iterator
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any

import pandas as pd
from app.config import Settings, get_settings
from app.exceptions import ResultLimitExceededError
from app.models import (
    Dataset,
    DatasetDetail,
    DownloadFormat,
    PreviewResponse,
    Provider,
    QueryRequest,
    SeriesPage,
)
from app.services.dbnomics_service import DBnomicsService
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

router = APIRouter()


@lru_cache
def get_dbnomics_service() -> DBnomicsService:
    return DBnomicsService(get_settings())


ServiceDependency = Annotated[DBnomicsService, Depends(get_dbnomics_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
DownloadFormatParameter = Annotated[DownloadFormat, Query(alias="format")]


@router.get("/providers", response_model=list[Provider])
def list_providers(service: ServiceDependency) -> list[Provider]:
    return service.list_providers()


@router.get("/providers/{provider_code}", response_model=Provider)
def get_provider(provider_code: str, service: ServiceDependency) -> Provider:
    return service.get_provider(provider_code)


@router.get(
    "/providers/{provider_code}/datasets",
    response_model=list[Dataset],
)
def list_datasets(
    provider_code: str,
    service: ServiceDependency,
    search: str | None = Query(default=None, max_length=200),
) -> list[Dataset]:
    return service.list_datasets(provider_code, search)


@router.get(
    "/providers/{provider_code}/datasets/{dataset_code}",
    response_model=DatasetDetail,
)
def get_dataset(
    provider_code: str,
    dataset_code: str,
    service: ServiceDependency,
) -> DatasetDetail:
    return service.get_dataset(provider_code, dataset_code)


@router.get("/search", response_model=list[Dataset])
def search_datasets(
    service: ServiceDependency,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Dataset]:
    return service.search_datasets(q, limit=limit)


@router.get(
    "/providers/{provider_code}/datasets/{dataset_code}/series",
    response_model=SeriesPage,
)
def list_series(
    provider_code: str,
    dataset_code: str,
    service: ServiceDependency,
    search: str | None = Query(default=None, max_length=200),
    dimensions: str | None = Query(
        default=None,
        description="JSON object mapping dimension codes to selected value lists",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int | None = Query(default=None, ge=1),
) -> SeriesPage:
    parsed_dimensions: dict[str, list[str]] | None = None
    if dimensions:
        try:
            parsed = json.loads(dimensions)
        except json.JSONDecodeError as error:
            raise HTTPException(
                status_code=422,
                detail="dimensions must be valid JSON",
            ) from error
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=422,
                detail="dimensions must be a JSON object",
            )
        parsed_dimensions = {
            str(key): [str(value) for value in values]
            for key, values in parsed.items()
            if isinstance(values, list)
        }
    return service.list_series(
        provider_code,
        dataset_code,
        search=search,
        dimensions=parsed_dimensions,
        offset=offset,
        limit=limit,
    )


@router.post("/query/preview", response_model=PreviewResponse)
def preview_query(
    query: QueryRequest,
    service: ServiceDependency,
    settings: SettingsDependency,
) -> PreviewResponse:
    frame = service.execute_query(query)
    if query.page_size > settings.preview_max_page_size:
        raise ResultLimitExceededError(
            f"Preview limit cannot exceed {settings.preview_max_page_size} rows"
        )
    offset = (query.page - 1) * query.page_size
    page = frame.iloc[offset : offset + query.page_size]
    total_rows = len(frame)
    return PreviewResponse(
        columns=[str(column) for column in frame.columns],
        rows=_json_safe_records(page),
        chart_series=service.build_chart_series(frame),
        page=query.page,
        page_size=query.page_size,
        total_rows=total_rows,
        has_next_page=offset + len(page) < total_rows,
    )


@router.post("/query/download")
def download_query(
    query: QueryRequest,
    service: ServiceDependency,
    settings: SettingsDependency,
    output_format: DownloadFormatParameter,
) -> StreamingResponse:
    frame = service.execute_query(query)
    if len(frame) > settings.export_max_rows:
        raise ResultLimitExceededError(
            f"Exports cannot exceed {settings.export_max_rows} rows"
        )
    safe_dataset_code = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in query.dataset_code
    )
    filename = f"{query.provider_code}_{safe_dataset_code}.{output_format.value}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if output_format is DownloadFormat.csv:
        return StreamingResponse(
            _csv_chunks(frame),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )
    return StreamingResponse(
        _json_chunks(frame),
        media_type="application/json",
        headers=headers,
    )


def _json_safe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(column): _json_safe_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _json_safe_value(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    return value


def _csv_chunks(frame: pd.DataFrame) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([str(column) for column in frame.columns])
    yield buffer.getvalue()
    for record in _json_safe_records(frame):
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([record[str(column)] for column in frame.columns])
        yield buffer.getvalue()


def _json_chunks(frame: pd.DataFrame) -> Iterator[str]:
    yield "["
    for index, record in enumerate(_json_safe_records(frame)):
        if index:
            yield ","
        yield json.dumps(record, ensure_ascii=False, allow_nan=False)
    yield "]"
