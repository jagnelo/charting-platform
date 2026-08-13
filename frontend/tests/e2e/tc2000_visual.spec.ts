/**
 * Board-guided visual parity. The npm commands gate the strict exact-build variant through
 * the backend manifest validator; the board variant uses the accepted composite board policy
 * and still requires deterministic local geometry and screenshot evidence.
 */
import type { Page } from '@playwright/test'
import { test, expect } from './helpers'

async function assertSeededBackend(page: Page) {
  if (process.env.E2E_SEED_MARKET_DATA !== 'true') return
  const response = await page.request.get('/health')
  expect(response.ok()).toBe(true)
  expect(response.headers()['content-type'] ?? '', 'health probe must return backend JSON').toContain('application/json')
  const payload = await response.json() as { e2e_seed_market_data?: boolean }
  expect(payload.e2e_seed_market_data, 'visual fixture mode must match the backend stack').toBe(true)
}

async function waitForShellReady(page: Page) {
  await expect(page.locator('.workstation')).toBeVisible()
  await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
  await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15_000 })
  if (process.env.E2E_SEED_MARKET_DATA === 'true') {
    await expect(page.locator('.ratio-chart__legend strong').first()).toHaveText('SPY/RSP', { timeout: 15_000 })
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
    await page.waitForTimeout(750)
    await expect(page.locator('.workstation__refresh')).toHaveText('Refresh', { timeout: 15_000 })
  }
}

test.describe('TC2000 Version 25 board-guided visual parity', () => {
  test.skip(
    process.env.RUN_APPROVED_VISUAL_PARITY !== '1' && process.env.RUN_BOARD_VISUAL_PARITY !== '1',
    'requires approved references or the accepted board-guided visual policy',
  )

  test.beforeEach(async ({ page }) => {
    await assertSeededBackend(page)
    // Visual cases share the authenticated fixture user. Restore the immutable
    // factory before each capture so a preceding interaction (for example a
    // resized watchlist column or a floated tool) cannot contaminate a later
    // environment's screenshot.
    await page.goto('/')
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
      await expect(page.locator('.workstation__layout-state')).toHaveCount(0, { timeout: 15_000 })
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
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('application shell workspace menu open state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    await page.getByRole('button', { name: 'Workspace', exact: true }).click()
    const menu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Clone', exact: true })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Export', exact: true })).toBeVisible()
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
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible()
    await tool.locator('[title="Tool menu"]').click()
    const menu = tool.getByRole('menu')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Maximize' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Float' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Close' })).toBeVisible()
    await expect(page).toHaveScreenshot('workspace-tool-menu-open.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('watchlist column editor open state has a deterministic board baseline', async ({ page, loggedIn, browserDiagnostics }) => {
    await page.goto('/')
    await waitForShellReady(page)
    const benchmarks = page.getByRole('region', { name: 'Major US benchmarks' })
    await expect(benchmarks).toBeVisible()
    await benchmarks.getByRole('button', { name: 'Columns', exact: true }).click()
    const editor = benchmarks.locator('.watchlist__column-menu')
    await expect(editor).toBeVisible()
    await expect(editor.getByRole('button', { name: 'Paste column settings' })).toBeVisible()
    await expect(editor.locator('.watchlist__column-editor-row')).toHaveCount(15)
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
    await page.getByRole('button', { name: 'Add tool', exact: true }).click()
    const toolMenu = page.getByRole('menu', { name: 'Workstation tools' })
    await expect(toolMenu).toBeVisible()
    await toolMenu.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    // The factory layout may retain an older hidden EasyScan virtual component;
    // target the newly foregrounded visible tool rather than a hidden tab body.
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 10_000 })
    await scan.getByRole('button', { name: 'Build technical condition tree', exact: true }).click()
    await expect(scan.getByRole('region', { name: 'Advanced technical condition builder' })).toBeVisible()
    await expect(scan.getByRole('combobox', { name: 'Condition group operator' })).toHaveValue('AND')
    await expect(scan.getByRole('button', { name: '+ Condition', exact: true })).toBeVisible()
    await expect(scan.getByRole('button', { name: '+ Group', exact: true })).toBeVisible()
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
    await tool.locator('[title="Tool menu"]').click()
    await tool.getByRole('menuitem', { name: 'Maximize' }).click()
    await expect(page.locator('.lm_maximised')).toHaveCount(1)
    await expect(tool).toBeVisible()
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
    const tabs = page.locator('.lm_tab:visible')
    await expect.poll(() => tabs.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const selectedTab = tabs.nth(1)
    await selectedTab.click()
    await expect(selectedTab).toHaveClass(/lm_active/)
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
    await tool.locator('[title="Tool menu"]').click()
    await tool.getByRole('menuitem', { name: 'Maximize' }).click()
    await expect(page.locator('.lm_maximised')).toHaveCount(1)
    await tool.locator('button[title="Maximize"]').click()
    await expect(page.locator('.lm_maximised')).toHaveCount(0)
    await expect(tool).toBeVisible()
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
    const popupPromise = context.waitForEvent('page')
    await sourceTool.locator('button[title="Float"]').click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    const popoutTool = popup.locator('.workstation__popout .tool-window')
    await expect(popoutTool).toBeVisible({ timeout: 15_000 })
    await expect(popup).toHaveScreenshot('workspace-floating.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    if (!popup.isClosed()) {
      const closed = popup.waitForEvent('close')
      await popoutTool.locator('button[title="Close"]').click()
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
    const menu = page.getByRole('menu', { name: 'Keyboard shortcuts' })
    await expect(menu).toBeVisible()
    await expect(menu).toContainText('Shift+Space')
    await expect(menu).toContainText('Shortcuts are inactive while a text, numeric, code, or search editor owns focus.')
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
    await expect(study.getByRole('button', { name: 'Run', exact: true })).toBeVisible()
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
    await expect(study.getByRole('button', { name: 'Run', exact: true })).toBeDisabled()
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
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(runningRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/778$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(runningRun) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual running study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('running', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--running')).toBeVisible({ timeout: 10_000 })
    await expect(study).toContainText('running 12/100')
    await expect(study.getByRole('button', { name: 'Cancel', exact: true })).toBeVisible()
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
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(structuredRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/779$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(structuredRun) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual structured study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('event_count', 4)\noutput.bar('monthly_frequency', ['2026-01', '2026-02'], [2, 2])\noutput.histogram('streak_distribution', [1, 2, 2, 3], 2, 2)\noutput.table('summary', [{'state': 'positive_close', 'count': 4}])\noutput.events('occurrences', [{'symbol': 'SPY', 'timestamp': '2026-01-02T00:00:00+00:00', 'kind': 'positive_close'}])")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'event_count' })).toContainText('4')
    await expect(study.locator('.study-bars-uplot, [class*="study-bars"]').first()).toBeVisible()
    await expect(study.locator('.study-histogram-uplot, [class*="study-histogram"]').first()).toBeVisible()
    await expect(study.locator('table').filter({ hasText: 'positive_close' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__events button').filter({ hasText: 'positive_close' })).toBeVisible()
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
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, diagnostics: [], dependencies: ['output'], lookback_hint: null, output_contracts: ['scalar'] }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ versions: [{ id: 779 }] }) })
    })
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(failedRun) })
    })
    await page.route(/\/api\/v1\/research\/runs\/780$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(failedRun) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('Visual sandbox failure')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('sandbox_error', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--failed')).toBeVisible({ timeout: 10_000 })
    await expect(study).toContainText('Run #780')
    const diagnostics = study.locator('.study-lab-tool__run-details').filter({ hasText: 'Diagnostics (1)' })
    await diagnostics.locator('summary').click()
    await expect(diagnostics).toContainText('Network access is disabled')
    const warnings = study.locator('.study-lab-tool__run-details').filter({ hasText: 'Warnings (1)' })
    await warnings.locator('summary').click()
    await expect(warnings).toContainText('run was terminated')
    await expect(study).toContainText('Rerun snapshot')
    await expect(page).toHaveScreenshot('study-lab-sandbox-error-gap.png', {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.005,
      scale: 'css',
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

})
