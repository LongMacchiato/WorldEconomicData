"""Registry of built-in sdmx1 statistical providers and endpoint overrides."""

from __future__ import annotations

from dataclasses import dataclass

from app.exceptions import ProviderNotFoundError
from sdmx.format import Version
from sdmx.model import Resource
from sdmx.source import sources as sdmx_sources

ABS_REST_BASE_URL = "https://data.api.abs.gov.au/rest"
BBK_REST_BASE_URL = "https://api.statistiken.bundesbank.de/rest"
ALL_AGENCIES_ID = "all"
LARGE_CATALOGUE_CAVEAT = (
    "The initial dataflow catalogue can take several seconds to load."
)
SDMX3_CAVEAT = "This endpoint uses SDMX 3.0; structure and data support may vary."
NO_DATAFLOW_CAVEAT = (
    "This source does not advertise a dataflow catalogue; browsing may fail."
)
UNREACHABLE_CATALOGUE_CAVEAT = (
    "The published catalogue endpoint is currently unreachable or incompatible; "
    "dataset browsing is disabled for this source."
)


@dataclass(frozen=True, slots=True)
class Sdmx1ProviderDefinition:
    """Metadata and transport flags for an sdmx1 source."""

    id: str
    provider_code: str
    name: str
    description: str
    caveat: str | None = None
    base_url: str | None = None
    uses_lightweight_catalog: bool = False
    agency_id: str | None = None
    supports_catalog: bool = True


@dataclass(frozen=True, slots=True)
class ProviderOverride:
    """Curated overrides for specific sdmx1 sources."""

    name: str | None = None
    description: str | None = None
    caveat: str | None = None
    base_url: str | None = None
    uses_lightweight_catalog: bool = False
    agency_id: str | None = None
    supports_catalog: bool | None = None
    is_excluded: bool = False


PROVIDER_OVERRIDES: dict[str, ProviderOverride] = {
    "ABS": ProviderOverride(
        description="Official statistics for Australia.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        base_url=ABS_REST_BASE_URL,
        uses_lightweight_catalog=True,
    ),
    "ABS_JSON": ProviderOverride(
        description="Australian Bureau of Statistics JSON SDMX endpoint.",
        caveat=NO_DATAFLOW_CAVEAT,
        supports_catalog=False,
    ),
    "BBK": ProviderOverride(
        description="Monetary and financial statistics for Germany (Bundesbank).",
        caveat=LARGE_CATALOGUE_CAVEAT,
        base_url=BBK_REST_BASE_URL,
        uses_lightweight_catalog=True,
        supports_catalog=True,
    ),
    "BIS": ProviderOverride(
        description="International banking and financial statistics.",
    ),
    "COMP": ProviderOverride(
        description="European Commission competition statistics.",
        caveat=UNREACHABLE_CATALOGUE_CAVEAT,
        supports_catalog=False,
    ),
    "ECB": ProviderOverride(
        description="Euro-area monetary, financial, and economic statistics.",
    ),
    "EMPL": ProviderOverride(
        description="European Commission employment and social statistics.",
    ),
    "ESTAT": ProviderOverride(
        description="Official statistics of the European Union.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "ESTAT3": ProviderOverride(
        description="Eurostat SDMX 3.0 dissemination API.",
        caveat=f"{SDMX3_CAVEAT} {UNREACHABLE_CATALOGUE_CAVEAT}",
        supports_catalog=False,
    ),
    "ESTAT_COMEXT": ProviderOverride(
        description="Eurostat Comext and Prodcom trade and production datasets.",
    ),
    "GROW": ProviderOverride(
        description="European Commission internal market and industry statistics.",
    ),
    "ILO": ProviderOverride(
        description="International labour and decent work statistics.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "IMF": ProviderOverride(
        description="International Monetary Fund SDMX Central registry.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "IMF_DATA": ProviderOverride(
        description="International Monetary Fund data API (SDMX 2.1).",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "IMF_DATA3": ProviderOverride(
        description="International Monetary Fund data API (SDMX 3.0).",
        caveat=SDMX3_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "INEGI": ProviderOverride(
        description="Official statistics for Mexico (SNIEG SDMX service).",
        agency_id=ALL_AGENCIES_ID,
    ),
    "INSEE": ProviderOverride(description="Official statistics for France."),
    "ISTAT": ProviderOverride(description="Official statistics for Italy."),
    "LSD": ProviderOverride(description="Official statistics for Lithuania."),
    "NB": ProviderOverride(description="Monetary and financial statistics for Norway."),
    "OECD": ProviderOverride(
        description="International economic and social statistics.",
        uses_lightweight_catalog=True,
    ),
    "OECD3": ProviderOverride(
        description="OECD SDMX 3.0 / REST v2 endpoint.",
        caveat=SDMX3_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "SGR": ProviderOverride(
        description="SDMX Global Registry structural metadata.",
        caveat=UNREACHABLE_CATALOGUE_CAVEAT,
        supports_catalog=False,
    ),
    "SPC": ProviderOverride(description="Pacific Community (SPC) DotStat statistics."),
    "UNESCO": ProviderOverride(
        description="UNESCO Institute for Statistics education and culture data.",
        caveat=UNREACHABLE_CATALOGUE_CAVEAT,
        supports_catalog=False,
    ),
    "UNICEF": ProviderOverride(
        description="UNICEF global child and development indicators.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "UNSD": ProviderOverride(
        description="United Nations Statistics Division data services.",
        caveat=LARGE_CATALOGUE_CAVEAT,
        uses_lightweight_catalog=True,
    ),
    "UY110": ProviderOverride(
        description="Labour market statistics for Uruguay.",
        caveat=UNREACHABLE_CATALOGUE_CAVEAT,
        supports_catalog=False,
    ),
    "WB": ProviderOverride(
        name="World Bank WITS",
        description="World Bank World Integrated Trade Solution statistics.",
    ),
    "WB_WDI": ProviderOverride(
        name="World Bank WDI",
        description="World Bank World Development Indicators.",
        caveat=NO_DATAFLOW_CAVEAT,
        supports_catalog=False,
    ),
}


def _is_sdmx3_source(source: object) -> bool:
    versions = getattr(source, "versions", None) or set()
    return Version["3.0.0"] in versions


def _build_providers() -> tuple[Sdmx1ProviderDefinition, ...]:
    providers: list[Sdmx1ProviderDefinition] = []
    for source_id, source in sdmx_sources.items():
        override = PROVIDER_OVERRIDES.get(source_id, ProviderOverride())
        if override.is_excluded:
            continue
        supports_dataflow = bool(source.supports.get(Resource.dataflow, False))
        supports_catalog = (
            override.supports_catalog
            if override.supports_catalog is not None
            else supports_dataflow
        )
        caveat_parts: list[str] = []
        if override.caveat:
            caveat_parts.append(override.caveat)
        elif not supports_catalog:
            caveat_parts.append(NO_DATAFLOW_CAVEAT)
        elif _is_sdmx3_source(source) and SDMX3_CAVEAT not in caveat_parts:
            caveat_parts.append(SDMX3_CAVEAT)
        source_name = str(getattr(source, "name", source_id) or source_id)
        sid = str(source_id)
        providers.append(
            Sdmx1ProviderDefinition(
                id=sid,
                provider_code=f"SDMX1_{sid.upper()}",
                name=f"{override.name or source_name} (SDMX)",
                description=override.description
                or f"SDMX data service for {source_name}.",
                caveat=" ".join(caveat_parts) if caveat_parts else None,
                base_url=override.base_url
                or str(getattr(source, "url", "") or "")
                or None,
                uses_lightweight_catalog=override.uses_lightweight_catalog,
                agency_id=override.agency_id,
                supports_catalog=supports_catalog,
            )
        )
    return tuple(sorted(providers, key=lambda p: (p.name.casefold(), p.id)))


SDMX1_PROVIDERS: tuple[Sdmx1ProviderDefinition, ...] = _build_providers()
SDMX1_BY_ID = {p.id.upper(): p for p in SDMX1_PROVIDERS}
SDMX1_BY_CODE = {p.provider_code.upper(): p for p in SDMX1_PROVIDERS}


def get_sdmx1_provider(identifier: str) -> Sdmx1ProviderDefinition:
    """Look up an Sdmx1ProviderDefinition by source id or `SDMX1_<ID>` code."""
    key = identifier.strip().upper()
    provider = SDMX1_BY_CODE.get(key) or SDMX1_BY_ID.get(key)
    if provider is None:
        raise ProviderNotFoundError(f"Unknown SDMX provider: {identifier}")
    return provider
