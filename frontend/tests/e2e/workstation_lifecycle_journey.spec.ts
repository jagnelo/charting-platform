import type { Page } from '@playwright/test'
import { expect, test } from './helpers'

// This table is keyed to the authenticated server catalogue.  The test fails
// closed if a canonical tool is added without a user-visible outcome assertion.
const TOOL_OUTCOMES: Record<string, 'watchlist' | 'chart' | 'ratio' | 'technicals' | 'breadth' | 'coverage' | 'notes' | 'alerts' | 'scan' | 'gauge' | 'rotation' | 'map' | 'study' | 'results' | 'library' | 'report'> = {
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
  'Market Map': 'map',
  Technicals: 'technicals',
  Coverage: 'coverage',
  'Instrument Report': 'report',
  'Python Library': 'library',
  Benchmarks: 'watchlist',
  'S&P 500 Sectors': 'watchlist',
  Industries: 'watchlist',
  Constituents: 'watchlist',
  'Relative Strength': 'ratio',
  'Sector Indexes': 'watchlist',
  'Industry Indexes': 'watchlist',
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
  const catalogue = catalogueResponse.body as { tools: Array<{ title: string }> }
  const workspace = workspaceResponse.body as { tabs: Array<{ name: string; windows: Array<{ title: string }> }> }
  const catalogueTitles = catalogue.tools.map(tool => tool.title).sort()
  expect(catalogueTitles.filter(title => !(title in TOOL_OUTCOMES)), 'every canonical catalogue entry needs a useful outcome assertion').toEqual([])
  expect(workspace.tabs.map(tab => tab.name).sort()).toEqual([...FACTORY_LAYOUT_NAMES].sort())
  const factoryTitles = [...new Set(workspace.tabs.flatMap(tab => tab.windows.map(window => window.title)))].sort()
  const unmappedFactoryTitles = factoryTitles.filter(title => !(title in TOOL_OUTCOMES))
  expect(unmappedFactoryTitles, 'every factory window must map to a useful outcome assertion').toEqual([])
  return { catalogue, workspace }
}

async function assertFactoryLayouts(page: Page, tabs: Array<{ name: string; windows: Array<{ title: string }> }>) {
  expect(tabs.map(tab => tab.name).sort()).toEqual([...FACTORY_LAYOUT_NAMES].sort())
  for (const layout of tabs) {
    await activateLayout(page, layout.name)
    const visibleTitles = await page.locator('.tool-window__title').allTextContents()
    expect(visibleTitles.sort(), `${layout.name} factory windows`).toEqual(layout.windows.map(window => window.title).sort())
    for (const window of layout.windows) expect(TOOL_OUTCOMES[window.title], `${layout.name}: ${window.title}`).toBeTruthy()
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

async function hasRrgMarkerCenters(canvas: ReturnType<Page['locator']>) {
  return canvas.evaluate((element) => {
    type MarkerArc = { x: number; y: number; radius: number; fillStyle: string }
    type AuditedCanvas = HTMLCanvasElement & { __rrgLatestMarkerDraw?: MarkerArc[] }
    const target = element as AuditedCanvas
    const markers = target.__rrgLatestMarkerDraw ?? []
    const dpr = window.devicePixelRatio || 1
    const visibleMarkers = markers.filter(marker => marker.radius >= 3.4 * dpr)
    if (!visibleMarkers.length) return false
    const context = target.getContext('2d', { willReadFrequently: true })
    if (!context) return false
    const colors = new Set(['#61c58c', '#e7bc68', '#6dbbe6', '#df8181'])
    return visibleMarkers.every((marker) => {
      if (!Number.isFinite(marker.x) || !Number.isFinite(marker.y) || !colors.has(marker.fillStyle.toLowerCase())) return false
      const x = Math.round(marker.x)
      const y = Math.round(marker.y)
      if (x < 0 || y < 0 || x >= target.width || y >= target.height) return false
      const pixel = context.getImageData(x, y, 1, 1).data
      if (pixel[3] !== 255) return false
      const expected = marker.fillStyle.slice(1).match(/../g)?.map(value => Number.parseInt(value, 16))
      return Boolean(expected && pixel[0] === expected[0] && pixel[1] === expected[1] && pixel[2] === expected[2])
    })
  })
}

async function installRrgArcAudit(page: Page) {
  await page.addInitScript(() => {
    type MarkerArc = { x: number; y: number; radius: number; fillStyle: string }
    type AuditedCanvas = HTMLCanvasElement & { __rrgLatestMarkerDraw?: MarkerArc[] }
    type AuditedContext = CanvasRenderingContext2D & { __rrgPendingMarkerArcs?: Array<{ x: number; y: number; radius: number }> }
    const prototype = CanvasRenderingContext2D.prototype
    const originalArc = prototype.arc
    const originalFill = prototype.fill
    const originalClearRect = prototype.clearRect
    const originalBeginPath = prototype.beginPath
    const isRrgCanvas = (context: CanvasRenderingContext2D) => Boolean(context.canvas.closest('.rotation-tool__plot-shell'))

    prototype.clearRect = function (..._args: Parameters<typeof originalClearRect>) {
      if (isRrgCanvas(this)) (this.canvas as AuditedCanvas).__rrgLatestMarkerDraw = []
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
          canvas.__rrgLatestMarkerDraw.push({ ...marker, fillStyle: String(this.fillStyle) })
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

async function assertUsefulTool(page: Page, title: string, kind: typeof TOOL_OUTCOMES[string]) {
  const tool = await activatePanel(page, title)
  if (kind === 'watchlist') {
    await expect(tool.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await expect.poll(() => tool.locator('.watchlist__row').count()).toBeGreaterThan(0)
  } else if (kind === 'chart' || kind === 'ratio') {
    const plot = kind === 'chart' ? tool.locator('.chart-tool canvas').first() : tool.locator('.ratio-chart__host canvas').first()
    await expect(plot).toBeVisible({ timeout: 20_000 })
    const seriesColors = kind === 'chart' ? [[38, 166, 154], [239, 83, 80]] as Array<[number, number, number]> : [[107, 192, 239]] as Array<[number, number, number]>
    await expect.poll(() => plottedSeriesPixels(plot, seriesColors), { timeout: 30_000 }).toBeGreaterThan(20)
    if (kind === 'ratio') await expect(tool.locator('.ratio-chart__state')).toHaveCount(0)
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
    await expect(coverage.locator('.coverage-summary__grid')).toBeVisible({ timeout: 20_000 })
    await expect(coverage.locator('.coverage-summary__grid')).toContainText(/\d/)
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
    await tool.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(tool.locator('.easy-scan__result')).toBeVisible({ timeout: 30_000 })
    await expect(tool.locator('.easy-scan__result')).toContainText(/\d+\/\d+ evaluated/)
    await expect(tool.locator('.easy-scan__result')).not.toContainText('0/0 evaluated')
    const scanSummary = (await tool.locator('.easy-scan__result > span').first().innerText()).match(/(\d+) matches · (\d+)\/(\d+) evaluated/)
    expect(scanSummary).not.toBeNull()
    expect(Number(scanSummary![2])).toBeGreaterThan(0)
    expect(Number(scanSummary![3])).toBeGreaterThanOrEqual(Number(scanSummary![2]))
    expect(Number(scanSummary![1])).toBeLessThanOrEqual(Number(scanSummary![2]))
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
    await expect.poll(() => hasRrgMarkerCenters(canvas), { timeout: 30_000 }).toBe(true)
    await plot.focus()
    await page.keyboard.press('Home')
    const tooltip = tool.locator('.rotation-tool__tooltip')
    await expect(tooltip).toBeVisible()
    await expect(tooltip.locator('strong')).not.toBeEmpty()
    await expect(tooltip).toContainText(/Trend .*Momentum/)
    await page.keyboard.press('ArrowRight')
    await expect(tooltip).toBeVisible()
    const rows = tool.getByRole('region', { name: 'Relative rotation rows' }).locator('.rotation-tool__row')
    await expect(rows.first()).toBeVisible({ timeout: 30_000 })
    await expect(rows).not.toHaveCount(0)
  } else if (kind === 'map') {
    const tiles = tool.locator('.market-map-tool__tiles')
    await expect(tiles).toBeVisible({ timeout: 30_000 })
    const tile = tiles.locator('.market-map-tool__tile').first()
    await expect(tile).toBeVisible()
    await tile.click()
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
  } else if (kind === 'study') {
    await tool.getByLabel('Factory study').selectOption('positive_streak')
    await tool.getByRole('button', { name: 'Validate study' }).click()
    await expect(tool).toContainText('Validated for isolated execution', { timeout: 20_000 })
    await tool.getByRole('button', { name: 'Run study' }).click()
    await expect(tool.locator('[aria-label^="Study run status:"]')).toHaveAttribute('data-status', 'completed', { timeout: 45_000 })
    await expect(tool.locator('.study-lab-tool__artifacts article').first()).toBeVisible()
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
    await create.getByLabel('New Python asset source').fill("output.scalar('catalogue_value', 1)")
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

test.describe('Workstation lifecycle journeys', () => {
  test.beforeEach(async ({ page }) => {
    await installRrgArcAudit(page)
  })

  test('duplicates a factory layout with remapped panels, preserves the original, and reloads both', async ({ page, loggedIn, browserDiagnostics }) => {
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
    await activateLayout(page, 'US Top Down')

    await page.getByRole('button', { name: 'Duplicate layout', exact: true }).click()
    const copied = page.getByRole('tab', { name: 'US Top Down Copy', exact: true })
    await expect(copied).toBeVisible()
    const copiedKey = await copied.getAttribute('data-tab-key')
    expect(copiedKey).toBeTruthy()
    expect(copiedKey).not.toBe(originalKey)
    const copiedWindowKey = await page.locator('.tool-window').first().getAttribute('data-window-key')
    expect(copiedWindowKey).toBeTruthy()
    expect(copiedWindowKey).not.toBe(originalWindowKey)

    await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await assertUsefulTool(page, 'Relative Rotation', 'rotation')
    await copied.click()
    await assertUsefulTool(page, 'Chart', 'chart')
    const copiedSemanticTitles = await page.locator('.lm_tab').allTextContents()
    expect(copiedSemanticTitles).toEqual(expect.arrayContaining(['Benchmarks', 'Chart', 'Relative Rotation']))

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
    await assertFactoryLayouts(page, workspace.tabs)
    await activateLayout(page, 'US Top Down')
    const chartTool = await activatePanel(page, 'Chart')
    const favoriteStar = chartTool.getByRole('button', { name: 'Add SPY to My Favorites', exact: true })
    await expect(favoriteStar, 'create the empty Favorites prerequisite through the public Chart star action').toBeVisible()
    await favoriteStar.click()
    await expect(chartTool.getByRole('button', { name: 'Remove SPY from My Favorites', exact: true })).toHaveAttribute('aria-pressed', 'true')
    for (const item of catalogue.tools) {
      const kind = TOOL_OUTCOMES[item.title]
      expect(kind, `missing useful-result mapping for ${item.title}`).toBeTruthy()
      const existingTab = page.locator('.lm_tab').filter({ hasText: new RegExp(`^${escapeRegExp(item.title)}$`) })
      if (await existingTab.count()) {
        const existingTool = await activatePanel(page, item.title)
        await existingTool.getByRole('button', { name: 'Close tool' }).click()
        await expect(page.getByRole('group', { name: item.title, exact: true })).toHaveCount(0)
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
    await openWorkspaceMenu(page)
    const renamed = `Review ${Date.now()}`
    const renameField = page.getByRole('textbox', { name: 'Rename layout' }).last()
    await renameField.fill(renamed)
    await renameField.press('Tab')
    const renamedTab = page.getByRole('tab', { name: renamed, exact: true })
    await expect(renamedTab).toBeVisible()
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
    const layoutMenu = await openWorkspaceMenu(page)
    await layoutMenu.getByRole('button', { name: `Delete layout ${renamed}`, exact: true }).click()
    await expect(renamedTab).toBeVisible()

    page.once('dialog', dialog => dialog.accept())
    const confirmMenu = await openWorkspaceMenu(page)
    await confirmMenu.getByRole('button', { name: `Delete layout ${renamed}`, exact: true }).click()
    await expect(renamedTab).toHaveCount(0)
    const recovery = page.locator('.workstation__layout-recovery')
    await expect(recovery).toContainText(renamed)
    await recovery.getByRole('button', { name: 'Undo', exact: true }).click()
    await expect(renamedTab).toBeVisible()
    await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await page.reload()
    await expect(renamedTab).toBeVisible()
    await expect(page.locator('.workstation__tabs > [role="tab"]')).toHaveCount(beforeOrder.length)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('duplicates and safely deletes a workspace while preserving its source and tool content through resize and maximize', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible()
    const sourceName = await page.locator('.workstation__workspace-name').textContent()
    expect(sourceName?.trim()).toBe('US Top Down')
    const sourceBenchmarks = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    const sourceRows = await sourceBenchmarks.locator('.watchlist__row').allTextContents()
    expect(sourceRows.length).toBeGreaterThan(0)

    const menu = await openWorkspaceMenu(page)
    await menu.getByRole('menuitem', { name: 'Duplicate workspace', exact: true }).click()
    const duplicateName = 'US Top Down Copy'
    await expect(page.locator('.workstation__workspace-name')).toHaveText(duplicateName)
    await assertUsefulTool(page, 'Benchmarks', 'watchlist')

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
      return { rect: element.getBoundingClientRect().toJSON(), before: before.map(pane => pane.getBoundingClientRect().width) }
    })
    await page.mouse.move(beforeSize.rect.x + beforeSize.rect.width / 2, beforeSize.rect.y + beforeSize.rect.height / 2)
    await page.mouse.down()
    await page.mouse.move(beforeSize.rect.x + beforeSize.rect.width / 2 + 24, beforeSize.rect.y + beforeSize.rect.height / 2, { steps: 5 })
    await page.mouse.up()
    await expect.poll(async () => splitter.evaluate(element => {
      const parent = element.parentElement!
      const siblings = Array.from(parent.children)
      const index = siblings.indexOf(element)
      const before = siblings.slice(0, index).filter(child => child.classList.contains('lm_item')) as HTMLElement[]
      return before.map(pane => pane.getBoundingClientRect().width)
    })).not.toEqual(beforeSize.before)
    await expect(canvas).toBeVisible()
    await chart.getByRole('button', { name: 'Maximize tool' }).click()
    await expect(chart).toBeVisible()
    await chart.getByRole('button', { name: 'Restore tool' }).click()
    await expect(canvas).toBeVisible()
    await page.setViewportSize({ width: 1100, height: 760 })
    await assertUsefulTool(page, 'Chart', 'chart')

    page.once('dialog', dialog => dialog.accept())
    const deleteMenu = await openWorkspaceMenu(page)
    await deleteMenu.getByRole('menuitem', { name: 'Delete workspace', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText('US Top Down')
    await expect((await openWorkspaceMenu(page)).getByRole('option', { name: duplicateName, exact: true })).toHaveCount(0)
    await expect(page.locator('.workstation__workspace-name')).toHaveText(sourceName!.trim())
    const restoredSource = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await expect(restoredSource.locator('.watchlist__row')).toHaveText(sourceRows)
    await page.reload()
    await expect(page.locator('.workstation__workspace-name')).toHaveText(sourceName!.trim())
    const afterReload = await assertUsefulTool(page, 'Benchmarks', 'watchlist')
    await expect(afterReload.locator('.watchlist__row')).toHaveText(sourceRows)
    await browserDiagnostics.expectNoCriticalIssues()
  })
})
