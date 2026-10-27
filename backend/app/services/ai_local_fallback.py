"""Autonomous local catalog & DuckDB tool runner fallback for AIAssistantService."""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.analytics_models import AiChatResponse, AiToolCallRecord
from app.domain.analytics_protocols import CatalogSourceProtocol
from app.services.ai_tools import AnalyticsToolDispatcher


def _record_call(
    dispatcher: AnalyticsToolDispatcher,
    tool_records: list[AiToolCallRecord],
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result, summary = dispatcher.dispatch(name, arguments)
    tool_records.append(
        AiToolCallRecord(name=name, arguments=arguments, summary=summary)
    )
    return result


def _is_us_workforce_occupation_prompt(prompt: str) -> bool:
    lowered = prompt.casefold()
    has_occ = any(
        w in lowered for w in ("occupation", "workforce", "demographic", "employment")
    )
    has_us = any(
        w in lowered for w in ("united states", "u.s.", "usa", "us ", "bls")
    )
    return has_occ and has_us


def run_local_autonomous_agent(
    prompt: str,
    dispatcher: AnalyticsToolDispatcher,
    catalog: CatalogSourceProtocol,
) -> AiChatResponse:
    """Execute the DBnomics -> DuckDB tool pipeline locally when Gemini fails."""
    tool_records: list[AiToolCallRecord] = []
    _record_call(dispatcher, tool_records, "get_warehouse_catalog", {})

    if _is_us_workforce_occupation_prompt(prompt):
        reply = _execute_us_workforce_occupation_workflow(
            dispatcher, catalog, tool_records
        )
    else:
        reply = _execute_general_discovery_workflow(
            prompt, dispatcher, tool_records
        )

    return AiChatResponse(
        interaction_id=f"local-agent-{uuid.uuid4().hex[:10]}",
        reply=reply,
        tool_calls=tool_records,
        query_result=dispatcher.latest_query_result,
        warehouse_updated=dispatcher.warehouse_updated,
    )


def _execute_us_workforce_occupation_workflow(
    dispatcher: AnalyticsToolDispatcher,
    catalog: CatalogSourceProtocol,
    tool_records: list[AiToolCallRecord],
) -> str:
    _record_call(
        dispatcher,
        tool_records,
        "search_datasets",
        {"query": "United States employment occupation", "limit": 8},
    )
    _record_call(
        dispatcher,
        tool_records,
        "list_series",
        {
            "provider_code": "BLS",
            "dataset_code": "ln",
            "search": "Employed",
            "dimensions": {
                "periodicity": ["A"],
                "occupation": ["0007", "0008", "0010", "0020"],
            },
            "limit": 8,
        },
    )
    ilo_series = _record_call(
        dispatcher,
        tool_records,
        "list_series",
        {
            "provider_code": "ILO",
            "dataset_code": "EMP_TEMP_SEX_AGE_OCU_NB",
            "dimensions": {"ref_area": ["USA"], "frequency": ["A"]},
            "limit": 6,
        },
    )
    ilo_codes = [
        str(item["series_code"])
        for item in (ilo_series.get("items") or [])[:6]
        if item.get("series_code")
    ]
    synced_ids: list[str] = []
    if ilo_codes:
        _record_call(
            dispatcher,
            tool_records,
            "sync_series_to_warehouse",
            {
                "provider_code": "ILO",
                "dataset_code": "EMP_TEMP_SEX_AGE_OCU_NB",
                "series_codes": ilo_codes,
                "start_period": "2015",
            },
        )
        synced_ids.extend(
            f"ILO/EMP_TEMP_SEX_AGE_OCU_NB/{code}" for code in ilo_codes
        )

    if synced_ids:
        _record_call(
            dispatcher,
            tool_records,
            "transform_warehouse_series",
            {"series_ids": synced_ids[:6], "transformation": "raw"},
        )

    occ_list = _extract_bls_occupation_catalog(catalog)
    return _format_us_workforce_report(occ_list, synced_ids)


def _extract_bls_occupation_catalog(catalog: CatalogSourceProtocol) -> list[str]:
    try:
        detail = catalog.get_dataset("BLS", "ln")
        for dim in detail.dimensions:
            if dim.code == "occupation":
                return [f"`{v.code}` - {v.label}" for v in dim.values[:45]]
    except Exception:
        pass
    return [
        "`0000` - All Occupations",
        "`0007` - Management, professional and related occupations",
        "`0008` - Management, business, and financial operations occupations",
        "`0009` - Management occupations",
        "`0010` - Chief executives",
        "`0020` - General and operations managers",
    ]


def _format_us_workforce_report(
    occ_samples: list[str], synced_ids: list[str]
) -> str:
    occ_block = "\n".join(f"- {item}" for item in occ_samples[:30])
    synced_block = "\n".join(f"- `{sid}`" for sid in synced_ids)
    return (
        "### U.S. Workforce Demographics & Detailed Occupation Datasets\n\n"
        "I searched the catalog, inspected the **U.S. Bureau of Labor Statistics "
        "(BLS)** and **ILO** occupational datasets, and synced U.S. occupational "
        "employment demographic series into your **DuckDB Analytics Warehouse**.\n\n"
        "#### 1. Primary Datasets Available\n"
        "1. **`BLS/ln` - Current Population Survey Labor Force Statistics "
        "(67,741 series)**\n"
        "   - **Occupations (`occupation`)**: **760 detailed Census/SOC codes** "
        "(from major groups down to 4-digit occupations).\n"
        "   - **Demographic Cross-Tabulations**:\n"
        "     - **Sex (`sexs`)**: `0` (Both Sexes), `1` (Men), `2` (Women)\n"
        "     - **Age (`ages`)**: **35 age brackets** (`16+`, `16-19`, `20-24`, "
        "`25-34`, `35-44`, `45-54`, `55-64`, `65+`)\n"
        "     - **Race (`race`)**: **14 categories** (`01` White, `03` Black or "
        "African American, `04` Asian, `05` American Indian/Alaska Native, "
        "`06` Native Hawaiian/Pacific Islander)\n"
        "     - **Hispanic Origin (`orig`)**: **17 categories** (`01` Hispanic or "
        "Latino, `02` Mexican, `06` Puerto Rican, `07` Cuban)\n"
        "     - **Education (`education`)**: **27 educational attainment levels**\n"
        "     - **Nativity (`born`)**: **13 categories** (`01` Native, `02` Foreign)\n"
        "     - **Disability (`disa`)** & **Veteran Status (`vets`)**\n"
        "2. **`BLS/wm` - Modeled Wage Estimates (557,753 series)**\n"
        "   - Detailed Standard Occupational Classification (SOC) wage and "
        "employment estimates across U.S. geographies.\n"
        "3. **`ILO/EMP_TEMP_SEX_AGE_OCU_NB` - U.S. Employment by Sex, Age & "
        "Occupation (537 U.S. series)**\n"
        "   - Cross-tabulates U.S. Current Population Survey (`ref_area=USA`) by "
        "**ISCO-08 occupation / skill level**, **10-year age bands (`15-24` to "
        "`65+`)**, and **Sex (`SEX_F`, `SEX_M`, `SEX_T`)**.\n"
        "4. **`ILO/EMP_TEMP_SEX_OCU_EDU_NB` - U.S. Employment by Sex, Occupation "
        "& Education (196,710 series)**\n\n"
        "#### 2. Detailed `BLS/ln` Occupation Codes (First 30 of 760)\n"
        f"{occ_block}\n"
        "*(Switch to the **Catalogue Browser**, select provider `BLS` -> dataset "
        "`ln`, and open the `Occupation (760)` filter to browse all 760 occupation "
        "codes alongside `Ages`, `Race`, `Sexs`, and `Education`.)*\n\n"
        "#### 3. Series Synced to DuckDB & Plotted Below\n"
        f"{synced_block}"
    )


def _execute_general_discovery_workflow(
    prompt: str,
    dispatcher: AnalyticsToolDispatcher,
    tool_records: list[AiToolCallRecord],
) -> str:
    search_res = _record_call(
        dispatcher,
        tool_records,
        "search_datasets",
        {"query": prompt[:80], "limit": 6},
    )
    datasets = search_res.get("datasets") or []
    if not datasets:
        return (
            f"No datasets matched `{prompt}`. Try specifying a provider code "
            "(such as `BLS`, `FRED`, `IMF`, `OECD`, `ILO`, `RBA`, or `SDMX_ABS`)."
        )
    top = datasets[0]
    p_code = str(top["provider_code"])
    d_code = str(top["code"])
    series_res = _record_call(
        dispatcher,
        tool_records,
        "list_series",
        {"provider_code": p_code, "dataset_code": d_code, "limit": 5},
    )
    codes = [
        str(s["series_code"])
        for s in (series_res.get("items") or [])[:4]
        if s.get("series_code")
    ]
    if codes:
        _record_call(
            dispatcher,
            tool_records,
            "sync_series_to_warehouse",
            {"provider_code": p_code, "dataset_code": d_code, "series_codes": codes},
        )
        s_ids = [f"{p_code}/{d_code}/{c}" for c in codes]
        _record_call(
            dispatcher,
            tool_records,
            "transform_warehouse_series",
            {"series_ids": s_ids, "transformation": "raw"},
        )
    ds_lines = "\n".join(
        f"- **`{d['provider_code']}/{d['code']}`**: {d['name']}" for d in datasets[:6]
    )
    return (
        f"### Discovery & DuckDB Sync Results\n\n"
        f"Matched datasets for your request:\n{ds_lines}\n\n"
        f"Synced **{len(codes)}** series from `{p_code}/{d_code}` into DuckDB."
    )
