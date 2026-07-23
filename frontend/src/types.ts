export interface Provider {
  code: string
  name: string
  region: string | null
  website: string | null
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
