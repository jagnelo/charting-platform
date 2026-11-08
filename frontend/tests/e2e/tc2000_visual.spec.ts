/**
 * Board-guided visual parity. The npm commands gate the strict exact-build variant through
 * the backend manifest validator; the board variant uses the accepted composite board policy
 * and still requires deterministic local geometry and screenshot evidence.
 */
import type { Page, Response } from '@playwright/test'
import { test, expect } from './helpers'

async function assertSeededBackend(page: Page) {
  if (process.env.E2E_SEED_MARKET_DATA !== 'true') return
  const response = await page.request.get('/health')
  expect(response.ok()).toBe(true)
  expect(response.headers()['content-type'] ?? '', 'health probe must return backend JSON').toContain('application/json')
  const payload = await response.json() as { e2e_seed_market_data?: boolean }
  expect(payload.e2e_seed_market_data, 'visual fixture mode must match the backend stack').toBe(true)
}

type ShellReadiness = 'loaded' | 'expected-chart-loading'

async function waitForSelectionPreparationToSettle(page: Page) {
  const summaries = page.locator('.workstation__selection-acquisition .compact-status__summary')
  // A terminal ready, waiting, unavailable, or failed notice is valid visual
  // state. Only the shared "preparing" summary is still changing as queued
  // identity/history work completes, so do not capture that intermediate UI.
  // Requiring both data domains prevents the initial empty toolbar from being
  // mistaken for settled preparation before Workstation mounts its notices.
  await expect.poll(async () => {
    const current = await summaries.allTextContents()
    return {
      history: current.some(summary => /^History\b/i.test(summary.trim())),
      holdings: current.some(summary => /^Holdings\b/i.test(summary.trim())),
      settled: current.every(summary => !/\bpreparing\b/i.test(summary.trim())),
    }
  }, { timeout: 15_000 }).toEqual({ history: true, holdings: true, settled: true })
}

async function waitForActiveWindowSnapshotAcknowledgement(page: Page, tabKey: string, windowKey: string) {
  return page.waitForResponse(async response => {
    const request = response.request()
    if (request.method() !== 'PUT' || !/\/workspaces\/[^/]+\/snapshot$/.test(new URL(request.url()).pathname)) return false
    try {
      const payload = request.postDataJSON() as { tabs?: Array<{ stable_key?: string; active_window_key?: string | null }> }
      return payload.tabs?.some(tab => tab.stable_key === tabKey && tab.active_window_key === windowKey) ?? false
    } catch {
      return false
    }
  })
}

async function waitForWindowConfigurationSnapshotAcknowledgement(
  page: Page,
  tabKey: string,
  windowKey: string,
  matches: (configuration: Record<string, unknown>) => boolean,
) {
  return page.waitForResponse(async response => {
    const request = response.request()
    if (request.method() !== 'PUT' || !/\/workspaces\/[^/]+\/snapshot$/.test(new URL(request.url()).pathname)) return false
    try {
      const payload = request.postDataJSON() as { tabs?: Array<{ stable_key?: string; windows?: Array<{ instance_key?: string; configuration?: Record<string, unknown> }> }> }
      const tab = payload.tabs?.find(candidate => candidate.stable_key === tabKey)
      const window = tab?.windows?.find(candidate => candidate.instance_key === windowKey)
      return Boolean(window?.configuration && matches(window.configuration))
    } catch {
      return false
    }
  })
}

async function waitForNewActiveWindowSnapshotAcknowledgement(page: Page, tabKey: string, previousWindowKey: string) {
  return page.waitForResponse(async response => {
    const request = response.request()
    if (request.method() !== 'PUT' || !/\/workspaces\/[^/]+\/snapshot$/.test(new URL(request.url()).pathname)) return false
    try {
      const payload = request.postDataJSON() as { tabs?: Array<{ stable_key?: string; active_window_key?: string | null }> }
      return payload.tabs?.some(tab => tab.stable_key === tabKey
        && Boolean(tab.active_window_key)
        && tab.active_window_key !== previousWindowKey) ?? false
    } catch {
      return false
    }
  })
}

async function waitForWorkspaceSnapshotAcknowledgement(page: Page) {
  return page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/workspaces\/[^/]+\/snapshot$/.test(new URL(response.url()).pathname))
}

async function activeWorkspaceTabKey(page: Page) {
  const key = await page.locator('.workstation__tabs [role="tab"][aria-selected="true"]').getAttribute('data-tab-key')
  expect(key).toBeTruthy()
  return key!
}

async function expectWorkspaceSaveAcknowledged(page: Page, response: Response) {
  expect(response.status()).toBe(200)
  const status = page.getByRole('status', { name: 'Workspace save status' })
  await expect(status).toHaveAttribute('data-state', 'saved')
  await expect(status).toHaveText('Workspace saved')
}

async function waitForShellReady(page: Page, readiness: ShellReadiness = 'loaded') {
  await expect(page.locator('.workstation')).toBeVisible()
  await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
  if (readiness === 'expected-chart-loading') {
    expect(process.env.E2E_SEED_MARKET_DATA, 'the loading-gap fixture requires the seeded market-data stack').toBe('true')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    const chartState = page.locator('.chart-tool .tool-state')
    await expect(chartState).toBeVisible({ timeout: 15_000 })
    await expect(chartState).toHaveText('Loading SPY…', { timeout: 15_000 })
    return
  }
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15_000 })
  if (process.env.E2E_SEED_MARKET_DATA === 'true') {
    await expect(page.locator('.ratio-chart__legend strong').first()).toHaveText('SPY/RSP', { timeout: 15_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
    // The shell freshness label can settle before the adjacent chart finishes
    // its canonical OHLCV request.  All board baselines include that chart, so
    // require its terminal state explicitly instead of allowing a loading
    // frame to race the screenshot oracle.
    await expect(page.locator('.chart-tool .tool-state')).toHaveCount(0, { timeout: 15_000 })
    await page.waitForTimeout(750)
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
  }
}

test.describe('TC2000 Version 25 board-guided visual parity', () => {
  test.skip(
    process.env.RUN_APPROVED_VISUAL_PARITY !== '1' && process.env.RUN_BOARD_VISUAL_PARITY !== '1',
    'requires approved references or the accepted board-guided visual policy',
  )

  test.beforeAll(async ({ browser }) => {
    // A visual run must never execute 104 copies of the same setup failure when
    // the stack was started with the wrong fixture mode. Use the worker-scoped
    // browser to perform one authoritative preflight, then let each test focus
    // on its own layout/state assertions.
    const context = await browser.newContext()
    const page = await context.newPage()
    try {
      await assertSeededBackend(page)
    } finally {
      await context.close()
    }
  })

  test.beforeEach(async ({ page }) => {
    // Visual cases share the authenticated fixture user. Restore the immutable
    // factory before each capture so a preceding interaction (for example a
    // resized watchlist column or a floated tool) cannot contaminate a later
    // environment's screenshot.
    await page.goto('/')
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      await expect(page.getByRole('status', { name: 'Workspace save status' })).toHaveAttribute('data-state', 'saved')
      const resetAcknowledgement = waitForWorkspaceSnapshotAcknowledgement(page)
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
      await expect(page.locator('.workstation__layout-state')).toHaveCount(0, { timeout: 15_000 })
      await expectWorkspaceSaveAcknowledged(page, await resetAcknowledgement)
    }
  })

  test('application shell default US Top Down workspace', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workstation__menu')).toBeVisible()
    await expect(page.locator('.workstation__tabs')).toBeVisible()
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15_000 })
    // Do not capture the transient first-render state. The saved layout must be
    // present before visual comparison, and the expected unavailable-data 404s
    // must have reached the diagnostics classifier before it inspects the page.
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    if (process.env.E2E_SEED_MARKET_DATA === 'true') {
      // The deterministic fixture is intentionally complete. Wait for both
      // canonical universes to hydrate before capturing a baseline; a first
      // canvas paint can occur while only the first virtualized row is present.
      await expect(page.getByRole('region', { name: 'Major US benchmarks' }).locator('.watchlist__controls b')).toContainText('5', { timeout: 10_000 })
      await expect(page.getByRole('region', { name: 'Relative to SPY' }).locator('.watchlist__controls b')).toContainText('11', { timeout: 10_000 })
      await expect(page.getByRole('region', { name: 'Major US benchmarks' }).locator('.watchlist__row')).toHaveCount(5, { timeout: 10_000 })
      await expect(page.getByRole('region', { name: 'Relative to SPY' }).locator('.watchlist__row')).toHaveCount(11, { timeout: 10_000 })
      const rowGeometry = await page.evaluate(() => Array.from(document.querySelectorAll('.watchlist__row')).map(row => {
        const rect = row.getBoundingClientRect()
        return { top: rect.top, bottom: rect.bottom, height: rect.height }
      }))
      expect(rowGeometry.every(row => row.height >= 20)).toBe(true)
      expect(new Set(rowGeometry.map(row => row.top)).size).toBe(rowGeometry.length)
      const viewportGeometry = await page.evaluate(() => Array.from(document.querySelectorAll('.watchlist__scroll')).map(scroll => {
        const viewport = scroll.getBoundingClientRect()
        const rows = Array.from(scroll.querySelectorAll<HTMLElement>('.watchlist__row'))
        return {
          viewportBottom: viewport.bottom,
          overflowingRows: rows.filter(row => row.getBoundingClientRect().bottom > viewport.bottom + 1).length,
        }
      }))
      expect(viewportGeometry.every(view => view.overflowingRows === 0)).toBe(true)
      // The ratio tool mounts before its linked benchmark state hydrates. Do
      // not let a transient self-ratio become the visual baseline; the default
      // workstation contract is the SPY/RSP benchmark-versus-equal-weight
      // comparison.
      await expect(page.locator('.ratio-chart__legend strong').first()).toHaveText('SPY/RSP', { timeout: 15_000 })
      await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
      // Require the ready label to remain stable across a refresh/render turn;
      // otherwise a second shared-analysis refresh can begin between the first
      // assertion and the screenshot and reintroduce a transient header state.
      await page.waitForTimeout(750)
      await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
    } else {
      await page.waitForTimeout(250)
    }
    await waitForSelectionPreparationToSettle(page)
    await expect(page.locator('.chart-tool .tool-state')).toHaveCount(0, { timeout: 15_000 })
    const overlapIssues = await page.evaluate(() => {
      const rect = (element: Element | null) => {
        if (!element) return null
        const box = element.getBoundingClientRect()
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
      }
      const overlaps = (left: ReturnType<typeof rect>, right: ReturnType<typeof rect>) => Boolean(
        left && right && left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top,
      )
      const issues: string[] = []
      document.querySelectorAll('.tool-window__header').forEach((header, index) => {
        if (overlaps(rect(header.querySelector('.tool-window__title')), rect(header.querySelector('.tool-window__actions')))) {
          issues.push(`header-${index}-title-actions`)
        }
        if (overlaps(rect(header.querySelector('.tool-window__symbol')), rect(header.querySelector('.tool-window__actions')))) {
          issues.push(`header-${index}-symbol-actions`)
        }
      })
      document.querySelectorAll('.chart-tool').forEach((chart, index) => {
        const toolbar = rect(chart.querySelector('.chart-tool__drawing-toolbar'))
        const surface = rect(chart.querySelector('.chart-tool__surface'))
        if (toolbar && surface && toolbar.right > surface.left) issues.push(`chart-${index}-toolbar-surface`)
        if (toolbar && surface && (toolbar.top < surface.top || toolbar.bottom > surface.bottom)) issues.push(`chart-${index}-toolbar-vertical-overlap`)
        const controls = [
          chart.querySelector('.chart-tool__compare'),
          chart.querySelector('.chart-tool__plots'),
          chart.querySelector('.chart-tool__templates'),
        ].map(rect)
        const ohlcv = rect(chart.querySelector('.ohlcv-info'))
        controls.forEach((control, controlIndex) => {
          if (control && ohlcv && overlaps(control, ohlcv)) issues.push(`chart-${index}-control-ohlcv-${controlIndex}`)
        })
        controls.forEach((left, leftIndex) => controls.slice(leftIndex + 1).forEach((right, rightIndex) => {
          if (left && right && overlaps(left, right)) issues.push(`chart-${index}-controls-${leftIndex}-${leftIndex + rightIndex + 1}`)
        }))
      })
      document.querySelectorAll('.ratio-chart').forEach((ratio, index) => {
        const bounds = rect(ratio)
        const warning = rect(ratio.querySelector('.ratio-chart__warning'))
        if (bounds && warning && (warning.left < bounds.left - 1 || warning.right > bounds.right + 1 || warning.top < bounds.top - 1 || warning.bottom > bounds.bottom + 1)) {
          issues.push(`ratio-${index}-warning-outside-tool`)
        }
        const duplicateLegend = ratio.querySelector<HTMLElement>('.u-legend')
        if (duplicateLegend && duplicateLegend.getBoundingClientRect().width > 0 && duplicateLegend.getBoundingClientRect().height > 0) {
          issues.push(`ratio-${index}-duplicate-uplot-legend`)
        }
      })
      return issues
    })
    expect(overlapIssues).toEqual([])
    await expect(page).toHaveScreenshot('application-shell-default.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })

    // An inactive Chart keeps the 40px rail but removes its controls from both
    // sight and keyboard focus. Verify the ordinary header-click path still
    // exposes the drawing tools in the current factory workstation.
    const chartWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.chart-tool') }).first()
    await expect(chartWindow).toBeVisible()
    let drawingToolbar = chartWindow.locator('.chart-tool__drawing-toolbar:not(.chart-tool__drawing-toolbar--inactive)')
    if (await drawingToolbar.count() === 0) {
      const inactiveRail = chartWindow.locator('.chart-tool__drawing-toolbar--inactive')
      await expect(inactiveRail).toHaveAttribute('aria-hidden', 'true')
      await expect(inactiveRail).toHaveAttribute('inert', '')
      await expect(inactiveRail.locator('button')).toHaveCount(0)
      const chartWindowKey = await chartWindow.getAttribute('data-window-key')
      const activeWorkspaceTabKey = await page.locator('.workstation__tabs [role="tab"][aria-selected="true"]').getAttribute('data-tab-key')
      expect(chartWindowKey).toBeTruthy()
      expect(activeWorkspaceTabKey).toBeTruthy()
      const saveAcknowledgement = waitForActiveWindowSnapshotAcknowledgement(page, activeWorkspaceTabKey!, chartWindowKey!)
      await chartWindow.locator('.tool-window__title').click()
      drawingToolbar = chartWindow.locator('.chart-tool__drawing-toolbar:not(.chart-tool__drawing-toolbar--inactive)')
      const savedSelection = await saveAcknowledgement
      expect(savedSelection.status()).toBe(200)
      await expect(page.getByRole('status', { name: 'Workspace save status' })).toHaveAttribute('data-state', 'saved')
    }
    await expect(drawingToolbar).toBeVisible()
    const lines = drawingToolbar.getByRole('button', { name: 'Lines', exact: true })
    await expect(lines).toBeVisible()
    await lines.click()
    await expect(drawingToolbar.getByRole('menuitem', { name: 'Trend Line', exact: true })).toBeVisible()
    await lines.click()
    await expect(drawingToolbar.getByRole('menu', { name: 'Lines drawing tools' })).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell workspace menu open state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    await page.getByRole('button', { name: 'Workspace', exact: true }).click()
    const menu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Duplicate active layout', exact: true })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Export workspace', exact: true })).toBeVisible()
    await expect(page).toHaveScreenshot('application-shell-menu-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace tool menu open state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    await waitForSelectionPreparationToSettle(page)
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible()
    const toolKey = await tool.getAttribute('data-window-key')
    expect(toolKey).toBeTruthy()
    const originalTool = page.locator(`.tool-window[data-window-key="${toolKey}"]`)
    await expect(originalTool).toHaveCount(1)
    const menuTrigger = tool.locator('[title="Tool menu"]')
    const menuId = await menuTrigger.getAttribute('aria-controls')
    expect(menuId).toBeTruthy()
    await menuTrigger.click()
    const menu = page.locator(`[id="${menuId}"]`)
    await expect(menu).toBeVisible()
    await expect(menu).toHaveRole('menu')
    await expect(menu).toHaveAttribute('aria-label', 'Benchmarks tool menu')
    await expect(menu.getByRole('menuitem', { name: 'Maximize' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Float' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Close' })).toBeVisible()
    const menuGeometry = await menu.evaluate(element => {
      const rect = element.getBoundingClientRect()
      const firstItem = element.querySelector<HTMLElement>('[role="menuitem"]')
      if (!firstItem) return { menuInViewport: false, itemInViewport: false, centerHit: false }
      const itemRect = firstItem.getBoundingClientRect()
      const centerX = (itemRect.left + itemRect.right) / 2
      const centerY = (itemRect.top + itemRect.bottom) / 2
      const hit = document.elementFromPoint(centerX, centerY)
      return {
        menuInViewport: rect.left >= -1 && rect.top >= -1 && rect.right <= window.innerWidth + 1 && rect.bottom <= window.innerHeight + 1,
        itemInViewport: itemRect.left >= -1 && itemRect.top >= -1 && itemRect.right <= window.innerWidth + 1 && itemRect.bottom <= window.innerHeight + 1,
        centerHit: Boolean(hit && (hit === firstItem || firstItem.contains(hit))),
      }
    })
    expect(menuGeometry).toEqual({ menuInViewport: true, itemInViewport: true, centerHit: true })
    await expect(page).toHaveScreenshot('workspace-tool-menu-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await menu.getByRole('menuitem', { name: 'Close' }).click()
    await expect(menu).toHaveCount(0)
    await expect(originalTool).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('watchlist column editor open state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const benchmarkWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.benchmark-surface') }).first()
    const benchmarkWindowKey = await benchmarkWindow.getAttribute('data-window-key')
    const benchmarkTabKey = await activeWorkspaceTabKey(page)
    expect(benchmarkWindowKey).toBeTruthy()
    const benchmarkSurface = page.locator('.benchmark-surface:visible')
    const familySelector = benchmarkSurface.getByLabel('Benchmark family', { exact: true })
    await expect(benchmarkSurface.getByLabel('Benchmark family readiness')).toHaveCount(0)
    let familySave = waitForWindowConfigurationSnapshotAcknowledgement(page, benchmarkTabKey, benchmarkWindowKey!, configuration => configuration.benchmark_family_key === 'sp500')
    await familySelector.selectOption({ label: 'S&P 500' })
    await expectWorkspaceSaveAcknowledged(page, await familySave)
    await expect(benchmarkSurface.getByLabel('Benchmark family readiness'))
      .toContainText('All-family readiness:', { timeout: 15_000 })
    familySave = waitForWindowConfigurationSnapshotAcknowledgement(page, benchmarkTabKey, benchmarkWindowKey!, configuration => configuration.benchmark_family_key == null)
    await familySelector.selectOption({ label: 'Major US benchmarks' })
    await expectWorkspaceSaveAcknowledged(page, await familySave)
    await expect(benchmarkSurface.getByLabel('Benchmark family readiness')).toHaveCount(0)
    await waitForShellReady(page)
    const benchmarks = page.getByRole('region', { name: 'Major US benchmarks' })
    await expect(benchmarks).toBeVisible()
    await expect(benchmarks).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect(benchmarks.getByText('Loading family legs…', { exact: true })).toHaveCount(0)
    await expect(benchmarks.locator('.watchlist__loading-status')).toHaveCount(0)
    const expectedBenchmarkSymbols = ['DIA', 'IWM', 'QQQ', 'RSP', 'SPY']
    const benchmarkRows = benchmarks.locator('.watchlist__row')
    await expect(benchmarkRows).toHaveCount(expectedBenchmarkSymbols.length)
    await expect.poll(async () => benchmarkRows.evaluateAll(rows => rows.map(row =>
      row.getAttribute('aria-label')?.trim().split(/\s+/)[0] ?? '',
    ))).toEqual(expectedBenchmarkSymbols)
    await benchmarks.getByRole('button', { name: 'Columns', exact: true }).click()
    const editor = benchmarks.locator('.watchlist__column-menu')
    await expect(editor).toBeVisible()
    await expect(editor.getByRole('button', { name: 'Paste column settings' })).toBeVisible()
    await expect(editor.locator('.watchlist__column-editor-row')).toHaveCount(15)
    await expect(benchmarks.locator('.watchlist__loading-status')).toHaveCount(0)
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh')
    await expect(page).toHaveScreenshot('watchlist-column-editor-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('EasyScan condition editor open state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    await expect(page.getByRole('status', { name: 'Workspace save status' })).toHaveAttribute('data-state', 'saved')
    const tabKey = await activeWorkspaceTabKey(page)
    const previousWindowKey = await page.locator('.tool-window:visible').first().getAttribute('data-window-key')
    expect(previousWindowKey).toBeTruthy()
    const saveAcknowledgement = waitForNewActiveWindowSnapshotAcknowledgement(page, tabKey, previousWindowKey!)
    await page.getByRole('button', { name: 'Add tool', exact: true }).click()
    const toolMenu = page.getByRole('menu', { name: 'Workstation tools' })
    await expect(toolMenu).toBeVisible()
    await toolMenu.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    // The factory layout may retain an older hidden EasyScan virtual component;
    // target the newly foregrounded visible tool rather than a hidden tab body.
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 10_000 })
    const scanWindowKey = await scan.locator('xpath=ancestor-or-self::*[contains(concat(" ", normalize-space(@class), " "), " tool-window ")]').getAttribute('data-window-key')
    expect(scanWindowKey).toBeTruthy()
    const savedLayout = await saveAcknowledgement
    expect(savedLayout.status()).toBe(200)
    const savedTab = (savedLayout.request().postDataJSON() as { tabs: Array<{ stable_key: string; active_window_key: string | null }> }).tabs
      .find(candidate => candidate.stable_key === tabKey)
    expect(savedTab?.active_window_key).toBe(scanWindowKey)
    await expectWorkspaceSaveAcknowledged(page, savedLayout)
    await scan.getByRole('button', { name: 'Build technical condition tree', exact: true }).click()
    await expect(scan.getByRole('region', { name: 'Advanced technical condition builder' })).toBeVisible()
    await expect(scan.getByRole('combobox', { name: 'Condition group operator' })).toHaveValue('AND')
    await expect(scan.getByRole('button', { name: '+ Condition', exact: true })).toBeVisible()
    await expect(scan.getByRole('button', { name: '+ Group', exact: true })).toBeVisible()
    await expect(page.getByRole('status', { name: 'Workspace save status' })).toHaveAttribute('data-state', 'saved')
    await expect(page).toHaveScreenshot('easyscan-condition-editor-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace maximized state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible()
    const menuTrigger = tool.locator('[title="Tool menu"]')
    const menuId = await menuTrigger.getAttribute('aria-controls')
    expect(menuId).toBeTruthy()
    const menu = page.locator(`[id="${menuId}"]`)
    await menuTrigger.click()
    await expect(menu).toHaveCount(1)
    await expect(menu).toHaveRole('menu')
    const tabKey = await activeWorkspaceTabKey(page)
    const windowKey = await tool.getAttribute('data-window-key')
    expect(windowKey).toBeTruthy()
    const saveAcknowledgement = waitForActiveWindowSnapshotAcknowledgement(page, tabKey, windowKey!)
    await menu.getByRole('menuitem', { name: 'Maximize' }).click()
    await expect(page.locator('.lm_maximised')).toHaveCount(1)
    await expect(tool).toBeVisible()
    await expectWorkspaceSaveAcknowledged(page, await saveAcknowledgement)
    await expect(page).toHaveScreenshot('workspace-maximized.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace tabbed state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    // The former tabs.nth(1) could be active already when multiple stacks are
    // present. The visual state now uses the first genuinely inactive public
    // tab, so the captured destination can differ from that ineffective case.
    const inactiveTabs = page.locator('.lm_tab:visible:not(.lm_active)')
    await expect.poll(() => inactiveTabs.count(), { timeout: 10_000 }).toBeGreaterThan(0)
    const selectedTab = inactiveTabs.first()
    await expect(selectedTab).not.toHaveClass(/lm_active/)
    const selectedTabKey = await page.locator('.workstation__tabs [role="tab"][aria-selected="true"]').getAttribute('data-tab-key')
    expect(selectedTabKey).toBeTruthy()
    const selectedTabTitle = await selectedTab.getAttribute('title')
    expect(selectedTabTitle).toBeTruthy()
    const stableSelectedTab = page.locator(`.lm_tab:visible[title=${JSON.stringify(selectedTabTitle)}]`)
    await expect(stableSelectedTab).toHaveCount(1)
    const selectedWindowKey = await stableSelectedTab.evaluate(tab => {
      const title = tab.querySelector('.lm_title')?.textContent?.trim() || tab.textContent?.trim()
      const matching = Array.from(document.querySelectorAll<HTMLElement>('.tool-window[data-window-key]'))
        .filter(window => window.querySelector('.tool-window__title')?.textContent?.trim() === title)
      return matching.length === 1 ? matching[0].dataset.windowKey ?? null : null
    })
    expect(selectedWindowKey).toBeTruthy()
    const saveAcknowledgement = waitForActiveWindowSnapshotAcknowledgement(page, selectedTabKey!, selectedWindowKey!)
    await stableSelectedTab.click()
    await expect(stableSelectedTab).toHaveClass(/lm_active/)
    const selectedWindow = page.locator(`.tool-window[data-window-key="${selectedWindowKey}"]`)
    await expect(selectedWindow).toBeVisible()
    await expect(selectedWindow).toHaveClass(/tool-window--active/)
    await expectWorkspaceSaveAcknowledged(page, await saveAcknowledgement)
    await expect(page).toHaveScreenshot('workspace-tabbed.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace restored state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible()
    const menuTrigger = tool.locator('[title="Tool menu"]')
    const menuId = await menuTrigger.getAttribute('aria-controls')
    expect(menuId).toBeTruthy()
    const menu = page.locator(`[id="${menuId}"]`)
    await menuTrigger.click()
    await expect(menu).toHaveCount(1)
    await expect(menu).toHaveRole('menu')
    const tabKey = await activeWorkspaceTabKey(page)
    const windowKey = await tool.getAttribute('data-window-key')
    expect(windowKey).toBeTruthy()
    const maximizeAcknowledgement = waitForActiveWindowSnapshotAcknowledgement(page, tabKey, windowKey!)
    await menu.getByRole('menuitem', { name: 'Maximize' }).click()
    await expect(page.locator('.lm_maximised')).toHaveCount(1)
    await expectWorkspaceSaveAcknowledged(page, await maximizeAcknowledgement)
    const restoreAcknowledgement = waitForActiveWindowSnapshotAcknowledgement(page, tabKey, windowKey!)
    await tool.locator('button[title="Maximize"]').click()
    await expect(page.locator('.lm_maximised')).toHaveCount(0)
    await expect(tool).toBeVisible()
    await expectWorkspaceSaveAcknowledged(page, await restoreAcknowledgement)
    await expect(page).toHaveScreenshot('workspace-restored.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace floating state has a deterministic board baseline', async ({ page, context, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const sourceTool = page.locator('.tool-window').first()
    const sourceWindowKey = await sourceTool.getAttribute('data-window-key')
    const tabKey = await activeWorkspaceTabKey(page)
    expect(sourceWindowKey).toBeTruthy()
    const expectedSymbols = ['DIA', 'IWM', 'QQQ', 'RSP', 'SPY']
    await expect(sourceTool.locator('.watchlist__row')).toHaveCount(expectedSymbols.length)
    const popupPromise = context.waitForEvent('page')
    const floatAcknowledgement = page.waitForResponse(async response => {
      const request = response.request()
      if (request.method() !== 'PUT' || !/\/workspaces\/[^/]+\/snapshot$/.test(new URL(request.url()).pathname)) return false
      try {
        const payload = request.postDataJSON() as { tabs?: Array<{ stable_key?: string; windows?: Array<{ instance_key?: string }> }> }
        const tab = payload.tabs?.find(candidate => candidate.stable_key === tabKey)
        return Boolean(tab && !tab.windows?.some(window => window.instance_key === sourceWindowKey))
      } catch { return false }
    })
    await sourceTool.locator('button[title="Float"]').click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    const popoutTool = popup.locator('.workstation__popout .tool-window')
    await expect(popoutTool).toBeVisible({ timeout: 15_000 })
    const popoutRows = popoutTool.locator('.watchlist__row')
    await expect(popoutRows).toHaveCount(expectedSymbols.length)
    const poppedSymbols = await popoutRows.evaluateAll((rows) =>
      rows.map((row) => row.getAttribute('aria-label')?.split(/\s+/)[0] ?? ''),
    )
    expect(poppedSymbols).toEqual(expectedSymbols)
    // The detached WatchList can paint its persisted row identities before it
    // hydrates shared market analysis. Do not capture the transient
    // unavailable/loading state as the deterministic populated-state baseline.
    await expect(popoutTool.getByLabel('Benchmark family universe provenance'))
      .toContainText('Universe:', { timeout: 15_000 })
    await expect.poll(async () => {
      const rowText = await popoutRows.allTextContents()
      return rowText.length === expectedSymbols.length && rowText.every(text => text.includes('Current'))
    }, { timeout: 15_000 }).toBe(true)
    await expectWorkspaceSaveAcknowledged(page, await floatAcknowledgement)
    await expect(popup).toHaveScreenshot('workspace-floating.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    if (!popup.isClosed()) {
      const closed = popup.waitForEvent('close')
      try {
        await popoutTool.locator('button[title="Close"]').click()
      } catch (error) {
        // The ordinary Close action can destroy this page before Chromium
        // acknowledges click completion. A still-open popup is a real failure.
        if (!popup.isClosed()) throw error
      }
      await closed
    }
    await expect(sourceTool).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('workspace drag-target state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const tabs = page.locator('.lm_tab:visible')
    await expect.poll(() => tabs.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const sourceBox = await tabs.first().boundingBox()
    const dockBox = await page.locator('.workspace-layout-host').boundingBox()
    expect(sourceBox).not.toBeNull()
    expect(dockBox).not.toBeNull()
    await page.mouse.move(sourceBox!.x + sourceBox!.width / 2, sourceBox!.y + sourceBox!.height / 2)
    await page.mouse.down()
    await page.mouse.move(dockBox!.x + dockBox!.width * 0.72, dockBox!.y + dockBox!.height * 0.45, { steps: 12 })
    await expect(page.locator('.lm_dropTargetIndicator')).toBeVisible({ timeout: 5_000 })
    await expect(page).toHaveScreenshot('workspace-drag-target.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await page.mouse.up()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell keyboard help state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    await page.getByRole('button', { name: 'Help', exact: true }).click()
    const helpDialog = page.getByRole('dialog', { name: 'Keyboard shortcuts' })
    await expect(helpDialog).toBeVisible()
    await expect(helpDialog).toContainText('Ctrl+Space')
    await expect(helpDialog).toContainText('Backspace')
    await expect(helpDialog).toContainText(/Over a chart: change timeframe; over a WatchList: move through symbols/i)
    await expect(helpDialog).toContainText('Shortcuts are inactive while a text, numeric, code, or search editor owns focus.')
    const helpLayout = await helpDialog.evaluate(dialog => {
      const dialogBounds = dialog.getBoundingClientRect()
      const rows = Array.from(dialog.querySelectorAll('dl > div'))
      const unreadableGaps: string[] = []
      const clipped: string[] = []
      for (const row of rows) {
        const key = row.querySelector('dt')
        const description = row.querySelector('dd')
        if (!key || !description) continue
        const keyText = document.createRange()
        keyText.selectNodeContents(key)
        const keyBounds = keyText.getBoundingClientRect()
        const descriptionBounds = description.getBoundingClientRect()
        const descriptionText = document.createRange()
        descriptionText.selectNodeContents(description)
        const descriptionLines = Array.from(descriptionText.getClientRects())
        if (keyBounds.right + 8 > descriptionBounds.left) unreadableGaps.push(key.textContent?.trim() ?? '')
        if (keyBounds.left < dialogBounds.left || keyBounds.right > dialogBounds.right
          || descriptionBounds.left < dialogBounds.left || descriptionBounds.right > dialogBounds.right
          || descriptionLines.some(line => line.left < dialogBounds.left || line.right > dialogBounds.right)) {
          clipped.push(key.textContent?.trim() ?? '')
        }
      }
      return { rowCount: rows.length, unreadableGaps, clipped }
    })
    expect(helpLayout.rowCount).toBeGreaterThan(0)
    expect(helpLayout.unreadableGaps, 'shortcut key labels must leave at least 8 CSS pixels before descriptions').toEqual([])
    expect(helpLayout.clipped, 'shortcut text must remain within the Help dialog width').toEqual([])
    await expect(page).toHaveScreenshot('application-shell-help-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell focused symbol search has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.route('**/api/v1/instruments/search**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { symbol: 'SPY', name: 'S&P 500 proxy ETF', exchange: 'ARCX', type: 'ETF' },
          { symbol: 'SPX', name: 'S&P 500 Index', exchange: 'INDEX', type: 'INDEX' },
        ]),
      })
    })
    await page.goto('/')
    await waitForShellReady(page)
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await symbolEntry.click()
    await symbolEntry.fill('')
    await expect(symbolEntry).toHaveValue('', { timeout: 2_000 })
    await symbolEntry.pressSequentially('SP', { delay: 50 })
    const results = page.getByRole('listbox', { name: 'Symbol search results' })
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(results).toContainText('SPY')
    await expect(symbolEntry).toHaveValue('SP')
    await expect(page).toHaveScreenshot('application-shell-search-focused.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell keyboard-selected symbol search has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.route('**/api/v1/instruments/search**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { symbol: 'SPY', name: 'S&P 500 proxy ETF', exchange: 'ARCX', type: 'ETF' },
          { symbol: 'SPX', name: 'S&P 500 Index', exchange: 'INDEX', type: 'INDEX' },
        ]),
      })
    })
    await page.goto('/')
    await waitForShellReady(page)
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await symbolEntry.click()
    await symbolEntry.fill('')
    await expect(symbolEntry).toHaveValue('', { timeout: 2_000 })
    await symbolEntry.pressSequentially('SP', { delay: 50 })
    const results = page.getByRole('listbox', { name: 'Symbol search results' })
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(results.getByRole('option', { selected: true })).toContainText('SPY')
    await symbolEntry.press('ArrowDown')
    await expect(results.getByRole('option', { selected: true })).toContainText('SPX')
    await expect(page).toHaveScreenshot('application-shell-search-keyboard-selected.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell fetching freshness gap state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.route(/\/api\/v1\/ohlcv(?:\/|$)/, async () => {
      // Keep the canonical technical request pending so the shell exposes its
      // honest fetching state while the rest of the workstation remains usable.
      await new Promise(() => undefined)
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('Fetching', { timeout: 10_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText(/Refreshing…|Refresh/, { timeout: 10_000 })
    await expect(page).toHaveScreenshot('fetching-freshness-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('Study Lab original surface uses the board-guided dense tool language', async ({ page, loggedIn, browserDiagnostics }) => {
    // Keep the adjacent chart and persisted research list in their stable
    // loading states. The surface baseline is about Study Lab composition, not
    // whichever asynchronous data response wins the capture race.
    await page.route(/\/api\/v1\/ohlcv(?:\/|$)/, async () => {
      await new Promise(() => undefined)
    })
    await page.route(/\/api\/v1\/research\/runs(?:\?|$)/, async () => {
      await new Promise(() => undefined)
    })
    await page.goto('/')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    // The visual projects share a seeded account. Reset the factory workspace
    // before this original-surface baseline so a preceding project's persisted
    // splitter geometry cannot change the Study Lab editor height in one
    // display-scale project while leaving the others visually identical.
    page.once('dialog', dialog => dialog.accept())
    await page.getByTitle('Reset factory workspace').first().click()
    // Reset is a persisted workspace transaction; under a loaded four-project
    // matrix the status surface can legitimately remain visible longer than
    // the default locator timeout while the server snapshot is replaced.
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0, { timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await expect(study.getByRole('textbox', { name: 'Study Python source' })).toBeVisible()
    await expect(study.getByRole('button', { name: 'Validate' })).toBeVisible()
    await expect(study.getByRole('button', { name: 'Run study', exact: true })).toBeVisible()
    const overlapIssues = await study.evaluate((root) => {
      const header = root.querySelector('.study-lab-tool__header')?.getBoundingClientRect()
      const editor = root.querySelector('.study-lab-tool__editor-shell')?.getBoundingClientRect()
      return header && editor && header.bottom > editor.top ? ['header-editor'] : []
    })
    expect(overlapIssues).toEqual([])
    await expect(page).toHaveScreenshot('study-lab-original.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('chart loading gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route(/\/api\/v1\/ohlcv(?:\/|$)/, async route => {
      // Keep the request pending so the loading state is stable for capture.
      // Provider-error behavior is covered separately by the authenticated flow
      // test; this visual baseline intentionally isolates the unrepresented
      // loading state without introducing a transient terminal response.
      await new Promise(() => undefined)
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.chart-tool .tool-state').filter({ hasText: /Loading SPY/i })).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.chart-tool canvas')).toHaveCount(0)
    await expect(page).toHaveScreenshot('chart-loading-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('chart provider-error gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route('**/api/v1/ohlcv/**', async route => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No local observations are available for SPY' }),
      })
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.chart-tool .tool-state--error')).toContainText(/Request failed|unavailable|observations/i, { timeout: 10_000 })
    await expect(page.locator('.chart-tool canvas')).toHaveCount(0)
    if (process.env.E2E_SEED_MARKET_DATA === 'true') {
      // This gap intentionally keeps the primary chart in its terminal 404
      // state, but the rest of the default board is still expected to show its
      // seeded analysis. A visible error can arrive before those independent
      // workspace requests finish, so establish their actual rendered state
      // without waiting for the chart to become ready.
      const benchmarks = page.getByRole('region', { name: 'Major US benchmarks' })
      const sectors = page.getByRole('region', { name: 'Relative to SPY' })
      const constituents = page.getByRole('group', { name: 'Constituents', exact: true })
      await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
      await expect(benchmarks).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
      await expect(benchmarks.locator('.watchlist__row')).toHaveCount(5, { timeout: 15_000 })
      await expect(sectors).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
      await expect(sectors.locator('.watchlist__row')).toHaveCount(11, { timeout: 15_000 })
      await expect(constituents).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
      await expect(constituents.locator('.watchlist__row')).toHaveCount(6, { timeout: 15_000 })
      await expect(page.locator('.industry-list__row')).toHaveCount(2, { timeout: 15_000 })
      await expect(page.locator('.ratio-chart')).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
      await expect(page.locator('.ratio-chart__legend strong').first()).toHaveText('SPY/RSP', { timeout: 15_000 })
      await expect(page.locator('.tool-window').filter({ hasText: 'Technicals' }).locator('.metrics')).toContainText('100.00', { timeout: 15_000 })
      // Keep the target failure—not a later state transition—as the screenshot
      // oracle's chart composition.
      await expect(page.locator('.chart-tool .tool-state--error')).toContainText(/Request failed|unavailable|observations/i)
      await expect(page.locator('.chart-tool canvas')).toHaveCount(0)
    }
    // Bind the capture to the terminal shared workstation state as well as the
    // chart's 404. This prevents an early current/busy shell from becoming the
    // screenshot even when the chart-local error has already rendered.
    await expect(page.locator('.workstation__footer .workstation__data-state'))
      .toHaveAttribute('aria-label', 'Market data freshness: Unavailable')
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh')
    await expect(page).toHaveScreenshot('chart-provider-error-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('blocked pop-out recovery gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.addInitScript(() => {
      window.open = (() => null) as typeof window.open
    })
    await page.goto('/chart')
    // The blocked-pop-out oracle must represent the same stable workstation
    // state in every display environment. Without this wait, the screenshot
    // races canonical market hydration and can capture either the loading or
    // ready data composition, making the gap baseline non-deterministic.
    await waitForShellReady(page)
    const sourceTool = page.locator('.tool-window').first()
    await expect(sourceTool).toBeVisible({ timeout: 10_000 })
    await sourceTool.locator('button[title="Float"]').click()
    await expect(page.locator('.workstation__footer')).toContainText(/Browser blocked the pop-out/i, { timeout: 10_000 })
    await expect(sourceTool).toBeVisible()
    await expect(page.locator('.workstation__popout')).toHaveCount(0)
    await waitForShellReady(page)
    await expect(page).toHaveScreenshot('blocked-popout-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('stale freshness gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route(/\/api\/v1\/analysis\/instruments\/[^/]+\/technical(?:\?|$)/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: '2026-08-01T00:00:00Z', adjustment: 'split_adjusted',
          last: 500, rsi14: 55, sma20: 498, sma50: 490, sma200: 450, position_52w: 0.8, volume_ratio_50: 1.1,
          freshness: 'stale', freshness_detail: { requested: 1, current: 0, stale: 1, other: 0 }, warnings: [],
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('Stale · cached', { timeout: 10_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 10_000 })
    await expect(page).toHaveScreenshot('stale-freshness-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('delayed freshness gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route(/\/api\/v1\/analysis\/instruments\/[^/]+\/technical(?:\?|$)/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: '2026-08-01T00:00:00Z', adjustment: 'split_adjusted',
          last: 500, rsi14: 55, sma20: 498, sma50: 490, sma200: 450, position_52w: 0.8, volume_ratio_50: 1.1,
          freshness: 'delayed', freshness_detail: { requested: 1, current: 0, stale: 0, other: 1 }, warnings: [],
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('Delayed', { timeout: 10_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 10_000 })
    await expect(page).toHaveScreenshot('delayed-freshness-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('unavailable freshness gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route(/\/api\/v1\/analysis\/instruments\/[^/]+\/technical(?:\?|$)/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: null, adjustment: 'split_adjusted',
          last: null, rsi14: null, sma20: null, sma50: null, sma200: null, position_52w: null, volume_ratio_50: null,
          freshness: 'unavailable', freshness_detail: { requested: 1, current: 0, stale: 0, other: 0 }, warnings: [],
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('Unavailable', { timeout: 10_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 10_000 })
    await expect(page).toHaveScreenshot('unavailable-freshness-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('partial coverage gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    await page.route(/\/api\/v1\/analysis\/instruments\/[^/]+\/technical(?:\?|$)/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: '2026-08-01T00:00:00Z', adjustment: 'split_adjusted',
          last: 500, rsi14: 55, sma20: 498, sma50: 490, sma200: null, position_52w: null, volume_ratio_50: null,
          freshness: 'partial', freshness_detail: { requested: 1, current: 0, stale: 1, other: 0 },
          warnings: [{ code: 'insufficient_history', message: 'SMA(200) requires 200 bars.', instrument_id: 1 }],
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('Partial coverage', { timeout: 10_000 })
    await expect(page).toHaveScreenshot('partial-coverage-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('Study Lab validation-error gap state has a deterministic local baseline', async ({ page, loggedIn }) => {
    // Keep the adjacent chart in its documented loading state. This visual case is
    // about the validation-error surface; allowing a seeded OHLCV response to race
    // the capture makes the expected loading baseline depend on fixture timing.
    await page.route(/\/api\/v1\/ohlcv(?:\/|$)/, async () => {})
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toHaveCount(1)
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual validation gap')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('broken'")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validation errors', { timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__validation--bad pre')).toBeVisible()
    await expect(study.getByRole('button', { name: 'Run study', exact: true })).toBeDisabled()
    await expect(page).toHaveScreenshot('study-lab-validation-error-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
  })

  test('Study Lab running gap state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    const runningRun = {
      id: 778,
      code_version_id: 777,
      status: 'running',
      progress: { status: 'running', completed_cells: 12, total_cells: 100 },
      diagnostics: [],
      warnings: [],
      logs: 'runner active',
      resource_usage: {},
      reproducibility_hash: null,
      dataset_manifest: { benchmark_coverage: { status: 'ready' } },
      artifacts: [],
    }
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ versions: [{ id: 777 }] }) })
    })
    await page.route(url => url.pathname.endsWith('/api/v1/research/runs'), async route => {
      if (route.request().method() === 'GET') {
        const requestUrl = new URL(route.request().url())
        if (!requestUrl.searchParams.has('before_created_at') && !requestUrl.searchParams.has('before_id')) {
          // Match the persisted-runs loading state in this chart-loading visual
          // without racing an empty first-page response.
          await new Promise<void>(() => undefined)
          return
        }
        await route.continue()
        return
      }
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(runningRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/778$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runningRun) })
    })
    await page.route(/\/api\/v1\/market-groups\/us-benchmarks(?:\?.*)?$/, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      // Keep shared benchmark freshness in the same unavailable state as the
      // protected loading-gap references instead of racing a seeded response.
      await new Promise<void>(() => {})
    })
    await page.route(/\/api\/v1\/ohlcv(?:\/|$)/, async () => {
      // This capture is about the Study run state, not chart-data readiness.
      // Keep the unrelated chart in its saved loading state even when a seeded
      // stack can satisfy the OHLCV request before the screenshot is taken.
      await new Promise(() => undefined)
    })
    await page.goto('/chart')
    await waitForShellReady(page, 'expected-chart-loading')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual running study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('running', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run study', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--running')).toBeVisible({ timeout: 10_000 })
    await expect(study).toContainText('running 12/100')
    await expect(study.getByRole('button', { name: 'Cancel study run', exact: true })).toBeVisible()
    await expect(page.locator('.workstation__refresh')).toHaveText('Refreshing…', { timeout: 15_000 })
    await expect(page.locator('.chart-tool .tool-state')).toHaveText('Loading SPY…')
    await expect(page.getByRole('region', { name: 'Study Lab research results' }))
      .toContainText('Loading reproducible research runs…')
    await expect(page).toHaveScreenshot('study-lab-running-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('Study Lab structured-result gap state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    const structuredRun = {
      id: 779,
      code_version_id: 778,
      status: 'completed',
      progress: { status: 'completed', completed_cells: 4, total_cells: 4 },
      diagnostics: [],
      warnings: [],
      logs: 'structured study complete',
      resource_usage: { wall_ms: 42 },
      reproducibility_hash: 'visual-structured-study',
      dataset_manifest: { benchmark_coverage: { status: 'ready' } },
      artifacts: [
        { id: 7791, name: 'event_count', artifact_type: 'scalar', payload: { value: 4 } },
        { id: 7792, name: 'monthly_frequency', artifact_type: 'bar', payload: { value: { labels: ['2026-01', '2026-02'], values: [2, 2] } } },
        { id: 7793, name: 'streak_distribution', artifact_type: 'histogram', payload: { value: { bins: [{ start: 1, end: 2, count: 1 }, { start: 2, end: 3, count: 2 }, { start: 3, end: 4, count: 1 }], current: 2 } } },
        { id: 7794, name: 'summary', artifact_type: 'table', payload: { value: [{ state: 'positive_close', count: 4 }] } },
        { id: 7795, name: 'occurrences', artifact_type: 'events', payload: { value: [{ symbol: 'SPY', timestamp: '2026-01-02T00:00:00+00:00', kind: 'positive_close' }] } },
      ],
    }
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['study'] }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ versions: [{ id: 778 }] }) })
    })
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() === 'GET') {
        // The adjacent Persisted runs tool must not depend on whatever rows a
        // shared E2E database happens to contain.  An empty, successful list
        // is the deterministic factory state for this visual capture.
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
        return
      }
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(structuredRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/779$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(structuredRun) })
    })
    await page.goto('/chart')
    await waitForShellReady(page)
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual structured study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('event_count', 4)\noutput.bar('monthly_frequency', ['2026-01', '2026-02'], [2, 2])\noutput.histogram('streak_distribution', [1, 2, 2, 3], 2, 2)\noutput.table('summary', [{'state': 'positive_close', 'count': 4}])\noutput.events('occurrences', [{'symbol': 'SPY', 'timestamp': '2026-01-02T00:00:00+00:00', 'kind': 'positive_close'}])")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run study', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'event_count' })).toContainText('4')
    await expect(study.locator('.study-bars-uplot, [class*="study-bars"]').first()).toBeVisible()
    await expect(study.locator('.study-histogram-uplot, [class*="study-histogram"]').first()).toBeVisible()
    await expect(study.locator('table').filter({ hasText: 'positive_close' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__events button').filter({ hasText: 'positive_close' })).toBeVisible()
    // Opening Study replaces the preceding layout. Its new chart and result
    // canvases must reach the ready state shown by this existing reference.
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
    await expect(page.locator('.chart-tool .tool-state')).toHaveCount(0, { timeout: 15_000 })
    await expect(page.locator('.chart-tool canvas').first()).toBeVisible()
    await expect(page.getByRole('region', { name: 'Study Lab research results' })).toContainText('No persisted studies yet.')
    await expect(study.locator('.study-bars canvas')).toBeVisible()
    await expect(study.locator('.study-histogram canvas')).toBeVisible()
    await expect(page).toHaveScreenshot('study-lab-structured-result-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('Study Lab sandbox-error gap state has a deterministic local baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    const failedRun = {
      id: 780,
      code_version_id: 779,
      status: 'failed',
      progress: { status: 'failed', completed_cells: 1, total_cells: 1 },
      diagnostics: [{ code: 'sandbox_violation', message: 'Network access is disabled in the isolated research runner.', source_span: { line: 1, column: 1 } }],
      warnings: [{ code: 'run_aborted', message: 'The isolated run was terminated before producing artifacts.' }],
      logs: 'sandbox policy denied socket access; run terminated',
      resource_usage: { wall_ms: 18, cpu_ms: 4 },
      reproducibility_hash: null,
      dataset_manifest: { benchmark_coverage: { status: 'ready' } },
      artifacts: [],
    }
    // This local screenshot intentionally depicts the Study failure while the
    // adjacent chart, persisted-results list, and shared analysis are loading.
    // Hold those reads explicitly so browser speed/viewport cannot decide which
    // state the visual oracle captures.
    await page.route(/\/api\/v1\/market-groups\/us-benchmarks(?:\?.*)?$/, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      await new Promise<void>(() => {})
    })
    await page.route(/\/api\/v1\/ohlcv\/(?:local\/)?SPY\/[^/?]+(?:\/transformed)?(?:\?.*)?$/, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      await new Promise<void>(() => {})
    })
    // R5 uses a 26-row lookahead; keep this deterministic loading fixture tied
    // to the initial page rather than a particular requested page size.
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ versions: [{ id: 779 }] }) })
    })
    await page.route(url => url.pathname.endsWith('/api/v1/research/runs'), async route => {
      if (route.request().method() === 'GET') {
        const requestUrl = new URL(route.request().url())
        if (!requestUrl.searchParams.has('before_created_at') && !requestUrl.searchParams.has('before_id')) {
          // Keep the first persisted-runs page pending; later pagination remains
          // an ordinary backend request and cannot be shadowed by another route.
          await new Promise<void>(() => undefined)
          return
        }
        await route.continue()
        return
      }
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(failedRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/780$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(failedRun) })
    })
    await page.goto('/chart')
    await waitForShellReady(page, 'expected-chart-loading')
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual sandbox failure')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('sandbox_error', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run study', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--failed')).toBeVisible({ timeout: 10_000 })
    await expect(study).toContainText('Run #780')
    const diagnostics = study.locator('.study-lab-tool__run-details').filter({ hasText: 'Diagnostics (1)' })
    await diagnostics.locator('summary').click()
    await expect(diagnostics).toContainText('Network access is disabled')
    const warnings = study.locator('.study-lab-tool__run-details').filter({ hasText: 'Warnings (1)' })
    await warnings.locator('summary').click()
    await expect(warnings).toContainText('run was terminated')
    await expect(study).toContainText('Rerun snapshot')
    await expect(page.locator('.workstation__refresh')).toHaveText('Refreshing…')
    await expect(page.locator('.chart-tool .tool-state')).toHaveText('Loading SPY…')
    await expect(page.getByRole('region', { name: 'Study Lab research results' }))
      .toContainText('Loading reproducible research runs…')
    await expect(page).toHaveScreenshot('study-lab-sandbox-error-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

})
