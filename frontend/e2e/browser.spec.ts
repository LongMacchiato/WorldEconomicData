import { expect, test } from '@playwright/test'

test('browses, filters, previews, and downloads DBnomics data', async ({ page }) => {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      json: [
        {
          code: 'IMF',
          name: 'International Monetary Fund',
          region: 'World',
          website: 'https://www.imf.org/',
        },
      ],
    })
  })
  await page.route('**/api/providers/IMF/datasets?**', async (route) => {
    await route.fulfill({
      json: [
        {
          provider_code: 'IMF',
          code: 'CPI',
          name: 'Consumer Price Index',
          description: 'Prices',
          nb_series: 10,
        },
      ],
    })
  })
  await page.route('**/api/providers/IMF/datasets/CPI', async (route) => {
    await route.fulfill({
      json: {
        provider_code: 'IMF',
        code: 'CPI',
        name: 'Consumer Price Index',
        description: 'Prices',
        nb_series: 10,
        dimensions: [
          {
            code: 'FREQ',
            label: 'Frequency',
            values: [{ code: 'M', label: 'Monthly' }],
          },
        ],
      },
    })
  })
  await page.route('**/api/providers/IMF/datasets/CPI/series?**', async (route) => {
    await route.fulfill({
      json: {
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
      },
    })
  })
  await page.route('**/api/query/preview', async (route) => {
    await route.fulfill({
      json: {
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
      },
    })
  })
  await page.route('**/api/query/download?format=csv', async (route) => {
    await route.fulfill({
      body: 'series_code,period,value\nM.US.PCPI_IX,2024-01-01,120.5\n',
      contentType: 'text/csv',
      headers: { 'content-disposition': 'attachment; filename="IMF_CPI.csv"' },
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /International Monetary Fund/ }).click()
  await page.getByRole('button', { name: /Consumer Price Index/ }).click()
  await page.getByRole('checkbox', { name: /Monthly/ }).check()
  await page.getByRole('checkbox', { name: /United States/ }).check()
  await page.getByRole('button', { name: 'Preview data' }).click()

  await expect(page.getByRole('cell', { name: 'M.US.PCPI_IX' })).toBeVisible()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download CSV' }).click(),
  ])
  expect(download.suggestedFilename()).toBe('IMF_CPI.csv')
  await expect(page.getByRole('alert')).toHaveCount(0)
})
