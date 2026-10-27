"""XML, DSD structure, and DataFrame parsing helpers for sdmx1 connectors."""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
from app.exceptions import UpstreamResponseError
from app.models import Dataset, Dimension, DimensionCode, SeriesSummary
from app.services.connectors.sdmx1_registry import Sdmx1ProviderDefinition

HTTP_NOT_FOUND = 404


@dataclass(frozen=True, slots=True)
class Sdmx1DimensionMeta:
    """Internal DSD dimension metadata including position and time flag."""

    code: str
    label: str
    position: int
    values: list[DimensionCode]
    is_time_dimension: bool = False


@dataclass(frozen=True, slots=True)
class Sdmx1StructureBundle:
    """Pairs extracted Dimension models with the underlying sdmx1 DSD object."""

    dimensions: list[Sdmx1DimensionMeta]
    dsd: Any


def agency_kwargs(provider: Sdmx1ProviderDefinition) -> dict[str, str]:
    """Return optional `agency_id` keyword argument for sdmx1 requests."""
    return {} if provider.agency_id is None else {"agency_id": provider.agency_id}


def upstream_error_detail(error: BaseException) -> str:
    """Format an upstream exception or HTTP status into a concise detail string."""
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    return (
        f"HTTP {status_code}"
        if status_code is not None
        else str(error).strip() or error.__class__.__name__
    )


def is_http_not_found(error: BaseException) -> bool:
    """Check whether an upstream exception represents HTTP 404 Not Found."""
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) == HTTP_NOT_FOUND


def display_name(value: Any, fallback: str) -> str:
    """Resolve a human-readable display label from an sdmx1 InternationalString."""
    if value is None:
        return fallback
    localized_default = getattr(value, "localized_default", None)
    if callable(localized_default):
        localized_default = localized_default()
    if localized_default:
        return str(localized_default)
    text = str(value)
    return text if text else fallback


def mapping_get(mapping: Any, key: str) -> Any:
    """Look up an item by key or matching `.id` attribute across mappings/iterables."""
    if isinstance(mapping, Mapping):
        if key in mapping:
            return mapping[key]
        return next(
            (v for v in mapping.values() if str(getattr(v, "id", "")) == key),
            None,
        )
    return next(
        (v for v in mapping or [] if str(getattr(v, "id", "")) == key),
        None,
    )


def datasets_from_message(provider_code: str, message: Any) -> list[Dataset]:
    """Convert an sdmx1 StructureMessage dataflow collection into Dataset models."""
    raw_dataflows = getattr(message, "dataflow", {})
    values = (
        raw_dataflows.values() if isinstance(raw_dataflows, Mapping) else raw_dataflows
    )
    items = [
        Dataset(
            provider_code=provider_code,
            code=str(getattr(flow, "id", "")),
            name=display_name(
                getattr(flow, "name", None), str(getattr(flow, "id", ""))
            ),
            description=display_name(getattr(flow, "description", None), "") or None,
        )
        for flow in values
        if getattr(flow, "id", None)
    ]
    return dedupe_datasets(items)


def parse_dataflow_catalog(provider_code: str, content: bytes) -> list[Dataset]:
    """Parse lightweight SDMX XML dataflow stubs without full sdmx1 overhead."""
    root = ElementTree.fromstring(content)
    datasets: list[Dataset] = []
    for element in root.iter():
        if _xml_local_name(element.tag) != "Dataflow":
            continue
        flow_id = element.get("id", "")
        if not flow_id:
            continue
        names = {
            child.get("{http://www.w3.org/XML/1998/namespace}lang", ""): child.text
            for child in element
            if _xml_local_name(child.tag) == "Name" and child.text
        }
        name = names.get("en") or next(iter(names.values()), flow_id)
        datasets.append(
            Dataset(
                provider_code=provider_code,
                code=flow_id,
                name=name or flow_id,
                description=element.get("agencyID"),
            )
        )
    return dedupe_datasets(datasets)


def dedupe_datasets(datasets: list[Dataset]) -> list[Dataset]:
    """Deduplicate datasets by code while preserving order."""
    unique: list[Dataset] = []
    seen: set[str] = set()
    for ds in datasets:
        if ds.code in seen:
            continue
        seen.add(ds.code)
        unique.append(ds)
    return unique


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def extract_dimensions(structure: Any) -> list[Sdmx1DimensionMeta]:
    """Extract ordered Dimension metadata and codelists from an sdmx1 DSD."""
    dimensions_container = getattr(structure, "dimensions", None)
    components = getattr(dimensions_container, "components", None)
    if components is None:
        descriptor = getattr(structure, "dimension_descriptor", None)
        components = getattr(descriptor, "components", [])
    result: list[Sdmx1DimensionMeta] = []
    for index, raw_dim in enumerate(components or []):
        dim_id = str(getattr(raw_dim, "id", ""))
        if not dim_id:
            continue
        rep = getattr(raw_dim, "local_representation", None)
        codelist = getattr(rep, "enumerated", None)
        raw_codes = getattr(codelist, "items", None)
        if raw_codes is None:
            raw_codes = getattr(codelist, "codes", None)
        values = _extract_codes(raw_codes)
        class_name = type(raw_dim).__name__.casefold()
        is_time = dim_id.casefold() in {"time", "time_period"} or "time" in class_name
        result.append(
            Sdmx1DimensionMeta(
                code=dim_id,
                label=display_name(getattr(raw_dim, "name", None), dim_id),
                position=index,
                values=values,
                is_time_dimension=is_time,
            )
        )
    return result


def to_public_dimensions(metas: Sequence[Sdmx1DimensionMeta]) -> list[Dimension]:
    """Convert non-time Sdmx1DimensionMeta entries into public Dimension models."""
    return [
        Dimension(code=m.code, label=m.label, values=m.values)
        for m in metas
        if not m.is_time_dimension
    ]


def _extract_codes(raw_codes: Any) -> list[DimensionCode]:
    values: Iterable[Any]
    if isinstance(raw_codes, Mapping):
        values = raw_codes.values()
    elif isinstance(raw_codes, Sequence) and not isinstance(raw_codes, str):
        values = raw_codes
    else:
        values = []
    return [
        DimensionCode(
            code=str(getattr(c, "id", "")),
            label=display_name(getattr(c, "name", None), str(getattr(c, "id", ""))),
        )
        for c in values
        if getattr(c, "id", None)
    ]


def build_synthetic_series_from_dsd(
    provider_code: str,
    dataset_code: str,
    metas: Sequence[Sdmx1DimensionMeta],
    *,
    search: str | None = None,
    dimensions: Mapping[str, list[str]] | None = None,
) -> list[SeriesSummary]:
    """Synthesize selectable SDMX series keys from DSD dimensions and filters."""
    query_dims = [
        m for m in sorted(metas, key=lambda d: d.position) if not m.is_time_dimension
    ]
    if not query_dims:
        return [
            SeriesSummary(
                provider_code=provider_code,
                dataset_code=dataset_code,
                series_code="ALL",
                series_name=f"{dataset_code} (All Series)",
                dimensions={},
            )
        ]
    key_parts: list[str] = []
    dim_summary: dict[str, str] = {}
    for m in query_dims:
        selected = (dimensions or {}).get(m.code, [])
        if selected:
            key_parts.append("+".join(selected))
            dim_summary[m.code] = "+".join(selected)
        else:
            key_parts.append("")
    wildcard_key = ".".join(key_parts)
    items = [
        SeriesSummary(
            provider_code=provider_code,
            dataset_code=dataset_code,
            series_code=wildcard_key or "ALL",
            series_name=(
                f"{dataset_code} ({wildcard_key})"
                if any(key_parts)
                else f"{dataset_code} (All matching series)"
            ),
            dimensions=dim_summary,
        )
    ]
    first_dim = query_dims[0]
    for code_item in first_dim.values[:25]:
        per_code_parts = [
            code_item.code if idx == 0 else key_parts[idx]
            for idx in range(len(query_dims))
        ]
        series_key = ".".join(per_code_parts)
        items.append(
            SeriesSummary(
                provider_code=provider_code,
                dataset_code=dataset_code,
                series_code=series_key,
                series_name=f"{code_item.label} ({series_key})",
                dimensions={**dim_summary, first_dim.code: code_item.code},
            )
        )
    if not search or not search.strip():
        return items
    needle = search.strip().casefold()
    return [
        s
        for s in items
        if needle in s.series_code.casefold() or needle in s.series_name.casefold()
    ]


def to_flat_dataframe(converted: Any) -> pd.DataFrame:
    """Normalize `sdmx.to_pandas` output into a flat pandas DataFrame."""
    if isinstance(converted, pd.Series):
        value_name = converted.name or "value"
        return converted.rename(value_name).reset_index()
    if isinstance(converted, pd.DataFrame):
        if converted.index.nlevels > 1 or converted.index.name is not None:
            return converted.reset_index()
        return converted.reset_index(drop=True)
    if isinstance(converted, Mapping):
        frames = [to_flat_dataframe(v) for v in converted.values()]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    raise UpstreamResponseError("The provider response was not tabular")
