import { AlertCircle, LoaderCircle, Play, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  deleteStoredSeries,
  getAnalyticsCatalog,
  getErrorMessage,
  runAnalyticsSql,
  runAnalyticsTransform,
} from '../api'
import {
  type AnalyticsQueryResult,
  type ProviderSourceFilter,
  type TransformationType,
  type WarehouseSummary,
  resolveProviderSourceType,
} from '../types'
import { AiAssistantPanel } from './AiAssistantPanel'
import { AnalyticsOutputPanel } from './AnalyticsOutputPanel'
import { ConnectorBadge, ConnectorFilterBar } from './ConnectorFilterBar'

const DEFAULT_SQL =
  'SELECT series_id, series_name, period, value FROM v_series_observations ORDER BY period DESC LIMIT 100'

const TRANSFORM_LABELS: Record<TransformationType, string> = {
  raw: 'Raw Levels',
  yoy_pct: 'Year-over-Year (%)',
  pop_pct: 'Period-over-Period (%)',
  rebased_100: 'Rebased Index (t₀ = 100)',
  rolling_avg: 'Rolling Mean',
}

interface AnalyticsWorkbenchProps {
  theme: 'light' | 'dark'
  refreshTrigger: number
}

export function AnalyticsWorkbench({ theme, refreshTrigger }: AnalyticsWorkbenchProps) {
  const [catalog, setCatalog] = useState<WarehouseSummary | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [seriesSourceFilter, setSeriesSourceFilter] = useState<ProviderSourceFilter>('all')
  const [transformation, setTransformation] = useState<TransformationType>('raw')
  const [rollingWindow, setRollingWindow] = useState(3)
  const [sqlInput, setSqlInput] = useState(DEFAULT_SQL)
  const [result, setResult] = useState<AnalyticsQueryResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const seriesCounts = useMemo<Record<ProviderSourceFilter, number>>(() => {
    const counts: Record<ProviderSourceFilter, number> = {
      all: 0,
      sdmx: 0,
      dbnomics: 0,
      central_bank: 0,
      financial: 0,
    }
    for (const item of catalog?.series ?? []) {
      counts.all += 1
      const st = resolveProviderSourceType({ code: item.provider_code })
      counts[st] += 1
    }
    return counts
  }, [catalog])

  const filteredStoredSeries = useMemo(() => {
    const allSeries = catalog?.series ?? []
    if (seriesSourceFilter === 'all') return allSeries
    return allSeries.filter(
      (item) => resolveProviderSourceType({ code: item.provider_code }) === seriesSourceFilter,
    )
  }, [catalog, seriesSourceFilter])

  function applyCatalogSummary(summary: WarehouseSummary): void {
    setCatalog(summary)
    setSelectedIds((prev) => {
      const available = new Set(summary.series.map((s) => s.series_id))
      const filtered = prev.filter((id) => available.has(id))
      if (filtered.length > 0) return filtered
      return summary.series.slice(0, 3).map((s) => s.series_id)
    })
  }

  async function loadCatalog(): Promise<void> {
    setError('')
    try {
      const summary = await getAnalyticsCatalog()
      applyCatalogSummary(summary)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    let isCurrent = true
    getAnalyticsCatalog(controller.signal)
      .then((summary) => {
        if (isCurrent) {
          setError('')
          applyCatalogSummary(summary)
        }
      })
      .catch((err: unknown) => {
        const message = getErrorMessage(err)
        if (isCurrent && message) setError(message)
      })
    return () => {
      isCurrent = false
      controller.abort()
    }
  }, [refreshTrigger])

  async function handleRunTransform(): Promise<void> {
    if (!selectedIds.length) return
    setIsLoading(true)
    setError('')
    try {
      const res = await runAnalyticsTransform({
        series_ids: selectedIds,
        transformation,
        rolling_window: rollingWindow,
      })
      setResult(res)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRunSql(): Promise<void> {
    if (!sqlInput.trim()) return
    setIsLoading(true)
    setError('')
    try {
      const res = await runAnalyticsSql(sqlInput, 500)
      setResult(res)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleDeleteSeries(seriesId: string): Promise<void> {
    setError('')
    try {
      await deleteStoredSeries(seriesId)
      await loadCatalog()
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  function toggleSeriesSelection(seriesId: string): void {
    setSelectedIds((prev) =>
      prev.includes(seriesId) ? prev.filter((id) => id !== seriesId) : [...prev, seriesId],
    )
  }

  return (
    <div className="space-y-6" data-testid="analytics-workbench">
      {error && (
        <div role="alert" className="alert">
          <AlertCircle className="mt-0.5 shrink-0 text-red-500" size={18} />
          <span className="flex-1">{error}</span>
        </div>
      )}

      <section className="panel">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="section-number">DuckDB Star Schema</p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">
              Analytics Warehouse Overview
            </h2>
          </div>
          <button type="button" className="secondary-button" onClick={() => void loadCatalog()}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: 'Providers', value: catalog?.total_providers ?? 0 },
            { label: 'Datasets', value: catalog?.total_datasets ?? 0 },
            { label: 'Stored Series', value: catalog?.total_series ?? 0 },
            { label: 'Observations', value: catalog?.total_observations ?? 0 },
          ].map((stat) => (
            <div key={stat.label} className="dimension-card">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">{stat.label}</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">
                {stat.value.toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <p className="section-number">Cross-Series Analysis</p>
        <h2 className="mt-1 mb-4 text-xl font-semibold tracking-tight">
          Stored Series & Transformations
        </h2>

        {!catalog?.series.length ? (
          <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
            No series stored in DuckDB yet. Switch to the Catalogue Browser, select series, and
            click <strong>Sync to Analytics DB</strong>.
          </div>
        ) : (
          <>
            <div className="mb-4">
              <ConnectorFilterBar
                activeFilter={seriesSourceFilter}
                counts={seriesCounts}
                onSelectFilter={setSeriesSourceFilter}
                ariaLabel="Filter stored series by connector"
              />
            </div>

            <div className="mb-4 max-h-60 space-y-2 overflow-y-auto">
              {filteredStoredSeries.map((item) => {
                const checked = selectedIds.includes(item.series_id)
                const sourceType = resolveProviderSourceType({ code: item.provider_code })
                return (
                  <div
                    key={item.series_id}
                    className={`flow-row ${checked ? 'flow-row-selected' : ''}`}
                  >
                    <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
                      <input
                        type="checkbox"
                        className="checkbox"
                        checked={checked}
                        onChange={() => toggleSeriesSelection(item.series_id)}
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-sm font-semibold">{item.series_name}</span>
                          <ConnectorBadge sourceType={sourceType} />
                        </span>
                        <span className="font-mono text-xs text-zinc-500 tabular-nums">
                          {item.series_id} · {item.observation_count.toLocaleString()} obs (
                          {item.min_period ?? '—'} to {item.max_period ?? '—'})
                        </span>
                      </span>
                    </label>
                    <button
                      type="button"
                      className="icon-button size-8"
                      aria-label={`Delete ${item.series_id}`}
                      onClick={() => void handleDeleteSeries(item.series_id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )
              })}
            </div>

            <div className="flex flex-wrap items-end gap-3">
              <label className="field-label">
                Transformation
                <select
                  aria-label="Transformation"
                  className="input mt-1.5"
                  value={transformation}
                  onChange={(e) => setTransformation(e.target.value as TransformationType)}
                >
                  {(Object.keys(TRANSFORM_LABELS) as TransformationType[]).map((key) => (
                    <option key={key} value={key}>
                      {TRANSFORM_LABELS[key]}
                    </option>
                  ))}
                </select>
              </label>

              {transformation === 'rolling_avg' && (
                <label className="field-label w-28">
                  Window
                  <input
                    type="number"
                    min={2}
                    max={60}
                    className="input mt-1.5"
                    value={rollingWindow}
                    onChange={(e) => setRollingWindow(Number(e.target.value) || 3)}
                  />
                </label>
              )}

              <button
                type="button"
                className="primary-button"
                disabled={isLoading || !selectedIds.length}
                onClick={() => void handleRunTransform()}
              >
                {isLoading ? (
                  <LoaderCircle className="animate-spin" size={16} />
                ) : (
                  <Play size={16} />
                )}
                Compute Transformation
              </button>
            </div>
          </>
        )}
      </section>

      <AiAssistantPanel
        onQueryResult={(aiResult) => {
          setResult(aiResult)
          if (aiResult.executed_sql) {
            setSqlInput(aiResult.executed_sql)
          }
        }}
        onWarehouseUpdated={() => void loadCatalog()}
      />

      <AnalyticsOutputPanel
        theme={theme}
        sqlInput={sqlInput}
        isLoading={isLoading}
        result={result}
        onSqlChange={setSqlInput}
        onRunSql={() => void handleRunSql()}
      />
    </div>
  )
}
