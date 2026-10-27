import { Cpu, LoaderCircle, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  getErrorMessage,
  getMacroDashboardStatus,
  refreshMacroDashboard,
  runAnalyticsTransform,
} from '../api'
import type { AnalyticsQueryResult, MacroDashboardStatus, MacroKpiMetric } from '../types'

interface MacroIntelligenceDashboardProps {
  theme: 'light' | 'dark'
  onSelectProviderInBrowser?: (providerCode: string) => void
}

async function fetchMacroCharts(): Promise<{
  yields: AnalyticsQueryResult
  trade: AnalyticsQueryResult
} | null> {
  try {
    const [yields, trade] = await Promise.all([
      runAnalyticsTransform({
        series_ids: [
          'RBA/F1_1/FIRMMCRT',
          'RBA/G1/GCPIOCPMTMYP',
          'YAHOO_FINANCE/INDICES/US10Y',
          'FRED/RATES/GS10',
        ],
        transformation: 'raw',
        rolling_window: 3,
        start_period: '2015-01-01',
      }),
      runAnalyticsTransform({
        series_ids: [
          'YAHOO_FINANCE/FX/AUDUSD',
          'YAHOO_FINANCE/COMMODITIES/IRON_ORE',
          'YAHOO_FINANCE/COMMODITIES/GOLD',
          'YAHOO_FINANCE/INDICES/ASX200',
        ],
        transformation: 'rebased_100',
        rolling_window: 3,
      }),
    ])
    return { yields, trade }
  } catch {
    return null
  }
}

export function MacroIntelligenceDashboard({
  theme,
  onSelectProviderInBrowser,
}: MacroIntelligenceDashboardProps) {
  const [status, setStatus] = useState<MacroDashboardStatus | null>(null)
  const [yieldResult, setYieldResult] = useState<AnalyticsQueryResult | null>(null)
  const [tradeResult, setTradeResult] = useState<AnalyticsQueryResult | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let isCurrent = true
    Promise.all([getMacroDashboardStatus(), fetchMacroCharts()])
      .then(([dash, charts]) => {
        if (!isCurrent) return
        setStatus(dash)
        if (charts) {
          setYieldResult(charts.yields)
          setTradeResult(charts.trade)
        }
      })
      .catch((err: unknown) => {
        if (isCurrent) setError(getErrorMessage(err))
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false)
      })
    return () => {
      isCurrent = false
    }
  }, [])

  async function handleRefresh(): Promise<void> {
    setIsRefreshing(true)
    setError('')
    try {
      const updated = await refreshMacroDashboard()
      setStatus(updated)
      const charts = await fetchMacroCharts()
      if (charts) {
        setYieldResult(charts.yields)
        setTradeResult(charts.trade)
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsRefreshing(false)
    }
  }

  const yieldChartOption = useMemo(
    () => buildLineChartOption(yieldResult, theme, '%'),
    [yieldResult, theme],
  )
  const tradeChartOption = useMemo(
    () => buildLineChartOption(tradeResult, theme, 'Idx (100)'),
    [tradeResult, theme],
  )

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-zinc-200 pb-5 dark:border-zinc-800">
        <div>
          <p className="text-xs font-semibold tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
            Systemic Risk & Multi-Source Intelligence
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">
            Global Macro-Economic Intelligence
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-1.5 text-xs font-medium tabular-nums dark:border-zinc-800">
            <span
              className={`size-2 rounded-full ${
                status?.internet_connected ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
            />
            {status?.internet_connected ? 'Live Network Ready' : 'Offline Mode'}
          </span>
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={isRefreshing}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 disabled:opacity-50"
          >
            {isRefreshing ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : (
              <RefreshCw size={15} />
            )}
            {isRefreshing ? 'Syncing & Running MLX...' : 'Sync Macro Bundle & Brief'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200">
          {error}
        </div>
      ) : null}

      {/* Focal KPI Strip */}
      <section aria-label="Systemic Risk Scoreboard">
        <div className="grid grid-cols-1 divide-y divide-zinc-200 rounded-2xl border border-zinc-200 bg-white sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-5 dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
          {(status?.kpis ?? []).map((kpi: MacroKpiMetric) => (
            <div key={kpi.key} className="p-5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{kpi.label}</p>
                {kpi.status_badge ? (
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-zinc-700 uppercase dark:bg-zinc-800 dark:text-zinc-300">
                    {kpi.status_badge}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">
                {kpi.value !== null
                  ? `${kpi.value}${kpi.unit === '%' ? '%' : ` ${kpi.unit}`}`
                  : 'Not Synced'}
              </p>
              <div className="mt-1 flex items-center justify-between text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                <span>{kpi.period ?? 'Click Sync above'}</span>
                {kpi.delta !== null ? (
                  <span
                    className={
                      kpi.delta > 0
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : kpi.delta < 0
                          ? 'text-rose-600 dark:text-rose-400'
                          : ''
                    }
                  >
                    {kpi.delta > 0 ? `+${kpi.delta}` : kpi.delta}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        {/* Left 2 Columns: Charts */}
        <div className="space-y-8 lg:col-span-2">
          <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <h3 className="text-sm font-semibold tracking-tight">
              Monetary Policy & Sovereign Yield Comparison (RBA Cash Rate, AU CPI & US 10Y)
            </h3>
            {yieldChartOption ? (
              <div className="mt-4 h-72">
                <ReactECharts
                  option={yieldChartOption}
                  style={{ height: '100%', width: '100%' }}
                  notMerge
                />
              </div>
            ) : (
              <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">
                {isLoading
                  ? 'Loading warehouse series...'
                  : 'Click "Sync Macro Bundle & Brief" to ingest live RBA, FRED, and Yahoo Finance yield curves.'}
              </p>
            )}
          </section>

          <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <h3 className="text-sm font-semibold tracking-tight">
              Trade Sensitivity & Commodity Matrix (Rebased = 100: AUD/USD, Iron Ore, Gold, ASX 200)
            </h3>
            {tradeChartOption ? (
              <div className="mt-4 h-72">
                <ReactECharts
                  option={tradeChartOption}
                  style={{ height: '100%', width: '100%' }}
                  notMerge
                />
              </div>
            ) : null}
            {tradeResult?.correlations.length ? (
              <div className="mt-4 overflow-x-auto border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <table className="w-full text-left text-xs tabular-nums">
                  <thead>
                    <tr className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                      <th className="pb-2 font-medium">Series Pair</th>
                      <th className="pb-2 font-medium">Pearson r</th>
                      <th className="pb-2 font-medium">Overlapping Days</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800/60">
                    {tradeResult.correlations.map((pair) => (
                      <tr key={`${pair.series_a}-${pair.series_b}`}>
                        <td className="py-2 font-mono">
                          {pair.series_a.split('/').pop()} vs {pair.series_b.split('/').pop()}
                        </td>
                        <td className="py-2 font-semibold">
                          {pair.correlation !== null ? pair.correlation.toFixed(4) : 'N/A'}
                        </td>
                        <td className="py-2 text-zinc-500">{pair.overlapping_periods}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        </div>

        {/* Right Column: AI Macro Brief & Direct Connectors */}
        <div className="space-y-8">
          <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Cpu size={17} className="text-blue-600 dark:text-blue-400" />
                <h3 className="text-sm font-semibold tracking-tight">
                  Daily Macro Brief (Apple Silicon MLX)
                </h3>
              </div>
              <span className="text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
                {status?.latest_brief?.insight_date ?? 'Pending'}
              </span>
            </div>
            <p className="mt-4 max-w-[70ch] text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {status?.latest_brief?.summary ??
                'Trigger "Sync Macro Bundle & Brief" to ingest live RBA, ABS, FRED, and Yahoo Finance series and synthesize a local AI macro brief.'}
            </p>
            <div className="mt-5 border-t border-zinc-200 pt-3 text-xs text-zinc-500 tabular-nums dark:border-zinc-800 dark:text-zinc-400">
              Engine: {status?.latest_brief?.model_id ?? 'Meta-Llama-3.1-8B-Instruct-4bit (MLX)'}
            </div>
          </section>

          <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <h3 className="text-sm font-semibold tracking-tight">
              Direct Statistical & Financial Connectors
            </h3>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Registered alongside 80+ global DBnomics providers.
            </p>
            <ul className="mt-4 divide-y divide-zinc-200 dark:divide-zinc-800">
              {(status?.connectors ?? []).map((conn) => (
                <li
                  key={conn.provider_code}
                  className="flex items-center justify-between gap-3 py-3 text-xs"
                >
                  <div>
                    <button
                      type="button"
                      onClick={() => onSelectProviderInBrowser?.(conn.provider_code)}
                      className="font-mono font-semibold text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {conn.provider_code}
                    </button>
                    <p className="text-zinc-500 dark:text-zinc-400">{conn.provider_name}</p>
                  </div>
                  <span
                    className={`shrink-0 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tabular-nums ${
                      conn.configured
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                        : 'bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300'
                    }`}
                  >
                    {conn.configured ? `${conn.dataset_count} datasets` : 'Key Needed'}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}

function buildLineChartOption(
  result: AnalyticsQueryResult | null,
  theme: 'light' | 'dark',
  unitLabel: string,
) {
  if (!result?.chart_series.length) return null
  const isDark = theme === 'dark'
  const periods = Array.from(
    new Set(result.chart_series.flatMap((s) => s.points.map((p) => p.period))),
  ).sort()
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      type: 'scroll',
      textStyle: { color: isDark ? '#d4d4d8' : '#3f3f46', fontSize: 11 },
    },
    grid: { left: 48, right: 20, top: 40, bottom: 32 },
    xAxis: {
      type: 'category',
      data: periods,
      axisLabel: { color: isDark ? '#a1a1aa' : '#71717a', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: unitLabel,
      axisLabel: { color: isDark ? '#a1a1aa' : '#71717a', fontSize: 11 },
      splitLine: { lineStyle: { color: isDark ? '#27272a' : '#e4e4e7' } },
    },
    series: result.chart_series.map((s) => {
      const lookup = new Map(s.points.map((pt) => [pt.period, pt.value]))
      return {
        name: s.series_name,
        type: 'line',
        showSymbol: false,
        connectNulls: true,
        data: periods.map((p) => lookup.get(p) ?? null),
      }
    }),
  }
}
