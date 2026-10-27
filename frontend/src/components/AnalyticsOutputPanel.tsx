import { Database, Terminal } from 'lucide-react'
import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import type { AnalyticsQueryResult } from '../types'

const SQL_PRESETS = [
  {
    label: 'Recent Observations',
    sql: 'SELECT series_id, series_name, period, value FROM v_series_observations ORDER BY period DESC LIMIT 100',
  },
  {
    label: 'Series Summary Stats',
    sql: 'SELECT series_id, series_name, COUNT(*) AS n_obs, MIN(period) AS min_p, MAX(period) AS max_p, ROUND(AVG(value), 2) AS avg_val FROM v_series_observations GROUP BY series_id, series_name ORDER BY series_id',
  },
  {
    label: 'Sync Audit Log',
    sql: 'SELECT run_id, provider_code, dataset_code, series_count, observations_upserted, status, started_at FROM sync_runs ORDER BY started_at DESC LIMIT 20',
  },
]

interface AnalyticsOutputPanelProps {
  theme: 'light' | 'dark'
  sqlInput: string
  isLoading: boolean
  result: AnalyticsQueryResult | null
  onSqlChange: (sql: string) => void
  onRunSql: () => void
}

export function AnalyticsOutputPanel({
  theme,
  sqlInput,
  isLoading,
  result,
  onSqlChange,
  onRunSql,
}: AnalyticsOutputPanelProps) {
  const chartOption = useMemo(() => {
    if (!result?.chart_series.length) return null
    const isDark = theme === 'dark'
    const periods = Array.from(
      new Set(result.chart_series.flatMap((s) => s.points.map((p) => p.period))),
    ).sort()
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll', textStyle: { color: isDark ? '#d4d4d8' : '#3f3f46' } },
      grid: { left: 48, right: 24, top: 48, bottom: 48 },
      xAxis: {
        type: 'category',
        data: periods,
        axisLabel: { color: isDark ? '#a1a1aa' : '#71717a' },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: isDark ? '#a1a1aa' : '#71717a' },
        splitLine: { lineStyle: { color: isDark ? '#27272a' : '#e4e4e7' } },
      },
      series: result.chart_series.map((s) => {
        const byPeriod = new Map(s.points.map((p) => [p.period, p.value]))
        return {
          name: s.series_name || s.series_code,
          type: 'line',
          showSymbol: false,
          connectNulls: false,
          data: periods.map((p) => byPeriod.get(p) ?? null),
        }
      }),
    }
  }, [result, theme])

  return (
    <>
      <section className="panel">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="section-number">DuckDB SQL Engine</p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">Read-Only SQL Workbench</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {SQL_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className="secondary-button"
                onClick={() => onSqlChange(preset.sql)}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
        <textarea
          aria-label="SQL query"
          rows={3}
          className="input font-mono text-xs"
          value={sqlInput}
          onChange={(e) => onSqlChange(e.target.value)}
        />
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            className="primary-button"
            disabled={isLoading || !sqlInput.trim()}
            onClick={onRunSql}
          >
            <Terminal size={16} /> Run SQL Query
          </button>
        </div>
      </section>

      {result && (
        <section className="panel space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">
              Query Output ({result.total_rows.toLocaleString()} rows)
            </h3>
            <Database size={18} className="text-blue-600" />
          </div>

          {chartOption && (
            <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
              <ReactECharts
                option={chartOption}
                style={{ height: 340, width: '100%' }}
                notMerge
                lazyUpdate
              />
            </div>
          )}

          {result.correlations.length > 0 && (
            <div>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Pairwise Pearson Correlations
              </h4>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {result.correlations.map((pair) => (
                  <div
                    key={`${pair.series_a}:${pair.series_b}`}
                    className="dimension-card flex items-center justify-between text-xs"
                  >
                    <span className="truncate font-mono">
                      {pair.series_a} ↔ {pair.series_b}
                    </span>
                    <span className="ml-2 font-mono font-semibold text-blue-600 dark:text-blue-400">
                      r = {pair.correlation != null ? pair.correlation.toFixed(4) : 'N/A'} (n=
                      {pair.overlapping_periods})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.rows.length > 0 && (
            <div className="max-h-96 overflow-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 bg-zinc-100/95 dark:bg-zinc-900/95">
                  <tr>
                    {result.columns.map((col) => (
                      <th key={col} className="table-heading">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {result.rows.slice(0, 100).map((row, idx) => (
                    <tr key={idx}>
                      {result.columns.map((col) => (
                        <td key={col} className="table-cell">
                          {row[col] == null ? '—' : String(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  )
}
