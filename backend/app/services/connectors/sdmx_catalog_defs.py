"""Curated SDMX 2.1 and 3.0 endpoint configurations and dataflow specifications."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.connector_protocols import SdmxEndpointConfig


@dataclass(frozen=True)
class SdmxDatasetSpec:
    """Curated SDMX dataflow definition for fast discovery."""

    code: str
    dataflow_ref: str
    name: str
    description: str
    key_filter: str = "all"


ABS_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="ANA_AGG",
        dataflow_ref="ABS,ANA_AGG",
        name="Australian National Accounts: Key Aggregates (GDP)",
        description="Headline quarterly GDP chain volume & percentage change series.",
    ),
    SdmxDatasetSpec(
        code="CPI",
        dataflow_ref="ABS,CPI",
        name="Consumer Price Index (Australia)",
        description="Headline & analytical CPI series across capital cities.",
    ),
    SdmxDatasetSpec(
        code="LF",
        dataflow_ref="ABS,LF",
        name="Labour Force, Australia",
        description="Unemployment rate, participation rate, and employment series.",
    ),
)

BIS_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="WS_CBPOL",
        dataflow_ref="BIS,WS_CBPOL,1.0",
        name="BIS Central Bank Policy Rates",
        description="Official policy interest rates across 40+ central banks.",
    ),
    SdmxDatasetSpec(
        code="WS_EER",
        dataflow_ref="BIS,WS_EER,1.0",
        name="BIS Effective Exchange Rates",
        description="Nominal and real effective exchange rate indices.",
    ),
)

STATSNZ_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="DF_CPI",
        dataflow_ref="STATSNZ,DF_CPI,1.0",
        name="Consumers Price Index (New Zealand)",
        description="Quarterly New Zealand headline and tradables/non-tradables CPI.",
    ),
    SdmxDatasetSpec(
        code="DF_GDP",
        dataflow_ref="STATSNZ,DF_GDP,1.0",
        name="Gross Domestic Product (New Zealand)",
        description="Production and expenditure GDP chain-volume series for NZ.",
    ),
    SdmxDatasetSpec(
        code="DF_HLFS",
        dataflow_ref="STATSNZ,DF_HLFS,1.0",
        name="Household Labour Force Survey (New Zealand)",
        description="New Zealand unemployment, employment, and participation rates.",
    ),
)

STATCAN_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="DF_18100004",
        dataflow_ref="STATCAN,DF_18100004,1.0",
        name="Consumer Price Index, Monthly (Canada)",
        description="Monthly Canadian CPI all-items and core inflation measures.",
    ),
    SdmxDatasetSpec(
        code="DF_36100434",
        dataflow_ref="STATCAN,DF_36100434,1.0",
        name="Gross Domestic Product at Basic Prices, Monthly (Canada)",
        description="Monthly Canadian GDP by industry (NAICS) in chained dollars.",
    ),
    SdmxDatasetSpec(
        code="DF_14100287",
        dataflow_ref="STATCAN,DF_14100287,1.0",
        name="Labour Force Characteristics, Monthly (Canada)",
        description="Seasonally adjusted Canadian employment and unemployment rates.",
    ),
)

BBK_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="BBK01",
        dataflow_ref="BBK,BBK01,1.0",
        name="Bundesanleihen Yields & Money Market Rates (Germany)",
        description="German sovereign yield curve (Bunds) and money market rates.",
    ),
    SdmxDatasetSpec(
        code="BBEX3",
        dataflow_ref="BBK,BBEX3,1.0",
        name="Foreign Exchange Reference Rates (Bundesbank)",
        description="Euro reference exchange rates and effective exchange indices.",
    ),
    SdmxDatasetSpec(
        code="BBDP1",
        dataflow_ref="BBK,BBDP1,1.0",
        name="Consumer Prices & Macro Indicators (Germany)",
        description="German HICP, national CPI, industrial orders, and production.",
    ),
)

BFS_CH_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="DF_LIK",
        dataflow_ref="CH1.LIK,DF_LIK,1.0",
        name="Swiss Consumer Price Index (LIK)",
        description="Monthly Swiss national consumer price index and core inflation.",
    ),
    SdmxDatasetSpec(
        code="DF_BIP",
        dataflow_ref="CH1.BIP,DF_BIP,1.0",
        name="Swiss Gross Domestic Product (Quarterly)",
        description="Quarterly real and nominal GDP aggregates for Switzerland.",
    ),
    SdmxDatasetSpec(
        code="DF_ES",
        dataflow_ref="CH1.ES,DF_ES,1.0",
        name="Swiss Employment & Labour Market Statistics",
        description="Swiss employment, unemployment, and cross-border workforce.",
    ),
)

FAO_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="DF_CP",
        dataflow_ref="FAO,DF_CP,1.0",
        name="FAO Food Price Index & Consumer Food Inflation",
        description="Global and national food consumer price indices and inflation.",
    ),
    SdmxDatasetSpec(
        code="DF_QCL",
        dataflow_ref="FAO,DF_QCL,1.0",
        name="Crops and Livestock Production (FAOSTAT)",
        description="Global agricultural production quantities, area, and yields.",
    ),
    SdmxDatasetSpec(
        code="DF_TCL",
        dataflow_ref="FAO,DF_TCL,1.0",
        name="Crops and Livestock Trade Volumes & Values (FAOSTAT)",
        description="Import and export quantities and USD values for agriculture.",
    ),
)

WB_WDI_DATASETS: tuple[SdmxDatasetSpec, ...] = (
    SdmxDatasetSpec(
        code="WDI_GDP",
        dataflow_ref="WB,WDI,1.0",
        name="World Development Indicators: GDP & Growth",
        description="Annual GDP (constant & current USD) and real per-capita growth.",
        key_filter="A.NY_GDP_MKTP_KD_ZG+NY_GDP_MKTP_CD.",
    ),
    SdmxDatasetSpec(
        code="WDI_INFL",
        dataflow_ref="WB,WDI,1.0",
        name="World Development Indicators: Inflation & Prices",
        description="Annual consumer price inflation and GDP deflator globally.",
        key_filter="A.FP_CPI_TOTL_ZG+NY_GDP_DEFL_KD_ZG.",
    ),
    SdmxDatasetSpec(
        code="WDI_UNEMP",
        dataflow_ref="WB,WDI,1.0",
        name="World Development Indicators: Labour & Unemployment",
        description="Total unemployment rate (ILO modeled estimate) across economies.",
        key_filter="A.SL_UEM_TOTL_ZS.",
    ),
)

DEFAULT_SDMX_ENDPOINTS: tuple[
    tuple[SdmxEndpointConfig, tuple[SdmxDatasetSpec, ...]], ...
] = (
    (
        SdmxEndpointConfig(
            provider_code="SDMX_ABS",
            provider_name="Australian Bureau of Statistics (Direct SDMX 3.0)",
            region="Australia",
            website="https://www.abs.gov.au",
            base_url="https://data.api.abs.gov.au/rest",
            agency_id="ABS",
            sdmx_version="3.0",
        ),
        ABS_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_BIS",
            provider_name="Bank for International Settlements (Direct SDMX)",
            region="World",
            website="https://www.bis.org",
            base_url="https://stats.bis.org/api/v1",
            agency_id="BIS",
            sdmx_version="2.1",
        ),
        BIS_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_STATSNZ",
            provider_name="Stats NZ Tatauranga Aotearoa (Direct SDMX)",
            region="New Zealand",
            website="https://www.stats.govt.nz",
            base_url="https://api.data.stats.govt.nz/rest",
            agency_id="STATSNZ",
            sdmx_version="2.1",
        ),
        STATSNZ_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_STATCAN",
            provider_name="Statistics Canada Web Data Service (Direct SDMX)",
            region="Canada",
            website="https://www.statcan.gc.ca",
            base_url="https://www150.statcan.gc.ca/t1/wds/sdmx/statcan/v1/rest",
            agency_id="STATCAN",
            sdmx_version="2.1",
        ),
        STATCAN_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_BBK",
            provider_name="Deutsche Bundesbank (Direct SDMX)",
            region="Germany",
            website="https://www.bundesbank.de",
            base_url="https://api.statistiken.bundesbank.de/rest",
            agency_id="BBK",
            sdmx_version="2.1",
        ),
        BBK_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_BFS_CH",
            provider_name="Swiss Federal Statistical Office (.Stat SDMX)",
            region="Switzerland",
            website="https://www.bfs.admin.ch",
            base_url="https://disseminate.stats.swiss/rest",
            agency_id="CH1",
            sdmx_version="2.1",
        ),
        BFS_CH_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_FAO",
            provider_name="Food and Agriculture Organization (FAOSTAT Direct SDMX)",
            region="World",
            website="https://www.fao.org/faostat",
            base_url="https://sdmx.fao.org/rest",
            agency_id="FAO",
            sdmx_version="2.1",
        ),
        FAO_DATASETS,
    ),
    (
        SdmxEndpointConfig(
            provider_code="SDMX_WB_WDI",
            provider_name="World Bank World Development Indicators (Direct SDMX)",
            region="World",
            website="https://datatopics.worldbank.org/world-development-indicators/",
            base_url="https://api.worldbank.org/v2/sdmx/rest",
            agency_id="WB",
            sdmx_version="2.1",
        ),
        WB_WDI_DATASETS,
    ),
)
