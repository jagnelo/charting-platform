import { expect, test } from './helpers'

type SearchCandidate = {
  symbol: string
  name: string
  instrument_id: number
}

async function chooseResolvedInstrument(page: import('@playwright/test').Page, symbol: string) {
  const input = page.getByPlaceholder('Add instrument')
  const responsePromise = page.waitForResponse(response => {
    const url = new URL(response.url())
    return url.pathname === '/api/v1/instruments/search' && url.searchParams.get('q')?.toUpperCase() === symbol
  })
  await input.fill(symbol)
  const response = await responsePromise
  expect(response.ok(), `Search API should resolve ${symbol}`).toBeTruthy()
  const candidates = await response.json() as SearchCandidate[]
  const canonical = candidates.find(candidate => candidate.symbol.toUpperCase() === symbol)
  expect(canonical, `Search API should return a canonical ${symbol} instrument`).toBeTruthy()
  expect(Number.isSafeInteger(canonical?.instrument_id) && (canonical?.instrument_id ?? 0) > 0).toBeTruthy()
  await page.getByRole('option', { name: new RegExp(`^${symbol}\\s`) }).click()
  return canonical!
}

test('ordinary basket lifecycle uses resolved instruments, persists edits, and opens the dashboard context', async ({
  page,
  request,
  loggedIn,
}) => {
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const headers = { Authorization: `Bearer ${token}` }
  const createdIds: number[] = []
  await page.goto('/legacy/baskets')
  await expect(page.getByRole('heading', { name: 'Baskets' })).toBeVisible()

  try {
    await page.getByRole('button', { name: '+ New' }).click()
    await page.getByPlaceholder('Basket name').fill(`Lifecycle A ${Date.now()}`)
    await page.locator('select.form-select').selectOption('custom')
    const aapl = await chooseResolvedInstrument(page, 'AAPL')
    const msft = await chooseResolvedInstrument(page, 'MSFT')
    await page.locator('input.weight-input').nth(0).fill('60')
    await page.locator('input.weight-input').nth(1).fill('40')

    const createA = page.waitForResponse(response =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/baskets')
    await page.getByRole('button', { name: 'Create' }).click()
    const createAResponse = await createA
    expect(createAResponse.status()).toBe(200)
    const basketA = await createAResponse.json() as { id: number; members: Array<{ instrument_id: number }> }
    createdIds.push(basketA.id)
    expect(basketA.members.map(member => member.instrument_id)).toEqual([aapl.instrument_id, msft.instrument_id])
    await expect(page.getByText('Basket saved.')).toBeVisible()

    await page.getByRole('button', { name: '+ New' }).click()
    const basketBName = `Lifecycle B ${Date.now()}`
    await page.getByPlaceholder('Basket name').fill(basketBName)
    const nvda = await chooseResolvedInstrument(page, 'NVDA')
    const createB = page.waitForResponse(response =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/baskets')
    await page.getByRole('button', { name: 'Create' }).click()
    const createBResponse = await createB
    expect(createBResponse.status()).toBe(200)
    const basketB = await createBResponse.json() as { id: number; members: Array<{ instrument_id: number }> }
    createdIds.push(basketB.id)
    expect(basketB.members.map(member => member.instrument_id)).toEqual([nvda.instrument_id])

    const basketACard = page.locator('.basket-card').filter({ hasText: /Lifecycle A/ })
    await page.getByPlaceholder('Basket name').fill('Unsaved lifecycle edit')
    await basketACard.click()
    await expect(page.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeVisible()
    await page.getByRole('button', { name: 'Keep editing' }).click()
    await expect(page.getByPlaceholder('Basket name')).toHaveValue('Unsaved lifecycle edit')
    await basketACard.click()
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByPlaceholder('Basket name')).toHaveValue(/Lifecycle A/)

    await page.locator('.basket-card').filter({ hasText: basketBName }).click()
    await page.getByRole('button', { name: `Remove ${nvda.symbol}` }).click()
    const added = await chooseResolvedInstrument(page, 'MSFT')
    const updateB = page.waitForResponse(response =>
      response.request().method() === 'PATCH' && new URL(response.url()).pathname === `/api/v1/baskets/${basketB.id}`)
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    const updateBResponse = await updateB
    expect(updateBResponse.status()).toBe(200)
    const updatedB = await updateBResponse.json() as { members: Array<{ instrument_id: number }> }
    expect(updatedB.members.map(member => member.instrument_id)).toEqual([added.instrument_id])

    await page.reload()
    await page.locator('.basket-card').filter({ hasText: basketBName }).click()
    await expect(page.locator('.member-row').filter({ hasText: 'MSFT' })).toBeVisible()
    await expect(page.locator('.member-row').filter({ hasText: 'NVDA' })).toHaveCount(0)

    const ensureCalls: Array<{ instrument_id: number; datasets: string[]; timeframe: string }> = []
    page.on('request', requestEvent => {
      if (requestEvent.method() !== 'POST' || new URL(requestEvent.url()).pathname !== '/api/v1/data/ensure') return
      const body = requestEvent.postDataJSON() as { target?: { instrument_id?: number }; datasets?: string[]; timeframe?: string }
      if (body.target?.instrument_id) ensureCalls.push({
        instrument_id: body.target.instrument_id,
        datasets: body.datasets ?? [],
        timeframe: body.timeframe ?? '',
      })
    })
    await page.locator('.basket-card').filter({ hasText: /Lifecycle A/ }).click()
    const selectedA = await request.get(`/api/v1/baskets/${basketA.id}`, { headers })
    expect(selectedA.status()).toBe(200)
    const selectedABody = await selectedA.json() as { members: Array<{ instrument_id: number }> }
    const basketChartRequest = page.waitForResponse(response =>
      new URL(response.url()).pathname.startsWith(`/api/v1/baskets/${basketA.id}/ohlcv/`))
    const ensureResponse = page.waitForResponse(response =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/data/ensure')
    await page.getByTestId('basket-open-chart').click()
    const prepared = await ensureResponse
    expect(prepared.ok()).toBeTruthy()
    await expect.poll(() => ensureCalls.length).toBe(selectedABody.members.length)
    expect(ensureCalls).toEqual(selectedABody.members.map(member => ({
      instrument_id: member.instrument_id,
      datasets: ['history'],
      timeframe: 'D1',
    })))
    await expect(page).toHaveURL(new RegExp(`/chart/BASKET%3A${basketA.id}$`), { timeout: 30_000 })
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    const basketChartResponse = await basketChartRequest
    expect(basketChartResponse.status()).toBe(200)
    const syntheticBars = await basketChartResponse.json() as Array<{ timestamp: string; close: number }>
    expect(syntheticBars.length).toBeGreaterThan(0)
    expect(syntheticBars.every(bar => Number.isFinite(bar.close))).toBeTruthy()

    await page.goto('/legacy/baskets')
    await page.locator('.basket-card').filter({ hasText: basketBName }).click()
    await page.getByRole('button', { name: 'Delete' }).click()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.locator('.basket-card').filter({ hasText: basketBName })).toBeVisible()

    await page.getByRole('button', { name: 'Delete' }).click()
    const deleteB = page.waitForResponse(response =>
      response.request().method() === 'DELETE' && new URL(response.url()).pathname === `/api/v1/baskets/${basketB.id}`)
    await page.getByRole('dialog', { name: 'Delete basket?' }).getByRole('button', { name: 'Delete' }).click()
    expect((await deleteB).status()).toBe(204)
    await expect(page.locator('.basket-card').filter({ hasText: basketBName })).toHaveCount(0)
    await expect(page.getByPlaceholder('Basket name')).toHaveValue(/Lifecycle A/)
  } finally {
    for (const basketId of createdIds) {
      await request.delete(`/api/v1/baskets/${basketId}`, { headers }).catch(() => undefined)
    }
  }

  expect(loggedIn).toBeUndefined()
})

test('existing issuer snapshot basket displays read-only source lineage from basket APIs', async ({ page, loggedIn }) => {
  const basketResponsePromise = page.waitForResponse(response =>
    response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/v1/baskets')
  await page.goto('/legacy/baskets')
  const basketResponse = await basketResponsePromise
  expect(basketResponse.ok()).toBeTruthy()
  const baskets = await basketResponse.json() as Array<{
    id: number
    name: string
    is_system_managed: boolean
    source_snapshot_id: number | null
    composition_date: string | null
    metadata?: Record<string, unknown>
  }>
  const sourceBasket = baskets.find(basket => basket.is_system_managed && basket.source_snapshot_id)
  expect(sourceBasket, 'combined fixture must include an existing issuer snapshot basket').toBeTruthy()
  expect(sourceBasket?.composition_date).toBeTruthy()
  expect(sourceBasket?.metadata?.source_provider).toBeTruthy()
  expect(sourceBasket?.metadata?.provenance).toBeTruthy()
  expect(sourceBasket?.metadata?.known_at).toBeTruthy()
  expect(sourceBasket?.metadata?.source_identifier).toBeTruthy()
  expect(sourceBasket?.metadata?.source_url).toBeTruthy()
  expect(sourceBasket?.metadata?.snapshot_hash).toBeTruthy()
  expect(sourceBasket?.metadata?.source_artifact_hash).toBeTruthy()
  await page.locator('.basket-card').filter({ hasText: sourceBasket!.name }).click()
  const provenance = page.getByTestId('basket-source-provenance')
  await expect(provenance).toBeVisible()
  await expect(provenance).toContainText(sourceBasket?.composition_date ?? '')
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.source_provider ?? ''))
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.provenance ?? ''))
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.source_identifier ?? ''))
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.source_artifact_hash ?? ''))
  await expect(page.getByTestId('basket-snapshot-history')).toContainText(String(sourceBasket?.metadata?.known_at ?? ''))
  await expect(page.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()
  expect(loggedIn).toBeUndefined()
})
