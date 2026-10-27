import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Database,
  Download,
  FileJson,
  LoaderCircle,
  Moon,
  Search,
  Sun,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import {
  downloadQuery,
  getDatasetDetail,
  getDatasets,
  getErrorMessage,
  getProviders,
  getSeriesPage,
  previewQuery,
  saveBlob,
  syncSeriesToAnalytics,
} from './api'
import { AnalyticsWorkbench } from './components/AnalyticsWorkbench'
import { ConnectorBadge, ConnectorFilterBar } from './components/ConnectorFilterBar'
import { MacroIntelligenceDashboard } from './components/MacroIntelligenceDashboard'
import {
  type Dataset,
  type DatasetDetail,
  type DimensionSelections,
  type DownloadFormat,
  type Provider,
  type ProviderSourceFilter,
  type QueryPreview,
  type QueryRequest,
  type SeriesSummary,
  resolveProviderSourceType,
} from './types'

const PAGE_SIZE = 25
const SERIES_PAGE_SIZE = 50
const MAX_SELECTED_SERIES = 10
const SEARCH_DELAY_MS = 250
const THEME_STORAGE_KEY = 'dbnomics-browser-theme'
const BROWSER_STATE_STORAGE_KEY = 'dbnomics-browser-state'

interface PersistedBrowserState {
  providerCode: string | null
  providerSourceFilter: ProviderSourceFilter
  datasetCode: string | null
  dimensionSelections: DimensionSelections
  selectedSeriesCodes: string[]
  startPeriod: string
  endPeriod: string
}

const EMPTY_BROWSER_STATE: PersistedBrowserState = {
  providerCode: null,
  providerSourceFilter: 'all',
  datasetCode: null,
  dimensionSelections: {},
  selectedSeriesCodes: [],
  startPeriod: '',
  endPeriod: '',
}

function readBrowserState(): PersistedBrowserState {
  try {
    const storedState = localStorage.getItem(BROWSER_STATE_STORAGE_KEY)
    return storedState
      ? { ...EMPTY_BROWSER_STATE, ...(JSON.parse(storedState) as PersistedBrowserState) }
      : EMPTY_BROWSER_STATE
  } catch {
    return EMPTY_BROWSER_STATE
  }
}

function getInitialTheme(): 'light' | 'dark' {
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY)
  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function App() {
  const [initialBrowserState] = useState(readBrowserState)
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme)
  const [providers, setProviders] = useState<Provider[]>([])
  const [selectedProviderCode, setSelectedProviderCode] = useState<string | null>(
    initialBrowserState.providerCode,
  )
  const [providerSourceFilter, setProviderSourceFilter] = useState<ProviderSourceFilter>(
    initialBrowserState.providerSourceFilter ?? 'all',
  )
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [selectedDatasetCode, setSelectedDatasetCode] = useState<string | null>(
    initialBrowserState.datasetCode,
  )
  const [datasetDetail, setDatasetDetail] = useState<DatasetDetail | null>(null)
  const [dimensionSelections, setDimensionSelections] = useState<DimensionSelections>(
    initialBrowserState.dimensionSelections,
  )
  const [seriesItems, setSeriesItems] = useState<SeriesSummary[]>([])
  const [seriesNumFound, setSeriesNumFound] = useState(0)
  const [selectedSeriesCodes, setSelectedSeriesCodes] = useState<string[]>(
    initialBrowserState.selectedSeriesCodes,
  )
  const [startPeriod, setStartPeriod] = useState(initialBrowserState.startPeriod)
  const [endPeriod, setEndPeriod] = useState(initialBrowserState.endPeriod)
  const [search, setSearch] = useState('')
  const [seriesSearch, setSeriesSearch] = useState('')
  const [providerSearch, setProviderSearch] = useState('')
  const [preview, setPreview] = useState<QueryPreview | null>(null)
  const [page, setPage] = useState(1)
  const [error, setError] = useState('')
  const [isProvidersLoading, setIsProvidersLoading] = useState(true)
  const [isDatasetsLoading, setIsDatasetsLoading] = useState(false)
  const [isDatasetDetailLoading, setIsDatasetDetailLoading] = useState(
    Boolean(initialBrowserState.providerCode && initialBrowserState.datasetCode),
  )
  const [isSeriesLoading, setIsSeriesLoading] = useState(false)
  const [isPreviewLoading, setIsPreviewLoading] = useState(false)
  const [downloadingFormat, setDownloadingFormat] = useState<DownloadFormat | null>(null)
  const [activeTab, setActiveTab] = useState<'browser' | 'analytics' | 'macro'>('browser')
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')
  const [analyticsRefreshKey, setAnalyticsRefreshKey] = useState(0)
  const previewControllerRef = useRef<AbortController | null>(null)
  const previewRequestIdRef = useRef(0)
  const downloadControllerRef = useRef<AbortController | null>(null)
  const downloadRequestIdRef = useRef(0)

  const selectedProvider = providers.find(({ code }) => code === selectedProviderCode)
  const providerSourceCounts = useMemo<Record<ProviderSourceFilter, number>>(() => {
    const counts: Record<ProviderSourceFilter, number> = {
      all: 0,
      sdmx: 0,
      dbnomics: 0,
      central_bank: 0,
      financial: 0,
    }
    for (const provider of providers) {
      counts.all += 1
      const sourceType = resolveProviderSourceType(provider)
      counts[sourceType] += 1
    }
    return counts
  }, [providers])

  const filteredProviders = useMemo(() => {
    const normalizedSearch = providerSearch.trim().toLowerCase()
    return providers.filter((provider) => {
      const sourceType = resolveProviderSourceType(provider)
      if (providerSourceFilter !== 'all' && sourceType !== providerSourceFilter) {
        return false
      }
      if (!normalizedSearch) return true
      return (
        provider.code.toLowerCase().includes(normalizedSearch) ||
        provider.name.toLowerCase().includes(normalizedSearch) ||
        (provider.region?.toLowerCase().includes(normalizedSearch) ?? false)
      )
    })
  }, [providerSearch, providerSourceFilter, providers])
  const selectedDataset = datasets.find(({ code }) => code === selectedDatasetCode)

  const queryRequest = useMemo<QueryRequest | null>(() => {
    if (!selectedProviderCode || !selectedDatasetCode || !selectedSeriesCodes.length) {
      return null
    }
    return {
      provider_code: selectedProviderCode,
      dataset_code: selectedDatasetCode,
      series_codes: selectedSeriesCodes,
      start_period: startPeriod || null,
      end_period: endPeriod || null,
      page,
      page_size: PAGE_SIZE,
    }
  }, [selectedProviderCode, selectedDatasetCode, selectedSeriesCodes, startPeriod, endPeriod, page])

  const chartOption = useMemo(() => {
    if (!preview?.chart_series.length) return null
    const isDark = theme === 'dark'
    const periods = Array.from(
      new Set(preview.chart_series.flatMap((series) => series.points.map((point) => point.period))),
    ).sort()
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: {
        type: 'scroll',
        textStyle: { color: isDark ? '#d4d4d8' : '#3f3f46' },
      },
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
      series: preview.chart_series.map((series) => {
        const valuesByPeriod = new Map(series.points.map((point) => [point.period, point.value]))
        return {
          name: series.series_name || series.series_code,
          type: 'line',
          showSymbol: false,
          connectNulls: false,
          data: periods.map((period) => valuesByPeriod.get(period) ?? null),
        }
      }),
    }
  }, [preview, theme])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem(
      BROWSER_STATE_STORAGE_KEY,
      JSON.stringify({
        providerCode: selectedProviderCode,
        providerSourceFilter,
        datasetCode: selectedDatasetCode,
        dimensionSelections,
        selectedSeriesCodes,
        startPeriod,
        endPeriod,
      } satisfies PersistedBrowserState),
    )
  }, [
    selectedProviderCode,
    providerSourceFilter,
    selectedDatasetCode,
    dimensionSelections,
    selectedSeriesCodes,
    startPeriod,
    endPeriod,
  ])

  useEffect(() => {
    const controller = new AbortController()
    let isCurrentRequest = true
    getProviders(controller.signal)
      .then((response) => {
        if (isCurrentRequest) setProviders(response)
      })
      .catch((requestError: unknown) => {
        const message = getErrorMessage(requestError)
        if (isCurrentRequest && message) setError(message)
      })
      .finally(() => {
        if (isCurrentRequest) setIsProvidersLoading(false)
      })
    return () => {
      isCurrentRequest = false
      controller.abort()
    }
  }, [])

  useEffect(() => {
    if (!selectedProviderCode) return

    const controller = new AbortController()
    let isCurrentRequest = true
    const timer = window.setTimeout(() => {
      setIsDatasetsLoading(true)
      getDatasets(selectedProviderCode, search, controller.signal)
        .then((response) => {
          if (isCurrentRequest) setDatasets(response)
        })
        .catch((requestError: unknown) => {
          const message = getErrorMessage(requestError)
          if (isCurrentRequest && message) setError(message)
        })
        .finally(() => {
          if (isCurrentRequest) setIsDatasetsLoading(false)
        })
    }, SEARCH_DELAY_MS)

    return () => {
      isCurrentRequest = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [selectedProviderCode, search])

  useEffect(() => {
    if (!selectedProviderCode || !selectedDatasetCode) return

    const controller = new AbortController()
    let isCurrentRequest = true
    getDatasetDetail(selectedProviderCode, selectedDatasetCode, controller.signal)
      .then((response) => {
        if (!isCurrentRequest) return
        setDatasetDetail(response)
        const dimensionCodes = new Set(response.dimensions.map((dimension) => dimension.code))
        setDimensionSelections((currentSelections) =>
          Object.fromEntries(
            Object.entries(currentSelections).filter(([dimensionCode]) =>
              dimensionCodes.has(dimensionCode),
            ),
          ),
        )
      })
      .catch((requestError: unknown) => {
        const message = getErrorMessage(requestError)
        if (isCurrentRequest && message) setError(message)
      })
      .finally(() => {
        if (isCurrentRequest) setIsDatasetDetailLoading(false)
      })
    return () => {
      isCurrentRequest = false
      controller.abort()
    }
  }, [selectedProviderCode, selectedDatasetCode])

  useEffect(() => {
    if (!selectedProviderCode || !selectedDatasetCode) return

    const controller = new AbortController()
    let isCurrentRequest = true
    const timer = window.setTimeout(() => {
      setIsSeriesLoading(true)
      getSeriesPage(
        selectedProviderCode,
        selectedDatasetCode,
        {
          search: seriesSearch,
          dimensions: dimensionSelections,
          offset: 0,
          limit: SERIES_PAGE_SIZE,
        },
        controller.signal,
      )
        .then((response) => {
          if (!isCurrentRequest) return
          setSeriesItems(response.items)
          setSeriesNumFound(response.num_found)
        })
        .catch((requestError: unknown) => {
          const message = getErrorMessage(requestError)
          if (isCurrentRequest && message) setError(message)
        })
        .finally(() => {
          if (isCurrentRequest) setIsSeriesLoading(false)
        })
    }, SEARCH_DELAY_MS)

    return () => {
      isCurrentRequest = false
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [selectedProviderCode, selectedDatasetCode, seriesSearch, dimensionSelections])

  useEffect(
    () => () => {
      previewControllerRef.current?.abort()
      downloadControllerRef.current?.abort()
    },
    [],
  )

  function selectProvider(providerCode: string): void {
    if (providerCode === selectedProviderCode) return
    cancelPendingActions()
    setSelectedProviderCode(providerCode)
    setDatasets([])
    setSelectedDatasetCode(null)
    setSearch('')
    setDatasetDetail(null)
    setIsDatasetDetailLoading(false)
    setDimensionSelections({})
    setSeriesItems([])
    setSeriesNumFound(0)
    setSelectedSeriesCodes([])
    setSeriesSearch('')
    setStartPeriod('')
    setEndPeriod('')
    setPreview(null)
    setPage(1)
    setError('')
  }

  function selectDataset(datasetCode: string): void {
    if (datasetCode === selectedDatasetCode) return
    cancelPendingActions()
    setSelectedDatasetCode(datasetCode)
    setIsDatasetDetailLoading(true)
    setDimensionSelections({})
    setSeriesItems([])
    setSeriesNumFound(0)
    setSelectedSeriesCodes([])
    setSeriesSearch('')
    setStartPeriod('')
    setEndPeriod('')
    setPreview(null)
    setPage(1)
    setError('')
  }

  function toggleDimensionCode(dimensionCode: string, valueCode: string): void {
    cancelPreview()
    setDimensionSelections((currentSelections) => {
      const selectedCodes = currentSelections[dimensionCode] ?? []
      const isSelected = selectedCodes.includes(valueCode)
      const updatedCodes = isSelected
        ? selectedCodes.filter((selectedCode) => selectedCode !== valueCode)
        : [...selectedCodes, valueCode]
      const updatedSelections = { ...currentSelections }
      if (updatedCodes.length) updatedSelections[dimensionCode] = updatedCodes
      else delete updatedSelections[dimensionCode]
      return updatedSelections
    })
    setSelectedSeriesCodes([])
    setPreview(null)
    setPage(1)
    setError('')
  }

  function toggleSeries(seriesCode: string): void {
    cancelPreview()
    setSelectedSeriesCodes((currentCodes) => {
      if (currentCodes.includes(seriesCode)) {
        return currentCodes.filter((code) => code !== seriesCode)
      }
      if (currentCodes.length >= MAX_SELECTED_SERIES) {
        setError(`Select at most ${MAX_SELECTED_SERIES} series for preview.`)
        return currentCodes
      }
      return [...currentCodes, seriesCode]
    })
    setPreview(null)
    setPage(1)
  }

  async function runPreview(nextPage = page): Promise<void> {
    if (!queryRequest) return
    previewControllerRef.current?.abort()
    const controller = new AbortController()
    previewControllerRef.current = controller
    const requestId = ++previewRequestIdRef.current
    const request = { ...queryRequest, page: nextPage }
    setError('')
    setIsPreviewLoading(true)
    try {
      const response = await previewQuery(request, controller.signal)
      if (requestId !== previewRequestIdRef.current) return
      setPreview(response)
      setPage(response.page)
    } catch (requestError) {
      if (requestId !== previewRequestIdRef.current) return
      const message = getErrorMessage(requestError)
      if (message) setError(message)
    } finally {
      if (requestId === previewRequestIdRef.current) {
        setIsPreviewLoading(false)
        previewControllerRef.current = null
      }
    }
  }

  async function download(format: DownloadFormat): Promise<void> {
    if (!queryRequest) return
    downloadControllerRef.current?.abort()
    const controller = new AbortController()
    downloadControllerRef.current = controller
    const requestId = ++downloadRequestIdRef.current
    setError('')
    setDownloadingFormat(format)
    try {
      const { blob, filename } = await downloadQuery(queryRequest, format, controller.signal)
      if (requestId !== downloadRequestIdRef.current) return
      saveBlob(blob, filename)
    } catch (requestError) {
      if (requestId !== downloadRequestIdRef.current) return
      const message = getErrorMessage(requestError)
      if (message) setError(message)
    } finally {
      if (requestId === downloadRequestIdRef.current) {
        setDownloadingFormat(null)
        downloadControllerRef.current = null
      }
    }
  }

  function cancelPreview(): void {
    previewRequestIdRef.current += 1
    previewControllerRef.current?.abort()
    previewControllerRef.current = null
    setIsPreviewLoading(false)
  }

  function cancelPendingActions(): void {
    cancelPreview()
    downloadRequestIdRef.current += 1
    downloadControllerRef.current?.abort()
    downloadControllerRef.current = null
    setDownloadingFormat(null)
  }

  function updatePeriod(period: 'start' | 'end', value: string): void {
    cancelPreview()
    if (period === 'start') setStartPeriod(value)
    else setEndPeriod(value)
    setPreview(null)
    setPage(1)
    setError('')
  }

  async function syncToWarehouse(): Promise<void> {
    if (!selectedProviderCode || !selectedDatasetCode || !selectedSeriesCodes.length) return
    setIsSyncing(true)
    setSyncMessage('')
    setError('')
    try {
      const summary = await syncSeriesToAnalytics({
        provider_code: selectedProviderCode,
        dataset_code: selectedDatasetCode,
        series_codes: selectedSeriesCodes,
        start_period: startPeriod || null,
        end_period: endPeriod || null,
      })
      setSyncMessage(
        `Synced ${summary.series_count} series (${summary.observations_upserted.toLocaleString()} observations) to DuckDB.`,
      )
      setAnalyticsRefreshKey((k) => k + 1)
    } catch (requestError) {
      const message = getErrorMessage(requestError)
      if (message) setError(message)
    } finally {
      setIsSyncing(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 transition-colors dark:bg-zinc-950 dark:text-zinc-100">
      <header className="sticky top-0 z-50 border-b border-zinc-200/80 bg-white/90 backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-950/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
              <Database size={21} aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-tight">WorldEconomicData</p>
              <p className="hidden text-xs text-zinc-500 sm:block dark:text-zinc-400">
                Global Macro, SDMX, DBnomics &amp; DuckDB Analytics Platform
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <nav
              aria-label="Workspace mode"
              className="flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900"
            >
              <button
                type="button"
                onClick={() => setActiveTab('browser')}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  activeTab === 'browser'
                    ? 'bg-white text-blue-600 shadow-xs dark:bg-zinc-800 dark:text-blue-400'
                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                }`}
              >
                Catalogue Browser
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('analytics')}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  activeTab === 'analytics'
                    ? 'bg-white text-blue-600 shadow-xs dark:bg-zinc-800 dark:text-blue-400'
                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                }`}
              >
                Analytics Database
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('macro')}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  activeTab === 'macro'
                    ? 'bg-white text-blue-600 shadow-xs dark:bg-zinc-800 dark:text-blue-400'
                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                }`}
              >
                Macro Intelligence
              </button>
            </nav>
            <button
              type="button"
              className="icon-button"
              aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
              onClick={() =>
                setTheme((currentTheme) => (currentTheme === 'light' ? 'dark' : 'light'))
              }
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {activeTab === 'analytics' ? (
          <AnalyticsWorkbench theme={theme} refreshTrigger={analyticsRefreshKey} />
        ) : activeTab === 'macro' ? (
          <MacroIntelligenceDashboard
            theme={theme}
            onSelectProviderInBrowser={(code) => {
              const target = providers.find((p) => p.code === code)
              if (
                target &&
                providerSourceFilter !== 'all' &&
                resolveProviderSourceType(target) !== providerSourceFilter
              ) {
                setProviderSourceFilter('all')
              }
              selectProvider(code)
              setActiveTab('browser')
            }}
          />
        ) : (
          <>
            <div className="mb-8">
              <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-blue-600 dark:text-blue-400">
                Data workspace
              </p>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                Explore WorldEconomicData series
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                Choose a provider and dataset, filter series, then preview charts, download
                observations, or sync directly to your DuckDB analytics database.
              </p>
            </div>

            <nav aria-label="Query progress" className="mb-6 flex items-center gap-2 text-xs">
              <Step
                number="1"
                label="Provider"
                isActive={!selectedProviderCode}
                isComplete={!!selectedProviderCode}
              />
              <ChevronRight size={14} className="text-zinc-400" />
              <Step
                number="2"
                label="Dataset"
                isActive={!!selectedProviderCode && !selectedDatasetCode}
                isComplete={!!selectedDatasetCode}
              />
              <ChevronRight size={14} className="text-zinc-400" />
              <Step
                number="3"
                label="Series"
                isActive={!!selectedDatasetCode}
                isComplete={!!preview}
              />
            </nav>

            {error && (
              <div role="alert" className="alert mb-6">
                <AlertCircle className="mt-0.5 shrink-0 text-red-500" size={18} />
                <span className="flex-1">{error}</span>
                <button
                  type="button"
                  className="icon-button size-7"
                  onClick={() => setError('')}
                  aria-label="Dismiss error"
                >
                  <X size={15} />
                </button>
              </div>
            )}

            <section aria-labelledby="provider-heading" className="panel mb-6">
              <SectionHeading
                number="01"
                title="Choose a provider"
                description="Select the organisation or direct data connector publishing the series you want."
                id="provider-heading"
              />
              {isProvidersLoading ? (
                <div
                  className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
                  aria-label="Loading providers"
                >
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="skeleton h-24" />
                  ))}
                </div>
              ) : providers.length ? (
                <div className="space-y-4">
                  <ConnectorFilterBar
                    activeFilter={providerSourceFilter}
                    counts={providerSourceCounts}
                    onSelectFilter={setProviderSourceFilter}
                    ariaLabel="Filter providers by connector"
                  />
                  <label className="relative block">
                    <span className="sr-only">Search providers</span>
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
                      size={17}
                    />
                    <input
                      type="search"
                      value={providerSearch}
                      onChange={(event) => setProviderSearch(event.target.value)}
                      placeholder="Search by name, code, or region…"
                      className="input pl-10"
                      aria-label="Search providers"
                    />
                  </label>
                  {filteredProviders.length ? (
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {filteredProviders.map((provider) => {
                        const isSelected = provider.code === selectedProviderCode
                        const sourceType = resolveProviderSourceType(provider)
                        return (
                          <button
                            key={provider.code}
                            type="button"
                            className={`provider-card ${isSelected ? 'provider-card-selected' : ''}`}
                            aria-pressed={isSelected}
                            onClick={() => selectProvider(provider.code)}
                          >
                            <span className="min-w-0 space-y-1.5">
                              <span className="block font-semibold">{provider.name}</span>
                              <span className="mt-1 flex flex-wrap items-center gap-1.5">
                                <span className="truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">
                                  {provider.code}
                                </span>
                                <ConnectorBadge sourceType={sourceType} />
                              </span>
                              {provider.region && (
                                <span className="block text-xs leading-5 text-zinc-600 dark:text-zinc-300">
                                  {provider.region}
                                </span>
                              )}
                            </span>
                            <span
                              className={`selection-mark ${isSelected ? 'selection-mark-selected' : ''}`}
                            >
                              {isSelected ? <Check size={14} /> : <ChevronRight size={14} />}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  ) : (
                    <EmptyState message="No providers match your current connector filter or search." />
                  )}
                </div>
              ) : (
                <EmptyState message="No providers are available." />
              )}
            </section>

            <section
              aria-labelledby="dataset-heading"
              className={`panel mb-6 transition-opacity ${selectedProviderCode ? '' : 'pointer-events-none opacity-50'}`}
            >
              <SectionHeading
                number="02"
                title="Find a dataset"
                description={
                  selectedProvider
                    ? `Browse datasets published by ${selectedProvider.name}.`
                    : 'Choose a provider to see its datasets.'
                }
                id="dataset-heading"
              />
              <label className="relative mb-4 block">
                <span className="sr-only">Search datasets</span>
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
                  size={17}
                />
                <input
                  type="search"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value)
                    setError('')
                  }}
                  disabled={!selectedProviderCode}
                  placeholder="Search by name or code…"
                  className="input pl-10"
                />
              </label>
              <div
                className="relative z-20 max-h-72 space-y-2 overflow-y-auto rounded-xl"
                data-testid="dataset-list"
              >
                {isDatasetsLoading ? (
                  [1, 2, 3].map((item) => <div key={item} className="skeleton h-16" />)
                ) : !selectedProviderCode ? (
                  <EmptyState message="Select a provider to continue." />
                ) : datasets.length ? (
                  datasets.map((dataset) => {
                    const isSelected = dataset.code === selectedDatasetCode
                    return (
                      <button
                        type="button"
                        key={`${dataset.provider_code}:${dataset.code}`}
                        aria-pressed={isSelected}
                        className={`flow-row ${isSelected ? 'flow-row-selected' : ''}`}
                        onClick={() => selectDataset(dataset.code)}
                      >
                        <span className="min-w-0 text-left">
                          <span className="block truncate text-sm font-semibold">
                            {dataset.name}
                          </span>
                          <span className="mt-1 block truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">
                            {dataset.code}
                            {dataset.nb_series != null
                              ? ` · ${dataset.nb_series.toLocaleString()} series`
                              : ''}
                          </span>
                        </span>
                        {isSelected ? (
                          <Check className="shrink-0 text-blue-600" size={18} />
                        ) : (
                          <ChevronRight className="shrink-0 text-zinc-400" size={18} />
                        )}
                      </button>
                    )
                  })
                ) : (
                  <EmptyState
                    message={
                      search ? `No datasets match “${search}”.` : 'No datasets are available.'
                    }
                  />
                )}
              </div>
            </section>

            <section
              aria-labelledby="series-heading"
              className={`panel transition-opacity ${selectedDatasetCode ? '' : 'pointer-events-none opacity-50'}`}
            >
              <SectionHeading
                number="03"
                title="Select series"
                description={
                  selectedDataset
                    ? `Filter and multi-select up to ${MAX_SELECTED_SERIES} series from ${selectedDataset.name}.`
                    : 'Choose a dataset to browse its series.'
                }
                id="series-heading"
              />
              {isDatasetDetailLoading ? (
                <div className="space-y-4" aria-label="Loading dataset detail">
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="skeleton h-24" />
                  ))}
                </div>
              ) : datasetDetail ? (
                <>
                  {datasetDetail.dimensions.length > 0 && (
                    <div className="mb-5 grid gap-4 lg:grid-cols-2">
                      {datasetDetail.dimensions.map((dimension) => (
                        <fieldset key={dimension.code} className="dimension-card">
                          <legend className="w-full px-1">
                            <span className="flex items-center justify-between gap-3">
                              <span className="text-sm font-semibold">{dimension.label}</span>
                              <span className="font-mono text-[11px] text-zinc-500">
                                {dimension.code}
                              </span>
                            </span>
                          </legend>
                          <div className="mt-3 max-h-40 space-y-1 overflow-y-auto pr-1">
                            {dimension.values.map((value) => {
                              const isSelected =
                                dimensionSelections[dimension.code]?.includes(value.code) ?? false
                              return (
                                <label key={value.code} className="code-option">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleDimensionCode(dimension.code, value.code)}
                                    className="checkbox"
                                  />
                                  <span className="min-w-0 flex-1 truncate">{value.label}</span>
                                  <span className="font-mono text-[11px] text-zinc-500">
                                    {value.code}
                                  </span>
                                </label>
                              )
                            })}
                          </div>
                        </fieldset>
                      ))}
                    </div>
                  )}

                  <label className="relative mb-4 block">
                    <span className="sr-only">Search series</span>
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
                      size={17}
                    />
                    <input
                      type="search"
                      value={seriesSearch}
                      onChange={(event) => {
                        setSeriesSearch(event.target.value)
                        setError('')
                      }}
                      placeholder="Search series by name or code…"
                      className="input pl-10"
                    />
                  </label>

                  <div
                    className="relative z-20 mb-5 max-h-72 space-y-2 overflow-y-auto rounded-xl"
                    data-testid="series-list"
                  >
                    {isSeriesLoading ? (
                      [1, 2, 3].map((item) => <div key={item} className="skeleton h-14" />)
                    ) : seriesItems.length ? (
                      seriesItems.map((series) => {
                        const isSelected = selectedSeriesCodes.includes(series.series_code)
                        return (
                          <label
                            key={series.series_code}
                            className={`flow-row cursor-pointer ${isSelected ? 'flow-row-selected' : ''}`}
                          >
                            <span className="flex min-w-0 items-center gap-3 text-left">
                              <input
                                type="checkbox"
                                className="checkbox"
                                checked={isSelected}
                                onChange={() => toggleSeries(series.series_code)}
                              />
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-semibold">
                                  {series.series_name}
                                </span>
                                <span className="mt-1 block truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">
                                  {series.series_code}
                                </span>
                              </span>
                            </span>
                          </label>
                        )
                      })
                    ) : (
                      <EmptyState message="No series match the current filters." />
                    )}
                  </div>
                  <p className="mb-4 text-xs text-zinc-500">
                    Showing {seriesItems.length.toLocaleString()} of{' '}
                    {seriesNumFound.toLocaleString()} series · {selectedSeriesCodes.length}/
                    {MAX_SELECTED_SERIES} selected
                  </p>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="field-label">
                      Start period <span className="font-normal text-zinc-400">(optional)</span>
                      <input
                        className="input mt-2"
                        value={startPeriod}
                        onChange={(event) => updatePeriod('start', event.target.value)}
                        placeholder="e.g. 2020-01-01"
                      />
                    </label>
                    <label className="field-label">
                      End period <span className="font-normal text-zinc-400">(optional)</span>
                      <input
                        className="input mt-2"
                        value={endPeriod}
                        onChange={(event) => updatePeriod('end', event.target.value)}
                        placeholder="e.g. 2024-12-31"
                      />
                    </label>
                  </div>

                  <div className="mt-6 flex flex-col gap-4 rounded-2xl border border-blue-200 bg-blue-50/70 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-blue-900/60 dark:bg-blue-950/30">
                    <div>
                      <p className="text-sm font-semibold">Query summary</p>
                      <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                        {selectedSeriesCodes.length
                          ? `${selectedSeriesCodes.length} series selected`
                          : 'No series selected'}
                        {' · '}
                        {startPeriod || endPeriod
                          ? `${startPeriod || 'earliest'} to ${endPeriod || 'latest'}`
                          : 'All periods'}
                      </p>
                      {syncMessage && (
                        <p className="mt-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                          {syncMessage}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void syncToWarehouse()}
                        disabled={isSyncing || !selectedSeriesCodes.length}
                      >
                        {isSyncing ? (
                          <LoaderCircle className="animate-spin" size={15} />
                        ) : (
                          <Database size={15} />
                        )}
                        {isSyncing ? 'Syncing…' : 'Sync to Analytics DB'}
                      </button>
                      <button
                        type="button"
                        className="primary-button"
                        onClick={() => void runPreview(1)}
                        disabled={isPreviewLoading || !selectedSeriesCodes.length}
                      >
                        {isPreviewLoading ? (
                          <LoaderCircle className="animate-spin" size={17} />
                        ) : (
                          <Database size={17} />
                        )}
                        {isPreviewLoading ? 'Loading preview…' : 'Preview data'}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <EmptyState message="Select a dataset to load its series." />
              )}
            </section>

            {preview && (
              <section aria-labelledby="results-heading" className="panel mt-6">
                <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="section-number">Results</p>
                    <h2 id="results-heading" className="mt-1 text-xl font-semibold tracking-tight">
                      Chart and data preview
                    </h2>
                    <p className="mt-1 text-sm text-zinc-500">
                      {preview.total_rows.toLocaleString()} observation
                      {preview.total_rows === 1 ? '' : 's'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <DownloadButton
                      format="csv"
                      isLoading={downloadingFormat === 'csv'}
                      onClick={() => void download('csv')}
                    />
                    <DownloadButton
                      format="json"
                      isLoading={downloadingFormat === 'json'}
                      onClick={() => void download('json')}
                    />
                  </div>
                </div>

                {chartOption && (
                  <div className="mb-5 overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
                    <ReactECharts
                      option={chartOption}
                      style={{ height: 360, width: '100%' }}
                      notMerge
                      lazyUpdate
                    />
                  </div>
                )}

                {preview.rows.length ? (
                  <>
                    <div className="relative z-10 max-h-[32rem] overflow-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
                      <table className="w-full border-collapse text-left text-sm">
                        <thead className="sticky top-0 z-10 bg-zinc-100/95 backdrop-blur dark:bg-zinc-900/95">
                          <tr>
                            {preview.columns.map((column) => (
                              <th key={column} scope="col" className="table-heading">
                                {column}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                          {preview.rows.map((row, rowIndex) => (
                            <tr
                              key={`${preview.page}-${rowIndex}`}
                              className="transition-colors hover:bg-blue-50/50 dark:hover:bg-blue-950/20"
                            >
                              {preview.columns.map((column) => (
                                <td key={column} className="table-cell">
                                  {formatCellValue(row[column])}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-4">
                      <p className="font-mono text-xs text-zinc-500">Page {preview.page}</p>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={preview.page <= 1 || isPreviewLoading}
                          onClick={() => void runPreview(preview.page - 1)}
                        >
                          <ArrowLeft size={15} /> Previous
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!preview.has_next_page || isPreviewLoading}
                          onClick={() => void runPreview(preview.page + 1)}
                        >
                          Next <ArrowRight size={15} />
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <EmptyState message="This query returned no observations. Try broadening your filters." />
                )}
              </section>
            )}
          </>
        )}
      </main>
      <footer className="mx-auto w-full max-w-7xl px-4 py-8 text-center text-xs text-zinc-500 sm:px-6 lg:px-8">
        WorldEconomicData · Unified SDMX, DBnomics, Central Bank &amp; Market Intelligence
      </footer>
    </div>
  )
}

function Step({
  number,
  label,
  isActive,
  isComplete,
}: {
  number: string
  label: string
  isActive: boolean
  isComplete: boolean
}) {
  return (
    <span
      className={`flex items-center gap-1.5 font-medium ${isActive ? 'text-blue-600 dark:text-blue-400' : isComplete ? 'text-zinc-700 dark:text-zinc-200' : 'text-zinc-400'}`}
    >
      <span
        className={`grid size-5 place-items-center rounded-full text-[10px] ${isComplete ? 'bg-blue-600 text-white' : isActive ? 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300' : 'bg-zinc-200 dark:bg-zinc-800'}`}
      >
        {isComplete ? <Check size={11} /> : number}
      </span>
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}

function SectionHeading({
  number,
  title,
  description,
  id,
}: {
  number: string
  title: string
  description: string
  id: string
}) {
  return (
    <div className="mb-5">
      <p className="section-number">{number}</p>
      <h2 id={id} className="mt-1 text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
      {message}
    </div>
  )
}

function DownloadButton({
  format,
  isLoading,
  onClick,
}: {
  format: DownloadFormat
  isLoading: boolean
  onClick: () => void
}) {
  const label = format.toUpperCase()
  return (
    <button
      type="button"
      className="secondary-button"
      disabled={isLoading}
      onClick={onClick}
      aria-label={`Download ${label}`}
    >
      {isLoading ? (
        <LoaderCircle className="animate-spin" size={15} />
      ) : format === 'json' ? (
        <FileJson size={15} />
      ) : (
        <Download size={15} />
      )}
      {isLoading ? 'Preparing…' : label}
    </button>
  )
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default App
