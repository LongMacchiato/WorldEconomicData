"""Financial market data connector powered by Yahoo Finance HTTP API / yfinance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd
from app.domain.connector_protocols import ProviderSourceType
from app.exceptions import (
    DatasetNotFoundError,
    SeriesNotFoundError,
    UpstreamUnavailableError,
)
from app.models import (
    Dataset,
    DatasetDetail,
    Provider,
    QueryRequest,
    SeriesPage,
    SeriesSummary,
)


@dataclass(frozen=True)
class MarketTickerSpec:
    """Metadata for a financial market ticker."""

    code: str
    yahoo_symbol: str
    name: str
    unit: str


@dataclass(frozen=True)
class MarketDatasetSpec:
    """Grouping of financial market instruments."""

    code: str
    name: str
    description: str
    tickers: Mapping[str, MarketTickerSpec]


MARKET_DATASETS: dict[str, MarketDatasetSpec] = {
    "FX": MarketDatasetSpec(
        code="FX",
        name="Foreign Exchange Spot Rates",
        description="Major G10 currency pairs including AUD/USD, EUR/USD, and USD/JPY.",
        tickers={
            "AUDUSD": MarketTickerSpec(
                "AUDUSD", "AUDUSD=X", "AUD/USD Spot Exchange Rate", "USD"
            ),
            "EURUSD": MarketTickerSpec(
                "EURUSD", "EURUSD=X", "EUR/USD Spot Exchange Rate", "USD"
            ),
            "USDJPY": MarketTickerSpec(
                "USDJPY", "JPY=X", "USD/JPY Spot Exchange Rate", "JPY"
            ),
            "NZDUSD": MarketTickerSpec(
                "NZDUSD", "NZDUSD=X", "NZD/USD Spot Exchange Rate", "USD"
            ),
        },
    ),
    "COMMODITIES": MarketDatasetSpec(
        code="COMMODITIES",
        name="Global Commodities & Trade Proxies",
        description=(
            "Iron Ore 62% Fe CFR futures, Gold, Brent Crude, and Copper futures."
        ),
        tickers={
            "IRON_ORE": MarketTickerSpec(
                "IRON_ORE", "TIO=F", "Iron Ore 62% Fe CFR Futures", "USD/t"
            ),
            "GOLD": MarketTickerSpec("GOLD", "GC=F", "Gold Futures (COMEX)", "USD/oz"),
            "BRENT": MarketTickerSpec(
                "BRENT", "BZ=F", "Brent Crude Oil Futures", "USD/bbl"
            ),
            "COPPER": MarketTickerSpec("COPPER", "HG=F", "Copper Futures", "USD/lb"),
        },
    ),
    "INDICES": MarketDatasetSpec(
        code="INDICES",
        name="Global Equity & Volatility Indices",
        description="S&P/ASX 200, S&P 500, NASDAQ 100, and CBOE VIX.",
        tickers={
            "ASX200": MarketTickerSpec(
                "ASX200", "^AXJO", "S&P/ASX 200 Index", "Points"
            ),
            "SP500": MarketTickerSpec("SP500", "^GSPC", "S&P 500 Index", "Points"),
            "VIX": MarketTickerSpec("VIX", "^VIX", "CBOE Volatility Index", "Index"),
            "US10Y": MarketTickerSpec(
                "US10Y", "^TNX", "CBOE 10-Year US Treasury Yield Index", "Percent"
            ),
        },
    ),
    "CRYPTO": MarketDatasetSpec(
        code="CRYPTO",
        name="Digital Assets & Global Liquidity Proxies",
        description="Bitcoin and Ethereum USD spot benchmarks.",
        tickers={
            "BTCUSD": MarketTickerSpec(
                "BTCUSD", "BTC-USD", "Bitcoin / US Dollar", "USD"
            ),
            "ETHUSD": MarketTickerSpec(
                "ETHUSD", "ETH-USD", "Ethereum / US Dollar", "USD"
            ),
        },
    ),
}

HistoryFetchFn = Callable[[str], pd.DataFrame]


class MarketConnector:
    """Financial market connector implementing DataConnectorProtocol."""

    def __init__(
        self,
        *,
        history_fetcher: HistoryFetchFn | None = None,
        default_period: str = "1y",
    ) -> None:
        """Initialize the Yahoo Finance MarketConnector.

        Args:
            history_fetcher: Optional history DataFrame fetcher override for testing.
            default_period: Default Yahoo Finance history window (e.g. '1y', '6mo').
        """
        self._fetch_history = history_fetcher or self._default_fetch_history
        self._default_period = default_period

    @property
    def provider_code(self) -> str:
        """Return YAHOO_FINANCE provider code."""
        return "YAHOO_FINANCE"

    @property
    def source_type(self) -> ProviderSourceType:
        """Return financial source type."""
        return ProviderSourceType.financial

    def get_provider(self) -> Provider:
        """Return Provider metadata for Yahoo Finance."""
        return Provider(
            code=self.provider_code,
            name="Yahoo Finance Live Market Feeds (FX, Commodities, Indices, Crypto)",
            region="World",
            website="https://finance.yahoo.com",
            source_type=ProviderSourceType.financial.value,
            requires_api_key=False,
        )

    def list_datasets(self, search: str | None = None) -> list[Dataset]:
        """List financial market asset class datasets."""
        items = [
            Dataset(
                provider_code=self.provider_code,
                code=spec.code,
                name=spec.name,
                description=spec.description,
                nb_series=len(spec.tickers),
            )
            for spec in MARKET_DATASETS.values()
        ]
        if not search or not search.strip():
            return items
        needle = search.strip().casefold()
        return [
            d
            for d in items
            if needle in d.code.casefold()
            or needle in d.name.casefold()
            or (d.description and needle in d.description.casefold())
        ]

    def get_dataset(self, dataset_code: str) -> DatasetDetail:
        """Return DatasetDetail for a financial market dataset."""
        spec = self._get_spec(dataset_code)
        return DatasetDetail(
            provider_code=self.provider_code,
            code=spec.code,
            name=spec.name,
            description=spec.description,
            nb_series=len(spec.tickers),
            dimensions=[],
        )

    def list_series(
        self,
        dataset_code: str,
        *,
        search: str | None = None,
        dimensions: Mapping[str, list[str]] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> SeriesPage:
        """List tickers in a financial market dataset."""
        _ = dimensions
        spec = self._get_spec(dataset_code)
        items = [
            SeriesSummary(
                provider_code=self.provider_code,
                dataset_code=spec.code,
                series_code=ticker.code,
                series_name=f"{ticker.name} [{ticker.yahoo_symbol}]",
                dimensions={"symbol": ticker.yahoo_symbol, "unit": ticker.unit},
            )
            for ticker in spec.tickers.values()
        ]
        if search and search.strip():
            needle = search.strip().casefold()
            items = [
                s
                for s in items
                if needle in s.series_code.casefold()
                or needle in s.series_name.casefold()
            ]
        page_limit = limit or 50
        sliced = items[offset : offset + page_limit]
        return SeriesPage(
            items=sliced,
            offset=offset,
            limit=page_limit,
            num_found=len(items),
            has_next_page=offset + len(sliced) < len(items),
        )

    def fetch_observations(self, query: QueryRequest) -> pd.DataFrame:
        """Fetch historical daily close prices from Yahoo Finance."""
        spec = self._get_spec(query.dataset_code)
        records: list[dict[str, Any]] = []
        for code in query.series_codes:
            ticker_spec = spec.tickers.get(code.upper())
            symbol = ticker_spec.yahoo_symbol if ticker_spec else code
            name = ticker_spec.name if ticker_spec else code
            unit = ticker_spec.unit if ticker_spec else "Price"
            hist = self._fetch_history(symbol)
            if hist.empty or "Close" not in hist.columns:
                continue
            for ts, row in hist.iterrows():
                val = row.get("Close")
                if val is None or pd.isna(val):
                    continue
                period_str = pd.Timestamp(str(ts)).strftime("%Y-%m-%d")
                records.append(
                    {
                        "provider_code": self.provider_code,
                        "dataset_code": spec.code,
                        "series_code": code.upper(),
                        "series_name": name,
                        "period": period_str,
                        "value": float(val),
                        "@frequency": "daily",
                        "unit": unit,
                    }
                )
        if not records:
            raise SeriesNotFoundError(
                f"No Yahoo Finance observations found for {query.series_codes}"
            )
        frame = pd.DataFrame(records)
        if query.start_period:
            frame = frame[frame["period"].astype(str) >= query.start_period]
        if query.end_period:
            frame = frame[frame["period"].astype(str) <= query.end_period]
        return frame.reset_index(drop=True)

    def _get_spec(self, dataset_code: str) -> MarketDatasetSpec:
        spec = MARKET_DATASETS.get(dataset_code.upper())
        if spec is None:
            raise DatasetNotFoundError(f"Market dataset {dataset_code!r} was not found")
        return spec

    def _default_fetch_history(self, symbol: str) -> pd.DataFrame:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        try:
            response = httpx.get(
                url,
                params={"range": self._default_period, "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not result:
                return pd.DataFrame()
            timestamps = result.get("timestamp") or []
            quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            closes = quotes.get("close") or []
            rows = [
                {
                    "Date": datetime.fromtimestamp(int(ts), tz=UTC).strftime(
                        "%Y-%m-%d"
                    ),
                    "Close": float(close),
                }
                for ts, close in zip(timestamps, closes, strict=False)
                if close is not None
            ]
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows).set_index("Date")
        except Exception as error:
            raise UpstreamUnavailableError(
                f"Yahoo Finance fetch failed for {symbol}: {error}"
            ) from error
