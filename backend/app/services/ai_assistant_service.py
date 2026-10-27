"""Gemini 3.8 AI Economist Assistant service using the Interactions API."""

from __future__ import annotations

from typing import Any, Protocol

from app.config import Settings
from app.domain.analytics_models import (
    AiChatRequest,
    AiChatResponse,
    AiToolCallRecord,
)
from app.domain.analytics_protocols import CatalogSourceProtocol
from app.exceptions import UpstreamUnavailableError
from app.services.ai_local_fallback import run_local_autonomous_agent
from app.services.ai_tools import TOOL_DECLARATIONS, AnalyticsToolDispatcher
from app.services.analytics_service import AnalyticsService
from google import genai

SYSTEM_INSTRUCTION = (
    "You are an autonomous AI Macroeconomic Analyst Agent embedded inside the "
    "DBnomics Data Browser and DuckDB Analytics Workbench. "
    "Whenever a user asks a question about economic data, follow this autonomous "
    "agent workflow without asking the user to manually browse or sync first:\n"
    "1. CHECK WAREHOUSE: Call `get_warehouse_catalog` to inspect what series are "
    "already stored in DuckDB.\n"
    "2. DISCOVER IN DBNOMICS: If the required series are not yet in DuckDB, call "
    "`search_datasets` (using `query` keywords and/or `provider_code` such as IMF, "
    "OECD, ECB, WB, EUROSTAT, FED) or `list_providers`. Then call `list_series` "
    "(using `search` keywords or `dimensions` filters from `dataset_dimensions`) "
    "to find the exact `series_code`s.\n"
    "3. INGEST TO DUCKDB: Call `sync_series_to_warehouse` with the discovered "
    "`provider_code`, `dataset_code`, and `series_codes` to load the observations "
    "into the local DuckDB star-schema database.\n"
    "4. RUN ANALYTICS FOR UI: Always finish by calling `transform_warehouse_series` "
    "(raw, yoy_pct, pop_pct, rebased_100, rolling_avg) or `query_warehouse_sql` "
    "(SELECT including `series_id`, `series_name`, `period`, `value` FROM "
    "`v_series_observations`) so the user's interactive chart and table populate "
    "automatically.\n"
    "5. SYNTHESIZE: Provide a concise, data-driven explanation citing the exact "
    "series IDs (`provider/dataset/series_code`), periods, and values."
)

MAX_TOOL_ROUNDS = 10


class InteractionsNamespaceProtocol(Protocol):
    """Protocol for the Google GenAI client.interactions namespace."""

    def create(self, **kwargs: Any) -> Any:
        """Create a Gemini interaction."""


class GenAIClientProtocol(Protocol):
    """Protocol for the Google GenAI Client to support unit test mocking."""

    @property
    def interactions(self) -> InteractionsNamespaceProtocol:
        """Return the interactions namespace."""


class AIAssistantService:
    """Orchestrates multi-turn Gemini Interactions with DBnomics & DuckDB tools."""

    def __init__(
        self,
        settings: Settings,
        catalog_source: CatalogSourceProtocol,
        analytics_service: AnalyticsService,
        genai_client: GenAIClientProtocol | None = None,
    ) -> None:
        """Initialize the AIAssistantService.

        Args:
            settings: Application settings containing Gemini API key and model.
            catalog_source: Upstream DBnomics catalog service.
            analytics_service: Local DuckDB analytics service.
            genai_client: Optional injected GenAI client for testing.
        """
        self._settings = settings
        self._catalog = catalog_source
        self._analytics = analytics_service
        self._client = genai_client

    def _get_client(self) -> GenAIClientProtocol:
        """Resolve the configured GenAI client or raise 503 if unconfigured.

        Returns:
            Configured GenAIClientProtocol instance.

        Raises:
            UpstreamUnavailableError: If GEMINI_API_KEY is not configured.
        """
        if self._client is not None:
            return self._client
        if not self._settings.gemini_api_key:
            raise UpstreamUnavailableError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in your "
                "environment or .env file to enable the AI Assistant."
            )
        self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    def chat(self, request: AiChatRequest) -> AiChatResponse:
        """Execute a user prompt with automatic multi-step tool calling.

        Args:
            request: AiChatRequest with user message and optional interaction ID.

        Returns:
            AiChatResponse with assistant text, tool trail, and latest query result.
        """
        client = self._get_client()
        dispatcher = AnalyticsToolDispatcher(self._catalog, self._analytics)
        tool_records: list[AiToolCallRecord] = []

        try:
            interaction = self._create_interaction(
                client,
                input_payload=request.prompt,
                previous_interaction_id=request.previous_interaction_id,
            )

            for _ in range(MAX_TOOL_ROUNDS):
                if getattr(interaction, "status", None) != "requires_action":
                    break
                pending_calls = _extract_pending_function_calls(interaction)
                if not pending_calls:
                    break
                tool_results = _execute_pending_calls(
                    pending_calls, dispatcher, tool_records
                )
                interaction = self._create_interaction(
                    client,
                    input_payload=tool_results,
                    previous_interaction_id=str(interaction.id),
                )
        except Exception:
            return run_local_autonomous_agent(
                request.prompt, dispatcher, self._catalog
            )

        reply = getattr(interaction, "output_text", None) or (
            "Completed tool execution."
        )
        return AiChatResponse(
            interaction_id=str(getattr(interaction, "id", "")),
            reply=str(reply),
            tool_calls=tool_records,
            query_result=dispatcher.latest_query_result,
            warehouse_updated=dispatcher.warehouse_updated,
        )

    def _create_interaction(
        self,
        client: GenAIClientProtocol,
        *,
        input_payload: Any,
        previous_interaction_id: str | None,
    ) -> Any:
        """Invoke client.interactions.create with interaction-scoped config."""
        kwargs: dict[str, Any] = {
            "model": self._settings.gemini_model,
            "input": input_payload,
            "system_instruction": SYSTEM_INSTRUCTION,
            "tools": TOOL_DECLARATIONS,
        }
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id
        return client.interactions.create(**kwargs)


def _extract_pending_function_calls(interaction: Any) -> list[Any]:
    """Return function_call steps that do not yet have a matching function_result."""
    steps = getattr(interaction, "steps", None) or []
    executed_ids = {
        getattr(step, "call_id", None)
        for step in steps
        if getattr(step, "type", None) == "function_result"
    }
    return [
        step
        for step in steps
        if getattr(step, "type", None) == "function_call"
        and getattr(step, "id", None) not in executed_ids
    ]


def _execute_pending_calls(
    pending_calls: list[Any],
    dispatcher: AnalyticsToolDispatcher,
    tool_records: list[AiToolCallRecord],
) -> list[dict[str, Any]]:
    """Run each pending function call through the dispatcher and format results."""
    results: list[dict[str, Any]] = []
    for fc_step in pending_calls:
        name = str(getattr(fc_step, "name", ""))
        raw_args = (
            getattr(fc_step, "arguments", None) or getattr(fc_step, "args", None) or {}
        )
        args_dict = dict(raw_args) if isinstance(raw_args, dict) else {}
        result_dict, summary = dispatcher.dispatch(name, args_dict)
        tool_records.append(
            AiToolCallRecord(
                name=name,
                arguments=args_dict,
                summary=summary,
            )
        )
        results.append(
            {
                "type": "function_result",
                "name": name,
                "call_id": str(getattr(fc_step, "id", "")),
                "result": result_dict,
            }
        )
    return results
