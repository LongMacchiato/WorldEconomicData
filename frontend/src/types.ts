export type ProviderSourceType = 'dbnomics' | 'sdmx' | 'central_bank' | 'financial'
export type ProviderSourceFilter = 'all' | ProviderSourceType

export const CONNECTOR_FILTER_OPTIONS: ReadonlyArray<{
  id: ProviderSourceFilter
  label: string
}> = [
  { id: 'all', label: 'All Connectors' },
  { id: 'sdmx', label: 'SDMX' },
  { id: 'dbnomics', label: 'DBnomics' },
  { id: 'central_bank', label: 'Central Banks' },
  { id: 'financial', label: 'Financial' },
]

export function resolveProviderSourceType(
  provider: Pick<Provider, 'code' | 'source_type'>,
): ProviderSourceType {
  if (
    provider.source_type === 'sdmx' ||
    provider.source_type === 'central_bank' ||
    provider.source_type === 'financial' ||
    provider.source_type === 'dbnomics'
  ) {
    return provider.source_type
  }
  const upperCode = provider.code.toUpperCase()
  if (upperCode.startsWith('SDMX_') || upperCode.startsWith('SDMX1_')) {
    return 'sdmx'
  }
  if (upperCode === 'RBA' || upperCode === 'FRED') {
    return 'central_bank'
  }
  if (upperCode === 'YAHOO_FINANCE') {
    return 'financial'
  }
  return 'dbnomics'
}

export function formatSourceTypeBadge(sourceType: ProviderSourceType): string {
  switch (sourceType) {
    case 'sdmx':
      return 'SDMX'
    case 'central_bank':
      return 'Central Bank'
    case 'financial':
      return 'Financial'
    default:
      return 'DBnomics'
  }
}

export interface Provider {
  code: string
  name: string
  region: string | null
  website: string | null
  source_type?: ProviderSourceType | string
  requires_api_key?: boolean
}

export interface Dataset {
  provider_code: string
  code: string
  name: string
  description: string | null
  nb_series: number | null
}

export interface DimensionCode {
  code: string
  label: string
}

export interface Dimension {
  code: string
  label: string
  values: DimensionCode[]
}

export interface DatasetDetail {
  provider_code: string
  code: string
  name: string
  description: string | null
  nb_series: number | null
  dimensions: Dimension[]
}

export interface SeriesSummary {
  provider_code: string
  dataset_code: string
  series_code: string
  series_name: string
  dimensions: Record<string, string>
}

export interface SeriesPage {
  items: SeriesSummary[]
  offset: number
  limit: number
  num_found: number
  has_next_page: boolean
}

export type DimensionSelections = Record<string, string[]>

export interface QueryRequest {
  provider_code: string
  dataset_code: string
  series_codes: string[]
  start_period: string | null
  end_period: string | null
  page: number
  page_size: number
}

export interface ChartPoint {
  period: string
  value: number | null
}

export interface ChartSeries {
  series_code: string
  series_name: string
  points: ChartPoint[]
}

export interface QueryPreview {
  columns: string[]
  rows: Array<Record<string, unknown>>
  chart_series: ChartSeries[]
  page: number
  page_size: number
  total_rows: number
  has_next_page: boolean
}

export type DownloadFormat = 'csv' | 'json'

export type TransformationType = 'raw' | 'yoy_pct' | 'pop_pct' | 'rebased_100' | 'rolling_avg'

export interface SyncRequest {
  provider_code: string
  dataset_code: string
  series_codes: string[]
  start_period?: string | null
  end_period?: string | null
}

export interface SyncRunSummary {
  run_id: string
  provider_code: string
  dataset_code: string
  series_count: number
  observations_upserted: number
  status: string
  error_detail: string | null
  started_at: string
  completed_at: string | null
}

export interface StoredSeries {
  series_id: string
  provider_code: string
  dataset_code: string
  series_code: string
  series_name: string
  frequency: string | null
  unit: string | null
  dimensions: Record<string, string>
  observation_count: number
  min_period: string | null
  max_period: string | null
  last_synced_at: string
}

export interface WarehouseSummary {
  total_providers: number
  total_datasets: number
  total_series: number
  total_observations: number
  series: StoredSeries[]
  recent_syncs: SyncRunSummary[]
}

export interface AnalyticsTransformRequest {
  series_ids: string[]
  transformation: TransformationType
  rolling_window: number
  start_period?: string | null
  end_period?: string | null
}

export interface CorrelationPair {
  series_a: string
  series_b: string
  correlation: number | null
  overlapping_periods: number
}

export interface AnalyticsQueryResult {
  columns: string[]
  rows: Array<Record<string, unknown>>
  chart_series: ChartSeries[]
  correlations: CorrelationPair[]
  total_rows: number
  executed_sql: string | null
}

export interface AiChatRequest {
  prompt: string
  previous_interaction_id?: string | null
}

export interface AiToolCallRecord {
  name: string
  arguments: Record<string, unknown>
  summary: string
}

export interface AiChatResponse {
  reply: string
  interaction_id: string
  tool_calls: AiToolCallRecord[]
  query_result: AnalyticsQueryResult | null
  warehouse_updated: boolean
}

export interface AiConfigStatus {
  gemini_key_configured: boolean
  gemini_key_masked: string | null
  gemini_model: string
  fred_key_configured: boolean
  fred_key_masked: string | null
}

export interface AiConfigUpdateRequest {
  gemini_api_key?: string | null
  gemini_model?: string | null
  fred_api_key?: string | null
}

export interface ConnectorStatusItem {
  provider_code: string
  provider_name: string
  source_type: ProviderSourceType
  requires_api_key: boolean
  configured: boolean
  dataset_count: number
}

export interface MacroKpiMetric {
  key: string
  label: string
  series_id: string
  value: number | null
  unit: string
  period: string | null
  previous_value: number | null
  delta: number | null
  status_badge: string | null
}

export interface MacroBriefRecord {
  insight_date: string
  model_id: string
  summary: string
  metrics_snapshot: Record<string, unknown>
  created_at: string
}

export interface MacroDashboardStatus {
  internet_connected: boolean
  connectors: ConnectorStatusItem[]
  kpis: MacroKpiMetric[]
  latest_brief: MacroBriefRecord | null
}
