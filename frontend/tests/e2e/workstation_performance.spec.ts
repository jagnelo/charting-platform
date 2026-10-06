import { type Page } from '@playwright/test'
import { test, expect } from './helpers'

async function closePopupWhenOpen(popup: Page) {
  if (popup.isClosed()) return
  const closed = popup.waitForEvent('close', { timeout: 10_000 }).catch((error: unknown) => {
    if (!popup.isClosed()) throw error
  })
  try {
    await popup.locator('button[title="Close"]').click()
  } catch (error) {
    // Golden Layout can close a sibling popup while it reconciles the source
    // workspace. Treat that narrow teardown race as already closed; the caller
    // still asserts that the browser context converges to one page.
    if (!popup.isClosed()) throw error
  }
  await closed
}

test.describe('TC2000 workstation performance guards', () => {
  test('defers optional research tools until they are opened', async ({ page, loggedIn, browserDiagnostics }) => {
    test.setTimeout(90_000)
    const requestedScripts: string[] = []
    page.on('request', request => {
      const url = new URL(request.url())
      if (url.pathname.startsWith('/assets/') && url.pathname.endsWith('.js')) requestedScripts.push(url.pathname)
    })

    // The authenticated fixture resets this account to the factory workspace;
    // reload after attaching the listener so this captures the real cold load.
    await page.reload()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.rotation-tool')).toHaveCount(1, { timeout: 30_000 })

    const deferredToolChunks = ['MarketMapTool', 'StudyLabTool', 'ResearchResultsTool', 'CodeLibraryTool', 'InstrumentInfoPanel']
    expect(requestedScripts.some(path => deferredToolChunks.some(name => path.includes(`/${name}-`)))).toBe(false)

    const toolsOpened = [
      { title: 'Market Map', chunk: 'MarketMapTool', selector: '.market-map-tool' },
      { title: 'Study Lab', chunk: 'StudyLabTool', selector: '.study-lab-tool' },
      { title: 'Study Results', chunk: 'ResearchResultsTool', selector: '.research-results-tool' },
      { title: 'Python Library', chunk: 'CodeLibraryTool', selector: '.code-library-tool' },
      { title: 'Instrument Report', chunk: 'InstrumentInfoPanel', selector: '.instrument-report' },
    ]

    for (const tool of toolsOpened) {
      await page.getByRole('button', { name: 'Add tool', exact: true }).click()
      await page.getByRole('menu', { name: 'Workstation tools' }).getByRole('menuitem', { name: tool.title, exact: true }).click()
      await expect(page.locator(`${tool.selector}:visible`).last()).toBeVisible({ timeout: 15_000 })
      await expect.poll(() => requestedScripts.some(path => path.includes(`/${tool.chunk}-`))).toBe(true)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('initializes multiple chart windows and recovers without canvas or tool growth', async ({ page, context, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    // Chart panes can add their volume/indicator canvases after the primary
    // canvas appears. Settle the one-time initialization before recording the
    // source baseline used by the pop-out recovery assertion.
    const settledCanvasCount = async () => {
      let previous = -1
      let stableSamples = 0
      for (let sample = 0; sample < 20; sample += 1) {
        const current = await page.locator('canvas').count()
        stableSamples = current === previous ? stableSamples + 1 : 0
        previous = current
        // Hidden analysis panes can finish their first uPlot render shortly after
        // their explicit aria-busy state clears. Require a longer quiet window so
        // the exact leak baseline includes those legitimate late canvases.
        if (stableSamples >= 8) return current
        await page.waitForTimeout(250)
      }
      return previous
    }
    await page.waitForTimeout(1_000)
    // The factory mounts ratio and relative-rotation surfaces even when they
    // are hidden behind another Golden Layout tab. Their local data requests
    // can finish after the primary chart's first canvas appears; wait for
    // those explicit readiness states before recording the exact canvas
    // baseline, otherwise a legitimate late renderer looks like a leak.
    const ratioTools = page.locator('.ratio-chart')
    if (await ratioTools.count()) {
      await expect.poll(() => page.locator('.ratio-chart[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await ratioTools.count())
    }
    const chartRoots = page.locator('.chart-root')
    if (await chartRoots.count()) {
      await expect.poll(() => page.locator('.chart-root[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await chartRoots.count())
    }
    const rotationTools = page.locator('.rotation-tool')
    if (await rotationTools.count()) {
      await expect.poll(() => page.locator('.rotation-tool[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await rotationTools.count())
    }
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await settledCanvasCount()
    const started = await page.evaluate(() => performance.now())
    const popups = []

    for (let index = 0; index < 2; index += 1) {
      const floatButton = page.locator('button[title="Float"]').nth(index)
      await expect(floatButton).toBeVisible({ timeout: 10_000 })
      const popupPromise = context.waitForEvent('page')
      await floatButton.click()
      const popup = await popupPromise
      popups.push(popup)
      await popup.waitForLoadState('domcontentloaded')
      await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })
      if (await popup.locator('.chart-tool').count()) {
        await expect.poll(() => popup.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
      }
    }

    await expect.poll(() => context.pages().length).toBe(3)
    const activeSymbolInput = page.locator('input[aria-label="Active symbol"]')
    await activeSymbolInput.fill('XLB')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
    await expect(activeSymbolInput).toHaveValue('XLB')
    await expect(page.locator('.workstation__footer')).toContainText('XLB')
    for (const popup of popups) {
      await expect.poll(() => popup.locator('.tool-window__symbol').allTextContents()).toContain('XLB')
    }
    await expect.poll(() => page.locator('.tool-window').count()).toBe(sourceToolCount)

    for (const popup of popups) {
      await closePopupWhenOpen(popup)
    }
    await expect.poll(() => context.pages().length).toBe(1)
    await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
    // Popup teardown can dispose chart panes asynchronously. Give the browser
    // a bounded cleanup window, while retaining the exact baseline assertion so
    // a genuine canvas leak still fails the performance gate.
    await expect.poll(() => page.locator('canvas').count(), {
      timeout: 15_000,
      intervals: [250, 500, 1_000],
    }).toBe(sourceCanvasCount)
    const elapsed = await page.evaluate((start) => performance.now() - start, started)
    expect(elapsed).toBeLessThan(20_000)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('repeated multi-window churn keeps the source workspace bounded', async ({ page, context, loggedIn, browserDiagnostics }) => {
    // Long lifecycle acceptance runs must not fail at Playwright's 30-second default
    // before all configured browser-window cycles can complete.
    const configuredRounds = Number(process.env.TC2000_POP_OUT_CHURN_ROUNDS ?? 5)
    const requestedRounds = Number.isInteger(configuredRounds) && configuredRounds > 0 ? configuredRounds : 5
    // Keep the soak bounded for CI while allowing an explicitly requested
    // long run to exercise substantially more lifecycle churn than the normal
    // smoke/default setting. Indefinite endurance remains a separate gate.
    test.setTimeout(Math.max(60_000, Math.min(requestedRounds, 500) * 2_500 + 120_000))
    await page.goto('/chart')
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => page.locator('canvas').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    // Establish a settled baseline before exercising repeated browser-window churn.
    const settledCanvasCount = async () => {
      let previous = -1
      let stableSamples = 0
      for (let sample = 0; sample < 20; sample += 1) {
        const current = await page.locator('canvas').count()
        stableSamples = current === previous ? stableSamples + 1 : 0
        previous = current
        // Hidden analysis panes can finish their first uPlot render shortly after
        // their explicit aria-busy state clears. Require a longer quiet window so
        // the exact leak baseline includes those legitimate late canvases.
        if (stableSamples >= 8) return current
        await page.waitForTimeout(250)
      }
      return previous
    }
    await page.waitForTimeout(1_000)
    const ratioTools = page.locator('.ratio-chart')
    if (await ratioTools.count()) {
      await expect.poll(() => page.locator('.ratio-chart[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await ratioTools.count())
    }
    const chartRoots = page.locator('.chart-root')
    if (await chartRoots.count()) {
      await expect.poll(() => page.locator('.chart-root[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await chartRoots.count())
    }
    const rotationTools = page.locator('.rotation-tool')
    if (await rotationTools.count()) {
      await expect.poll(() => page.locator('.rotation-tool[aria-busy="false"]').count(), { timeout: 30_000 }).toBe(await rotationTools.count())
    }
    const sourceToolCount = await page.locator('.tool-window').count()
    const sourceCanvasCount = await settledCanvasCount()
    const sourceChartCount = await page.locator('.chart-tool').count()
    // Keep an explicit upper bound so CI cannot accidentally become unbounded, but allow
    // the acceptance job to exercise a genuine long-duration lifecycle soak rather than
    // silently truncating every run to the short default smoke limit.
    const rounds = Number.isInteger(configuredRounds) && configuredRounds > 0
      ? Math.min(configuredRounds, 500)
      : 5
    const memorySamples: number[] = []
    const readHeap = async () => page.evaluate(() => {
      const performanceWithMemory = performance as Performance & { memory?: { usedJSHeapSize: number } }
      return performanceWithMemory.memory?.usedJSHeapSize ?? null
    })
    const initialMemory = await readHeap()
    if (initialMemory != null) memorySamples.push(initialMemory)

    for (let round = 0; round < rounds; round += 1) {
      const popups = []
      for (let index = 0; index < 2; index += 1) {
        const floatButton = page.locator('button[title="Float"]').nth(index)
        await expect(floatButton).toBeVisible({ timeout: 10_000 })
        const popupPromise = context.waitForEvent('page')
        await floatButton.click()
        const popup = await popupPromise
        popups.push(popup)
        await popup.waitForLoadState('domcontentloaded')
        await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })
      }

      await expect.poll(() => context.pages().length).toBe(3)
      for (const popup of popups) {
        await closePopupWhenOpen(popup)
      }
      await expect.poll(() => context.pages().length).toBe(1)
      await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
      // Cleanup is asynchronous, but must converge back to the original
      // canvas count within a bounded interval after every churn round.
      await expect.poll(() => page.locator('canvas').count(), {
        timeout: 15_000,
        intervals: [250, 500, 1_000],
      }).toBe(sourceCanvasCount)
      await expect(page.locator('.chart-tool')).toHaveCount(sourceChartCount)
      const currentMemory = await readHeap()
      if (currentMemory != null) memorySamples.push(currentMemory)
    }

    // Chromium does not expose performance.memory in every environment; when it does,
    // reject unbounded churn without making the guard browser-engine dependent. The
    // absolute ceiling catches catastrophic growth; the relative ceiling catches a
    // leak that remains below the ceiling during a short run.
    if (memorySamples.length) {
      expect(Math.max(...memorySamples)).toBeLessThan(512 * 1024 * 1024)
      expect(Math.max(...memorySamples) - memorySamples[0]).toBeLessThan(256 * 1024 * 1024)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('hydrates a 10,000-row personal watchlist over the network within the row budget', async ({ page, request, loggedIn, browserDiagnostics }) => {
    test.skip(process.env.E2E_SEED_LARGE_UNIVERSE !== 'true', 'requires the opt-in controlled dense-universe fixture')
    test.setTimeout(120_000)

    const token = await page.evaluate(() => localStorage.getItem('access_token'))
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined
    const instrumentIds: number[] = []
    let pageNumber = 1
    while (instrumentIds.length < 10_000) {
      const response = await request.get('/api/v1/instruments/browse', {
        headers,
        params: { q: 'E2E_ROW_', page: pageNumber, page_size: 200 },
      })
      expect(response.ok()).toBeTruthy()
      const body = await response.json() as { total: number; items: Array<{ id: number }> }
      expect(body.total).toBeGreaterThanOrEqual(10_000)
      instrumentIds.push(...body.items.map(item => item.id))
      if (!body.items.length) break
      pageNumber += 1
    }
    expect(instrumentIds).toHaveLength(10_000)

    const name = `E2E 10k network budget ${Date.now().toString(36)}`
    const created = await request.post('/api/v1/watchlists', {
      headers,
      data: { name },
    })
    expect(created.status()).toBe(200)
    const watchlist = await created.json() as { id: number }
    const seeded = await request.post(`/api/v1/watchlists/${watchlist.id}/seed`, {
      headers,
      data: { instrument_ids: instrumentIds },
    })
    expect(seeded.status()).toBe(200)
    await seeded.dispose()

    try {
      await page.goto('/chart')
      await page.getByRole('button', { name: 'Add tool', exact: true }).click()
      const toolMenu = page.locator('.workstation__tool-library-menu')
      await expect(toolMenu).toBeVisible({ timeout: 10_000 })
      await toolMenu.getByRole('menuitem', { name: 'WatchList', exact: true }).click()
      const watchlistTab = page.locator('.lm_tab').filter({ hasText: 'WatchList' }).last()
      await expect(watchlistTab).toBeVisible({ timeout: 10_000 })
      if (!(await watchlistTab.evaluate(node => node.classList.contains('lm_active')))) await watchlistTab.click()
      const personal = page.locator('.tool-window--active .personal-watchlist-tool').last()
      await expect(personal).toBeVisible({ timeout: 10_000 })
      const select = personal.getByRole('combobox', { name: 'Personal watchlist', exact: true })
      await expect(select.locator('option', { hasText: name })).toHaveCount(1, { timeout: 30_000 })
      await select.selectOption({ label: name })
      const virtualWatchlist = personal.locator('.watchlist')
      await expect(virtualWatchlist).toHaveAttribute('data-row-count', '10000', { timeout: 30_000 })
      await expect(virtualWatchlist).toHaveAttribute('data-row-budget', 'within')
      await expect.poll(async () => Number(await virtualWatchlist.getAttribute('data-rendered-row-count'))).toBeLessThan(100)
      await expect.poll(() => virtualWatchlist.locator('.watchlist__row').count()).toBeLessThan(100)
      await browserDiagnostics.expectNoCriticalIssues()
    } finally {
      const deleted = await request.delete(`/api/v1/watchlists/${watchlist.id}`, { headers })
      expect([200, 204, 404]).toContain(deleted.status())
    }
  })

  test('renders and interacts with a 10,000-cell Market Map within the canvas budget', async ({ page, loggedIn, browserDiagnostics }, testInfo) => {
    test.setTimeout(90_000)

    // This is a consumer-side stress fixture: the map is supplied by the
    // existing Market Map read contract, so the test exercises TC geometry,
    // canvas painting, hit testing, keyboard search, zoom and pan without
    // manufacturing provider or canonical-history evidence.
    const source = {
      source_id: 'watchlist:tc2000-10k-map',
      source_kind: 'personal',
      name: 'TC2000 10k canvas fixture',
      locked: false,
      can_follow: true,
      can_clone: true,
      can_edit_membership: true,
      member_count: 10_000,
      membership_version: 'watchlist:tc2000-10k-map:v1',
      provenance: { availability: 'available' },
    }
    const cells = Array.from({ length: 10_000 }, (_, index) => ({
      instrument_id: index + 1,
      symbol: index === 9_999 ? 'SPY' : `E2E_MAP_${String(index).padStart(5, '0')}`,
      name: `Synthetic Market Map member ${index}`,
      sector: null,
      industry: null,
      group_path: [],
      area_value: 1,
      color_value: (index % 21 - 10) / 100,
      return_value: (index % 21 - 10) / 100,
      coverage: 1,
      color_coverage: 1,
      area_coverage: 1,
      warnings: [],
    }))
    await page.route('**/api/v1/watchlists/sources**', async route => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.includes('/history-status/')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          source_id: source.source_id,
          source_kind: source.source_kind,
          name: source.name,
          locked: false,
          membership_version: source.membership_version,
          max_instruments: 10_000,
          available_instrument_count: 10_000,
          selected_instrument_count: 10_000,
          limited: false,
          excluded_count: 0,
          overall_status: 'ready',
          timeframes: [],
        }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([source]) })
    })
    await page.route('**/api/v1/watchlists', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })
    await page.route('**/api/v1/analysis/market-map/snapshots**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })
    await page.route('**/api/v1/analysis/market-map', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        source,
        group_by: 'sector_industry',
        period: '1D',
        period_start: '2026-10-05T00:00:00Z',
        period_end: '2026-10-06T00:00:00Z',
        timeframe: 'D1',
        adjustment: 'split_adjusted',
        area_metric: 'equal',
        color_metric: 'return',
        membership_version: source.membership_version,
        calculation_version: 'market-map-performance-fixture-v1',
        cache_key: 'tc2000-10k-map-performance-fixture',
        cache_hit: false,
        freshness: 'current',
        freshness_detail: { requested: 10_000, current: 10_000, stale: 0, other: 0 },
        requested_count: 10_000,
        evaluated_count: 10_000,
        coverage: 1,
        color_coverage: 1,
        area_coverage: 1,
        warnings: [],
        exclusions: [],
        nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 10_000, covered_count: 10_000, area_total: 10_000, color_value: 0, coverage: 1, color_coverage: 1, area_coverage: 1, aggregation_method: 'equal_member_mean', warnings: [] }],
        cells,
      }) })
    })

    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Market Map', exact: true }).click()
    const mapWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.market-map-tool') }).last()
    await expect(mapWindow).toBeVisible({ timeout: 15_000 })
    const sourcePicker = mapWindow.getByRole('combobox', { name: 'Market Map universe' })
    await expect(sourcePicker).toContainText(source.name, { timeout: 15_000 })
    await sourcePicker.selectOption(source.source_id)

    await page.evaluate(() => { (window as Window & { __tc2000MapStart?: number }).__tc2000MapStart = performance.now() })
    await mapWindow.getByRole('button', { name: 'Refresh Market Map', exact: true }).click()
    const canvas = mapWindow.locator('canvas.market-map-tool__canvas-map')
    await expect(canvas).toBeVisible({ timeout: 15_000 })
    await expect(canvas).toHaveAttribute('aria-label', '10000 Market Map members')
    await expect.poll(() => canvas.evaluate(element => (element as HTMLCanvasElement).width)).toBeGreaterThan(0)
    expect(await mapWindow.locator('.market-map-tool__tile').count()).toBe(0)
    const renderMilliseconds = await page.evaluate(() => performance.now() - ((window as Window & { __tc2000MapStart?: number }).__tc2000MapStart ?? performance.now()))
    expect(renderMilliseconds, '10,000 cells must reach a painted canvas within the declared 5-second local budget').toBeLessThan(5_000)
    await testInfo.attach('market-map-10k-render-budget.json', {
      body: JSON.stringify({ cells: 10_000, render_milliseconds: Math.round(renderMilliseconds * 100) / 100, budget_milliseconds: 5_000 }),
      contentType: 'application/json',
    })

    // Canvas pointer hit-testing selects a real cell; the search affordance
    // then provides deterministic keyboard selection for the dense mode.
    await canvas.scrollIntoViewIfNeeded()
    const canvasBounds = await canvas.boundingBox()
    expect(canvasBounds).not.toBeNull()
    await page.mouse.move(canvasBounds!.x + canvasBounds!.width * 0.5, canvasBounds!.y + canvasBounds!.height * 0.5)
    await expect(mapWindow.locator('.market-map-tool__hover')).toBeVisible()
    await expect(mapWindow.locator('.market-map-tool__hover')).toContainText('Synthetic Market Map member')

    const memberSearch = mapWindow.getByRole('textbox', { name: 'Find Large Market Map member' })
    await memberSearch.fill('SPY')
    await memberSearch.press('Enter')
    await expect(mapWindow.locator('.market-map-tool__source-analysis-actions')).toContainText('1 selected members')
    await expect(mapWindow.locator('.market-map-tool__selection-announcement'))
      .toHaveText('1 selected member: SPY')

    const mapCanvas = mapWindow.locator('.market-map-tool__canvas')
    await mapWindow.getByRole('button', { name: 'Zoom in Market Map' }).click()
    await expect(mapCanvas).toHaveAttribute('style', /scale\(1\.25\)/)
    const viewport = mapWindow.locator('.market-map-tool__tiles')
    await viewport.scrollIntoViewIfNeeded()
    const viewportBounds = await viewport.boundingBox()
    expect(viewportBounds).not.toBeNull()
    const panStartX = viewportBounds!.x + viewportBounds!.width / 2
    const panStartY = viewportBounds!.y + viewportBounds!.height / 2
    await page.mouse.move(panStartX, panStartY)
    await page.mouse.down()
    await page.mouse.move(panStartX - 60, panStartY - 30, { steps: 4 })
    await page.mouse.up()
    await expect(mapCanvas).toHaveAttribute('style', /translate\((?!0%, 0%)[^)]+\) scale\(1\.25\)/)
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
