import { expect, test } from './helpers'

type SearchCandidate = {
  symbol: string
  name: string
  instrument_id: number
}

async function resolveCanonicalInstrument(
  request: import('@playwright/test').APIRequestContext,
  headers: Record<string, string>,
  symbol: string,
): Promise<SearchCandidate> {
  const response = await request.get('/api/v1/instruments/search', {
    headers,
    params: { q: symbol, canonical_only: 'true' },
  })
  expect(response.ok(), `Search API should resolve ${symbol}`).toBeTruthy()
  const candidates = await response.json() as SearchCandidate[]
  const exact = candidates.filter(candidate => candidate.symbol.toUpperCase() === symbol)
  expect(exact, `Search API should return one canonical ${symbol} instrument`).toHaveLength(1)
  expect(Number.isSafeInteger(exact[0]?.instrument_id) && (exact[0]?.instrument_id ?? 0) > 0).toBeTruthy()
  return exact[0]
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

test('ordinary basket lifecycle persists edits across save, reload, member-chart navigation, cancel and delete', async ({
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
    const amzn = await chooseResolvedInstrument(page, 'AMZN')
    const createB = page.waitForResponse(response =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/baskets')
    await page.getByRole('button', { name: 'Create' }).click()
    const createBResponse = await createB
    expect(createBResponse.status()).toBe(200)
    const basketB = await createBResponse.json() as {
      id: number
      weighting_scheme: string
      members: Array<{ instrument_id: number; weight: number | null }>
    }
    createdIds.push(basketB.id)
    expect(basketB.weighting_scheme).toBe('equal')
    expect(basketB.members.map(member => member.instrument_id)).toEqual([nvda.instrument_id, amzn.instrument_id])
    expect(basketB.members.every(member => member.weight === null)).toBeTruthy()

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
    const updatedB = await updateBResponse.json() as { weighting_scheme: string; members: Array<{ instrument_id: number; weight: number | null }> }
    expect(updatedB.weighting_scheme).toBe('equal')
    expect(updatedB.members.map(member => member.instrument_id)).toEqual([amzn.instrument_id, added.instrument_id])
    expect(updatedB.members.every(member => member.weight === null)).toBeTruthy()

    await page.reload()
    await page.locator('.basket-card').filter({ hasText: basketBName }).click()
    await expect(page.locator('.member-row').filter({ hasText: 'MSFT' })).toBeVisible()
    await expect(page.locator('.member-row').filter({ hasText: 'NVDA' })).toHaveCount(0)

    await page.locator('.member-row').filter({ hasText: 'MSFT' }).locator('.member-symbol').click()
    await expect(page).toHaveURL(/\/chart\/MSFT$/)
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    const basketAfterMemberChart = await request.get(`/api/v1/baskets/${basketB.id}`, { headers })
    expect(basketAfterMemberChart.ok()).toBeTruthy()
    const unchangedBasket = await basketAfterMemberChart.json() as { members: Array<{ instrument_id: number }> }
    expect(unchangedBasket.members.map(member => member.instrument_id)).toEqual([amzn.instrument_id, added.instrument_id])

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

test('opening a basket submits each member preparation independently while cached chart data stays visible', async ({
  page,
  request,
  loggedIn,
}) => {
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const headers = { Authorization: `Bearer ${token}` }
  const canonicalMembers = await Promise.all(['AAPL', 'MSFT'].map(symbol =>
    resolveCanonicalInstrument(request, headers, symbol)))
  const created = await request.post('/api/v1/baskets', {
    headers,
    data: {
      name: `Delayed preparation ${Date.now()}`,
      weighting_scheme: 'equal',
      members: canonicalMembers.map(member => ({ instrument_id: member.instrument_id })),
    },
  })
  const createdText = await created.text()
  expect(created.status(), `POST /api/v1/baskets returned ${createdText}`).toBe(200)
  const basket = JSON.parse(createdText) as {
    id: number
    name: string
    members: Array<{ instrument_id: number; symbol?: string }>
  }
  const memberIds = new Set(canonicalMembers.map(member => member.instrument_id))
  const memberIdBySymbol = new Map(canonicalMembers.map(member => [member.symbol.toUpperCase(), member.instrument_id]))
  expect(basket.members.map(member => member.instrument_id)).toEqual([...memberIds])

  let chartEntryStarted = false
  let firstEnsureWasHeld = false
  let firstEnsureWasReleased = false
  let firstEnsureStatus: number | null = null
  let releaseFirstEnsure!: () => void
  const firstEnsureGate = new Promise<void>(resolve => { releaseFirstEnsure = resolve })
  const chartEnsureCalls: Array<{ instrument_id: number; datasets: string[]; timeframe: string; adjusted: boolean }> = []
  const acceptedChartEnsureIds: number[] = []

  try {
    await page.goto('/legacy/baskets')
    await expect(page.getByRole('heading', { name: 'Baskets' })).toBeVisible()
    await page.locator('.basket-card').filter({ hasText: basket.name }).click()
    await page.route('**/api/v1/data/ensure', async route => {
      if (!chartEntryStarted) return route.continue()
      const body = route.request().postDataJSON() as {
        target?: { kind?: string; instrument_id?: number; symbol?: string }
        datasets?: string[]
        timeframe?: string
        adjusted?: boolean
      }
      if (body.target?.kind !== 'instrument') return route.continue()
      const targetId = body.target?.instrument_id
        ?? memberIdBySymbol.get(body.target?.symbol?.trim().toUpperCase() ?? '')
      if (!targetId || !memberIds.has(targetId) || body.timeframe !== 'D1' || !body.datasets?.includes('history')) {
        return route.continue()
      }

      const response = await route.fetch()
      chartEnsureCalls.push({
        instrument_id: targetId,
        datasets: body.datasets,
        timeframe: body.timeframe,
        adjusted: body.adjusted === true,
      })
      if (response.ok()) acceptedChartEnsureIds.push(targetId)
      if (!firstEnsureWasHeld) {
        firstEnsureStatus = response.status()
        firstEnsureWasHeld = true
        await firstEnsureGate
        firstEnsureWasReleased = true
      }
      await route.fulfill({ response })
    })

    const basketChartResponse = page.waitForResponse(response =>
      new URL(response.url()).pathname.startsWith(`/api/v1/baskets/${basket.id}/ohlcv/`))
    chartEntryStarted = true
    await page.getByTestId('basket-open-chart').click()
    await expect(page).toHaveURL(new RegExp(`/chart/BASKET%3A${basket.id}$`), { timeout: 30_000 })
    await expect(page.locator('.workspace-layout-host')).toBeVisible()

    try {
      // This hold begins only after the ordinary Open chart action. Verify the
      // current chart action reaches the server independently for every member.
      await expect.poll(() => firstEnsureWasHeld).toBeTruthy()
      await expect.poll(() => new Set(acceptedChartEnsureIds).size).toBe(memberIds.size)
      expect(firstEnsureStatus).not.toBeNull()
      expect(firstEnsureStatus).toBeGreaterThanOrEqual(200)
      expect(firstEnsureStatus).toBeLessThan(300)
      expect(firstEnsureWasReleased).toBeFalsy()
      expect(new Set(chartEnsureCalls.map(call => call.instrument_id))).toEqual(memberIds)
      expect(chartEnsureCalls).toHaveLength(memberIds.size)
      expect(chartEnsureCalls.every(call =>
        call.timeframe === 'D1' && call.adjusted && call.datasets.includes('history'))).toBeTruthy()
      const requestKeys = chartEnsureCalls.map(call => JSON.stringify([
        call.instrument_id,
        [...call.datasets].sort(),
        call.timeframe,
        call.adjusted,
      ]))
      expect(new Set(requestKeys).size, 'identical member preparations are deduplicated').toBe(requestKeys.length)
      expect(new Set(acceptedChartEnsureIds)).toEqual(memberIds)

      const chartResponse = await basketChartResponse
      expect(chartResponse.status()).toBe(200)
      const bars = await chartResponse.json() as Array<{ timestamp: string; close: number }>
      expect(bars.length).toBeGreaterThan(0)
      expect(bars.every(bar => Number.isFinite(bar.close) && bar.close > 0)).toBeTruthy()

      const primaryChart = page.locator('.tool-window[data-window-key="primary-chart"]')
      await expect(primaryChart).toBeVisible()
      const chartRoot = primaryChart.locator('.chart-root')
      await expect(chartRoot).toBeVisible()
      const renderer = chartRoot.locator('.uplot-wrapper .uplot')
      await expect(renderer).toBeVisible()
      for (let attempt = 0; attempt < 3; attempt += 1) {
        if (await chartRoot.getAttribute('data-date-pointer-mode') === 'on_with_values') break
        await chartRoot.focus()
        await chartRoot.press('.')
      }
      await expect(chartRoot).toHaveAttribute('data-date-pointer-mode', 'on_with_values')
      const rendererBox = await renderer.boundingBox()
      expect(rendererBox).toBeTruthy()
      const tooltip = primaryChart.locator('.ohlcv-info')
      const priorTooltip = await tooltip.getAttribute('aria-label')
      await page.mouse.move(rendererBox!.x + rendererBox!.width * 0.58, rendererBox!.y + rendererBox!.height * 0.46)
      await expect(tooltip).toBeVisible()
      await expect.poll(async () => (await tooltip.getAttribute('aria-label')) !== priorTooltip).toBe(true)
      const label = (await tooltip.getAttribute('aria-label')) ?? ''
      const tooltipDate = label.split('.')[0]
      const tooltipClose = label.match(/close ([0-9]+(?:\.[0-9]+)?)/i)?.[1]
      expect(tooltipClose, 'visible basket OHLC tooltip exposes a close').toBeTruthy()
      expect(bars.some(bar => {
        const timestamp = new Date(bar.timestamp)
        const date = `${timestamp.getFullYear()}-${String(timestamp.getMonth() + 1).padStart(2, '0')}-${String(timestamp.getDate()).padStart(2, '0')}`
        return date === tooltipDate && bar.close.toFixed(4) === tooltipClose
      }), 'visible basket tooltip matches the returned cached chart series').toBeTruthy()
    } finally {
      releaseFirstEnsure()
    }
    expect(firstEnsureWasReleased).toBeTruthy()
  } finally {
    releaseFirstEnsure()
    await request.delete(`/api/v1/baskets/${basket.id}`, { headers }).catch(() => undefined)
  }
  expect(loggedIn).toBeUndefined()
})

test('controlled snapshot basket materializes through the normal API and displays read-only source lineage', async ({ page, request, loggedIn }) => {
  await page.goto('/legacy/baskets')

  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const headers = { Authorization: `Bearer ${token}` }
  const profilesResponse = await request.get('/api/v1/etf-holdings', { headers })
  const profilesText = await profilesResponse.text()
  expect(profilesResponse.status(), `GET /api/v1/etf-holdings returned ${profilesText}`).toBe(200)
  const profiles = JSON.parse(profilesText) as Array<{ symbol: string; latest_snapshot_id: number | null }>
  const profile = profiles.find(candidate => candidate.latest_snapshot_id !== null)
  expect(profile, 'combined fixture must include an ETF with a persisted issuer snapshot').toBeTruthy()

  // Use the application's supported materialization path. The explicit
  // snapshot ID preserves historical point-in-time behavior and does not
  // trigger a holdings refresh or provider request.
  const materializedResponse = await request.get(`/api/v1/etf-holdings/${encodeURIComponent(profile!.symbol)}/basket`, {
    headers,
    params: { snapshot_id: profile!.latest_snapshot_id! },
  })
  const materializedText = await materializedResponse.text()
  expect(materializedResponse.status(), `GET ETF holdings basket returned ${materializedText}`).toBe(200)
  const materializedBasket = JSON.parse(materializedText) as {
    id: number
    source_snapshot_id: number | null
    is_system_managed: boolean
  }
  expect(materializedBasket.is_system_managed).toBe(true)
  expect(materializedBasket.source_snapshot_id).toBe(profile?.latest_snapshot_id)

  const basketResponsePromise = page.waitForResponse(response =>
    response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/v1/baskets')
  await page.reload()
  const basketResponse = await basketResponsePromise
  expect(basketResponse.ok()).toBeTruthy()
  const baskets = await basketResponse.json() as Array<{
    id: number
    name: string
    is_system_managed: boolean
    source_snapshot_id: number | null
    composition_date: string | null
    metadata?: Record<string, unknown>
    members: Array<{ instrument_id: number }>
  }>
  const sourceBasket = baskets.find(basket => basket.id === materializedBasket.id)
  expect(sourceBasket, 'the normal ETF holdings API must expose the materialized source basket').toBeTruthy()
  expect(sourceBasket?.is_system_managed).toBe(true)
  expect(sourceBasket?.source_snapshot_id).toBe(profile?.latest_snapshot_id)
  expect(sourceBasket?.composition_date).toBeTruthy()
  expect(sourceBasket?.metadata?.source_provider).toBe('e2e_reference')
  expect(sourceBasket?.metadata?.provenance).toBe('controlled_fixture')
  expect(sourceBasket?.metadata?.known_at).toBeTruthy()
  expect(sourceBasket?.metadata?.source_identifier).toBeTruthy()
  expect(sourceBasket?.metadata?.source_url).toBeTruthy()
  expect(sourceBasket?.metadata?.snapshot_hash).toBeTruthy()
  expect(sourceBasket?.metadata?.source_artifact_hash).toBeNull()
  await page.locator('.basket-card').filter({ hasText: sourceBasket!.name }).click()
  const provenance = page.getByTestId('basket-source-provenance')
  await expect(provenance).toBeVisible()
  await expect(provenance).toContainText(sourceBasket?.composition_date ?? '')
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.source_provider ?? ''))
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.provenance ?? ''))
  await expect(provenance).toContainText(String(sourceBasket?.metadata?.source_identifier ?? ''))
  await expect(provenance).not.toContainText('source artifact')
  await expect(page.getByTestId('basket-snapshot-history')).toContainText(String(sourceBasket?.metadata?.known_at ?? ''))
  await expect(page.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save' })).toBeDisabled()

  const editAttempt = await request.patch(`/api/v1/baskets/${sourceBasket!.id}`, {
    headers,
    data: { name: 'Must remain read-only' },
  })
  expect(editAttempt.status()).toBe(403)
  const deleteAttempt = await request.delete(`/api/v1/baskets/${sourceBasket!.id}`, { headers })
  expect(deleteAttempt.status()).toBe(403)
  const unchanged = await request.get(`/api/v1/baskets/${sourceBasket!.id}`, { headers })
  expect(unchanged.ok()).toBeTruthy()
  const unchangedBody = await unchanged.json() as typeof sourceBasket
  expect(unchangedBody?.source_snapshot_id).toBe(sourceBasket?.source_snapshot_id)
  expect(unchangedBody?.composition_date).toBe(sourceBasket?.composition_date)
  expect(unchangedBody?.metadata).toEqual(sourceBasket?.metadata)
  expect(unchangedBody?.members.map(member => member.instrument_id))
    .toEqual(sourceBasket?.members?.map((member: { instrument_id: number }) => member.instrument_id))
  expect(loggedIn).toBeUndefined()
})
