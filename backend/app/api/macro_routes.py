"""FastAPI router for Macro-Economic Risk Scoreboard, Connectors & Local MLX Briefs."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from app.api.analytics_routes import get_analytics_service
from app.config import get_settings
from app.domain.connector_protocols import (
    ConnectorStatusItem,
    MacroBriefRecord,
    MacroDashboardStatus,
)
from app.services.composite_catalog_service import (
    CompositeCatalogService,
    build_default_composite_catalog,
)
from app.services.mlx_macro_service import MlxMacroService
from fastapi import APIRouter, Depends

macro_router = APIRouter()


@lru_cache
def get_composite_catalog_service() -> CompositeCatalogService:
    """Provide the singleton CompositeCatalogService instance."""
    return build_default_composite_catalog(get_settings())


@lru_cache
def get_mlx_macro_service() -> MlxMacroService:
    """Provide the singleton MlxMacroService instance."""
    return MlxMacroService(
        settings=get_settings(),
        catalog=get_composite_catalog_service(),
        analytics=get_analytics_service(),
    )


MacroServiceDependency = Annotated[MlxMacroService, Depends(get_mlx_macro_service)]
CatalogDependency = Annotated[
    CompositeCatalogService, Depends(get_composite_catalog_service)
]


@macro_router.get("/status", response_model=MacroDashboardStatus)
def get_macro_dashboard_status(
    service: MacroServiceDependency,
) -> MacroDashboardStatus:
    """Return systemic risk KPIs, connector statuses, and the latest AI Macro Brief."""
    return service.get_dashboard_status()


@macro_router.post("/refresh", response_model=MacroDashboardStatus)
def refresh_macro_dashboard(
    service: MacroServiceDependency,
) -> MacroDashboardStatus:
    """Sync core macro/market bundles into DuckDB and generate a fresh AI brief."""
    return service.refresh_macro_intelligence()


@macro_router.get("/insights", response_model=MacroBriefRecord | None)
def get_latest_macro_insight(
    service: MacroServiceDependency,
) -> MacroBriefRecord | None:
    """Return the latest AI Macro Brief stored in DuckDB."""
    return service.get_latest_brief()


@macro_router.get("/connectors", response_model=list[ConnectorStatusItem])
def list_registered_connectors(
    catalog: CatalogDependency,
) -> list[ConnectorStatusItem]:
    """List all registered direct statistical and financial connectors."""
    return catalog.list_connector_statuses()
