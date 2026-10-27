"""FastAPI router for the DuckDB analytics warehouse and workbench."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from app.api.routes import get_dbnomics_service
from app.config import get_settings
from app.domain.analytics_models import (
    AiChatRequest,
    AiChatResponse,
    AiConfigStatus,
    AiConfigUpdateRequest,
    AnalyticsQueryResult,
    AnalyticsTransformRequest,
    SqlQueryRequest,
    SyncRequest,
    SyncRunSummary,
    WarehouseSummary,
)
from app.services.ai_assistant_service import AIAssistantService
from app.services.analytics_service import AnalyticsService
from app.services.duckdb_repository import DuckDBAnalyticsRepository
from app.services.env_config_service import get_ai_config_status, update_env_config
from fastapi import APIRouter, Depends

analytics_router = APIRouter()


@lru_cache
def get_analytics_repository() -> DuckDBAnalyticsRepository:
    """Provide the singleton DuckDBAnalyticsRepository instance.

    Returns:
        Configured DuckDBAnalyticsRepository.
    """
    settings = get_settings()
    return DuckDBAnalyticsRepository(settings.analytics_db_path)


@lru_cache
def get_analytics_service() -> AnalyticsService:
    """Provide the singleton AnalyticsService instance.

    Returns:
        Configured AnalyticsService.
    """
    return AnalyticsService(
        settings=get_settings(),
        catalog_source=get_dbnomics_service(),
        repository=get_analytics_repository(),
    )


@lru_cache
def get_ai_assistant_service() -> AIAssistantService:
    """Provide the singleton AIAssistantService instance.

    Returns:
        Configured AIAssistantService.
    """
    return AIAssistantService(
        settings=get_settings(),
        catalog_source=get_dbnomics_service(),
        analytics_service=get_analytics_service(),
    )


AnalyticsServiceDependency = Annotated[AnalyticsService, Depends(get_analytics_service)]
AIAssistantDependency = Annotated[AIAssistantService, Depends(get_ai_assistant_service)]


@analytics_router.get("/catalog", response_model=WarehouseSummary)
def get_analytics_catalog(
    service: AnalyticsServiceDependency,
) -> WarehouseSummary:
    """Return summary metrics, stored series, and recent sync runs."""
    return service.get_catalog_summary()


@analytics_router.post("/sync", response_model=SyncRunSummary)
def sync_series_to_warehouse(
    request: SyncRequest,
    service: AnalyticsServiceDependency,
) -> SyncRunSummary:
    """Sync selected DBnomics series into the local DuckDB warehouse."""
    return service.sync_series(request)


@analytics_router.delete("/series/{series_id:path}")
def delete_warehouse_series(
    series_id: str,
    service: AnalyticsServiceDependency,
) -> dict[str, str]:
    """Delete a stored series and its observations from the DuckDB warehouse."""
    service.delete_stored_series(series_id)
    return {"status": "deleted", "series_id": series_id}


@analytics_router.post("/transform", response_model=AnalyticsQueryResult)
def transform_warehouse_series(
    request: AnalyticsTransformRequest,
    service: AnalyticsServiceDependency,
) -> AnalyticsQueryResult:
    """Run cross-series transformations and correlations on stored series."""
    return service.run_transformation(request)


@analytics_router.post("/sql", response_model=AnalyticsQueryResult)
def execute_warehouse_sql(
    request: SqlQueryRequest,
    service: AnalyticsServiceDependency,
) -> AnalyticsQueryResult:
    """Execute a validated read-only SQL query against the DuckDB warehouse."""
    return service.run_sql_query(request)


@analytics_router.post("/ai/chat", response_model=AiChatResponse)
def chat_with_ai_assistant(
    request: AiChatRequest,
    ai_service: AIAssistantDependency,
) -> AiChatResponse:
    """Run a Gemini 3.8 AI Assistant prompt with DBnomics and DuckDB tool calling."""
    return ai_service.chat(request)


@analytics_router.get("/ai/config", response_model=AiConfigStatus)
def read_ai_config() -> AiConfigStatus:
    """Return masked API key status and selected Gemini model."""
    return get_ai_config_status(get_settings())


@analytics_router.put("/ai/config", response_model=AiConfigStatus)
def save_ai_config(request: AiConfigUpdateRequest) -> AiConfigStatus:
    """Persist API keys/model to `.env` and hot-reload backend singletons."""
    update_env_config(request)
    get_settings.cache_clear()
    get_dbnomics_service.cache_clear()
    get_analytics_service.cache_clear()
    get_ai_assistant_service.cache_clear()
    return get_ai_config_status(get_settings())
