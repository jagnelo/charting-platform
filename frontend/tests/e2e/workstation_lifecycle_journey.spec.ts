import type { Page } from '@playwright/test'
import { expect, test } from './helpers'

// This table is keyed to the authenticated server catalogue.  The test fails
// closed if a canonical tool is added without a user-visible outcome assertion.
const TOOL_OUTCOMES: Record<string, 'watchlist' | 'industry' | 'chart' | 'ratio' | 'technicals' | 'breadth' | 'coverage' | 'notes' | 'alerts' | 'scan' | 'gauge' | 'rotation' | 'map' | 'study' | 'results' | 'library' | 'report'> = {
  Chart: 'chart',
  WatchList: 'watchlist',
  'My Favorites': 'watchlist',
  Notes: 'notes',
  Alerts: 'alerts',
  EasyScan: 'scan',
  'Market Gauge': 'gauge',
  'Study Lab': 'study',
  'Study Results': 'results',
  'Relative Rotation': 'rotation',
  'Market Breadth': 'breadth',
  Breadth: 'breadth',
  'Market Map': 'map',
  Technicals: 'technicals',
  Coverage: 'coverage',
  'Instrument Report': 'report',
  'Python Library': 'library',
  Benchmarks: 'watchlist',
  'S&P 500 Sectors': 'watchlist',
  Industries: 'industry',
  Constituents: 'watchlist',
  'Relative Strength': 'ratio',
  'Sector Indexes': 'watchlist',
  'Industry Indexes': 'industry',
  Components: 'watchlist',
  'Selected Symbol': 'chart',
  'Sector Comparison': 'chart',
  'Normalized Comparison': 'chart',
  '15 Minute': 'chart',
  Daily: 'chart',
  Weekly: 'chart',
  Monthly: 'chart',
  'Fundamentals WatchList': 'watchlist',
  'Supported Symbol Report': 'report',
}

const FACTORY_LAYOUT_NAMES = [
  'US Top Down', 'TC Classic', 'Drill Down', 'Sector by Year',
  '1 Chart', '4 Timeframe', 'Fundamentals', 'Study Lab',
]
const FACTORY_INSTANCE_KEYS_BY_CATALOGUE_KEY: Record<string, string[]> = {
  chart: ['primary-chart'],
  breadth: ['breadth-summary'],
  coverage: ['coverage-summary'],
}
let retainedGaugeScanName = ''

async function openWorkspaceMenu(page: Page) {
  const menu = page.getByRole('menu', { name: 'Workspace layouts' })
  if (!(await menu.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: 'Workspace', exact: true }).click()
  }
  await expect(menu).toBeVisible()
  return menu
}

async function activatePanel(page: Page, title: string) {
  const tab = page.locator('.lm_tab').filter({ hasText: new RegExp(`^${escapeRegExp(title)}$`) })
  if (await tab.first().isVisible().catch(() => false)) {
    await tab.first().click()
  } else {
    // Golden Layout moves excess tabs into its ordinary header dropdown.
    const header = tab.first().locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," lm_header ")][1]')
    const dropdown = header.locator('.lm_tabdropdown')
    await expect(dropdown).toBeVisible()
    await dropdown.click()
    const overflowTab = header.locator('.lm_tabdropdown_list .lm_tab').filter({ hasText: new RegExp(`^${escapeRegExp(title)}$`) })
    await expect(overflowTab).toBeVisible()
    await overflowTab.click()
  }
  const tool = page.getByRole('group', { name: title, exact: true })
  await expect(tool).toBeVisible()
  return tool
}

async function authenticatedJson(page: Page, path: string) {
  return page.evaluate(async (url) => {
    const token = localStorage.getItem('access_token')
    const response = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    return { status: response.status, body: await response.json() }
  }, path)
}

async function assertCanonicalCoverage(page: Page) {
  const [catalogueResponse, workspaceResponse] = await Promise.all([
    authenticatedJson(page, '/api/v1/workspaces/tool-catalogue'),
    authenticatedJson(page, '/api/v1/workspaces/default'),
  ])
  expect(catalogueResponse.status).toBe(200)
  expect(workspaceResponse.status).toBe(200)
  const catalogue = catalogueResponse.body as { tools: Array<{ key: string; tool_type: string; title: string }> }
  const workspace = workspaceResponse.body as { tabs: Array<{ name: string; windows: Array<{ instance_key: string; tool_type: string; title: string; configuration: Record<string, unknown> }> }> }
  const catalogueTitles = catalogue.tools.map(tool => tool.title).sort()
  expect(catalogueTitles.filter(title => !(title in TOOL_OUTCOMES)), 'every canonical catalogue entry needs a useful outcome assertion').toEqual([])
  expect(workspace.tabs.map(tab => tab.name).sort()).toEqual([...FACTORY_LAYOUT_NAMES].sort())
  const factoryTitles = [...new Set(workspace.tabs.flatMap(tab => tab.windows.map(window => window.title)))].sort()
  const unmappedFactoryTitles = factoryTitles.filter(title => !(title in TOOL_OUTCOMES))
  expect(unmappedFactoryTitles, 'every factory window must map to a useful outcome assertion').toEqual([])
  const topDown = workspace.tabs.find(tab => tab.name === 'US Top Down')
  expect(topDown?.windows.find(window => window.title === 'Coverage')).toMatchObject({
    instance_key: 'coverage-summary',
    tool_type: 'coverage',
  })
  return { catalogue, workspace }
}

async function assertFactoryLayouts(page: Page, tabs: Array<{ name: string; windows: Array<{ instance_key: string; tool_type: string; title: string; configuration: Record<string, unknown> }> }>) {
  expect(tabs.map(tab => tab.name).sort()).toEqual([...FACTORY_LAYOUT_NAMES].sort())
  for (const layout of tabs) {
    await activateLayout(page, layout.name)
    const visibleTitles = await page.locator('.tool-window__title').allTextContents()
    expect(visibleTitles.sort(), `${layout.name} factory windows`).toEqual(layout.windows.map(window => window.title).sort())
    for (const window of layout.windows) {
      const outcome = TOOL_OUTCOMES[window.title]
      expect(outcome, `${layout.name}: ${window.title} must map to a useful outcome`).toBeTruthy()
      await assertUsefulTool(page, window.title, outcome, window.configuration)
    }
  }
}

async function activateLayout(page: Page, name: string) {
  const tab = page.getByRole('tab', { name, exact: true })
  await tab.scrollIntoViewIfNeeded()
  await expect(tab).toBeVisible()
  await tab.click()
}

async function plottedSeriesPixels(canvas: ReturnType<Page['locator']>, colors: Array<[number, number, number]>, tolerance = 10) {
  return canvas.evaluate((element, { expectedColors, colorTolerance }: { expectedColors: Array<[number, number, number]>; colorTolerance: number }) => {
    const canvas = element as HTMLCanvasElement
    if (canvas.width < 2 || canvas.height < 2) return 0
    const pixels = canvas.getContext('2d')?.getImageData(0, 0, canvas.width, canvas.height).data
    if (!pixels) return 0
    let matches = 0
    for (let index = 0; index < pixels.length; index += 4) {
      if (pixels[index + 3] === 0) continue
      if (expectedColors.some(([red, green, blue]) => Math.abs(pixels[index] - red) <= colorTolerance && Math.abs(pixels[index + 1] - green) <= colorTolerance && Math.abs(pixels[index + 2] - blue) <= colorTolerance)) matches += 1
    }
    return matches
  }, { expectedColors: colors, colorTolerance: tolerance })
}

async function readRrgMarkerAudit(canvas: ReturnType<Page['locator']>) {
  return canvas.evaluate((element) => {
    type MarkerArc = { x: number; y: number; radius: number; fillStyle: string; frame: number }
    type AuditedCanvas = HTMLCanvasElement & { __rrgLatestMarkerDraw?: MarkerArc[]; __rrgAuditFrame?: number }
    const target = element as AuditedCanvas
    const auditFrame = target.__rrgAuditFrame ?? 0
    const markers = (target.__rrgLatestMarkerDraw ?? []).filter(marker => marker.frame === auditFrame)
    const dpr = window.devicePixelRatio || 1
    const visibleMarkers = markers.filter(marker => marker.radius >= 3.4 * dpr)
    const context = target.getContext('2d', { willReadFrequently: true })
    const colors = new Set(['#61c58c', '#e7bc68', '#6dbbe6', '#df8181'])
    const rect = target.getBoundingClientRect()
    const clip = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight }
    for (let node: HTMLElement | null = target; node; node = node.parentElement) {
      const style = window.getComputedStyle(node)
      const bounds = node.getBoundingClientRect()
      if (['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX)) {
        clip.left = Math.max(clip.left, bounds.left)
        clip.right = Math.min(clip.right, bounds.right)
      }
      if (['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowY)) {
        clip.top = Math.max(clip.top, bounds.top)
        clip.bottom = Math.min(clip.bottom, bounds.bottom)
      }
    }
    const completeCanvasVisible = rect.width > 0 && rect.height >= 100
      && target.height / dpr >= 100
      && rect.left >= clip.left && rect.top >= clip.top
      && rect.right <= clip.right && rect.bottom <= clip.bottom
      && window.getComputedStyle(target).visibility === 'visible'
      && Number(window.getComputedStyle(target).opacity) > 0
    const samples = visibleMarkers.map((marker) => {
      const x = Math.round(marker.x)
      const y = Math.round(marker.y)
      const inBounds = Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0 && x < target.width && y < target.height
      const pixel = context && inBounds ? Array.from(context.getImageData(x, y, 1, 1).data) : null
      const expected = marker.fillStyle.slice(1).match(/../g)?.map(value => Number.parseInt(value, 16))
      const opaqueStateColor = Boolean(
        pixel && pixel[3] === 255 && expected && colors.has(marker.fillStyle.toLowerCase())
        && pixel[0] === expected[0] && pixel[1] === expected[1] && pixel[2] === expected[2],
      )
      return { x, y, radius: marker.radius, fillStyle: marker.fillStyle, frame: marker.frame, pixel, opaqueStateColor }
    })
    const passed = Boolean(target.isConnected && auditFrame > 0 && completeCanvasVisible && visibleMarkers.length === 11
      && samples.every(sample => sample.opaqueStateColor))
    return {
      passed,
      currentDocument: location.href,
      connected: target.isConnected,
      canvas: { width: target.width, height: target.height, rect: target.getBoundingClientRect().toJSON() },
      clip,
      completeCanvasVisible,
      dpr,
      frame: auditFrame,
      markerCount: markers.length,
      visibleMarkerCount: visibleMarkers.length,
      samples,
    }
  })
}

async function installRrgArcAudit(page: Page) {
  await page.addInitScript(() => {
    type MarkerArc = { x: number; y: number; radius: number; fillStyle: string; frame: number }
    type AuditedCanvas = HTMLCanvasElement & { __rrgLatestMarkerDraw?: MarkerArc[]; __rrgAuditFrame?: number }
    type AuditedContext = CanvasRenderingContext2D & { __rrgPendingMarkerArcs?: Array<{ x: number; y: number; radius: number }> }
    const prototype = CanvasRenderingContext2D.prototype
    const originalArc = prototype.arc
    const originalFill = prototype.fill
    const originalClearRect = prototype.clearRect
    const originalBeginPath = prototype.beginPath
    const isRrgCanvas = (context: CanvasRenderingContext2D) => Boolean(context.canvas.closest('.rotation-tool__plot-shell'))

    prototype.clearRect = function (..._args: Parameters<typeof originalClearRect>) {
      if (isRrgCanvas(this)) {
        const canvas = this.canvas as AuditedCanvas
        canvas.__rrgAuditFrame = (canvas.__rrgAuditFrame ?? 0) + 1
        canvas.__rrgLatestMarkerDraw = []
      }
      return Reflect.apply(originalClearRect, this, arguments)
    }
    prototype.beginPath = function (..._args: Parameters<typeof originalBeginPath>) {
      if (isRrgCanvas(this)) (this as AuditedContext).__rrgPendingMarkerArcs = []
      return Reflect.apply(originalBeginPath, this, arguments)
    }
    prototype.arc = function (...args: Parameters<typeof originalArc>) {
      if (isRrgCanvas(this)) {
        const [x, y, radius] = args
        const context = this as AuditedContext
        ;(context.__rrgPendingMarkerArcs ??= []).push({ x, y, radius })
      }
      return Reflect.apply(originalArc, this, arguments)
    }
    prototype.fill = function (...args: Parameters<typeof originalFill>) {
      if (isRrgCanvas(this)) {
        const context = this as AuditedContext
        const canvas = this.canvas as AuditedCanvas
        const pending = context.__rrgPendingMarkerArcs ?? []
        for (const marker of pending) {
          canvas.__rrgLatestMarkerDraw ??= []
          canvas.__rrgLatestMarkerDraw.push({ ...marker, fillStyle: String(this.fillStyle), frame: canvas.__rrgAuditFrame ?? 0 })
        }
        context.__rrgPendingMarkerArcs = []
      }
      return Reflect.apply(originalFill, this, arguments)
    }
  })
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

async function assertUsefulTool(page: Page, title: string, kind: typeof TOOL_OUTCOMES[string], configuration: Record<string, unknown> = {}) {
  const tool = await activatePanel(page, title)
  if (kind === 'watchlist') {
    const rows = tool.locator('.watchlist__row')
    const spyRow = tool.getByRole('option', { name: /^SPY\s/ })
    const emptyPersonalList = tool.getByText('No personal watchlists available.', { exact: true })
    await expect.poll(async () => (await rows.count()) > 0 || await emptyPersonalList.isVisible()).toBe(true)
    if (title === 'WatchList' && await spyRow.count() === 0) {
      if (await rows.count() === 0) {
        const listName = `Factory journey ${Date.now()}`
        await tool.getByLabel('Personal watchlist name').fill(listName)
        const createResponsePromise = page.waitForResponse(response => {
          const request = response.request()
          const url = new URL(response.url())
          if (request.method() !== 'POST' || url.pathname !== '/api/v1/watchlists') return false
          try {
            return request.postDataJSON()?.name === listName
          } catch {
            return false
          }
        })
        await tool.getByRole('button', { name: 'Create personal watchlist', exact: true }).click()
        const createResponse = await createResponsePromise
        expect(createResponse.status()).toBe(200)
        const createdList = await createResponse.json() as { id: number; name: string }
        expect(Number.isInteger(createdList.id)).toBe(true)
        expect(createdList.name).toBe(listName)
        const personalList = tool.getByLabel('Personal watchlist', { exact: true })
        await expect(personalList.locator(`option[value="${createdList.id}"]`)).toHaveText(listName, { timeout: 15_000 })
        await expect(personalList).toHaveValue(String(createdList.id), { timeout: 15_000 })
      }
      await tool.getByRole('textbox', { name: 'Add symbol to personal watchlist', exact: true }).fill('SPY')
      const selectedListId = await tool.getByLabel('Personal watchlist', { exact: true }).inputValue()
      expect(Number.isInteger(Number(selectedListId))).toBe(true)
      const addResponsePromise = page.waitForResponse(response => response.request().method() === 'POST'
        && new URL(response.url()).pathname === `/api/v1/watchlists/${selectedListId}/items`)
      await tool.getByRole('button', { name: 'Add symbol to personal watchlist', exact: true }).click()
      const addResponse = await addResponsePromise
      expect(addResponse.status()).toBe(200)
      const addedItem = await addResponse.json() as { id: number; instrument_id: number; symbol?: string | null }
      expect(Number.isInteger(addedItem.id)).toBe(true)
      expect(Number.isInteger(addedItem.instrument_id)).toBe(true)
      expect(addedItem.symbol).toBe('SPY')
      await expect(spyRow).toBeVisible({ timeout: 20_000 })
    }
    const firstRow = rows.first()
    await expect(firstRow).toBeVisible({ timeout: 20_000 })
    await expect.poll(() => rows.count()).toBeGreaterThan(0)
    await expect(firstRow).toHaveAttribute('aria-label', /^[A-Z0-9._-]+ .+\. Position 1 of \d+\./)
    await expect(firstRow).not.toContainText(/Loading|Unavailable/i)
    if (title === 'WatchList' || title === 'Fundamentals WatchList') {
      await expect(firstRow).toHaveAttribute('aria-label', /SPY .+Last:.*\d/)
    } else if (title === 'My Favorites') {
      await expect(spyRow).toBeVisible({ timeout: 20_000 })
      await assertFavoritePriceAndReturnAgainstCanonicalApi(page, tool, spyRow)
    } else {
      await assertUsefulWatchlistNumbers(tool)
    }
  } else if (kind === 'industry') {
    const industryList = tool.locator('.industry-list')
    await expect(industryList, `${title} should render its dated industry ranking, not watchlist placeholders`).toBeVisible({ timeout: 30_000 })
    const provenance = industryList.locator('.industry-list__provenance')
    await expect(provenance).toBeVisible()
    await expect(provenance).toContainText(/holdings ·/)
    const industryRows = industryList.getByRole('button')
    const usefulIndustryIndex = async () => industryRows.evaluateAll(rows => rows.findIndex(row => {
      const label = row.getAttribute('aria-label') ?? ''
      const match = label.match(/, (\d+) of (\d+) constituents resolved,.*Classification source: ([^.]*)\./)
      return Boolean(match && Number(match[1]) > 0 && Number(match[2]) >= Number(match[1]) && match[3].trim())
    }))
    await expect.poll(async () => {
      return (await industryRows.count()) > 0 ? usefulIndustryIndex() : -1
    }, { timeout: 30_000 }).toBeGreaterThanOrEqual(0)
    const classifiedIndustry = industryRows.nth(await usefulIndustryIndex())
    await expect(classifiedIndustry).toBeVisible()
    await expect(classifiedIndustry.locator('.industry-list__classification')).not.toContainText(/unknown|unclassified/i)
  } else if (kind === 'chart' || kind === 'ratio') {
    const expectedTimeframe = typeof configuration.timeframe === 'string' ? configuration.timeframe : null
    if (expectedTimeframe) await expect(tool.getByLabel(`${title} timeframe`, { exact: true })).toHaveValue(expectedTimeframe)
    const plot = kind === 'chart' ? tool.locator('.chart-tool .uplot canvas').first() : tool.locator('.ratio-chart__host canvas').first()
    await expect(plot).toBeVisible({ timeout: 20_000 })
    const seriesColors = kind === 'chart' ? [[38, 166, 154], [239, 83, 80]] as Array<[number, number, number]> : [[107, 192, 239]] as Array<[number, number, number]>
    await expect.poll(() => plottedSeriesPixels(plot, seriesColors), { timeout: 30_000 }).toBeGreaterThan(20)
    if (kind === 'ratio') {
      await expect(tool.locator('.ratio-chart__state')).toHaveCount(0)
      const expression = typeof configuration.expression === 'string' ? configuration.expression : ''
      const denominator = expression.match(/^=\s*[A-Z0-9._-]+\s*\/\s*([A-Z0-9._-]+)\s*$/)?.[1]
      if (denominator) await expect(tool.locator('.ratio-chart__chip').filter({ hasText: denominator })).toBeVisible()
    } else {
      const comparisons = Array.isArray(configuration.comparison_symbols) ? configuration.comparison_symbols.filter((symbol): symbol is string => typeof symbol === 'string') : []
      for (const symbol of comparisons) await expect(tool.locator('.chart-tool__compare').getByRole('button', { name: new RegExp(`^Remove ${escapeRegExp(symbol)}$`) })).toBeVisible()
    }
  } else if (kind === 'technicals') {
    const metrics = tool.locator('.metrics').first()
    await expect(metrics).toBeVisible({ timeout: 20_000 })
    await expect(metrics).toContainText(/\d/)
    await expect(metrics).not.toContainText(/Loading|No canonical instrument/i)
  } else if (kind === 'breadth') {
    const breadth = tool.locator('.breadth-tool')
    await expect(breadth).toBeVisible({ timeout: 20_000 })
    await expect(breadth).toHaveAttribute('aria-busy', 'false', { timeout: 30_000 })
    await expect(breadth.locator('.breadth-tool__coverage-detail')).toContainText(/\d/)
  } else if (kind === 'coverage') {
    const coverage = tool.locator('.coverage-summary')
    await expect(coverage).toBeVisible({ timeout: 20_000 })
    const publicActiveSymbol = page.getByRole('combobox', { name: 'Active symbol', exact: true })
    await expect(publicActiveSymbol).toBeVisible()
    const activeSymbol = (await publicActiveSymbol.inputValue()).trim().toUpperCase()
    expect(activeSymbol).toMatch(/^[A-Z0-9._-]+$/)
    await expect(coverage).toHaveAttribute('aria-label', `${activeSymbol} coverage`)
    const canonicalCoverageRead = await authenticatedJson(page, `/api/v1/coverage/instruments/${encodeURIComponent(activeSymbol)}`)
    expect(canonicalCoverageRead.status).toBe(200)
    const canonicalCoverage = canonicalCoverageRead.body as {
      local_coverage?: Record<string, { oldest?: string | null; newest?: string | null; bar_count?: number }>
    }
    const canonicalDaily = canonicalCoverage.local_coverage?.D1
    expect(canonicalDaily?.oldest).toBeTruthy()
    expect(canonicalDaily?.newest).toBeTruthy()
    expect(Number.isInteger(canonicalDaily?.bar_count)).toBe(true)
    expect(canonicalDaily!.bar_count).toBeGreaterThan(0)
    await expect(coverage.getByText('Canonical instrument', { exact: true }).locator('..').locator('strong')).toHaveText(activeSymbol)
    const dailyGrid = coverage.locator('.coverage-summary__grid')
    await expect(dailyGrid).toBeVisible({ timeout: 20_000 })
    const dailyBarCount = Number((await dailyGrid.locator('b').first().innerText()).replaceAll(',', ''))
    expect(dailyBarCount, 'coverage must report the exact canonical local daily bar count for the current active symbol').toBe(canonicalDaily!.bar_count)
    await expect(coverage.locator('.coverage-summary__note')).toContainText('Local canonical data only')
  } else if (kind === 'notes') {
    const note = tool.getByRole('textbox', { name: 'Instrument note' })
    const content = `Lifecycle note ${Date.now()}`
    await note.fill(content)
    await expect(tool.locator('.note-tool__status')).toContainText(/Saved/, { timeout: 10_000 })
    await expect(note).toHaveValue(content)
  } else if (kind === 'alerts') {
    const form = tool.getByRole('form', { name: 'Create instrument alert' })
    await expect(form.getByLabel('Alert price')).toBeEnabled({ timeout: 20_000 })
    await form.getByLabel('Alert price').fill('1')
    await form.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(tool.getByRole('list', { name: 'Saved alerts' })).toContainText(/1\.00|1/)
  } else if (kind === 'scan') {
    const conditionName = `Lifecycle ${Date.now()}`
    await tool.getByLabel('Condition name').fill(conditionName)
    await expect(tool.getByLabel('Comparison')).toBeVisible()
    await expect(tool.getByLabel('Scan universe')).toHaveValue('all')
    await tool.getByLabel('Condition threshold').fill('1')
    await tool.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(tool.getByLabel('Saved condition')).toContainText(conditionName, { timeout: 10_000 })
    const instruments = await authenticatedJson(page, '/api/v1/instruments/search?q=SPY&canonical_only=true')
    expect(instruments.status).toBe(200)
    const instrumentId = Number((instruments.body as Array<{ instrument_id: number }>)[0]?.instrument_id)
    expect(Number.isInteger(instrumentId)).toBe(true)
    await tool.getByLabel('Scan universe').selectOption('custom')
    await tool.getByLabel('Scan universe value').fill(String(instrumentId))
    const scanName = `Lifecycle Gauge ${Date.now()}`
    await tool.getByLabel('Scan name').fill(scanName)
    const runResponsePromise = page.waitForResponse(response =>
      response.request().method() === 'POST' && /^\/api\/v1\/screeners\/\d+\/run$/.test(new URL(response.url()).pathname),
      { timeout: 30_000 },
    )
    await tool.getByRole('button', { name: 'Run', exact: true }).click()
    const runResponse = await runResponsePromise
    expect(runResponse.ok(), 'the ordinary EasyScan run request must be accepted').toBe(true)
    const runPath = new URL(runResponse.url()).pathname
    const scanId = Number(runPath.match(/^\/api\/v1\/screeners\/(\d+)\/run$/)?.[1])
    expect(Number.isSafeInteger(scanId) && scanId > 0).toBe(true)
    const createdResult = await runResponse.json() as { id?: number }
    const resultId = Number(createdResult.id)
    expect(Number.isSafeInteger(resultId) && resultId > 0).toBe(true)
    const terminalResult = await waitForTerminalEasyScanResult(page, scanId, resultId)
    const terminalCoverage = terminalResult.result_data?._coverage as { evaluated_count: number; universe_count: number }
    const terminalMatches = terminalResult.matched_ids?.length ?? 0

    await expect(tool.locator('.easy-scan__result')).toBeVisible({ timeout: 30_000 })
    await expect(tool.locator('.easy-scan__result')).toContainText(/\d+\/\d+ evaluated/)
    await expect(tool.locator('.easy-scan__result')).not.toContainText('0/0 evaluated')
    const scanSummary = (await tool.locator('.easy-scan__result > span').first().innerText()).match(/(\d+) matches · (\d+)\/(\d+) evaluated/)
    expect(scanSummary).not.toBeNull()
    expect(Number(scanSummary![1])).toBe(terminalMatches)
    expect(Number(scanSummary![2])).toBe(terminalCoverage.evaluated_count)
    expect(Number(scanSummary![3])).toBe(terminalCoverage.universe_count)
    expect(terminalCoverage.evaluated_count).toBeGreaterThan(0)
    expect(terminalCoverage.universe_count).toBeGreaterThanOrEqual(terminalCoverage.evaluated_count)
    expect(terminalMatches).toBeLessThanOrEqual(terminalCoverage.evaluated_count)
    retainedGaugeScanName = scanName
    return { tool, scanName }
  } else if (kind === 'gauge') {
    await expect(tool.getByRole('region', { name: 'Market Gauge' })).toBeVisible()
    const scanSelect = tool.getByLabel('Saved EasyScan')
    await expect(scanSelect).toBeVisible()
    await expect(scanSelect.locator('option')).not.toHaveCount(1)
    expect(retainedGaugeScanName, 'the preceding EasyScan case must have run and retained a result').toBeTruthy()
    await scanSelect.selectOption({ label: retainedGaugeScanName })
    const reading = tool.locator('.market-gauge__reading b')
    await expect(reading).toBeVisible({ timeout: 30_000 })
    await expect.poll(async () => Number.isFinite(Number.parseFloat((await reading.innerText()).replace('%', '')))).toBe(true)
    await expect(reading).not.toHaveText('—')
    const coverage = tool.locator('p').filter({ hasText: /evaluated · .*excluded/ })
    await expect(coverage).toBeVisible()
    const counts = (await coverage.innerText()).match(/(\d+)\/(\d+) evaluated · (\d+) excluded/)
    expect(counts).not.toBeNull()
    expect(Number(counts![1])).toBeGreaterThan(0)
    expect(Number(counts![2])).toBeGreaterThanOrEqual(Number(counts![1]))
    const matches = Number((await tool.locator('.market-gauge__reading span').innerText()).match(/\d+/)?.[0])
    expect(matches).toBeLessThanOrEqual(Number(counts![1]))
    await expect(reading).toHaveText(`${((matches / Number(counts![1])) * 100).toFixed(1)}%`)
  } else if (kind === 'rotation') {
    const plot = tool.getByRole('group', { name: 'Relative rotation trend and momentum plane' })
    await expect(plot).toBeVisible({ timeout: 30_000 })
    const canvas = plot.locator('canvas')
    await expect(canvas).toBeVisible()

    const settings = tool.locator('.rotation-tool__settings')
    const settingsSummary = settings.locator('summary')
    await expect(settingsSummary).toHaveText('Settings')
    if (await settings.getAttribute('open') === null) await settingsSummary.click()
    await expect(settings).toHaveAttribute('open', '')
    const timeframe = tool.getByRole('combobox', { name: 'Rotation timeframe', exact: true })
    if (typeof configuration.timeframe === 'string') {
      await expect(timeframe).toHaveValue(configuration.timeframe)
    }

    const rowsDisclosure = tool.locator('.rotation-tool__rows-disclosure')
    const rowsSummary = rowsDisclosure.locator('summary')
    await expect(rowsSummary).toContainText('Rows')
    if (await rowsDisclosure.getAttribute('open') === null) await rowsSummary.click()
    await expect(rowsDisclosure).toHaveAttribute('open', '')
    const rows = tool.getByRole('region', { name: 'Relative rotation rows' }).locator('.rotation-tool__row')
    await expect(rows.first()).toBeVisible({ timeout: 30_000 })
    await expect(rows).not.toHaveCount(0)
    await plot.focus()
    await page.keyboard.press('Home')
    const tooltip = tool.locator('.rotation-tool__tooltip')
    await expect(tooltip).toBeVisible()
    await expect(tooltip.locator('strong')).not.toBeEmpty()
    await expect(tooltip).toContainText(/Trend .*Momentum/)
    await page.keyboard.press('ArrowRight')
    await expect(tooltip).toBeVisible()

    await rowsSummary.click()
    await expect(rowsDisclosure).not.toHaveAttribute('open', '')
    await settingsSummary.click()
    await expect(settings).not.toHaveAttribute('open', '')
    await expect(plot).toBeVisible()
    await expect.poll(() => readRrgMarkerAudit(canvas), { timeout: 30_000 }).toMatchObject({ passed: true })
  } else if (kind === 'map') {
    const tiles = tool.locator('.market-map-tool__tiles')
    await expect(tiles).toBeVisible({ timeout: 30_000 })
    const tile = tiles.locator('.market-map-tool__tile').first()
    await expect(tile).toBeVisible()
    await tile.click()
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
  } else if (kind === 'study') {
    await tool.getByLabel('Factory study').selectOption('positive_streak')
    // The offline positive factory witness uses the retained controlled D1
    // range. An unbounded request can legitimately remain held when external
    // providers are disabled; this journey must exercise real supported data.
    const studyStartDate = '2024-01-01'
    const studyEndDate = '2025-12-29'
    await tool.getByLabel('Study start date').fill(studyStartDate)
    await tool.getByLabel('Study end date').fill(studyEndDate)
    await tool.getByRole('button', { name: 'Validate study' }).click()
    await expect(tool).toContainText('Validated for isolated execution', { timeout: 20_000 })
    const studyRunRequest = page.waitForRequest(request => request.method() === 'POST'
      && new URL(request.url()).pathname.endsWith('/research/runs'))
    await tool.getByRole('button', { name: 'Run study' }).click()
    const studyRunBody = (await studyRunRequest).postDataJSON() as {
      run_config?: { start_date?: string; end_date?: string }
      dataset_manifest?: { start_date?: string; end_date?: string }
    }
    expect(studyRunBody).toMatchObject({
      run_config: { start_date: studyStartDate, end_date: studyEndDate },
      dataset_manifest: { start_date: studyStartDate, end_date: studyEndDate },
    })
    await expect(tool.locator('[aria-label^="Study run status:"]')).toHaveAttribute('data-status', 'completed', { timeout: 45_000 })
    const currentStreak = tool.getByRole('status', { name: 'current_streak metric', exact: true })
    await expect(currentStreak).toBeVisible()
    await expect.poll(async () => {
      const value = (await currentStreak.locator('strong').innerText()).trim()
      return /^-?\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value))
    }).toBe(true)
    const completedStreaks = tool.getByRole('article', { name: 'completed_streaks table result', exact: true })
    await expect(completedStreaks).toBeVisible()
    await expect(completedStreaks.locator('table caption')).toHaveText('completed_streaks table')
    await expect(completedStreaks.locator('table tbody tr').first()).toBeVisible()
  } else if (kind === 'results') {
    await expect(tool.locator('.research-results-tool__run-select').first()).toBeVisible({ timeout: 30_000 })
    await expect(tool.locator('.research-results-tool__artifacts article').first()).toBeVisible({ timeout: 20_000 })
  } else if (kind === 'library') {
    await tool.getByRole('button', { name: 'New', exact: true }).click()
    const create = tool.getByRole('form', { name: 'Create Python asset' })
    const assetName = `Factory journey ${Date.now()}`
    await create.getByLabel('New Python asset name').fill(assetName)
    await create.getByLabel('New Python asset key').fill(`factory-journey-${Date.now()}`)
    await create.getByLabel('New Python asset kind').selectOption('study')
    const librarySource = create.getByRole('textbox', { name: 'New Python asset source', exact: true })
    await expect(librarySource).toBeVisible()
    await librarySource.fill("output.scalar('catalogue_value', 1)")
    await create.getByRole('button', { name: 'Validate', exact: true }).click()
    await expect(create).toContainText('Validated', { timeout: 20_000 })
    await create.getByRole('button', { name: 'Create asset', exact: true }).click()
    await expect(tool.locator('.code-library-tool__assets')).toContainText(assetName, { timeout: 20_000 })
  } else if (kind === 'report') {
    await expect(tool.locator('.instrument-report')).toBeVisible({ timeout: 20_000 })
    await expect(tool.locator('.instrument-report')).not.toContainText(/Loading|No instrument selected/i)
  }
  return tool
}

async function watchlistConfigurationSignature(tool: ReturnType<Page['locator']>) {
  const [columns, members] = await Promise.all([
    tool.locator('.watchlist__header button').evaluateAll(elements => elements.map(element => element.getAttribute('aria-label'))),
    tool.locator('.watchlist__row').evaluateAll(elements => elements.map(element => {
      const label = element.getAttribute('aria-label') ?? ''
      const match = label.match(/^(.+?)\. Position (\d+) of (\d+)\./)
      return {
        identity: match?.[1] ?? null,
        position: Number(element.getAttribute('aria-posinset')),
        count: Number(element.getAttribute('aria-setsize')),
      }
    })),
  ])
  return { columns, members }
}

async function assertUsefulWatchlistNumbers(tool: ReturnType<Page['locator']>) {
  const numericCells = tool.locator('.watchlist__row .watchlist__cell--positive, .watchlist__row .watchlist__cell--negative, .watchlist__row .watchlist__cell--zero')
  await expect.poll(async () => {
    const values = await numericCells.allTextContents()
    return values.filter(value => {
      const normalized = value.trim()
      return /^-?\d+(?:\.\d+)?%$/.test(normalized) && Number.isFinite(Number(normalized.slice(0, -1)))
    }).length
  }, { timeout: 30_000 }).toBeGreaterThanOrEqual(2)
}

async function assertFavoritePriceAndReturnAgainstCanonicalApi(page: Page, tool: ReturnType<Page['locator']>, row: ReturnType<Page['locator']>) {
  const canonical = await authenticatedJson(page, '/api/v1/ohlcv/local/SPY/D1?limit=31')
  expect(canonical.status).toBe(200)
  const bars = canonical.body as Array<{ close?: number }>
  expect(bars.length).toBeGreaterThanOrEqual(2)
  const latest = Number(bars.at(-1)?.close)
  const previous = Number(bars.at(-2)?.close)
  expect(Number.isFinite(latest) && latest > 0).toBe(true)
  expect(Number.isFinite(previous) && previous > 0).toBe(true)

  const headerLabels = await tool.locator('.watchlist__header button').evaluateAll(buttons =>
    buttons.map(button => button.getAttribute('aria-label') ?? ''),
  )
  expect(headerLabels).toEqual(expect.arrayContaining(['Sort by Last', 'Sort by Chg %']))
  const accessibleRow = await row.getAttribute('aria-label')
  expect(accessibleRow).toBeTruthy()
  const priceText = accessibleRow!.match(/(?:^|\. )Last: ([\d,]+(?:\.\d+)?)(?:\.|$)/)?.[1]
  const returnText = accessibleRow!.match(/(?:^|\. )Chg %: (-?[\d,]+(?:\.\d+)?)%(?:\.|$)/)?.[1]
  expect(priceText, 'the configured Last column must expose a finite value').toBeTruthy()
  expect(returnText, 'the configured Chg % column must expose a finite return').toBeTruthy()
  expect(Number(priceText!.replaceAll(',', ''))).toBe(Number(latest.toFixed(2)))
  expect(Number(returnText!.replaceAll(',', ''))).toBe(Number((((latest - previous) / previous) * 100).toFixed(2)))
}

async function waitForTerminalEasyScanResult(page: Page, scanId: number, resultId: number) {
  let terminal: {
    id?: number
    matched_ids?: number[]
    result_data?: Record<string, any>
  } | null = null
  await expect.poll(async () => {
    const response = await authenticatedJson(page, `/api/v1/screeners/${scanId}/results?limit=10`)
    expect(response.status).toBe(200)
    const results = response.body as Array<{ id?: number; matched_ids?: number[]; result_data?: Record<string, any> }>
    const current = results.find(result => Number(result.id) === resultId)
    if (!current) return false
    const status = String(current.result_data?._status ?? '')
    if (status === 'failed' || status === 'canceled') throw new Error(`EasyScan result ${resultId} ended ${status}`)
    const coverage = current.result_data?._coverage as { evaluated_count?: number; universe_count?: number } | undefined
    if (status !== 'completed' || !coverage || !Number.isInteger(coverage.evaluated_count)
      || !Number.isInteger(coverage.universe_count) || Number(coverage.evaluated_count) <= 0
      || Number(coverage.universe_count) < Number(coverage.evaluated_count)) return false
    terminal = current
    return true
  }, { timeout: 60_000, intervals: [250, 500, 1_000] }).toBe(true)
  return terminal!
}

function isWorkspaceSnapshotWithTab(request: import('@playwright/test').Request, stableKey: string, name: string) {
  if (request.method() !== 'PUT' || !/^\/api\/v1\/workspaces\/\d+\/snapshot$/.test(new URL(request.url()).pathname)) return false
  let body: { tabs?: Array<{ stable_key?: string; name?: string }> }
  try {
    body = request.postDataJSON() as typeof body
  } catch {
    return false
  }
  return body.tabs?.some(tab => tab.stable_key === stableKey && tab.name === name) ?? false
}

test.describe('Workstation lifecycle journeys', () => {
  test.beforeEach(async ({ page }) => {
    await installRrgArcAudit(page)
  })

  test('duplicates a factory layout with remapped panels, preserves the original, and reloads both', async ({ page, loggedIn, browserDiagnostics }) => {
    test.setTimeout(300_000)
    retainedGaugeScanName = ''
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    const original = page.getByRole('tab', { name: 'US Top Down', exact: true })
    const originalKey = await original.getAttribute('data-tab-key')
    expect(originalKey).toBeTruthy()
    const originalPanelTitles = await page.locator('.lm_tab').allTextContents()
    const originalWindowKey = await page.locator('.tool-window').first().getAttribute('data-window-key')
    expect(originalWindowKey).toBeTruthy()
    expect(originalPanelTitles).toEqual(expect.arrayContaining(['Benchmarks', 'Chart', 'Relative Rotation']))

    const { workspace } = await assertCanonicalCoverage(page)
    await assertFactoryLayouts(page, workspace.tabs)
    const usTopDown = workspace.tabs.find(layout => layout.name === 'US Top Down')
    expect(usTopDown, 'the authenticated default US Top Down layout is required').toBeDefined()
    await activateLayout(page, usTopDown!.name)

    await page.getByRole('button', { name: 'Duplicate layout', exact: true }).click()
    const copied = page.getByRole('tab', { name: 'US Top Down Copy', exact: true })
    await expect(copied).toBeVisible()
    const copiedKey = await copied.getAttribute('data-tab-key')
    expect(copiedKey).toBeTruthy()
    expect(copiedKey).not.toBe(originalKey)
    const copiedWindowKey = await page.locator('.tool-window').first().getAttribute('data-window-key')
    expect(copiedWindowKey).toBeTruthy()
    expect(copiedWindowKey).not.toBe(originalWindowKey)

    for (const window of usTopDown!.windows) {
      const outcome = TOOL_OUTCOMES[window.title]
      expect(outcome, `the copied ${window.title} panel needs a useful-outcome assertion`).toBeTruthy()
      await assertUsefulTool(page, window.title, outcome)
    }
    const copiedSemanticTitles = await page.locator('.lm_tab').allTextContents()
    expect(copiedSemanticTitles).toEqual(expect.arrayContaining(usTopDown!.windows.map(window => window.title)))

    await original.click()
    await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await page.reload()
    await expect(page.getByRole('tab', { name: 'US Top Down', exact: true })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'US Top Down Copy', exact: true })).toBeVisible()
    await page.getByRole('tab', { name: 'US Top Down Copy', exact: true }).click()
    await assertUsefulTool(page, 'Relative Rotation', 'rotation')
    await page.getByRole('tab', { name: 'US Top Down', exact: true }).click()
    await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('closes and recreates every factory tool through the public catalogue with useful defaults', async ({ page, loggedIn, browserDiagnostics }) => {
    test.setTimeout(240_000)
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    retainedGaugeScanName = ''
    const { catalogue, workspace } = await assertCanonicalCoverage(page)
    await activateLayout(page, 'US Top Down')
    const usTopDown = workspace.tabs.find(layout => layout.name === 'US Top Down')!
    const chartTool = await activatePanel(page, 'Chart')
    const favoriteStar = chartTool.getByRole('button', { name: 'Add SPY to My Favorites', exact: true })
    await expect(favoriteStar, 'create the empty Favorites prerequisite through the public Chart star action').toBeVisible()
    await favoriteStar.click()
    await expect(chartTool.getByRole('button', { name: 'Remove SPY from My Favorites', exact: true })).toHaveAttribute('aria-pressed', 'true')
    for (const item of catalogue.tools) {
      const kind = TOOL_OUTCOMES[item.title]
      expect(kind, `missing useful-result mapping for ${item.title}`).toBeTruthy()
      const factoryKeys = new Set([item.key, ...(FACTORY_INSTANCE_KEYS_BY_CATALOGUE_KEY[item.key] ?? [])])
      const existingFactoryWindow = usTopDown.windows.find(window => window.tool_type === item.tool_type && factoryKeys.has(window.instance_key))
      if (existingFactoryWindow) {
        const existingFactoryTool = page.locator(`.tool-window[data-window-key="${escapeRegExp(existingFactoryWindow.instance_key)}"]`)
        if (await existingFactoryTool.count()) {
          await activatePanel(page, existingFactoryWindow.title)
          await existingFactoryTool.getByRole('button', { name: 'Close tool', exact: true }).click()
          await expect(existingFactoryTool).toHaveCount(0)
        }
      }

      await page.getByRole('button', { name: 'Add tool', exact: true }).click()
      const catalogue = page.getByRole('menu', { name: 'Workstation tools' })
      await expect(catalogue).toBeVisible()
      await catalogue.getByRole('menuitem', { name: item.title, exact: true }).click()
      await assertUsefulTool(page, item.title, kind)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('renames, reorders, cancels and confirms layout deletion, then undoes and reloads', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    await page.getByRole('button', { name: 'Duplicate layout', exact: true }).click()
    const layoutMenu = await openWorkspaceMenu(page)
    const renamed = `Review ${Date.now()}`
    // The row's menu-item name changes as soon as its input is filled. Map the
    // copied tab's stable key to the parallel menu-row position before editing.
    const copiedTab = page.getByRole('tab', { name: 'US Top Down Copy', exact: true })
    const copiedTabKey = await copiedTab.getAttribute('data-tab-key')
    expect(copiedTabKey).toBeTruthy()
    const copiedLayoutIndex = await page.locator('.workstation__tabs > [role="tab"]').evaluateAll((tabs, stableKey) => tabs.findIndex(tab => tab.getAttribute('data-tab-key') === stableKey), copiedTabKey!)
    expect(copiedLayoutIndex, 'the copied stable tab key should map to its layout-menu row').toBeGreaterThanOrEqual(0)
    // Resolve the textbox by its stable position before changing the name.
    // Do not scope through the layout's menuitem/accessibility name: filling
    // this textbox immediately changes that name while the locator is live.
    const renameField = layoutMenu.getByRole('textbox', { name: 'Rename layout', exact: true }).nth(copiedLayoutIndex)
    await expect(renameField).toHaveValue('US Top Down Copy')
    await renameField.fill(renamed)
    await expect(renameField).toHaveValue(renamed)
    await renameField.press('Tab')
    const renamedTab = page.getByRole('tab', { name: renamed, exact: true })
    await expect(renamedTab).toBeVisible()
    const renamedKey = await renamedTab.getAttribute('data-tab-key')
    expect(renamedKey).toBeTruthy()
    await page.keyboard.press('Escape')

    const beforeOrder = await page.locator('.workstation__tabs > [role="tab"]').allTextContents()
    const first = await page.locator('.workstation__tabs > [role="tab"]').first().boundingBox()
    const last = await page.locator('.workstation__tabs > [role="tab"]').last().boundingBox()
    expect(first).not.toBeNull()
    expect(last).not.toBeNull()
    await page.mouse.move(last!.x + last!.width / 2, last!.y + last!.height / 2)
    await page.mouse.down()
    await page.mouse.move(first!.x + first!.width / 2, first!.y + first!.height / 2, { steps: 6 })
    await page.mouse.up()
    await expect.poll(() => page.locator('.workstation__tabs > [role="tab"]').allTextContents()).not.toEqual(beforeOrder)

    page.once('dialog', dialog => dialog.dismiss())
    const deleteMenu = await openWorkspaceMenu(page)
    await deleteMenu.getByRole('button', { name: `Delete layout ${renamed}`, exact: true }).click()
    await expect(renamedTab).toBeVisible()

    page.once('dialog', dialog => dialog.accept())
    const confirmMenu = await openWorkspaceMenu(page)
    await confirmMenu.getByRole('button', { name: `Delete layout ${renamed}`, exact: true }).click()
    await expect(renamedTab).toHaveCount(0)
    const recovery = page.locator('.workstation__layout-recovery')
    await expect(recovery).toContainText(renamed)
    const recoverySnapshotRequest = page.waitForRequest(request => isWorkspaceSnapshotWithTab(request, renamedKey!, renamed))
    await recovery.getByRole('menuitem', { name: 'Undo', exact: true }).click()
    await expect(renamedTab).toBeVisible()
    const snapshotRequest = await recoverySnapshotRequest
    const snapshotResponse = await snapshotRequest.response()
    expect(snapshotResponse).not.toBeNull()
    expect(snapshotResponse?.ok()).toBe(true)
    const persistedWorkspace = await snapshotResponse!.json() as { tabs?: Array<{ stable_key?: string; name?: string }> }
    expect(persistedWorkspace.tabs?.some(tab => tab.stable_key === renamedKey && tab.name === renamed)).toBe(true)
    const saveStatus = page.getByRole('status', { name: 'Workspace save status', exact: true })
    await expect(saveStatus).toHaveAttribute('data-state', 'saved')
    await expect(saveStatus).toHaveText('Workspace saved')
    await page.reload()
    await expect(renamedTab).toBeVisible()
    await expect(page.locator('.workstation__tabs > [role="tab"]')).toHaveCount(beforeOrder.length)
    await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('duplicates and safely deletes a workspace while preserving its source and tool content through resize and maximize', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    const originalViewport = page.viewportSize()
    expect(originalViewport).not.toBeNull()
    const sourceName = await page.locator('.workstation__workspace-name').textContent()
    expect(sourceName?.trim()).toBe('US Top Down')
    const sourceBenchmarks = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await assertUsefulWatchlistNumbers(sourceBenchmarks)
    const sourceConfiguration = await watchlistConfigurationSignature(sourceBenchmarks)
    expect(sourceConfiguration.members.length).toBeGreaterThan(0)
    expect(sourceConfiguration.members.every(member => member.identity && member.position > 0 && member.count > 0)).toBe(true)

    const menu = await openWorkspaceMenu(page)
    await menu.getByRole('menuitem', { name: 'Duplicate workspace', exact: true }).click()
    const duplicateName = 'US Top Down Copy'
    await expect(page.locator('.workstation__workspace-name')).toHaveText(duplicateName)
    const duplicateBenchmarks = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await assertUsefulWatchlistNumbers(duplicateBenchmarks)
    expect(await watchlistConfigurationSignature(duplicateBenchmarks)).toEqual(sourceConfiguration)

    page.once('dialog', dialog => dialog.dismiss())
    const cancelMenu = await openWorkspaceMenu(page)
    await cancelMenu.getByRole('menuitem', { name: 'Delete workspace', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText(duplicateName)
    await expect((await openWorkspaceMenu(page)).getByRole('option', { name: duplicateName, exact: true })).toBeVisible()

    const chart = await activatePanel(page, 'Chart')
    const canvas = chart.locator('.uplot canvas').first()
    await expect(canvas).toBeVisible({ timeout: 20_000 })
    const splitters = page.locator('.workspace-layout-host .lm_splitter.lm_vertical')
    await expect.poll(() => splitters.count(), { timeout: 15_000 }).toBeGreaterThan(0)
    const splitter = splitters.first()
    const beforeSize = await splitter.evaluate(element => {
      const parent = element.parentElement!
      const siblings = Array.from(parent.children)
      const index = siblings.indexOf(element)
      const before = siblings.slice(0, index).filter(child => child.classList.contains('lm_item')) as HTMLElement[]
      return { rect: element.getBoundingClientRect().toJSON(), before: before.map(pane => pane.getBoundingClientRect().height) }
    })
    expect(beforeSize.rect.height).toBeLessThan(beforeSize.rect.width)
    await page.mouse.move(beforeSize.rect.x + beforeSize.rect.width / 2, beforeSize.rect.y + beforeSize.rect.height / 2)
    await page.mouse.down()
    await page.mouse.move(beforeSize.rect.x + beforeSize.rect.width / 2, beforeSize.rect.y + beforeSize.rect.height / 2 + 24, { steps: 5 })
    await page.mouse.up()
    await expect.poll(async () => splitter.evaluate(element => {
      const parent = element.parentElement!
      const siblings = Array.from(parent.children)
      const index = siblings.indexOf(element)
      const before = siblings.slice(0, index).filter(child => child.classList.contains('lm_item')) as HTMLElement[]
      return before.map(pane => pane.getBoundingClientRect().height)
    })).not.toEqual(beforeSize.before)
    await expect(canvas).toBeVisible()
    await chart.getByRole('button', { name: 'Maximize tool' }).click()
    await expect(chart).toBeVisible()
    await chart.getByRole('button', { name: 'Restore tool' }).click()
    await expect(canvas).toBeVisible()
    await page.setViewportSize({ width: 1100, height: 760 })
    await assertUsefulTool(page, 'Chart', 'chart')
    await page.setViewportSize(originalViewport!)

    page.once('dialog', dialog => dialog.accept())
    const deleteMenu = await openWorkspaceMenu(page)
    await deleteMenu.getByRole('menuitem', { name: 'Delete workspace', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText('US Top Down')
    await expect((await openWorkspaceMenu(page)).getByRole('option', { name: duplicateName, exact: true })).toHaveCount(0)
    await expect(page.locator('.workstation__workspace-name')).toHaveText(sourceName!.trim())
    const restoredSource = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await assertUsefulWatchlistNumbers(restoredSource)
    expect(await watchlistConfigurationSignature(restoredSource)).toEqual(sourceConfiguration)
    await page.reload()
    await expect(page.locator('.workstation__workspace-name')).toHaveText(sourceName!.trim())
    const afterReload = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await assertUsefulWatchlistNumbers(afterReload)
    expect(await watchlistConfigurationSignature(afterReload)).toEqual(sourceConfiguration)
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
