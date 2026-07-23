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
  }
})

const providers = [
  {
    code: 'IMF',
    name: 'International Monetary Fund',
    region: 'World',
    website: 'https://www.imf.org/',
  },
  {
    code: 'ECB',
    name: 'European Central Bank',
    region: 'Europe',
    website: null,
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

describe('DBnomics data browser', () => {
  beforeEach(() => {
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
})
