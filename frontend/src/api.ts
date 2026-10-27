import axios, { AxiosError } from 'axios'
import type {
  AiChatRequest,
  AiChatResponse,
  AiConfigStatus,
  AiConfigUpdateRequest,
  AnalyticsQueryResult,
  AnalyticsTransformRequest,
  Dataset,
  DatasetDetail,
  DimensionSelections,
  DownloadFormat,
  MacroDashboardStatus,
  Provider,
  QueryPreview,
  QueryRequest,
  SeriesPage,
  SyncRequest,
  SyncRunSummary,
  WarehouseSummary,
} from './types'

// In dev, Vite proxies /api to the backend (see vite.config.ts).
// Set VITE_API_BASE_URL when the API is hosted elsewhere (e.g. production).
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 90_000,
  headers: { Accept: 'application/json' },
})

export async function getProviders(signal?: AbortSignal): Promise<Provider[]> {
  const response = await apiClient.get<Provider[]>('/api/providers', { signal })
  return response.data
}

export async function getDatasets(
  providerCode: string,
  search: string,
  signal?: AbortSignal,
): Promise<Dataset[]> {
  const response = await apiClient.get<Dataset[]>(
    `/api/providers/${encodeURIComponent(providerCode)}/datasets`,
    { params: { search }, signal },
  )
  return response.data
}

export async function getDatasetDetail(
  providerCode: string,
  datasetCode: string,
  signal?: AbortSignal,
): Promise<DatasetDetail> {
  const response = await apiClient.get<DatasetDetail>(
    `/api/providers/${encodeURIComponent(providerCode)}/datasets/${encodeURIComponent(datasetCode)}`,
    { signal },
  )
  return response.data
}

export async function searchDatasets(query: string, signal?: AbortSignal): Promise<Dataset[]> {
  const response = await apiClient.get<Dataset[]>('/api/search', {
    params: { q: query },
    signal,
  })
  return response.data
}

export async function getSeriesPage(
  providerCode: string,
  datasetCode: string,
  options: {
    search?: string
    dimensions?: DimensionSelections
    offset?: number
    limit?: number
  },
  signal?: AbortSignal,
): Promise<SeriesPage> {
  const response = await apiClient.get<SeriesPage>(
    `/api/providers/${encodeURIComponent(providerCode)}/datasets/${encodeURIComponent(datasetCode)}/series`,
    {
      params: {
        search: options.search,
        offset: options.offset,
        limit: options.limit,
        dimensions: options.dimensions ? JSON.stringify(options.dimensions) : undefined,
      },
      signal,
    },
  )
  return response.data
}

export async function previewQuery(
  request: QueryRequest,
  signal?: AbortSignal,
): Promise<QueryPreview> {
  const response = await apiClient.post<QueryPreview>('/api/query/preview', request, {
    signal,
  })
  return response.data
}

export async function downloadQuery(
  request: QueryRequest,
  format: DownloadFormat,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  try {
    const response = await apiClient.post<Blob>('/api/query/download', request, {
      params: { format },
      responseType: 'blob',
      signal,
    })

    return {
      blob: response.data,
      filename: getDownloadFilename(response.headers['content-disposition'], format),
    }
  } catch (error) {
    if (error instanceof AxiosError && error.response?.data instanceof Blob) {
      const message = await getBlobErrorMessage(error.response.data)
      if (message) {
        throw new Error(message, { cause: error })
      }
    }
    throw error
  }
}

export function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function getAnalyticsCatalog(signal?: AbortSignal): Promise<WarehouseSummary> {
  const response = await apiClient.get<WarehouseSummary>('/api/analytics/catalog', { signal })
  return response.data
}

export async function syncSeriesToAnalytics(
  request: SyncRequest,
  signal?: AbortSignal,
): Promise<SyncRunSummary> {
  const response = await apiClient.post<SyncRunSummary>('/api/analytics/sync', request, { signal })
  return response.data
}

export async function deleteStoredSeries(seriesId: string, signal?: AbortSignal): Promise<void> {
  await apiClient.delete(`/api/analytics/series/${seriesId}`, { signal })
}

export async function runAnalyticsTransform(
  request: AnalyticsTransformRequest,
  signal?: AbortSignal,
): Promise<AnalyticsQueryResult> {
  const response = await apiClient.post<AnalyticsQueryResult>('/api/analytics/transform', request, {
    signal,
  })
  return response.data
}

export async function runAnalyticsSql(
  sql: string,
  limit = 500,
  signal?: AbortSignal,
): Promise<AnalyticsQueryResult> {
  const response = await apiClient.post<AnalyticsQueryResult>(
    '/api/analytics/sql',
    { sql, limit },
    { signal },
  )
  return response.data
}

export async function sendAiChatMessage(
  request: AiChatRequest,
  signal?: AbortSignal,
): Promise<AiChatResponse> {
  const response = await apiClient.post<AiChatResponse>('/api/analytics/ai/chat', request, {
    signal,
  })
  return response.data
}

export async function getAiConfig(signal?: AbortSignal): Promise<AiConfigStatus> {
  const response = await apiClient.get<AiConfigStatus>('/api/analytics/ai/config', { signal })
  return response.data
}

export async function updateAiConfig(
  request: AiConfigUpdateRequest,
  signal?: AbortSignal,
): Promise<AiConfigStatus> {
  const response = await apiClient.put<AiConfigStatus>('/api/analytics/ai/config', request, {
    signal,
  })
  return response.data
}

export async function getMacroDashboardStatus(signal?: AbortSignal): Promise<MacroDashboardStatus> {
  const response = await apiClient.get<MacroDashboardStatus>('/api/macro/status', { signal })
  return response.data
}

export async function refreshMacroDashboard(signal?: AbortSignal): Promise<MacroDashboardStatus> {
  const response = await apiClient.post<MacroDashboardStatus>('/api/macro/refresh', {}, { signal })
  return response.data
}

export function getErrorMessage(error: unknown): string {
  if (axios.isCancel(error)) {
    return ''
  }

  if (error instanceof AxiosError) {
    const responseData = error.response?.data as
      { detail?: string; message?: string } | string | undefined
    if (typeof responseData === 'string' && responseData.trim()) {
      return responseData
    }
    if (responseData && typeof responseData === 'object') {
      return responseData.detail || responseData.message || error.message
    }
    return error.message
  }

  return error instanceof Error ? error.message : 'An unexpected error occurred.'
}

function getDownloadFilename(
  contentDisposition: string | undefined,
  format: DownloadFormat,
): string {
  if (contentDisposition) {
    const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
    if (utf8Match?.[1]) {
      return decodeURIComponent(utf8Match[1].replace(/["']/g, ''))
    }

    const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
    if (filenameMatch?.[1]) {
      return filenameMatch[1]
    }
  }

  return `dbnomics-data.${format}`
}

async function getBlobErrorMessage(blob: Blob): Promise<string> {
  const text = await blob.text()
  if (!text.trim()) return ''

  try {
    const payload = JSON.parse(text) as { detail?: unknown; message?: unknown }
    if (typeof payload.detail === 'string') return payload.detail
    if (typeof payload.message === 'string') return payload.message
  } catch {
    return text
  }

  return text
}
