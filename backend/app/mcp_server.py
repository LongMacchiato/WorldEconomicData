"""Local Model Context Protocol (MCP) server for DBnomics and DuckDB Analytics."""

from __future__ import annotations

from typing import Any

from app.api.analytics_routes import get_analytics_service
from app.api.routes import get_dbnomics_service
from app.domain.analytics_protocols import CatalogSourceProtocol
from app.services.ai_tools import AnalyticsToolDispatcher
from app.services.analytics_service import AnalyticsService
from mcp.server.mcpserver import MCPServer


def create_mcp_server(
    catalog_source: CatalogSourceProtocol | None = None,
    analytics_service: AnalyticsService | None = None,
) -> MCPServer:
    """Create and configure the DBnomics + DuckDB MCPServer instance.

    Args:
        catalog_source: Optional CatalogSourceProtocol override for testing.
        analytics_service: Optional AnalyticsService override for testing.

    Returns:
        Configured MCPServer with 7 DBnomics and DuckDB warehouse tools.
    """
    catalog = catalog_source or get_dbnomics_service()
    analytics = analytics_service or get_analytics_service()
    dispatcher = AnalyticsToolDispatcher(catalog, analytics)
    server = MCPServer("dbnomics-analytics-warehouse")

    @server.tool()
    def list_providers(
        search: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """List DBnomics statistical providers with optional search filter."""
        res, _ = dispatcher.dispatch(
            "list_providers", {"search": search, "limit": limit}
        )
        return res

    @server.tool()
    def search_datasets(
        query: str,
        provider_code: str | None = None,
        limit: int = 15,
    ) -> dict[str, Any]:
        """Search DBnomics datasets globally or within a specific provider_code."""
        res, _ = dispatcher.dispatch(
            "search_datasets",
            {"query": query, "provider_code": provider_code, "limit": limit},
        )
        return res

    @server.tool()
    def list_series(
        provider_code: str,
        dataset_code: str,
        search: str | None = None,
        dimensions: dict[str, list[str]] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List time series inside a DBnomics provider/dataset with dimension hints."""
        res, _ = dispatcher.dispatch(
            "list_series",
            {
                "provider_code": provider_code,
                "dataset_code": dataset_code,
                "search": search,
                "dimensions": dimensions,
                "limit": limit,
            },
        )
        return res

    @server.tool()
    def sync_series_to_warehouse(
        provider_code: str,
        dataset_code: str,
        series_codes: list[str],
        start_period: str | None = None,
        end_period: str | None = None,
    ) -> dict[str, Any]:
        """Fetch DBnomics series and upsert them into the local DuckDB warehouse."""
        res, _ = dispatcher.dispatch(
            "sync_series_to_warehouse",
            {
                "provider_code": provider_code,
                "dataset_code": dataset_code,
                "series_codes": series_codes,
                "start_period": start_period,
                "end_period": end_period,
            },
        )
        return res

    @server.tool()
    def get_warehouse_catalog() -> dict[str, Any]:
        """Return stored series and summary counts from the local DuckDB warehouse."""
        res, _ = dispatcher.dispatch("get_warehouse_catalog", {})
        return res

    @server.tool()
    def transform_warehouse_series(
        series_ids: list[str],
        transformation: str = "raw",
        rolling_window: int = 3,
    ) -> dict[str, Any]:
        """Compute transformations and correlations on stored series in DuckDB."""
        res, _ = dispatcher.dispatch(
            "transform_warehouse_series",
            {
                "series_ids": series_ids,
                "transformation": transformation,
                "rolling_window": rolling_window,
            },
        )
        return res

    @server.tool()
    def query_warehouse_sql(sql: str, limit: int = 100) -> dict[str, Any]:
        """Execute a read-only DuckDB SQL query against v_series_observations."""
        res, _ = dispatcher.dispatch(
            "query_warehouse_sql", {"sql": sql, "limit": limit}
        )
        return res

    return server


if __name__ == "__main__":
    mcp_server = create_mcp_server()
    mcp_server.run()
