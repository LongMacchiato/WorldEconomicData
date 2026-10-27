import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as api from './api'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="chart-preview">chart</div>,
}))

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    getProviders: vi.fn(),
    getDatasets: vi.fn(),
    getDatasetDetail: vi.fn(),
    getSeriesPage: vi.fn(),
    previewQuery: vi.fn(),
    downloadQuery: vi.fn(),
    saveBlob: vi.fn(),
    getAnalyticsCatalog: vi.fn(),
    syncSeriesToAnalytics: vi.fn(),
    runAnalyticsTransform: vi.fn(),
    runAnalyticsSql: vi.fn(),
    deleteStoredSeries: vi.fn(),
    sendAiChatMessage: vi.fn(),
    getAiConfigStatus: vi.fn().mockResolvedValue({
      gemini_configured: true,
      gemini_key_masked: 'AIza...test',
      gemini_model: 'gemini-3.8-flash',
      fred_configured: true,
      fred_key_masked: 'abcd...1234',
      env_file_path: '/tmp/.env',
    }),
    updateAiConfig: vi.fn(),
  }
})

const providers = [
  {
    code: 'SDMX_ABS',
    name: 'Australian Bureau of Statistics (Direct SDMX 3.0)',
    region: 'Australia',
    website: 'https://www.abs.gov.au',
    source_type: 'sdmx',
  },
  {
    code: 'RBA',
    name: 'Reserve Bank of Australia (Direct Statistical Tables)',
    region: 'Australia',
    website: 'https://www.rba.gov.au',
    source_type: 'central_bank',
  },
  {
    code: 'YAHOO_FINANCE',
    name: 'Yahoo Finance Live Market Feeds',
    region: 'World',
    website: 'https://finance.yahoo.com',
    source_type: 'financial',
  },
  {
    code: 'IMF',
    name: 'International Monetary Fund',
    region: 'World',
    website: 'https://www.imf.org/',
    source_type: 'dbnomics',
  },
  {
    code: 'ECB',
    name: 'European Central Bank',
    region: 'Europe',
    website: null,
    source_type: 'dbnomics',
  },
]

const imfDataset = {
  provider_code: 'IMF',
  code: 'CPI',
  name: 'Consumer Price Index',
  description: 'Prices',
  nb_series: 10,
}

const ecbDataset = {
  provider_code: 'ECB',
  code: 'EXR',
  name: 'Exchange rates',
  description: null,
  nb_series: 5,
}

describe('WorldEconomicData', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(api.getProviders).mockResolvedValue(providers)
    vi.mocked(api.getDatasets).mockImplementation(async (providerCode) =>
      providerCode === 'IMF' ? [imfDataset] : [ecbDataset],
    )
    vi.mocked(api.getDatasetDetail).mockResolvedValue({
      ...imfDataset,
      dimensions: [
        {
          code: 'FREQ',
          label: 'Frequency',
          values: [
            { code: 'M', label: 'Monthly' },
            { code: 'A', label: 'Annual' },
          ],
        },
      ],
    })
    vi.mocked(api.getSeriesPage).mockResolvedValue({
      items: [
        {
          provider_code: 'IMF',
          dataset_code: 'CPI',
          series_code: 'M.US.PCPI_IX',
          series_name: 'Monthly - United States - CPI',
          dimensions: { FREQ: 'M', REF_AREA: 'US' },
        },
      ],
      offset: 0,
      limit: 50,
      num_found: 1,
      has_next_page: false,
    })
    vi.mocked(api.previewQuery).mockResolvedValue({
      columns: ['series_code', 'period', 'value'],
      rows: [{ series_code: 'M.US.PCPI_IX', period: '2024-01-01', value: 120.5 }],
      chart_series: [
        {
          series_code: 'M.US.PCPI_IX',
          series_name: 'US CPI',
          points: [{ period: '2024-01-01', value: 120.5 }],
        },
      ],
      page: 1,
      page_size: 25,
      total_rows: 1,
      has_next_page: false,
    })
    vi.mocked(api.syncSeriesToAnalytics).mockResolvedValue({
      run_id: 'run-123',
      provider_code: 'IMF',
      dataset_code: 'CPI',
      series_count: 1,
      observations_upserted: 24,
      status: 'completed',
      error_detail: null,
      started_at: '2026-10-18T00:00:00Z',
      completed_at: '2026-10-18T00:00:01Z',
    })
    vi.mocked(api.getAnalyticsCatalog).mockResolvedValue({
      total_providers: 1,
      total_datasets: 1,
      total_series: 1,
      total_observations: 24,
      series: [
        {
          series_id: 'IMF/CPI/M.US.PCPI_IX',
          provider_code: 'IMF',
          dataset_code: 'CPI',
          series_code: 'M.US.PCPI_IX',
          series_name: 'Monthly - United States - CPI',
          frequency: 'M',
          unit: 'Index',
          dimensions: { FREQ: 'M', REF_AREA: 'US' },
          observation_count: 24,
          min_period: '2023-01',
          max_period: '2024-12',
          last_synced_at: '2026-10-18T00:00:01Z',
        },
      ],
      recent_syncs: [],
    })
    vi.mocked(api.runAnalyticsTransform).mockResolvedValue({
      columns: ['series_id', 'period', 'transformed_value'],
      rows: [{ series_id: 'IMF/CPI/M.US.PCPI_IX', period: '2024-01', transformed_value: 3.2 }],
      chart_series: [
        {
          series_code: 'IMF/CPI/M.US.PCPI_IX',
          series_name: 'Monthly - United States - CPI',
          points: [{ period: '2024-01', value: 3.2 }],
        },
      ],
      correlations: [],
      total_rows: 1,
      executed_sql: 'SELECT ...',
    })
    vi.mocked(api.sendAiChatMessage).mockResolvedValue({
      reply: 'US CPI YoY inflation was 3.2% in January 2024.',
      interaction_id: 'inter_101',
      tool_calls: [
        {
          name: 'transform_warehouse_series',
          arguments: { series_ids: ['IMF/CPI/M.US.PCPI_IX'], transformation: 'yoy_pct' },
          summary: 'Computed yoy_pct across 1 series',
        },
      ],
      query_result: {
        columns: ['series_id', 'period', 'transformed_value'],
        rows: [
          { series_id: 'IMF/CPI/M.US.PCPI_IX', period: '2024-01', transformed_value: 3.2 },
          { series_id: 'IMF/CPI/M.US.PCPI_IX', period: '2024-02', transformed_value: 3.1 },
        ],
        chart_series: [
          {
            series_code: 'IMF/CPI/M.US.PCPI_IX',
            series_name: 'Monthly - United States - CPI',
            points: [
              { period: '2024-01', value: 3.2 },
              { period: '2024-02', value: 3.1 },
            ],
          },
        ],
        correlations: [],
        total_rows: 2,
        executed_sql: 'SELECT * FROM v_series_observations',
      },
      warehouse_updated: false,
    })
  })

  it('completes the provider, dataset, series, and preview journey', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('International Monetary Fund')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /International Monetary Fund/ }))
    await user.click(await screen.findByRole('button', { name: /Consumer Price Index/ }))
    await user.click(await screen.findByRole('checkbox', { name: /Monthly/ }))
    await waitFor(() =>
      expect(api.getSeriesPage).toHaveBeenCalledWith(
        'IMF',
        'CPI',
        expect.objectContaining({ dimensions: { FREQ: ['M'] } }),
        expect.any(AbortSignal),
      ),
    )
    await user.click(await screen.findByRole('checkbox', { name: /United States/ }))
    await user.type(screen.getByLabelText(/Start period/), '2020-01-01')
    await user.click(screen.getByRole('button', { name: 'Preview data' }))

    await screen.findByRole('heading', { name: 'Chart and data preview' })
    expect(screen.getByTestId('chart-preview')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'M.US.PCPI_IX' })).toBeInTheDocument()
    expect(api.previewQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_code: 'IMF',
        dataset_code: 'CPI',
        series_codes: ['M.US.PCPI_IX'],
        start_period: '2020-01-01',
      }),
      expect.any(AbortSignal),
    )
  })

  it('filters providers by connector source type (SDMX, DBnomics, Central Banks, Financial)', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('International Monetary Fund')).toBeInTheDocument()
    const filterGroup = screen.getByRole('group', { name: 'Filter providers by connector' })

    // Filter to SDMX only
    await user.click(within(filterGroup).getByRole('button', { name: /^SDMX/i }))
    expect(
      screen.getByText('Australian Bureau of Statistics (Direct SDMX 3.0)'),
    ).toBeInTheDocument()
    expect(screen.queryByText('International Monetary Fund')).not.toBeInTheDocument()
    expect(screen.queryByText('Yahoo Finance Live Market Feeds')).not.toBeInTheDocument()

    // Filter to DBnomics only
    await user.click(within(filterGroup).getByRole('button', { name: /^DBnomics/i }))
    expect(screen.getByText('International Monetary Fund')).toBeInTheDocument()
    expect(screen.getByText('European Central Bank')).toBeInTheDocument()
    expect(
      screen.queryByText('Australian Bureau of Statistics (Direct SDMX 3.0)'),
    ).not.toBeInTheDocument()

    // Filter to Central Banks only
    await user.click(within(filterGroup).getByRole('button', { name: /^Central Banks/i }))
    expect(
      screen.getByText('Reserve Bank of Australia (Direct Statistical Tables)'),
    ).toBeInTheDocument()
    expect(screen.queryByText('International Monetary Fund')).not.toBeInTheDocument()

    // Filter to Financial only
    await user.click(within(filterGroup).getByRole('button', { name: /^Financial/i }))
    expect(screen.getByText('Yahoo Finance Live Market Feeds')).toBeInTheDocument()
    expect(
      screen.queryByText('Reserve Bank of Australia (Direct Statistical Tables)'),
    ).not.toBeInTheDocument()

    // Reset to All Connectors
    await user.click(within(filterGroup).getByRole('button', { name: /^All Connectors/i }))
    expect(screen.getByText('International Monetary Fund')).toBeInTheDocument()
    expect(
      screen.getByText('Australian Bureau of Statistics (Direct SDMX 3.0)'),
    ).toBeInTheDocument()
  })

  it('resets downstream state when the provider changes', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /International Monetary Fund/ }))
    await user.click(await screen.findByRole('button', { name: /Consumer Price Index/ }))
    await user.click(await screen.findByRole('checkbox', { name: /United States/ }))

    await user.click(screen.getByRole('button', { name: /European Central Bank/ }))

    await waitFor(() =>
      expect(api.getDatasets).toHaveBeenLastCalledWith('ECB', '', expect.any(AbortSignal)),
    )
    expect(screen.queryByRole('checkbox', { name: /United States/ })).not.toBeInTheDocument()
    expect(screen.getByText('Choose a dataset to browse its series.')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('dataset-list')).getByRole('button', { name: /Exchange rates/ }),
    ).toBeInTheDocument()
  })

  it('syncs selected series to DuckDB, runs transformations, and queries AI Assistant', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /International Monetary Fund/ }))
    await user.click(await screen.findByRole('button', { name: /Consumer Price Index/ }))
    await user.click(await screen.findByRole('checkbox', { name: /United States/ }))

    await user.click(screen.getByRole('button', { name: 'Sync to Analytics DB' }))
    expect(
      await screen.findByText(/Synced 1 series \(24 observations\) to DuckDB\./),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Analytics Database' }))
    expect(await screen.findByTestId('analytics-workbench')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Compute Transformation' }))

    expect(await screen.findByText(/Query Output \(1 rows\)/)).toBeInTheDocument()

    const aiInput = screen.getByLabelText('Ask AI Economist Assistant')
    await user.type(aiInput, 'Analyze US CPI YoY')
    await user.click(screen.getByRole('button', { name: 'Ask AI' }))

    expect(
      await screen.findByText('US CPI YoY inflation was 3.2% in January 2024.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Query Output \(2 rows\)/)).toBeInTheDocument()
  })
})
