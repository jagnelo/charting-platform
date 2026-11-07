import { test, expect } from './helpers'
import type { Locator, Page, Request, Response, Route } from '@playwright/test'

type DashboardWidget = {
  id: number
  widget_type: string
  title: string | null
  config: Record<string, any>
  layout: { x: number; y: number; w: number; h: number }
}

type Dashboard = {
  tabs: Array<{ widgets: DashboardWidget[] }>
}

function responsePath(response: Response) {
  return new URL(response.url()).pathname
}

async function enterEditMode(page: Page) {
  if (await page.locator('.widget-catalog').count() === 0) {
    const emptyDashboardButton = page.getByRole('button', { name: 'Edit Dashboard', exact: true })
    if (await emptyDashboardButton.count()) await emptyDashboardButton.click()
    else await page.getByRole('button', { name: 'Edit', exact: true }).click()
  }
  await expect(page.locator('.widget-catalog')).toBeVisible()
}

async function addWidget(page: Page, label: string): Promise<DashboardWidget> {
  await enterEditMode(page)
  const created = page.waitForResponse(response =>
    response.request().method() === 'POST'
      && /\/api\/v1\/dashboards\/tabs\/\d+\/widgets$/.test(responsePath(response)),
  )
  await page.getByRole('button', { name: new RegExp(`^${label}`) }).click()
  const response = await created
  expect(response.status()).toBe(201)
  const widget = await response.json() as DashboardWidget
  await expect(page.locator('.config-modal')).toBeVisible()
  return widget
}

async function closeConfig(page: Page) {
  const modal = page.locator('.config-modal')
  await modal.getByRole('button', { name: 'x', exact: true }).click()
  await expect(modal).toHaveCount(0)
}

async function persistedDashboard(page: Page): Promise<Dashboard> {
  return page.evaluate(async () => {
    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/v1/dashboards/default', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`Dashboard read failed: ${response.status}`)
    return await response.json() as Dashboard
  })
}

function dailyBarsResponse(page: Page, symbol: string, limit: number) {
  return page.waitForResponse(response => {
    if (response.request().method() !== 'GET') return false
    const url = new URL(response.url())
    const escaped = symbol.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const path = new RegExp(`/ohlcv(?:/local)?/${escaped}/D1(?:/transformed)?$`)
    return path.test(url.pathname) && Number(url.searchParams.get('limit')) === limit
  }, { timeout: 20_000 })
}

function localDailyBarsResponse(page: Page, symbol: string, limit: number) {
  return page.waitForResponse(response => {
    if (response.request().method() !== 'GET') return false
    const url = new URL(response.url())
    return url.pathname === `/api/v1/ohlcv/local/${encodeURIComponent(symbol)}/D1`
      && Number(url.searchParams.get('limit')) === limit
  }, { timeout: 20_000 })
}

function preparationResponse(page: Page, symbol: string) {
  return page.waitForResponse(response => {
    if (response.request().method() !== 'POST' || responsePath(response) !== '/api/v1/data/ensure') return false
    const body = response.request().postDataJSON() as { target?: { symbol?: string } }
    return body.target?.symbol?.toUpperCase() === symbol.toUpperCase()
  }, { timeout: 20_000 })
}

function instrumentProfileResponse(page: Page, symbol: string) {
  return page.waitForResponse(response =>
    response.request().method() === 'GET'
      && responsePath(response) === `/api/v1/instruments/${encodeURIComponent(symbol)}`,
    { timeout: 20_000 },
  )
}

type DailyBar = { ts?: string; close?: number }

async function assertUsefulBars(response: Response, minimum: number): Promise<DailyBar[]> {
  expect(response.ok()).toBe(true)
  const bars = await response.json() as DailyBar[]
  expect(bars.length).toBeGreaterThanOrEqual(minimum)
  expect(bars.slice(-Math.min(20, bars.length)).every(bar =>
    typeof bar.ts === 'string' && Number.isFinite(Number(bar.close)) && Number(bar.close) > 0,
  )).toBe(true)
  return bars
}

async function expectSeriesPainted(chart: Locator, color: string) {
  const [red, green, blue] = color.match(/[0-9a-f]{2}/gi)!.map(value => Number.parseInt(value, 16))
  await expect.poll(() => chart.locator('.uplot-host canvas').evaluate((canvas, expected) => {
    const element = canvas as HTMLCanvasElement
    const context = element.getContext('2d')
    if (!context || !element.width || !element.height) return 0
    const pixels = context.getImageData(0, 0, element.width, element.height).data
    let matching = 0
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset + 3]! > 220
        && Math.abs(pixels[offset]! - expected.red) <= 18
        && Math.abs(pixels[offset + 1]! - expected.green) <= 18
        && Math.abs(pixels[offset + 2]! - expected.blue) <= 18) matching++
    }
    return matching
  }, { red, green, blue }), { timeout: 5_000, intervals: [100, 250, 500] }).toBeGreaterThan(8)
}

async function expectAdvancedCandlesPainted(widget: Locator) {
  const plot = widget.locator('.advanced-chart-widget .chart-root .uplot')
  await expect(plot).toBeVisible()
  const canvas = plot.locator('canvas').first()
  await expect(canvas).toBeVisible()
  await expect.poll(() => canvas.evaluate(element => {
    const canvas = element as HTMLCanvasElement
    const context = canvas.getContext('2d')
    if (!context || !canvas.width || !canvas.height) return 0
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    let candles = 0
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset + 3]! <= 220) continue
      const up = Math.abs(pixels[offset]! - 38) <= 10
        && Math.abs(pixels[offset + 1]! - 166) <= 10
        && Math.abs(pixels[offset + 2]! - 154) <= 10
      const down = Math.abs(pixels[offset]! - 239) <= 10
        && Math.abs(pixels[offset + 1]! - 83) <= 10
        && Math.abs(pixels[offset + 2]! - 80) <= 10
      if (up || down) candles++
    }
    return candles
  }), { timeout: 30_000, intervals: [100, 250, 500] }).toBeGreaterThan(20)
}

type CachedInstrumentProfile = {
  symbol: string
  name?: string | null
  description?: string | null
  currency?: string | null
  equity_detail?: { sector?: string | null; industry?: string | null; country?: string | null } | null
}

async function expectUsefulInstrumentDetails(widget: Locator, response: Response, symbol: string) {
  expect(response.ok()).toBe(true)
  const profile = await response.json() as CachedInstrumentProfile
  expect(profile.symbol).toBe(symbol)
  const name = profile.name || profile.description
  expect(name?.trim()).toBeTruthy()
  await expect(widget.locator('.details-symbol')).toHaveText(symbol)
  await expect(widget.locator('.details-name')).toHaveText(name!)

  const descriptiveFields: Array<[string, string | null | undefined]> = [
    ['Currency', profile.currency],
    ['Sector', profile.equity_detail?.sector],
    ['Industry', profile.equity_detail?.industry],
    ['Country', profile.equity_detail?.country],
  ]
  const availableFields = descriptiveFields.filter(([, value]) => Boolean(value?.trim()))
  expect(availableFields.length, 'cached profile must expose useful descriptive metadata').toBeGreaterThanOrEqual(2)
  for (const [label, value] of availableFields) {
    const row = widget.locator('.detail-row').filter({ has: widget.getByText(label, { exact: true }) })
    await expect(row.locator('b')).toHaveText(value!)
  }
}

function deferredGate() {
  let release!: () => void
  const promise = new Promise<void>(resolve => { release = resolve })
  return { promise, release }
}

async function expectComparisonTooltip(page: Page, chart: Locator, symbols: string[]) {
  await chart.scrollIntoViewIfNeeded()
  const plot = chart.locator('.uplot')
  await expect(plot).toBeVisible()
  const bounds = await plot.boundingBox()
  expect(bounds).not.toBeNull()
  await page.mouse.move(bounds!.x + bounds!.width * 0.65, bounds!.y + bounds!.height * 0.5)
  const tooltip = chart.locator('.chart-tooltip')
  await expect(tooltip).toBeVisible()
  for (const symbol of symbols) {
    await expect(tooltip.locator('b').filter({ hasText: new RegExp(`^${symbol}\\s`) })).toBeVisible()
  }
  await expect(tooltip.locator('b')).toHaveCount(symbols.length)
}

function formattedQuote(close: number, currency: string | null | undefined) {
  if (!currency) return close.toFixed(4)
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(close)
}

function searchCandidate(symbol: string) {
  return {
    symbol,
    name: `Controlled candidate ${symbol}`,
    exchange: 'XNAS',
    type: 'Common Stock',
    provider: 'dashboard-journey-fixture',
    instrument_id: null,
    identity_status: 'provider_candidate',
  }
}

async function returnDiscovery(route: Route, requestId: string, candidates: string[]) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      request_id: requestId,
      status: 'complete',
      candidates: candidates.map(searchCandidate),
      source_outcomes: [],
    }),
  })
}

async function returnDiscoveryUnavailable(route: Route, requestId: string) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ request_id: requestId, status: 'unavailable', candidates: [], source_outcomes: [] }),
  })
}

async function returnResolvedAcquire(route: Route, requestId: string, symbol: string) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      request_id: requestId,
      status: 'resolved',
      instrument: {
        instrument_id: 900001,
        symbol,
        identity_status: 'confirmed',
        instrument_type: 'equity',
        domain_key: null,
        primary_identifier_type: 'ticker',
        primary_identifier_value: symbol,
        primary_listing_mic: 'XNAS',
      },
      source_outcomes: [],
    }),
  })
}

function controlledUnavailablePreparation(requestId: string, target: Record<string, unknown>, symbol: string) {
  const now = '2026-11-07T00:00:00Z'
  const dependencies = ['identity', 'profile', 'history'].map(dataset => ({
    dependency_id: `${requestId}:${dataset}`,
    depends_on: [],
    instrument_id: null,
    symbol,
    dataset,
    status: 'unavailable',
    requested_start: null,
    requested_end: null,
    covered_start: null,
    covered_end: null,
    reason_code: 'controlled_dashboard_journey_fixture',
    retry_at: null,
    updated_at: now,
    covered_ranges: [],
  }))
  return {
    request_id: requestId,
    status: 'unavailable',
    created_at: now,
    updated_at: now,
    version: 1,
    target,
    dependencies,
    completed: dependencies.length,
    total: dependencies.length,
    last_progress_at: now,
    has_pending_work: false,
  }
}

test('Dashboard creates useful seeded quote and chart widgets and restores saved configuration', async ({ page, loggedIn, browserDiagnostics }) => {
  // The comparison widget starts with QQQ/DIA defaults. These are not part of this
  // SPY/XLB witness, so keep their initial preparation attempts controlled and fail closed.
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as { request_id: string; target: { symbol?: string } }
    const symbol = body.target.symbol?.toUpperCase()
    if (symbol === 'QQQ' || symbol === 'DIA') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(controlledUnavailablePreparation(`dashboard-default-${symbol}`, body.target, symbol)),
      })
      return
    }
    await route.continue()
  })
  await page.goto('/dashboard')
  await expect(page.locator('.dashboard-view')).toBeVisible()

  const chartBars = dailyBarsResponse(page, 'SPY', 300)
  const chartWidget = await addWidget(page, 'Simple Chart')
  const chartModal = page.locator('.config-modal')
  const title = chartModal.getByPlaceholder('Widget title')
  const titleSave = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${chartWidget.id}`,
  )
  await title.fill('SPY Daily Research')
  await title.press('Tab')
  expect((await titleSave).ok()).toBe(true)
  await closeConfig(page)
  await assertUsefulBars(await chartBars, 50)

  const chart = page.locator('.dashboard-widget').filter({ hasText: 'SPY Daily Research' })
  await chart.scrollIntoViewIfNeeded()
  await expect(chart.locator('.line-chart-widget .uplot-host .uplot')).toBeVisible()
  await expectSeriesPainted(chart.locator('.line-chart-widget'), '#64b5f6')

  const quoteBars = dailyBarsResponse(page, 'SPY', 2)
  const quoteInstrument = instrumentProfileResponse(page, 'SPY')
  const quoteWidget = await addWidget(page, 'Quote Card')
  await closeConfig(page)
  const quoteResponseBars = await assertUsefulBars(await quoteBars, 2)
  const quoteInstrumentResponse = await quoteInstrument
  expect(quoteInstrumentResponse.ok()).toBe(true)
  const quoteCurrency = (await quoteInstrumentResponse.json()).currency as string | null | undefined
  const quote = page.locator('.dashboard-widget').filter({ hasText: 'Quote Card' }).locator('.quote-widget')
  await expect(quote.locator('.quote-symbol')).toHaveText('SPY')
  await expect(quote.locator('.quote-price')).toHaveText(formattedQuote(Number(quoteResponseBars.at(-1)?.close), quoteCurrency))

  const comparisonWidget = await addWidget(page, 'Comparison Chart')
  const comparisonRows = page.locator('.config-modal .comparison-config-row')
  const removeDia = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${comparisonWidget.id}`,
  )
  await comparisonRows.nth(2).getByRole('button', { name: 'Remove' }).click()
  expect((await removeDia).ok()).toBe(true)
  await expect.poll(async () => (await persistedDashboard(page)).tabs.flatMap(tab => tab.widgets)
    .find(widget => widget.id === comparisonWidget.id)?.config.targets?.length).toBe(2)

  const comparisonXlbBars = dailyBarsResponse(page, 'XLB', 300)
  const comparisonXlbPreparation = preparationResponse(page, 'XLB')
  const changeSecondTarget = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${comparisonWidget.id}`,
  )
  await comparisonRows.nth(1).locator('.dash-search-input').fill('XLB')
  expect((await changeSecondTarget).ok()).toBe(true)
  const xlbPreparation = await comparisonXlbPreparation
  expect(xlbPreparation.ok()).toBe(true)
  expect((await xlbPreparation.json()).status).toBe('ready')
  const comparisonSaved = await persistedDashboard(page)
  expect(comparisonSaved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === comparisonWidget.id)?.config.targets)
    .toMatchObject([{ symbol: 'SPY' }, { symbol: 'XLB', label: 'XLB' }])
  const comparisonXlbResponseBars = await assertUsefulBars(await comparisonXlbBars, 50)
  await closeConfig(page)

  const comparison = page.locator('.dashboard-widget').filter({ hasText: 'Comparison Chart' }).locator('.line-chart-widget')
  await expectSeriesPainted(comparison, '#64b5f6')
  await expectSeriesPainted(comparison, '#81c784')
  await expectComparisonTooltip(page, comparison, ['SPY', 'XLB'])

  const beforeReload = await persistedDashboard(page)
  const widgetsBeforeReload = beforeReload.tabs.flatMap(tab => tab.widgets)
  expect(widgetsBeforeReload.find(widget => widget.id === chartWidget.id)).toMatchObject({
    title: 'SPY Daily Research',
    widget_type: 'simple_chart',
    config: { symbol: 'SPY' },
  })
  expect(widgetsBeforeReload.find(widget => widget.id === quoteWidget.id)).toMatchObject({
    widget_type: 'quote',
    config: { symbol: 'SPY' },
  })
  expect(widgetsBeforeReload.find(widget => widget.id === comparisonWidget.id)?.config.targets)
    .toMatchObject([{ symbol: 'SPY' }, { symbol: 'XLB', label: 'XLB' }])

  const restoredChartBars = dailyBarsResponse(page, 'SPY', 300)
  const restoredQuoteBars = dailyBarsResponse(page, 'SPY', 2)
  const restoredQuoteInstrument = instrumentProfileResponse(page, 'SPY')
  const restoredComparisonXlbBars = dailyBarsResponse(page, 'XLB', 300)
  await page.reload()
  await expect(page.locator('.dashboard-view')).toBeVisible()
  await assertUsefulBars(await restoredChartBars, 50)
  const restoredQuote = await assertUsefulBars(await restoredQuoteBars, 2)
  const restoredInstrumentResponse = await restoredQuoteInstrument
  expect(restoredInstrumentResponse.ok()).toBe(true)
  const restoredCurrency = (await restoredInstrumentResponse.json()).currency as string | null | undefined
  const restoredComparison = await assertUsefulBars(await restoredComparisonXlbBars, 50)
  expect(restoredComparison.at(-1)?.close).toBe(comparisonXlbResponseBars.at(-1)?.close)
  const restoredChart = page.locator('.dashboard-widget').filter({ hasText: 'SPY Daily Research' })
  await restoredChart.scrollIntoViewIfNeeded()
  await expect(restoredChart.locator('.line-chart-widget .uplot-host .uplot')).toBeVisible()
  await expectSeriesPainted(restoredChart.locator('.line-chart-widget'), '#64b5f6')
  await expect(page.locator('.dashboard-widget').filter({ hasText: 'Quote Card' }).locator('.quote-symbol')).toHaveText('SPY')
  const restoredQuotePrice = page.locator('.dashboard-widget').filter({ hasText: 'Quote Card' }).locator('.quote-price')
  await expect(restoredQuotePrice).toHaveText(formattedQuote(Number(restoredQuote.at(-1)?.close), restoredCurrency))
  const restoredComparisonChart = page.locator('.dashboard-widget').filter({ hasText: 'Comparison Chart' }).locator('.line-chart-widget')
  await expectSeriesPainted(restoredComparisonChart, '#64b5f6')
  await expectSeriesPainted(restoredComparisonChart, '#81c784')
  await expectComparisonTooltip(page, restoredComparisonChart, ['SPY', 'XLB'])
  const comparisonAfterReload = await persistedDashboard(page)
  expect(comparisonAfterReload.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === comparisonWidget.id)?.config.targets)
    .toMatchObject([{ symbol: 'SPY' }, { symbol: 'XLB', label: 'XLB' }])
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Dashboard symbol and comparison edits roll back with visible cancel and retry', async ({ page, loggedIn }) => {
  const remainingFailures = new Map<number, number>()
  await page.route('**/api/v1/instruments/discover', async route => {
    const body = route.request().postDataJSON() as { query: string; request_id: string }
    if (body.query.toUpperCase() === 'XLB') return returnDiscovery(route, body.request_id, ['XLB'])
    return returnDiscoveryUnavailable(route, body.request_id)
  })
  await page.route('**/api/v1/instruments/acquire', async route => {
    const body = route.request().postDataJSON() as { symbol: string; request_id: string }
    return returnResolvedAcquire(route, body.request_id, body.symbol)
  })
  await page.route('**/api/v1/dashboards/widgets/*', async route => {
    const request = route.request()
    const match = new URL(request.url()).pathname.match(/\/dashboards\/widgets\/(\d+)$/)
    const widgetId = match ? Number(match[1]) : 0
    const remaining = remainingFailures.get(widgetId) ?? 0
    if (request.method() === 'PATCH' && widgetId && remaining > 0) {
      remainingFailures.set(widgetId, remaining - 1)
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Controlled dashboard save failure' }) })
      return
    }
    await route.continue()
  })

  await page.goto('/dashboard')
  const chart = await addWidget(page, 'Simple Chart')
  remainingFailures.set(chart.id, 2)
  await closeConfig(page)
  const chartWidget = page.locator('.dashboard-widget').filter({ hasText: 'Simple Chart' })

  const editSymbol = async () => {
    await chartWidget.getByRole('button', { name: 'Configure' }).click()
    return page.locator('.config-modal .dash-search-input')
  }
  let search = await editSymbol()
  let saveResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${chart.id}`,
  )
  await search.fill('XLB')
  expect((await saveResponse).status()).toBe(503)
  let modal = page.locator('.config-modal')
  await expect(modal.getByRole('alert')).toContainText('The previous saved value was restored.')
  await expect(modal.getByRole('button', { name: 'Retry save' })).toBeVisible()
  await expect(modal.getByRole('button', { name: 'Cancel' })).toBeVisible()
  let saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === chart.id)?.config.symbol).toBe('SPY')

  await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(modal.getByRole('alert')).toHaveCount(0)
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === chart.id)?.config.symbol).toBe('SPY')

  search = page.locator('.config-modal .dash-search-input')
  saveResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${chart.id}`,
  )
  await search.fill('XLB')
  expect((await saveResponse).status()).toBe(503)
  modal = page.locator('.config-modal')
  const retriedSymbolSave = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${chart.id}`,
  )
  await modal.getByRole('button', { name: 'Retry save' }).click()
  expect((await retriedSymbolSave).ok()).toBe(true)
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === chart.id)?.config.symbol).toBe('XLB')
  await closeConfig(page)

  const comparison = await addWidget(page, 'Comparison Chart')
  remainingFailures.set(comparison.id, 2)
  await closeConfig(page)
  const comparisonWidget = page.locator('.dashboard-widget').filter({ hasText: 'Comparison Chart' })
  const editComparison = async () => {
    await comparisonWidget.getByRole('button', { name: 'Configure' }).click()
    return page.locator('.config-modal .comparison-config-row .dash-search-input').first()
  }
  search = await editComparison()
  saveResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${comparison.id}`,
  )
  await search.fill('XLB')
  expect((await saveResponse).status()).toBe(503)
  modal = page.locator('.config-modal')
  await expect(modal.getByRole('alert')).toContainText('The previous saved value was restored.')
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === comparison.id)?.config.targets[0].symbol).toBe('SPY')
  await modal.getByRole('button', { name: 'Cancel', exact: true }).click()
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === comparison.id)?.config.targets[0].symbol).toBe('SPY')

  search = page.locator('.config-modal .comparison-config-row .dash-search-input').first()
  saveResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${comparison.id}`,
  )
  await search.fill('XLB')
  expect((await saveResponse).status()).toBe(503)
  modal = page.locator('.config-modal')
  const retriedComparisonSave = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${comparison.id}`,
  )
  await modal.getByRole('button', { name: 'Retry save' }).click()
  expect((await retriedComparisonSave).ok()).toBe(true)
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === comparison.id)?.config.targets[0].symbol).toBe('XLB')
  // The 503 responses above are this test's explicitly asserted controlled failure inputs.
})

test('Dashboard drag and resize failures restore saved layout and recover by retry', async ({ page, loggedIn }) => {
  let failuresRemaining = 1
  await page.route('**/api/v1/dashboards/tabs/*/widgets/layout', async route => {
    if (route.request().method() === 'PATCH' && failuresRemaining > 0) {
      failuresRemaining -= 1
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Controlled dashboard layout failure' }) })
      return
    }
    await route.continue()
  })

  await page.goto('/dashboard')
  const notes = await addWidget(page, 'Notes')
  await closeConfig(page)
  const widget = page.locator('.dashboard-widget').filter({ hasText: 'Notes' })
  const initial = await persistedDashboard(page)
  const initialLayout = initial.tabs.flatMap(tab => tab.widgets).find(item => item.id === notes.id)!.layout

  const dragResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && /\/api\/v1\/dashboards\/tabs\/\d+\/widgets\/layout$/.test(responsePath(response)),
  )
  const header = widget.locator('.widget-header')
  await header.scrollIntoViewIfNeeded()
  const headerBox = await header.boundingBox()
  expect(headerBox).not.toBeNull()
  await page.mouse.move(headerBox!.x + headerBox!.width / 2, headerBox!.y + headerBox!.height / 2)
  await page.mouse.down()
  await page.mouse.move(headerBox!.x + headerBox!.width / 2 + 120, headerBox!.y + headerBox!.height / 2 + 70, { steps: 3 })
  await page.mouse.up()
  expect((await dragResponse).status()).toBe(503)
  const layoutAlert = page.getByRole('alert')
  await expect(layoutAlert).toContainText('The previous saved arrangement was restored.')
  let saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(item => item.id === notes.id)?.layout).toEqual(initialLayout)

  const dragRetry = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && /\/api\/v1\/dashboards\/tabs\/\d+\/widgets\/layout$/.test(responsePath(response)),
  )
  await page.getByRole('button', { name: 'Retry layout save' }).click()
  expect((await dragRetry).ok()).toBe(true)
  const afterDrag = await persistedDashboard(page)
  const draggedLayout = afterDrag.tabs.flatMap(tab => tab.widgets).find(item => item.id === notes.id)!.layout
  expect(draggedLayout).not.toEqual(initialLayout)
  await expect(page.getByRole('alert')).toHaveCount(0)

  failuresRemaining = 1
  const resizeResponse = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && /\/api\/v1\/dashboards\/tabs\/\d+\/widgets\/layout$/.test(responsePath(response)),
  )
  const resize = widget.locator('.resize-handle')
  await resize.scrollIntoViewIfNeeded()
  const resizeBox = await resize.boundingBox()
  expect(resizeBox).not.toBeNull()
  await page.mouse.move(resizeBox!.x + resizeBox!.width / 2, resizeBox!.y + resizeBox!.height / 2)
  await page.mouse.down()
  await page.mouse.move(resizeBox!.x + resizeBox!.width / 2 + 120, resizeBox!.y + resizeBox!.height / 2 + 70, { steps: 3 })
  await page.mouse.up()
  expect((await resizeResponse).status()).toBe(503)
  await expect(page.getByRole('alert')).toContainText('The previous saved arrangement was restored.')
  saved = await persistedDashboard(page)
  expect(saved.tabs.flatMap(tab => tab.widgets).find(item => item.id === notes.id)?.layout).toEqual(draggedLayout)

  const resizeRetry = page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && /\/api\/v1\/dashboards\/tabs\/\d+\/widgets\/layout$/.test(responsePath(response)),
  )
  await page.getByRole('button', { name: 'Retry layout save' }).click()
  expect((await resizeRetry).ok()).toBe(true)
  const afterResize = await persistedDashboard(page)
  const resizedLayout = afterResize.tabs.flatMap(tab => tab.widgets).find(item => item.id === notes.id)!.layout
  expect(resizedLayout.w > draggedLayout.w || resizedLayout.h > draggedLayout.h).toBe(true)
  // The 503 responses above are this test's explicitly asserted controlled failure inputs.
})

test('Dashboard search resolves exact and explicit candidates and ignores a superseded response', async ({ page, loggedIn, browserDiagnostics }) => {
  let releaseOldResponse!: () => void
  const oldResponseGate = new Promise<void>(resolve => { releaseOldResponse = resolve })
  let oldRequestStarted!: () => void
  const oldRequest = new Promise<void>(resolve => { oldRequestStarted = resolve })
  const acquiredSymbols: string[] = []
  const acquiredBindings: Array<{ symbol: string; provider_candidate?: { symbol?: string; provider?: string; exchange?: string } }> = []

  await page.route('**/api/v1/instruments/discover', async route => {
    const body = route.request().postDataJSON() as { query: string; request_id: string }
    const query = body.query.toUpperCase()
    if (query === 'QZX') return returnDiscovery(route, body.request_id, ['QZX'])
    if (query === 'AMB') return returnDiscovery(route, body.request_id, ['AMB-A', 'AMB-B'])
    if (query === 'OLD') {
      oldRequestStarted()
      await oldResponseGate
      return returnDiscovery(route, body.request_id, ['OLD'])
    }
    if (query === 'NEW') return returnDiscovery(route, body.request_id, ['NEW-A', 'NEW-B'])
    return returnDiscoveryUnavailable(route, body.request_id)
  })
  await page.route('**/api/v1/instruments/acquire', async route => {
    const body = route.request().postDataJSON() as { symbol: string; request_id: string; provider_candidate?: { symbol?: string; provider?: string } }
    acquiredSymbols.push(body.symbol)
    acquiredBindings.push(body)
    if (body.provider_candidate) expect(body.provider_candidate.symbol).toBe(body.symbol)
    await returnResolvedAcquire(route, body.request_id, body.symbol)
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as { target: { symbol?: string } }
    const symbol = body.target.symbol ?? 'controlled'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(controlledUnavailablePreparation(`dashboard-search-${symbol}`, body.target, symbol)),
    })
  })

  await page.goto('/dashboard')
  const widget = await addWidget(page, 'Simple Chart')
  const input = () => page.locator('.config-modal .dash-search-input')
  const save = (id: number) => page.waitForResponse(response =>
    response.request().method() === 'PATCH'
      && responsePath(response) === `/api/v1/dashboards/widgets/${id}`,
  )

  let savedChange = save(widget.id)
  await input().fill('QZX')
  expect((await savedChange).ok()).toBe(true)
  expect(acquiredSymbols).toContain('QZX')
  expect(acquiredBindings.find(binding => binding.symbol === 'QZX')?.provider_candidate).toMatchObject({
    symbol: 'QZX',
    provider: 'dashboard-journey-fixture',
    exchange: 'XNAS',
  })
  let current = await persistedDashboard(page)
  expect(current.tabs.flatMap(tab => tab.widgets).find(item => item.id === widget.id)?.config.symbol).toBe('QZX')

  savedChange = save(widget.id)
  const acquiredBeforeAmbiguous = acquiredSymbols.length
  await input().fill('AMB')
  await expect(page.getByRole('button', { name: /AMB-A/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /AMB-B/ })).toBeVisible()
  expect(acquiredSymbols).toHaveLength(acquiredBeforeAmbiguous)
  await page.getByRole('button', { name: /AMB-B/ }).click()
  expect((await savedChange).ok()).toBe(true)
  expect(acquiredSymbols.at(-1)).toBe('AMB-B')

  try {
    const acquiredBeforeOld = acquiredSymbols.length
    await input().fill('OLD')
    await oldRequest
    savedChange = save(widget.id)
    await input().fill('NEW')
    await expect(page.getByRole('button', { name: /NEW-B/ })).toBeVisible()
    await page.getByRole('button', { name: /NEW-B/ }).click()
    expect((await savedChange).ok()).toBe(true)
    releaseOldResponse()
    await expect.poll(() => acquiredSymbols.length).toBe(acquiredBeforeOld + 1)
    current = await persistedDashboard(page)
    expect(current.tabs.flatMap(tab => tab.widgets).find(item => item.id === widget.id)?.config.symbol).toBe('NEW-B')
    expect(acquiredSymbols).not.toContain('OLD')
  } finally {
    releaseOldResponse()
  }

  await browserDiagnostics.expectNoCriticalIssues()
  // Discovery/acquire and the resulting history-unavailable response are controlled transition fixtures;
  // this journey does not claim genuine source discovery or history acquisition.
})

test('Dashboard Advanced Chart and Instrument Details stay useful on cached data while each preparation is pending and after reload', async ({ page, loggedIn, browserDiagnostics }) => {
  test.setTimeout(180_000)
  const spyGate = deferredGate()
  const xlbGate = deferredGate()
  const releasedSymbols = new Set<string>()
  const heldRequests = new Set<Request>()
  const completedRequests = new Set<Request>()
  let markSpyEnsureStarted!: () => void
  let markXlbEnsureStarted!: () => void
  const spyEnsureStarted = new Promise<void>(resolve => { markSpyEnsureStarted = resolve })
  const xlbEnsureStarted = new Promise<void>(resolve => { markXlbEnsureStarted = resolve })

  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as {
      target?: { kind?: string; symbol?: string }
      datasets?: string[]
      timeframe?: string
    }
    const symbol = body.target?.symbol?.toUpperCase()
    if (body.target?.kind === 'instrument' && body.timeframe === 'D1'
      && body.datasets?.includes('history') && symbol === 'SPY' && !releasedSymbols.has(symbol)) {
      heldRequests.add(route.request())
      markSpyEnsureStarted()
      await spyGate.promise
    } else if (body.target?.kind === 'instrument' && body.timeframe === 'D1'
      && body.datasets?.includes('history') && symbol === 'XLB' && !releasedSymbols.has(symbol)) {
      heldRequests.add(route.request())
      markXlbEnsureStarted()
      await xlbGate.promise
    }
    await route.continue()
  })
  page.on('response', response => {
    if (response.request().method() !== 'POST' || responsePath(response) !== '/api/v1/data/ensure') return
    completedRequests.add(response.request())
  })

  try {
    await page.goto('/dashboard')
    await expect(page.locator('.dashboard-view')).toBeVisible()

    const spyBars = localDailyBarsResponse(page, 'SPY', 500)
    const spyEnsureResponse = page.waitForResponse(response =>
      response.request().method() === 'POST' && responsePath(response) === '/api/v1/data/ensure'
      && (response.request().postDataJSON() as { target?: { symbol?: string }; datasets?: string[] }).target?.symbol?.toUpperCase() === 'SPY'
      && (response.request().postDataJSON() as { datasets?: string[] }).datasets?.includes('history') === true,
      { timeout: 20_000 },
    )
    const advancedRecord = await addWidget(page, 'Advanced Chart')
    await closeConfig(page)
    await spyEnsureStarted

    const actualSpyBars = await assertUsefulBars(await spyBars, 50)
    const advanced = page.locator('.dashboard-widget').filter({ has: page.locator('.advanced-chart-widget') })
    await expect(advanced).toHaveCount(1)
    await expect(advanced.locator('.advanced-chart-widget .chart-root')).toBeVisible()
    await expectAdvancedCandlesPainted(advanced)
    expect(actualSpyBars.at(-1)?.close).toBeGreaterThan(0)
    const heldSpyRequests = [...heldRequests].filter(request =>
      (request.postDataJSON() as { target?: { symbol?: string } }).target?.symbol?.toUpperCase() === 'SPY',
    )
    expect(heldSpyRequests.length).toBeGreaterThan(0)
    expect(heldSpyRequests.some(request => completedRequests.has(request))).toBe(false)

    releasedSymbols.add('SPY')
    spyGate.release()
    const spyPreparation = await spyEnsureResponse
    expect(spyPreparation.ok()).toBe(true)
    expect(heldRequests.has(spyPreparation.request())).toBe(true)
    expect(completedRequests.has(spyPreparation.request())).toBe(true)
    expect((spyPreparation.request().postDataJSON() as { target?: unknown; datasets?: string[]; timeframe?: string })).toMatchObject({
      target: { kind: 'instrument', symbol: 'SPY' },
      timeframe: 'D1',
    })
    expect((spyPreparation.request().postDataJSON() as { datasets?: string[] }).datasets)
      .toEqual(expect.arrayContaining(['profile', 'history']))

    const detailsRecord = await addWidget(page, 'Instrument Details')
    const detailsSearch = page.locator('.config-modal .dash-search-input')
    const detailsSave = page.waitForResponse(response =>
      response.request().method() === 'PATCH'
        && responsePath(response) === `/api/v1/dashboards/widgets/${detailsRecord.id}`,
    )
    const xlbProfile = instrumentProfileResponse(page, 'XLB')
    const xlbBars = dailyBarsResponse(page, 'XLB', 260)
    const xlbEnsureResponse = page.waitForResponse(response =>
      response.request().method() === 'POST' && responsePath(response) === '/api/v1/data/ensure'
      && (response.request().postDataJSON() as { target?: { symbol?: string }; datasets?: string[] }).target?.symbol?.toUpperCase() === 'XLB'
      && (response.request().postDataJSON() as { datasets?: string[] }).datasets?.includes('history') === true,
      { timeout: 20_000 },
    )
    await detailsSearch.fill('XLB')
    expect((await detailsSave).ok()).toBe(true)
    await xlbEnsureStarted
    await closeConfig(page)

    const actualXlbProfile = await xlbProfile
    await assertUsefulBars(await xlbBars, 50)
    const details = page.locator('.dashboard-widget').filter({ has: page.locator('.details-widget') })
    await expect(details).toHaveCount(1)
    await expectUsefulInstrumentDetails(details, actualXlbProfile, 'XLB')
    const heldXlbRequests = [...heldRequests].filter(request =>
      (request.postDataJSON() as { target?: { symbol?: string } }).target?.symbol?.toUpperCase() === 'XLB',
    )
    expect(heldXlbRequests.length).toBeGreaterThan(0)
    expect(heldXlbRequests.some(request => completedRequests.has(request))).toBe(false)

    releasedSymbols.add('XLB')
    xlbGate.release()
    const xlbPreparation = await xlbEnsureResponse
    expect(xlbPreparation.ok()).toBe(true)
    expect(heldRequests.has(xlbPreparation.request())).toBe(true)
    expect(completedRequests.has(xlbPreparation.request())).toBe(true)
    expect((xlbPreparation.request().postDataJSON() as { target?: unknown; datasets?: string[]; timeframe?: string })).toMatchObject({
      target: { kind: 'instrument', symbol: 'XLB' },
      timeframe: 'D1',
    })
    expect((xlbPreparation.request().postDataJSON() as { datasets?: string[] }).datasets)
      .toEqual(expect.arrayContaining(['profile', 'history']))

    const beforeReload = await persistedDashboard(page)
    expect(beforeReload.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === advancedRecord.id)).toMatchObject({
      widget_type: 'advanced_chart',
      config: { symbol: 'SPY', timeframe: 'D1', chartType: 'candles' },
    })
    expect(beforeReload.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === detailsRecord.id)).toMatchObject({
      widget_type: 'instrument_details',
      config: { symbol: 'XLB', timeframe: 'D1' },
    })

    const restoredSpyBars = localDailyBarsResponse(page, 'SPY', 500)
    const restoredXlbProfile = instrumentProfileResponse(page, 'XLB')
    const restoredXlbBars = dailyBarsResponse(page, 'XLB', 260)
    await page.reload()
    await expect(page.locator('.dashboard-view')).toBeVisible()
    const restoredAdvanced = page.locator('.dashboard-widget').filter({ has: page.locator('.advanced-chart-widget') })
    const restoredDetails = page.locator('.dashboard-widget').filter({ has: page.locator('.details-widget') })
    await expect(restoredAdvanced).toHaveCount(1)
    await expect(restoredDetails).toHaveCount(1)
    await assertUsefulBars(await restoredSpyBars, 50)
    await expectAdvancedCandlesPainted(restoredAdvanced)
    await assertUsefulBars(await restoredXlbBars, 50)
    await expectUsefulInstrumentDetails(restoredDetails, await restoredXlbProfile, 'XLB')
    const afterReload = await persistedDashboard(page)
    expect(afterReload.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === advancedRecord.id)?.config)
      .toMatchObject({ symbol: 'SPY', timeframe: 'D1', chartType: 'candles' })
    expect(afterReload.tabs.flatMap(tab => tab.widgets).find(widget => widget.id === detailsRecord.id)?.config)
      .toMatchObject({ symbol: 'XLB', timeframe: 'D1' })
    await browserDiagnostics.expectNoCriticalIssues()
    // Only POST /data/ensure is held. Instrument profiles and OHLCV responses above are real backend reads;
    // no profile/history response or provider outcome is fabricated by this journey.
  } finally {
    releasedSymbols.add('SPY')
    releasedSymbols.add('XLB')
    spyGate.release()
    xlbGate.release()
  }
})
