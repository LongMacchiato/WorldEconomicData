"""Unified tool definitions and dispatcher for Gemini AI Assistant and MCP Server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.domain.analytics_models import (
    AnalyticsQueryResult,
    AnalyticsTransformRequest,
    SqlQueryRequest,
    SyncRequest,
    TransformationType,
)
from app.domain.analytics_protocols import CatalogSourceProtocol
from app.services.analytics_service import AnalyticsService


def _str(desc: str) -> dict[str, str]:
    return {"type": "string", "description": desc}


def _int(desc: str) -> dict[str, str]:
    return {"type": "integer", "description": desc}


def _fn_tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Build a Function Calling declaration dictionary."""
    params: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": params,
    }


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    _fn_tool(
        "list_providers",
        "List DBnomics providers with optional search filter.",
        {
            "search": _str("Substring filter on provider code or name."),
            "limit": _int("Max providers to return (default 25)."),
        },
    ),
    _fn_tool(
        "search_datasets",
        "Search DBnomics datasets globally or within a specific provider_code.",
        {
            "query": _str("Keywords to search for (e.g. 'CPI', 'GDP')."),
            "provider_code": _str("Optional provider code (e.g. IMF, OECD, ECB)."),
            "limit": _int("Max datasets to return (default 15)."),
        },
        required=["query"],
    ),
    _fn_tool(
        "list_series",
        "List series in a DBnomics dataset with search/dimension filters and hints.",
        {
            "provider_code": _str("Provider code."),
            "dataset_code": _str("Dataset code."),
            "search": _str("Text filter for series name or code."),
            "dimensions": {
                "type": "object",
                "description": "Dimension code to list of values map.",
            },
            "limit": _int("Max series to return (default 20)."),
        },
        required=["provider_code", "dataset_code"],
    ),
    _fn_tool(
        "sync_series_to_warehouse",
        "Fetch DBnomics series and upsert into DuckDB warehouse.",
        {
            "provider_code": _str("Provider code."),
            "dataset_code": _str("Dataset code."),
            "series_codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of series codes to ingest.",
            },
            "start_period": _str("Start period."),
            "end_period": _str("End period."),
        },
        required=["provider_code", "dataset_code", "series_codes"],
    ),
    _fn_tool(
        "get_warehouse_catalog",
        "Return stored series and summary counts from DuckDB.",
        {},
    ),
    _fn_tool(
        "transform_warehouse_series",
        "Compute transformations (raw, yoy_pct, pop_pct, rebased_100, rolling_avg).",
        {
            "series_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Full series IDs (provider/dataset/series_code).",
            },
            "transformation": {
                "type": "string",
                "enum": ["raw", "yoy_pct", "pop_pct", "rebased_100", "rolling_avg"],
                "description": "Analytical transformation type.",
            },
            "rolling_window": _int("Window length for rolling_avg."),
        },
        required=["series_ids"],
    ),
    _fn_tool(
        "query_warehouse_sql",
        "Execute a read-only DuckDB SQL query against v_series_observations.",
        {
            "sql": _str("Read-only SELECT SQL query."),
            "limit": _int("Row cap (default 100)."),
        },
        required=["sql"],
    ),
]


class AnalyticsToolDispatcher:
    """Executes AI/MCP tools against CatalogSourceProtocol and AnalyticsService."""

    def __init__(
        self,
        catalog_source: CatalogSourceProtocol,
        analytics_service: AnalyticsService,
    ) -> None:
        """Initialize the tool dispatcher.

        Args:
            catalog_source: Upstream DBnomics catalog service.
            analytics_service: Local DuckDB analytics service.
        """
        self._catalog = catalog_source
        self._analytics = analytics_service
        self.warehouse_updated: bool = False
        self.latest_query_result: AnalyticsQueryResult | None = None
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "list_providers": self._handle_list_providers,
            "search_datasets": self._handle_search_datasets,
            "list_series": self._handle_list_series,
            "sync_series_to_warehouse": self._handle_sync_series,
            "get_warehouse_catalog": self._handle_get_catalog,
            "transform_warehouse_series": self._handle_transform,
            "query_warehouse_sql": self._handle_sql,
        }

    def dispatch(
        self, name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        """Dispatch a tool call by name and return a JSON-safe result and summary.

        Args:
            name: Tool name.
            arguments: Tool call arguments dictionary.

        Returns:
            Tuple of (result_dict, human_readable_summary).
        """
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}, f"Unknown tool {name}"
        try:
            result = handler(arguments)
            summary = str(result.get("_summary") or f"Executed {name}")
            return result, summary
        except Exception as error:
            return {"error": str(error)}, f"{name} failed: {error}"

    def _handle_list_providers(self, args: dict[str, Any]) -> dict[str, Any]:
        providers = self._catalog.list_providers()
        needle = str(args.get("search") or "").strip().casefold()
        if needle:
            providers = [
                p
                for p in providers
                if needle in p.code.casefold() or needle in p.name.casefold()
            ]
        limit = max(1, min(int(args.get("limit") or 25), 100))
        sliced = [p.model_dump() for p in providers[:limit]]
        return {
            "providers": sliced,
            "total_matching": len(providers),
            "_summary": f"Listed {len(sliced)} providers",
        }

    def _handle_search_datasets(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        provider_code = str(args.get("provider_code") or "").strip()
        limit = max(1, min(int(args.get("limit") or 15), 50))
        if provider_code and hasattr(self._catalog, "list_datasets"):
            datasets = self._catalog.list_datasets(provider_code, search=query or None)[
                :limit
            ]
        else:
            datasets = self._catalog.search_datasets(query, limit=limit)
        label = query or provider_code
        return {
            "datasets": [d.model_dump() for d in datasets],
            "_summary": f"Found {len(datasets)} datasets for '{label}'",
        }

    def _handle_list_series(self, args: dict[str, Any]) -> dict[str, Any]:
        provider_code = str(args["provider_code"])
        dataset_code = str(args["dataset_code"])
        search = str(args["search"]) if args.get("search") else None
        raw_dims = args.get("dimensions")
        dims: dict[str, list[str]] | None = None
        if isinstance(raw_dims, dict):
            dims = {
                str(k): [str(v) for v in (vals if isinstance(vals, list) else [vals])]
                for k, vals in raw_dims.items()
                if vals
            }
        limit = max(1, min(int(args.get("limit") or 20), 50))
        page = self._catalog.list_series(
            provider_code, dataset_code, dimensions=dims, search=search, limit=limit
        )
        dataset = self._catalog.get_dataset(provider_code, dataset_code)
        dim_hints = [
            {
                "code": d.code,
                "label": d.label,
                "sample_values": [v.model_dump() for v in d.values[:20]],
            }
            for d in dataset.dimensions
        ]
        n_items = len(page.items)
        return {
            "items": [item.model_dump() for item in page.items],
            "num_found": page.num_found,
            "dataset_dimensions": dim_hints,
            "_summary": f"Listed {n_items} series in {provider_code}/{dataset_code}",
        }

    def _handle_sync_series(self, args: dict[str, Any]) -> dict[str, Any]:
        req = SyncRequest(
            provider_code=str(args["provider_code"]),
            dataset_code=str(args["dataset_code"]),
            series_codes=[str(c) for c in args.get("series_codes") or []],
            start_period=str(args["start_period"])
            if args.get("start_period")
            else None,
            end_period=str(args["end_period"]) if args.get("end_period") else None,
        )
        summary = self._analytics.sync_series(req)
        self.warehouse_updated = True
        obs = summary.observations_upserted
        return {
            **summary.model_dump(),
            "_summary": f"Synced {summary.series_count} series ({obs} obs)",
        }

    def _handle_get_catalog(self, _args: dict[str, Any]) -> dict[str, Any]:
        summary = self._analytics.get_catalog_summary()
        payload = summary.model_dump()
        payload["_summary"] = (
            f"Warehouse has {summary.total_series} series "
            f"({summary.total_observations} observations)"
        )
        return payload

    def _handle_transform(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_transform = str(args.get("transformation") or "raw")
        req = AnalyticsTransformRequest(
            series_ids=[str(s) for s in args.get("series_ids") or []],
            transformation=TransformationType(raw_transform),
            rolling_window=int(args.get("rolling_window") or 3),
        )
        res = self._analytics.run_transformation(req)
        self.latest_query_result = res
        return {
            "total_rows": res.total_rows,
            "correlations": [c.model_dump() for c in res.correlations],
            "sample_rows": res.rows[:40],
            "_summary": f"Computed {raw_transform} across {len(req.series_ids)} series",
        }

    def _handle_sql(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(int(args.get("limit") or 100), 500))
        req = SqlQueryRequest(sql=str(args["sql"]), limit=limit)
        res = self._analytics.run_sql_query(req)
        self.latest_query_result = res
        return {
            "columns": res.columns,
            "total_rows": res.total_rows,
            "rows": res.rows[:50],
            "_summary": f"Executed SQL query ({res.total_rows} rows)",
        }
