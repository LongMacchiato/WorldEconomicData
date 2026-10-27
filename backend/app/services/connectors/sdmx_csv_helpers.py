"""Pure CSV DataFrame parsing helpers for direct SDMX REST CSV connectors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
from app.models import SeriesSummary

SDMX_METADATA_COLS = frozenset(
    {
        "STRUCTURE",
        "STRUCTURE_ID",
        "STRUCTURE_NAME",
        "ACTION",
        "DATAFLOW",
        "TIME_PERIOD",
        "OBS_VALUE",
        "OBS_STATUS",
        "OBS_COMMENT",
        "UNIT_MEASURE",
        "UNIT_MULT",
        "DECIMALS",
    }
)


def extract_dimension_columns(df: pd.DataFrame) -> list[str]:
    """Return non-metadata SDMX dimension column names."""
    return [
        str(col)
        for col in df.columns
        if str(col).upper() not in SDMX_METADATA_COLS
        and not str(col).startswith(" Unnamed")
    ]


def build_series_code(row: Mapping[str, Any], dim_cols: list[str]) -> str:
    """Construct a dot-separated SDMX series code from dimension columns."""
    parts = [str(row.get(col, "")).strip() for col in dim_cols]
    return ".".join(p for p in parts if p) or "HEADLINE"


def apply_dimension_filters(
    df: pd.DataFrame,
    dimensions: Mapping[str, list[str]] | None,
) -> pd.DataFrame:
    """Filter an SDMX DataFrame by selected dimension code lists."""
    if not dimensions:
        return df
    result = df
    for col, allowed in dimensions.items():
        if col in result.columns and allowed:
            allowed_str = {str(v) for v in allowed}
            result = result[result[col].astype(str).isin(allowed_str)]
    return result


def extract_series_summaries(
    provider_code: str,
    dataset_code: str,
    df: pd.DataFrame,
    *,
    search: str | None,
    dimensions: Mapping[str, list[str]] | None,
) -> list[SeriesSummary]:
    """Extract unique SeriesSummary items from an SDMX CSV DataFrame."""
    if df.empty:
        return []
    dim_cols = extract_dimension_columns(df)
    filtered = apply_dimension_filters(df, dimensions)
    seen: dict[str, SeriesSummary] = {}
    needle = search.strip().casefold() if search and search.strip() else None
    for row in filtered.to_dict(orient="records"):
        code = build_series_code(row, dim_cols)
        if code in seen:
            continue
        dims = {
            col: str(row.get(col, "")) for col in dim_cols if row.get(col) is not None
        }
        name = f"{dataset_code} ({code})"
        if needle and needle not in code.casefold() and needle not in name.casefold():
            continue
        seen[code] = SeriesSummary(
            provider_code=provider_code,
            dataset_code=dataset_code,
            series_code=code,
            series_name=name,
            dimensions=dims,
        )
    return list(seen.values())


def normalize_sdmx_observations(
    provider_code: str,
    dataset_code: str,
    df: pd.DataFrame,
    *,
    selected_codes: set[str],
) -> pd.DataFrame:
    """Normalize an SDMX CSV DataFrame into the canonical observations schema."""
    if df.empty or "OBS_VALUE" not in df.columns or "TIME_PERIOD" not in df.columns:
        return pd.DataFrame()
    dim_cols = extract_dimension_columns(df)
    records: list[dict[str, Any]] = []
    match_all = "ALL" in {c.upper() for c in selected_codes}
    for row in df.to_dict(orient="records"):
        val = row.get("OBS_VALUE")
        if val is None or pd.isna(val):
            continue
        code = build_series_code(row, dim_cols)
        if not match_all and code not in selected_codes:
            continue
        try:
            numeric_val = float(val)
        except TypeError, ValueError:
            continue
        period = str(row.get("TIME_PERIOD", "")).strip()
        if not period:
            continue
        records.append(
            {
                "provider_code": provider_code,
                "dataset_code": dataset_code,
                "series_code": code,
                "series_name": f"{dataset_code} ({code})",
                "period": period,
                "value": numeric_val,
                "@frequency": str(row.get("FREQ") or "quarterly").lower(),
                "unit": str(row.get("UNIT_MEASURE") or "Percent"),
            }
        )
    return pd.DataFrame(records)
