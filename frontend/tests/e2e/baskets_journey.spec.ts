import { expect, test } from './helpers'

type SearchCandidate = {
  symbol: string
  name: string
  instrument_id: number
}

async function chooseResolvedInstrument(
  page: import('@playwright/test').Page,
  symbol: string,
  onResolved?: (candidate: SearchCandidate) => void,
) {
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
  onResolved?.(canonical!)
  await page.getByRole('option', { name: new RegExp(`^${symbol}\\s`) }).click()
  return canonical!
}

test('ordinary basket lifecycle persists edits and opens the shared dashboard chart before background preparation settles', async ({
  page,
  request,
  loggedIn,
}) => {
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(token).toBeTruthy()
  const headers = { Authorization: `Bearer ${token}` }
  const createdIds: number[] = []
  const ensureCalls: Array<{ instrument_id: number; datasets: string[]; timeframe: string }> = []
  const acceptedEnsureInstrumentIds: number[] = []
  let firstMemberInstrumentId: number | null = null
  let firstEnsureAccepted = false
  let firstEnsureWasHeld = false
  let firstEnsureWasReleased = false
  let releaseFirstEnsure!: () => void
  const firstEnsureGate = new Promise<void>(resolve => { releaseFirstEnsure = resolve })
  page.on('request', requestEvent => {
    if (requestEvent.method() !== 'POST' || new URL(requestEvent.url()).pathname !== '/api/v1/data/ensure') return
    const body = requestEvent.postDataJSON() as { target?: { instrument_id?: number }; datasets?: string[]; timeframe?: string }
    if (body.target?.instrument_id) ensureCalls.push({
      instrument_id: body.target.instrument_id,
      datasets: body.datasets ?? [],
      timeframe: body.timeframe ?? '',
    })
  })
  await page.route('**/api/v1/data/ensure', async route => {
    const body = route.request().postDataJSON() as { target?: { instrument_id?: number } }
    const response = await route.fetch()
    if (body.target?.instrument_id && response.ok()) acceptedEnsureInstrumentIds.push(body.target.instrument_id)
    if (body.target?.instrument_id === firstMemberInstrumentId && !firstEnsureWasHeld) {
      firstEnsureAccepted = response.ok()
      firstEnsureWasHeld = true
      await firstEnsureGate
      firstEnsureWasReleased = true
    }
    await route.fulfill({ response })
  })
  await page.goto('/legacy/baskets')
  await expect(page.getByRole('heading', { name: 'Baskets' })).toBeVisible()
  const firstMemberSearch = await request.get('/api/v1/instruments/search', {
    headers,
    params: { q: 'AAPL', canonical_only: 'true' },
  })
  expect(firstMemberSearch.ok()).toBeTruthy()
  const firstMemberCandidates = await firstMemberSearch.json() as SearchCandidate[]
  const firstMemberCandidate = firstMemberCandidates.filter(candidate => candidate.symbol.toUpperCase() === 'AAPL')
  expect(firstMemberCandidate).toHaveLength(1)
  firstMemberInstrumentId = firstMemberCandidate[0].instrument_id

  try {
    await page.getByRole('button', { name: '+ New' }).click()
    await page.getByPlaceholder('Basket name').fill(`Lifecycle A ${Date.now()}`)
    await page.locator('select.form-select').selectOption('custom')
    const aapl = await chooseResolvedInstrument(page, 'AAPL', candidate =>
      expect(candidate.instrument_id).toBe(firstMemberInstrumentId))
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
    const selectedA = await request.get(`/api/v1/baskets/${basketA.id}`, { headers })
    expect(selectedA.status()).toBe(200)
    const selectedABody = await selectedA.json() as { members: Array<{ instrument_id: number }> }
    expect(selectedABody.members.length).toBeGreaterThan(1)
    expect(firstMemberInstrumentId).toBe(selectedABody.members[0]?.instrument_id)
    await page.locator('.basket-card').filter({ hasText: /Lifecycle A/ }).click()
    const basketChartRequest = page.waitForResponse(response =>
      new URL(response.url()).pathname.startsWith(`/api/v1/baskets/${basketA.id}/ohlcv/`))
    await page.getByTestId('basket-open-chart').click()
    await expect(page).toHaveURL(new RegExp(`/chart/BASKET%3A${basketA.id}$`), { timeout: 30_000 })
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    let syntheticBars: Array<{ timestamp: string; close: number }> = []
    try {
      // The first real preparation response is held after the server accepts it.
      // Later member submissions and valid cached basket output must still proceed.
      await expect.poll(() => firstEnsureWasHeld).toBeTruthy()
      await expect.poll(() => new Set(ensureCalls
        .filter(call => selectedABody.members.some(member => member.instrument_id === call.instrument_id)
          && call.timeframe === 'D1' && call.datasets.includes('history'))
        .map(call => call.instrument_id)).size).toBe(selectedABody.members.length)
      expect(firstEnsureWasHeld).toBeTruthy()
      expect(firstEnsureAccepted).toBeTruthy()
      expect(firstEnsureWasReleased).toBeFalsy()
      const memberHistoryCalls = ensureCalls.filter(call =>
        selectedABody.members.some(member => member.instrument_id === call.instrument_id)
          && call.timeframe === 'D1' && call.datasets.includes('history'))
      expect(new Set(memberHistoryCalls.map(call => call.instrument_id)))
        .toEqual(new Set(selectedABody.members.map(member => member.instrument_id)))
      expect(memberHistoryCalls.every(call => call.datasets.includes('history'))).toBeTruthy()
      expect(new Set(acceptedEnsureInstrumentIds.filter(instrumentId =>
        selectedABody.members.some(member => member.instrument_id === instrumentId))))
        .toEqual(new Set(selectedABody.members.map(member => member.instrument_id)))
      const basketChartResponse = await basketChartRequest
      expect(basketChartResponse.status()).toBe(200)
      syntheticBars = await basketChartResponse.json() as Array<{ timestamp: string; close: number }>
      expect(syntheticBars.length).toBeGreaterThan(0)
      expect(syntheticBars.every(bar => Number.isFinite(bar.close))).toBeTruthy()

      // The held preparation must not prevent the already available basket
      // series from reaching the visible shared chart. Tie its ordinary OHLC
      // tooltip back to the real basket response, not merely a mounted canvas.
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
      expect(syntheticBars.some(bar => {
        const timestamp = new Date(bar.timestamp)
        const date = `${timestamp.getFullYear()}-${String(timestamp.getMonth() + 1).padStart(2, '0')}-${String(timestamp.getDate()).padStart(2, '0')}`
        return date === tooltipDate && bar.close.toFixed(4) === tooltipClose
      }), 'visible basket tooltip matches the held-window API response').toBeTruthy()
    } finally {
      releaseFirstEnsure()
    }
    expect(firstEnsureWasReleased).toBeTruthy()

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
    releaseFirstEnsure()
    for (const basketId of createdIds) {
      await request.delete(`/api/v1/baskets/${basketId}`, { headers }).catch(() => undefined)
    }
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
