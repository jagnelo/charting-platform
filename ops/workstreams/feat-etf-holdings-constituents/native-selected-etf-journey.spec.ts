import { expect, test } from '../../../frontend/tests/e2e/helpers'
import type { APIRequestContext, Page, Request } from '@playwright/test'

type Listing = { instrument_id: number; symbol: string; name: string }
type Bar = { ts: string; open: number; high: number; low: number; close: number }
type Holding = {
  id: number; snapshot_id: number; constituent_instrument_id: number | null
  constituent_symbol: string | null; reported_symbol: string | null; constituent_name: string | null
  holding_type: string; row_type: string; is_resolved: boolean; source_row_id?: string | null
  extra_data?: Record<string, unknown> | null
}
type Snapshot = {
  id: number; etf_profile_id: number; etf_instrument_id: number; etf_symbol: string
  composition_date: string; known_at: string | null; provenance: string; source_provider: string
  source_identifier: string | null; source_quality: string; completeness_status: string
  row_count: number; resolved_count: number; unresolved_count: number
}
type Preparation = { symbol: string; requestId: string; httpStatus: number; status: string; datasets: string[] }
type FundEvidence = { symbol: string; instrumentId: number; snapshotId: number; compositionDate: string; knownAt: string | null; provenance: string; sourceProvider: string; sourceIdentifier: string | null; completeness: string; rowCount: number }

async function json<T>(request: APIRequestContext, path: string, token: string, params?: Record<string, string | number>): Promise<T> {
  const response = await request.get(path, { headers: { Authorization: `Bearer ${token}` }, ...(params ? { params } : {}) })
  expect(response.status(), `Authenticated read ${path} should succeed`).toBe(200)
  return await response.json() as T
}

function selectedEnsure(request: Request, symbol: string, instrumentId: number): boolean {
  if (request.method() !== 'POST' || new URL(request.url()).pathname !== '/api/v1/data/ensure') return false
  try {
    const body = request.postDataJSON() as { target?: { kind?: string; symbol?: string; instrument_id?: number }; datasets?: string[] }
    return body.target?.kind === 'instrument'
      && (body.target.symbol?.toUpperCase() === symbol || body.target.instrument_id === instrumentId)
      && (body.datasets ?? []).some(dataset => ['history', 'holdings'].includes(dataset))
  } catch { return false }
}

async function chooseETF(page: Page, symbol: string): Promise<{ listing: Listing; preparation: Preparation }> {
  const input = page.getByRole('combobox', { name: 'Active symbol' })
  const searchPromise = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/instruments/search' && url.searchParams.get('q')?.toUpperCase() === symbol
  })
  await input.fill(symbol)
  const search = await searchPromise
  expect(search.status(), `Canonical search for ${symbol}`).toBe(200)
  const exact = (await search.json() as Listing[]).filter(row => row.symbol.toUpperCase() === symbol)
  expect(exact, `One exact ${symbol} listing should be selectable`).toHaveLength(1)
  const listing = exact[0]!
  const ensureRequest = page.waitForRequest(request => selectedEnsure(request, symbol, listing.instrument_id))
  await page.getByRole('option', { name: new RegExp(`^${symbol}\\b`) }).click()
  await expect(input).toHaveValue(symbol)
  const request = await ensureRequest
  const response = await page.waitForResponse(item => item.request() === request)
  expect(response.status(), `${symbol} automatic preparation should be accepted`).toBe(200)
  const body = await response.json() as { request_id?: string; status?: string; dependencies?: Array<{ dataset?: string }> }
  expect(body.request_id).toBeTruthy()
  expect(body.status).toBeTruthy()
  expect(['held', 'failed', 'unavailable', 'blocked']).not.toContain(body.status)
  const datasets = (body.dependencies ?? []).map(item => item.dataset ?? '').filter(Boolean)
  expect(datasets.some(dataset => ['history', 'holdings'].includes(dataset))).toBeTruthy()
  return { listing, preparation: { symbol, requestId: body.request_id!, httpStatus: response.status(), status: body.status!, datasets } }
}

async function reselectKnownETF(page: Page, listing: Listing): Promise<Preparation> {
  const input = page.getByRole('combobox', { name: 'Active symbol' })
  const ensureRequest = page.waitForRequest(request => selectedEnsure(request, listing.symbol, listing.instrument_id))
  await input.fill(listing.symbol)
  const option = page.getByRole('option', { name: new RegExp(`^${listing.symbol}\\b`) })
  await expect(option).toBeVisible()
  await option.click()
  await expect(input).toHaveValue(listing.symbol)
  const request = await ensureRequest
  const response = await page.waitForResponse(item => item.request() === request)
  expect(response.status(), `${listing.symbol} re-selection preparation should be accepted`).toBe(200)
  const body = await response.json() as { request_id?: string; status?: string; dependencies?: Array<{ dataset?: string }> }
  expect(body.request_id).toBeTruthy()
  expect(body.status).toBeTruthy()
  expect(['held', 'failed', 'unavailable', 'blocked']).not.toContain(body.status)
  const datasets = (body.dependencies ?? []).map(item => item.dataset ?? '').filter(Boolean)
  expect(datasets.some(dataset => ['history', 'holdings'].includes(dataset))).toBeTruthy()
  return { symbol: listing.symbol, requestId: body.request_id!, httpStatus: response.status(), status: body.status!, datasets }
}

async function assertSelectedBars(page: Page, request: APIRequestContext, symbol: string, token: string): Promise<Bar[]> {
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(symbol)
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/ohlcv/local/${symbol}/D1`, {
      headers: { Authorization: `Bearer ${token}` }, params: { limit: 500, adjusted: 'true' },
    })
    return response.status() === 200 ? (await response.json() as Bar[]).length : 0
  }, { message: `${symbol} should have persisted daily bars`, timeout: 60_000 }).toBeGreaterThan(1)
  const bars = await json<Bar[]>(request, `/api/v1/ohlcv/local/${symbol}/D1`, token, { limit: 500, adjusted: 'true' })
  expect(bars.every(bar => Number.isFinite(Date.parse(bar.ts)) && [bar.open, bar.high, bar.low, bar.close].every(Number.isFinite))).toBeTruthy()

  const chart = page.getByRole('region', { name: 'Chart workspace' }).first()
  await expect(chart).toHaveAttribute('aria-busy', 'false')
  const plot = chart.locator('.uplot').first()
  await expect(plot).toBeVisible()
  await expect.poll(() => plot.locator('canvas:not(.drawing-canvas)').first().evaluate(canvas => {
    const element = canvas as HTMLCanvasElement
    if (element.width < 2 || element.height < 2) return 0
    const data = element.getContext('2d')?.getImageData(0, 0, element.width, element.height).data
    if (!data) return 0
    const colors = new Set<string>()
    let painted = 0
    for (let y = Math.floor(element.height * 0.05); y < element.height * 0.95; y += 1) {
      for (let x = Math.floor(element.width * 0.1); x < element.width * 0.98; x += 1) {
        const i = (y * element.width + x) * 4
        if (data[i + 3] === 0) continue
        painted += 1
        colors.add(`${data[i]},${data[i + 1]},${data[i + 2]}`)
      }
    }
    return colors.size >= 3 ? painted : 0
  }), { message: `${symbol} actual price series should paint the chart`, timeout: 15_000 }).toBeGreaterThan(10)
  const box = await plot.boundingBox()
  expect(box && box.width > 100 && box.height > 80).toBeTruthy()
  await page.mouse.move(box!.x + box!.width * 0.62, box!.y + box!.height * 0.48)
  const tooltip = chart.locator('.ohlcv-info')
  await expect(tooltip).toBeVisible()
  const close = (await tooltip.locator('.tt-item').filter({ hasText: /^C\s/ }).innerText()).replace(/^C\s*/, '').trim()
  const bar = bars.find(item => item.close.toFixed(4) === close)
  expect(bar, `${symbol} tooltip close should match a persisted selected-symbol bar`).toBeTruthy()
  const date = await page.evaluate(ts => {
    const value = new Date(ts)
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
  }, bar!.ts)
  await expect(tooltip.locator('.tt-date')).toHaveText(date)
  return bars
}

async function currentHoldings(request: APIRequestContext, symbol: string, instrumentId: number, token: string) {
  await expect.poll(async () => (await request.get(`/api/v1/etf-holdings/${symbol}/latest`, {
    headers: { Authorization: `Bearer ${token}` },
  })).status(), { message: `${symbol} selection should expose a real current holdings snapshot`, timeout: 45_000 }).toBe(200)
  const profiles = await json<Array<{
    id: number; instrument_id: number; symbol: string; latest_snapshot_id: number | null
    holdings_capability?: { availability: string; identity_verified: boolean; usable_for_current_analysis: boolean }
  }>>(request, '/api/v1/etf-holdings', token, { q: symbol })
  const profile = profiles.filter(item => item.symbol.toUpperCase() === symbol)
  expect(profile).toHaveLength(1)
  expect(profile[0]!.instrument_id).toBe(instrumentId)
  expect(profile[0]!.holdings_capability?.availability).toBe('current')
  expect(profile[0]!.holdings_capability?.identity_verified).toBe(true)
  expect(profile[0]!.holdings_capability?.usable_for_current_analysis).toBe(true)

  const snapshot = await json<Snapshot>(request, `/api/v1/etf-holdings/${symbol}/latest`, token)
  expect(snapshot.etf_symbol.toUpperCase()).toBe(symbol)
  expect(snapshot.etf_instrument_id).toBe(instrumentId)
  expect(snapshot.etf_profile_id).toBe(profile[0]!.id)
  expect(profile[0]!.latest_snapshot_id).toBe(snapshot.id)
  expect(snapshot.completeness_status).toBe('complete')
  expect(snapshot.row_count).toBeGreaterThan(0)
  expect(snapshot.composition_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(snapshot.known_at && snapshot.provenance.trim() && snapshot.source_provider.trim() && snapshot.source_quality.trim()).toBeTruthy()
  const page = await json<{ snapshot: Snapshot; holdings: Holding[]; total: number }>(
    request, `/api/v1/etf-holdings/${symbol}/holdings`, token, { snapshot_id: snapshot.id, limit: 500 },
  )
  expect(page.snapshot.id).toBe(snapshot.id)
  expect(page.total).toBe(snapshot.row_count)
  expect(page.holdings.length).toBeGreaterThan(0)
  expect(page.holdings.every(row => row.snapshot_id === snapshot.id)).toBeTruthy()
  return { snapshot, holdings: page.holdings }
}

async function selectVisibleResolvedHolding(page: Page, holdings: Holding[]) {
  const resolved = new Map(holdings.filter(row => {
    const type = row.holding_type.trim().toLowerCase().replace(/[\s_-]+/g, '')
    const equityTypes = new Set(['equity', 'stock', 'commonstock', 'commonshares', 'ordinaryshares', 'realestateinvestmenttrust'])
    return row.is_resolved && (row.constituent_instrument_id ?? 0) > 0 && row.constituent_symbol
      && row.row_type.trim().toLowerCase() === 'security' && equityTypes.has(type)
      && !/^holding-/i.test(row.reported_symbol ?? '')
      && row.extra_data?.is_synthetic !== true && row.extra_data?.synthetic !== true
      && row.extra_data?.is_reference !== true && row.extra_data?.reference !== true
  }).map(row => [row.constituent_symbol!.toUpperCase(), row] as const))
  expect(resolved.size, 'The selected snapshot needs a resolved equity holding').toBeGreaterThan(0)
  const rows = page.locator('.constituent-tool').getByRole('option')
  await expect.poll(() => rows.count(), { message: 'Current reported holdings should render in Workstation', timeout: 30_000 }).toBeGreaterThan(0)
  const count = await rows.count()
  let holding: Holding | undefined
  for (let index = 0; index < count; index += 1) {
    const symbol = (await rows.nth(index).getAttribute('aria-label'))?.trim().split(/\s+/, 1)[0]?.toUpperCase()
    if (symbol) holding = resolved.get(symbol)
    if (holding) break
  }
  expect(holding, 'A visible Workstation row must be a resolved equity in this snapshot').toBeTruthy()
  await page.locator('.constituent-tool').getByRole('option', {
    name: new RegExp(`^${holding!.constituent_symbol!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s`),
  }).click()
  return holding!
}

test('genuine BWET to XHB to IGV selection retains current holdings provenance on Workstation', async ({
  page, request, loggedIn, browserDiagnostics,
}, testInfo) => {
  test.setTimeout(180_000)
  expect(loggedIn).toBeUndefined()
  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const evidence: Preparation[] = []
  const fundEvidence: FundEvidence[] = []
  let igv: Awaited<ReturnType<typeof currentHoldings>> | null = null
  let igvListing: Listing | null = null

  for (const symbol of ['BWET', 'XHB', 'IGV']) {
    const { listing, preparation } = await chooseETF(page, symbol)
    evidence.push(preparation)
    await assertSelectedBars(page, request, symbol, token!)
    const fund = await currentHoldings(request, symbol, listing.instrument_id, token!)
    fundEvidence.push({
      symbol, instrumentId: listing.instrument_id, snapshotId: fund.snapshot.id,
      compositionDate: fund.snapshot.composition_date, knownAt: fund.snapshot.known_at,
      provenance: fund.snapshot.provenance, sourceProvider: fund.snapshot.source_provider,
      sourceIdentifier: fund.snapshot.source_identifier, completeness: fund.snapshot.completeness_status,
      rowCount: fund.snapshot.row_count,
    })
    const rows = page.locator('.constituent-tool').getByRole('option')
    await expect.poll(async () => {
      const labels = await rows.evaluateAll(items => items.map(item => item.getAttribute('aria-label') ?? ''))
      return labels.length > 0 && labels.every(label => fund.holdings.some(row =>
        (row.constituent_symbol ?? row.reported_symbol) && label.startsWith(`${row.constituent_symbol ?? row.reported_symbol} `)))
    }, { message: `${symbol} rows must switch to its own dated snapshot`, timeout: 30_000 }).toBeTruthy()
    if (symbol !== 'BWET') await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
    if (symbol === 'BWET') {
      const row = await selectVisibleResolvedHolding(page, fund.holdings)
      const lineage = page.getByTestId('active-holding-lineage')
      await expect(lineage).toContainText(`from BWET holdings · ${fund.snapshot.composition_date}`)
      await expect(lineage).toHaveAttribute('aria-label', expect.stringContaining(`snapshot ${fund.snapshot.id}`))
      await expect(page).toHaveURL(/\/chart(?:\/|[?#]|$)/)
      await expect(page).not.toHaveURL(/\/legacy\/chart/)
      await assertSelectedBars(page, request, row.constituent_symbol!, token!)
    }
    if (symbol === 'IGV') {
      igv = fund
      igvListing = listing
    }
  }

  expect(igv).toBeTruthy()
  const row = await selectVisibleResolvedHolding(page, igv!.holdings)
  const lineage = page.getByTestId('active-holding-lineage')
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(row.constituent_symbol!)
  await expect(page).toHaveURL(/\/chart(?:\/|[?#]|$)/)
  await expect(page).not.toHaveURL(/\/legacy\/chart/)
  await expect(lineage).toContainText('from IGV holdings')
  const details = await lineage.getAttribute('aria-label')
  for (const proof of [`snapshot ${igv!.snapshot.id}`, `row ${row.id}`, `instrument ${row.constituent_instrument_id}`,
    `composition ${igv!.snapshot.composition_date}`, `known ${igv!.snapshot.known_at}`,
    `${igv!.snapshot.source_provider} / ${igv!.snapshot.provenance}`]) expect(details).toContain(proof)
  if (row.reported_symbol) expect(details).toContain(`reported ${row.reported_symbol}`)
  if (row.source_row_id) expect(details).toContain(`source row ${row.source_row_id}`)
  await assertSelectedBars(page, request, row.constituent_symbol!, token!)
  await page.screenshot({ path: testInfo.outputPath('native-selected-igv-holding.png') })

  expect(igvListing).toBeTruthy()
  const reopenPreparation = await reselectKnownETF(page, igvListing!)
  expect(reopenPreparation.httpStatus).toBe(200)
  await assertSelectedBars(page, request, 'IGV', token!)
  const reopenedFund = await currentHoldings(request, 'IGV', igvListing!.instrument_id, token!)
  expect(reopenedFund.snapshot.id).toBe(igv!.snapshot.id)
  await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)

  await page.reload()
  await expect(page.locator('.workspace-layout-host')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('IGV')
  await expect(page.getByTestId('active-holding-lineage')).toHaveCount(0)
  await assertSelectedBars(page, request, 'IGV', token!)
  const reloadedFund = await currentHoldings(request, 'IGV', igvListing!.instrument_id, token!)
  expect(reloadedFund.snapshot.id).toBe(igv!.snapshot.id)

  expect(evidence.map(item => item.symbol)).toEqual(['BWET', 'XHB', 'IGV'])
  expect(evidence.every(item => item.httpStatus === 200 && item.requestId && item.status)).toBeTruthy()
  await testInfo.attach('native-selection-public-evidence.json', {
    body: Buffer.from(JSON.stringify({ preparations: evidence, funds: fundEvidence, drilldown: {
      symbol: row.constituent_symbol, rowId: row.id, instrumentId: row.constituent_instrument_id,
      parentSnapshotId: igv!.snapshot.id,
    } }, null, 2)),
    contentType: 'application/json',
  })
  await browserDiagnostics.expectNoCriticalIssues()
})
