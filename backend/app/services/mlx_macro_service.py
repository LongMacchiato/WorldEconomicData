"""Macro-Economic Intelligence & Local Apple Silicon MLX Briefing Service."""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
from app.config import Settings
from app.domain.analytics_models import SyncRequest
from app.domain.connector_protocols import (
    MacroBriefRecord,
    MacroDashboardStatus,
    MacroKpiMetric,
)
from app.services.analytics_service import AnalyticsService
from app.services.composite_catalog_service import CompositeCatalogService
from app.services.duckdb_queries import UPSERT_AI_INSIGHT_SQL

CORE_KPI_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("cash_rate", "RBA Cash Rate Target", "RBA/F1_1/FIRMMCRT", "%"),
    ("yield_curve", "US Yield Curve (10Y-2Y)", "FRED/RATES/T10Y2Y", "%"),
    ("trimmed_cpi", "AU Trimmed Mean CPI (YoY)", "RBA/G1/GCPIOCPMTMYP", "%"),
    ("aud_usd", "AUD / USD Spot", "YAHOO_FINANCE/FX/AUDUSD", "USD"),
    (
        "iron_ore",
        "Iron Ore 62% Fe Futures",
        "YAHOO_FINANCE/COMMODITIES/IRON_ORE",
        "USD/t",
    ),
)

DEFAULT_SYNC_BUNDLES: tuple[tuple[str, str, list[str]], ...] = (
    ("RBA", "F1_1", ["FIRMMCRT", "FIRMMBAB90"]),
    ("RBA", "G1", ["GCPIOCPMTMYP", "GCPIAGYP"]),
    ("YAHOO_FINANCE", "FX", ["AUDUSD", "EURUSD", "USDJPY"]),
    ("YAHOO_FINANCE", "COMMODITIES", ["IRON_ORE", "GOLD", "BRENT"]),
    ("YAHOO_FINANCE", "INDICES", ["ASX200", "SP500", "US10Y"]),
    ("YAHOO_FINANCE", "CRYPTO", ["BTCUSD"]),
)


class MlxMacroService:
    """Service managing Macro Risk Scoreboard KPIs, core bundle sync, and AI briefs."""

    def __init__(
        self,
        settings: Settings,
        catalog: CompositeCatalogService,
        analytics: AnalyticsService,
    ) -> None:
        """Initialize the MlxMacroService.

        Args:
            settings: Application Settings.
            catalog: CompositeCatalogService instance.
            analytics: AnalyticsService instance.
        """
        self._settings = settings
        self._catalog = catalog
        self._analytics = analytics
        raw_db = settings.analytics_db_path
        if raw_db != ":memory:" and not Path(raw_db).is_absolute():
            self._db_path = str(Path(__file__).resolve().parents[3] / raw_db)
        else:
            self._db_path = raw_db
        cache_dir = Path(settings.hf_cache_dir).expanduser().resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_dir))

    def get_dashboard_status(self) -> MacroDashboardStatus:
        """Build the complete Macro Intelligence Dashboard status payload."""
        return MacroDashboardStatus(
            internet_connected=check_internet_connectivity(),
            connectors=self._catalog.list_connector_statuses(),
            kpis=self._query_kpis(),
            latest_brief=self.get_latest_brief(),
        )

    def refresh_macro_intelligence(self) -> MacroDashboardStatus:
        """Sync core macro/market bundles into DuckDB and generate a fresh AI brief."""
        bundles = list(DEFAULT_SYNC_BUNDLES)
        if self._settings.fred_api_key:
            bundles.append(("FRED", "RATES", ["T10Y2Y", "GS10", "DGS10", "DGS2"]))
        for provider_code, dataset_code, series_codes in bundles:
            try:
                self._analytics.sync_series(
                    SyncRequest(
                        provider_code=provider_code,
                        dataset_code=dataset_code,
                        series_codes=series_codes,
                    )
                )
            except Exception:
                continue

        kpis = self._query_kpis()
        brief = self._generate_and_store_brief(kpis)
        return MacroDashboardStatus(
            internet_connected=check_internet_connectivity(),
            connectors=self._catalog.list_connector_statuses(),
            kpis=kpis,
            latest_brief=brief,
        )

    def get_latest_brief(self) -> MacroBriefRecord | None:
        """Fetch the most recent AI Macro Brief from DuckDB."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT CAST(insight_date AS VARCHAR), model_id, summary, "
                "CAST(metrics_snapshot AS VARCHAR), CAST(created_at AS VARCHAR) "
                "FROM ai_insights ORDER BY insight_date DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return MacroBriefRecord(
            insight_date=str(row[0]),
            model_id=str(row[1]),
            summary=str(row[2]),
            metrics_snapshot=json.loads(row[3]) if row[3] else {},
            created_at=str(row[4]),
        )

    def _query_kpis(self) -> list[MacroKpiMetric]:
        metrics: list[MacroKpiMetric] = []
        with self._connect() as conn:
            for key, label, series_id, unit in CORE_KPI_SPECS:
                rows = conn.execute(
                    "SELECT period, value FROM fact_observations "
                    "WHERE series_id = ? AND value IS NOT NULL "
                    "ORDER BY period DESC LIMIT 2",
                    [series_id],
                ).fetchall()
                metrics.append(_build_kpi_metric(key, label, series_id, unit, rows))
        return metrics

    def _generate_and_store_brief(self, kpis: list[MacroKpiMetric]) -> MacroBriefRecord:
        snapshot = {
            m.key: {
                "label": m.label,
                "value": m.value,
                "delta": m.delta,
                "period": m.period,
                "unit": m.unit,
            }
            for m in kpis
            if m.value is not None
        }
        summary_text, model_used = _run_local_or_fallback_inference(
            snapshot, self._settings.mlx_model_id
        )
        now_iso = datetime.now(UTC).isoformat()
        today_str = date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                UPSERT_AI_INSIGHT_SQL,
                [
                    today_str,
                    model_used,
                    summary_text,
                    json.dumps(snapshot, ensure_ascii=False),
                    now_iso,
                ],
            )
        return MacroBriefRecord(
            insight_date=today_str,
            model_id=model_used,
            summary=summary_text,
            metrics_snapshot=snapshot,
            created_at=now_iso,
        )

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self._db_path)


def _build_kpi_metric(
    key: str,
    label: str,
    series_id: str,
    unit: str,
    rows: list[tuple[Any, ...]],
) -> MacroKpiMetric:
    if not rows:
        return MacroKpiMetric(key=key, label=label, series_id=series_id, unit=unit)
    latest_period = str(rows[0][0])
    latest_val = float(rows[0][1])
    prev_val = float(rows[1][1]) if len(rows) > 1 else None
    delta = round(latest_val - prev_val, 4) if prev_val is not None else None
    badge: str | None = None
    if key == "yield_curve":
        badge = "INVERTED" if latest_val < 0 else "NORMAL"
    elif key == "trimmed_cpi":
        badge = "ABOVE TARGET" if latest_val > 3.0 else "IN TARGET BAND"
    return MacroKpiMetric(
        key=key,
        label=label,
        series_id=series_id,
        value=round(latest_val, 4),
        unit=unit,
        period=latest_period,
        previous_value=round(prev_val, 4) if prev_val is not None else None,
        delta=delta,
        status_badge=badge,
    )


def _run_local_or_fallback_inference(
    snapshot: dict[str, Any],
    mlx_model_id: str,
) -> tuple[str, str]:
    """Run local Apple Silicon MLX inference if available, else rule synthesis."""
    try:
        from mlx_lm import generate, load

        model, tokenizer = load(mlx_model_id)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Senior Macro-Economic Strategist. Write a concise, "
                    "3-sentence Daily Macro Brief analyzing the provided indicators "
                    "(monetary policy stance, inflation, and AUD/commodity drivers). "
                    "Output plain prose only-never output code or markdown."
                ),
            },
            {
                "role": "user",
                "content": f"Latest Macro Snapshot: {json.dumps(snapshot)}",
            },
        ]
        if hasattr(tokenizer, "apply_chat_template"):
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = f"{messages[0]['content']}\n\n{messages[1]['content']}\n\nBrief:"
        response = generate(model, tokenizer, prompt=prompt, max_tokens=180)
        return str(response).strip(), f"{mlx_model_id} (Apple Silicon MLX)"
    except Exception:
        return _synthesize_deterministic_brief(snapshot), "Macro-Rule-Synthesizer-v1"


def _synthesize_deterministic_brief(snapshot: dict[str, Any]) -> str:
    cash = snapshot.get("cash_rate", {}).get("value")
    cpi = snapshot.get("trimmed_cpi", {}).get("value")
    aud = snapshot.get("aud_usd", {}).get("value")
    iron = snapshot.get("iron_ore", {}).get("value")
    yc = snapshot.get("yield_curve", {}).get("value")

    parts: list[str] = []
    if cash is not None and cpi is not None:
        stance = (
            "restrictive above the 2-3% inflation target band"
            if cpi > 3.0
            else "aligned with the target band"
        )
        parts.append(
            f"Australian monetary policy remains anchored at a {cash:.2f}% "
            f"RBA Cash Rate with Trimmed Mean CPI at {cpi:.1f}% YoY ({stance})."
        )
    if aud is not None and iron is not None:
        parts.append(
            f"External terms-of-trade proxies show AUD/USD trading at {aud:.4f} "
            f"alongside Iron Ore futures at ${iron:.2f}/t."
        )
    if yc is not None:
        curve_state = "inverted" if yc < 0 else "positively sloped"
        parts.append(
            f"The US 10Y-2Y Treasury spread stands at {yc:.2f}% ({curve_state}), "
            "shaping global sovereign yield differentials."
        )
    if not parts:
        return "Sync core macro series to generate an automated systemic risk briefing."
    return " ".join(parts)


def check_internet_connectivity(host: str = "8.8.8.8", port: int = 53) -> bool:
    """Perform a fast socket check for external network connectivity."""
    try:
        socket.setdefaulttimeout(2.0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
        return True
    except OSError:
        return False
