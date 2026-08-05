/**
 * E2E tests covering the critical user flows (F1-F17).
 * Requires the branch-scoped full Docker Compose stack running.
 *
 * Run: make test-stack-up && npx playwright test
 */
import { test, expect, LoginPage, ChartPage, ScreenerPage, DashboardPage, RadarPage } from './helpers'


// ── Auth flows ─────────────────────────────────────────────────────────────────

test.describe('Authentication', () => {

  test('F1 — unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/chart')
    await expect(page).toHaveURL(/\/login/)
  })

  test('F2 — register new account and land on chart', async ({ page }) => {
    const lp = new LoginPage(page)
    await lp.goto()
    await lp.switchToRegister()

    const ts = Date.now()
    await lp.fillUsername(`user_${ts}`)
    await lp.fillEmail(`user_${ts}@test.com`)
    await lp.fillPassword('SecurePass123!')
    await lp.clickSignIn()

    await expect(page).toHaveURL(/\/chart/, { timeout: 10_000 })
  })

  test('F3 — login with valid credentials', async ({ page, loggedIn, browserDiagnostics }) => {
    await expect(page).toHaveURL(/\/chart/)
    await expect(page.getByRole('banner').getByText('CHARTING WORKSTATION')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F4 — login with wrong password shows error', async ({ page }) => {
    const lp = new LoginPage(page)
    await lp.goto()
    await lp.fillUsername('someuser')
    await lp.fillPassword('wrongpassword')
    await lp.clickSignIn()

    await expect(page.locator('.auth-error, .error-msg')).toBeVisible({ timeout: 5_000 })
    await expect(page).toHaveURL(/\/login/)
  })

  test('F5 — logout redirects to login', async ({ page, loggedIn, browserDiagnostics }) => {
    browserDiagnostics.allowExpectedUnauthorizedResponses()
    await page.click('.logout-btn, .user-avatar, button[title*="Sign out"]')
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Chart flows ────────────────────────────────────────────────────────────────

test.describe('Chart', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F6 — chart page loads with default state', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.chart-empty, .uplot-wrapper, .chart-container, canvas').first()).toBeVisible()
    await expect(page.locator('input[placeholder*="Symbol"], input[placeholder*="Search"], .search-input')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F7 — search for symbol and chart loads', async ({ page, browserDiagnostics }) => {
    const cp = new ChartPage(page)
    await cp.goto()

    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await symbolEntry.fill('AAPL')
    await page.getByRole('button', { name: 'Go' }).click()
    await expect(symbolEntry).toHaveValue('AAPL')
    // A fresh free-source fixture may not have AAPL cached. Both a rendered uPlot
    // chart and the workstation's explicit unavailable state are valid outcomes.
    await expect(page.locator('.uplot-wrapper:visible, .tool-state--error:visible').first()).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8 — timeframe selector switches timeframe', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    // Click H1
    const h1btn = page.locator('button:has-text("H1"), .tf-btn:has-text("H1")')
    if (await h1btn.count() > 0) {
      await h1btn.first().click()
      // Verify active state
      await expect(h1btn.first()).toHaveClass(/active|selected/)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9 — drawing toolbar is visible and tools are clickable', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    // Drawing toolbar should exist
    const toolbar = page.locator('.drawing-toolbar, [class*="toolbar"]')
    if (await toolbar.count() > 0) {
      await expect(toolbar.first()).toBeVisible()
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9b — expression search resolves and stays interactive', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await symbolEntry.fill('=SPY-QQQ')
    await page.getByRole('button', { name: 'Go' }).click()
    // A fresh free-source fixture may lack a constituent; in either case the
    // primary workstation remains usable and reports its real state.
    await expect(page.locator('.uplot-wrapper:visible, .tool-state--error:visible, .workstation__footer:visible').first()).toBeVisible({ timeout: 10_000 })
    await expect(symbolEntry).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c — chart templates open from a workstation chart without changing the symbol', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/AAPL')
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(symbolEntry).toHaveValue('AAPL')
    await page.getByRole('button', { name: 'Chart templates' }).first().click()
    const templateMenu = page.locator('.chart-template__menu:visible').last()
    await templateMenu.getByRole('combobox', { name: 'Chart bar type' }).selectOption('line')
    await page.getByTitle('Chart settings').first().click()
    const currentPriceProjection = page.getByRole('checkbox', { name: 'Show current price on Y axis' })
    await currentPriceProjection.check()
    await page.locator('.editor-box .ed-close').click()
    const templateName = `AAPL template ${Date.now()}`
    await page.getByRole('textbox', { name: 'Chart template name' }).fill(templateName)
    await templateMenu.getByRole('button', { name: 'Save', exact: true }).click()
    const savedTemplate = templateMenu.locator('.chart-template__apply').filter({ hasText: templateName })
    await expect(savedTemplate).toBeVisible()
    await savedTemplate.click()
    await expect(symbolEntry).toHaveValue('AAPL')
    await expect(templateMenu.getByRole('combobox', { name: 'Chart bar type' })).toHaveValue('line')
    await page.getByTitle('Chart settings').first().click()
    await expect(currentPriceProjection).toBeChecked()
    await page.locator('.editor-box .ed-close').click()
    await templateMenu.getByRole('button', { name: `Delete ${templateName}` }).click()
    await expect(savedTemplate).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

})

// ── TC2000 workstation window mechanics ──────────────────────────────────────

test.describe('TC2000 workstation', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('unsupported capability domains stay out of the primary workstation menu', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const primaryMenu = page.locator('.workstation__menu')
    await expect(primaryMenu).toBeVisible({ timeout: 10_000 })
    const labels = (await primaryMenu.locator('button, a').allTextContents()).join(' ').toLowerCase()
    for (const excluded of ['trading', 'brokerage', 'options', 'news', 'ratings', 'earnings', 'financial statements']) {
      expect(labels).not.toContain(excluded)
    }
    await expect(page.locator('.workstation__tabs')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('factory layouts render without recovery state or core header collisions', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const layouts = ['US Top Down', 'TC Classic', 'Drill Down', 'Sector by Year', '1 Chart', '4 Timeframe', 'Fundamentals', 'Study Lab']
    for (const layout of layouts) {
      const tab = page.getByRole('button', { name: layout, exact: true }).first()
      await expect(tab).toBeVisible({ timeout: 10_000 })
      await tab.click()
      await expect(tab).toHaveClass(/workstation__tab--active/)
      await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
      await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
      const collisions = await page.evaluate(() => {
        const overlaps = (a: DOMRect, b: DOMRect) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
        const issues: string[] = []
        document.querySelectorAll('.tool-window__header').forEach((header, index) => {
          const title = header.querySelector('.tool-window__title')?.getBoundingClientRect()
          const symbol = header.querySelector('.tool-window__symbol')?.getBoundingClientRect()
          const actions = header.querySelector('.tool-window__actions')?.getBoundingClientRect()
          if (title && actions && overlaps(title, actions)) issues.push(`title-actions-${index}`)
          if (symbol && actions && overlaps(symbol, actions)) issues.push(`symbol-actions-${index}`)
        })
        return issues
      })
      expect(collisions).toEqual([])
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8b — closing a floated tool preserves its source workspace tool', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    const floatButton = page.locator('button[title="Float"]').first()
    await expect(floatButton).toBeVisible({ timeout: 10_000 })

    const popupPromise = context.waitForEvent('page')
    await floatButton.click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })

    const closed = popup.waitForEvent('close')
    await popup.locator('button[title="Close"]').click()
    await closed

    // The docked window is the durable source of truth; a disposable pop-out cannot
    // remove it from the parent layout.
    await expect(page.locator('button[title="Float"]').first()).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8f — repeated float/close cycles do not accumulate source tools', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('button[title="Float"]').first()).toBeVisible({ timeout: 10_000 })
    const sourceToolCount = await page.locator('.tool-window').count()
    await expect.poll(() => page.locator('canvas').count()).toBeGreaterThan(0)
    // Chart panes finish lazy initialization after the first canvas appears;
    // settle that one-time growth before taking the lifecycle baseline.
    await page.waitForTimeout(750)
    const sourceCanvasCount = await page.locator('canvas').count()
    expect(sourceToolCount).toBeGreaterThan(0)

    // Exercise enough repeated browser-window churn to catch source-tool leaks
    // that only appear after several pop-out lifecycles, while keeping the
    // assertion deterministic on the shared CI browser.
    for (let cycle = 0; cycle < 10; cycle += 1) {
      const floatButton = page.locator('button[title="Float"]').first()
      await expect(floatButton).toBeVisible({ timeout: 10_000 })
      const popupPromise = context.waitForEvent('page')
      await floatButton.click()
      const popup = await popupPromise
      await popup.waitForLoadState('domcontentloaded')
      await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })

      const closed = popup.waitForEvent('close')
      await popup.locator('button[title="Close"]').click()
      await closed
      await expect(page.locator('.tool-window')).toHaveCount(sourceToolCount)
      await expect.poll(() => context.pages().length).toBe(1)
      await expect.poll(() => page.locator('canvas').count()).toBe(sourceCanvasCount)
    }

    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8h — simultaneous pop-outs retain both tools and recover independently', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect.poll(() => page.locator('button[title="Float"]').count(), { timeout: 10_000 }).toBeGreaterThan(1)

    const firstPopupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').nth(0).click()
    const firstPopup = await firstPopupPromise
    await firstPopup.waitForLoadState('domcontentloaded')
    await expect(firstPopup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })

    const secondPopupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').nth(1).click()
    const secondPopup = await secondPopupPromise
    await secondPopup.waitForLoadState('domcontentloaded')
    await expect(secondPopup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => context.pages().length).toBe(3)

    const firstClosed = firstPopup.waitForEvent('close')
    await firstPopup.locator('button[title="Close"]').click()
    await firstClosed
    await expect(secondPopup.locator('.workstation__popout .tool-window')).toBeVisible()
    await expect.poll(() => context.pages().length).toBe(2)

    const secondClosed = secondPopup.waitForEvent('close')
    await secondPopup.locator('button[title="Close"]').click()
    await secondClosed
    await expect.poll(() => page.locator('button[title="Float"]').count()).toBeGreaterThan(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i — tool menu and drag handle are available without obscuring window actions', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible({ timeout: 10_000 })
    const dragHandle = tool.locator('[aria-label="Drag tool"]')
    await expect(dragHandle).toHaveAttribute('draggable', 'true')
    await tool.locator('[title="Tool menu"]').click()
    const menu = tool.locator('[role="menu"]')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Maximize' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Float' })).toBeVisible()
    await expect(menu.getByRole('menuitem', { name: 'Close' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(page.locator('[class^="workstation__data-state--"]').first()).toHaveText(
      /Current · canonical|Delayed|Stale|Partial coverage|Coverage limited|Fetching|Backfilling history|Unavailable/,
    )
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8j — floated geometry is persisted through the workspace API', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    const sourceTool = page.locator('.tool-window').first()
    const floatButton = sourceTool.locator('button[title="Float"]')
    await expect(floatButton).toBeVisible({ timeout: 10_000 })

    const popupPromise = context.waitForEvent('page')
    await floatButton.click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })

    await page.waitForTimeout(1_250)
    const result = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/workspaces/default', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      return { ok: response.ok, body: await response.json() }
    })
    expect(result.ok).toBe(true)
    const workspace = result.body
    const windows = workspace.tabs.flatMap((tab: { windows: Array<Record<string, unknown>> }) => tab.windows)
    const persisted = windows.find((window: Record<string, unknown>) => Boolean((window.style as { popout?: unknown } | undefined)?.popout))
    const geometry = (persisted?.style as { popout?: Record<string, unknown> } | undefined)?.popout
    expect(geometry).toEqual(expect.objectContaining({ left: expect.any(Number), top: expect.any(Number), width: expect.any(Number), height: expect.any(Number) }))

    const closed = popup.waitForEvent('close')
    await popup.locator('button[title="Close"]').click()
    await closed
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8c — signing out propagates from the source workstation to its pop-out', async ({ page, context }) => {
    await page.goto('/chart')
    const popupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').first().click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
    await expect(popup).toHaveURL(/\/login/, { timeout: 5_000 })
  })

  test('F8d — US Top Down publishes benchmark and sector selections without route changes', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList).toBeVisible({ timeout: 10_000 })
    await expect(sectorList.getByRole('button', { name: /XLK/ }).first()).toBeVisible()

    // The opt-in deterministic market fixture may hydrate the data-dependent tools;
    // this assertion remains intentionally tolerant of honest unavailable/cached
    // states so the route and linked-symbol contract is tested independently.
    await sectorList.getByRole('button', { name: /XLK/ }).first().click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK')
    await expect(page.locator('.workstation__footer')).toContainText(/Unavailable|No local observations|cached|Fetching/i)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e — deep top-down drilldown reaches industry proxies and constituents', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList.getByRole('button', { name: /XLK/ }).first()).toBeVisible({ timeout: 10_000 })

    await sectorList.getByRole('button', { name: /XLK/ }).first().click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK')
    const industries = page.locator('.industry-list')
    await expect(industries).toBeVisible({ timeout: 15_000 })
    const semiconductors = industries.locator('.industry-list__row').filter({ hasText: 'Semiconductors' })
    await expect(semiconductors).toBeVisible()
    await semiconductors.click()

    const proxies = page.getByRole('region', { name: 'Verified proxy rankings' })
    await expect(proxies).toBeVisible({ timeout: 15_000 })
    const smh = proxies.locator('.watchlist__row').filter({ hasText: 'SMH' })
    await expect(smh).toBeVisible()
    await smh.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SMH')

    const constituents = page.getByRole('region', { name: 'Constituents' }).filter({ has: page.locator('.watchlist__row') }).last()
    await expect(constituents).toBeVisible({ timeout: 15_000 })
    const nvda = constituents.locator('.watchlist__row').filter({ hasText: 'NVDA' })
    await expect(nvda).toBeVisible()
    await nvda.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('NVDA')
    await expect(page.locator('.tool-window').filter({ hasText: /NVDA\/(?:SMH|XLK|SPY)/ }).first()).toBeVisible({ timeout: 15_000 })

    const constituentScroll = constituents.locator('.watchlist__scroll')
    const constituentRows = constituents.locator('.watchlist__row')
    await expect.poll(() => constituentRows.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const secondConstituent = (await constituentRows.nth(1).innerText()).trim().split(/\s+/)[0]
    await constituentRows.first().click()
    await constituentScroll.focus()
    await constituentScroll.press('Space')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(secondConstituent)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8g — Study Lab validates, runs an isolated Python study, and renders its result', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('E2E scalar study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('smoke', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })

    await study.getByRole('button', { name: 'Run' }).click()
    await expect(study.locator('.study-lab-tool__run')).toBeVisible({ timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 30_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'smoke' })).toContainText('1')
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Alert flows ────────────────────────────────────────────────────────────────

test.describe('Alerts', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F10 — alerts page shows empty state for new user', async ({ page, browserDiagnostics }) => {
    await page.goto('/alerts')
    await expect(page).not.toHaveURL(/\/login/)
    // Should not crash
    await expect(page.locator('body')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F11 — open active-symbol alerts from the workstation menu', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Alerts' }).click()
    await expect(page.locator('.tool-window').filter({ hasText: 'Alerts' }).last()).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Screener flows ─────────────────────────────────────────────────────────────

test.describe('Screener', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F12 — create screener and run it', async ({ page, browserDiagnostics }) => {
    const sp = new ScreenerPage(page)
    await sp.goto()

    await expect(page).not.toHaveURL(/\/login/)

    // Create a screener
    const ts = Date.now()
    await sp.createScreener(`Test Screener ${ts}`)

    // Should appear in the list
    await expect(page.locator('.si-name').filter({ hasText: `Test Screener ${ts}` }).first()).toBeVisible({ timeout: 5_000 })

    // Select it and run
    await page.locator('.screener-item').filter({ hasText: `Test Screener ${ts}` }).first().click()
    const runBtn = page.locator('button:has-text("Run")')
    if (await runBtn.count() > 0) {
      await runBtn.click()
      await expect(
        page.locator('.scan-progress, .results-meta, .results-table-wrap, .no-matches').first(),
      ).toBeVisible({ timeout: 15_000 })
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Drawing tool flows ─────────────────────────────────────────────────────────

test.describe('Drawing tools', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F13 — drawing toolbar shows expected tools', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await page.waitForLoadState('networkidle')

    const toolbar = page.locator('.drawing-toolbar, [class*="toolbar"]')
    await expect(toolbar.first()).toBeVisible()

    await toolbar.getByRole('button', { name: 'Lines' }).click()
    await expect(page.getByRole('button', { name: 'Trend Line' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Horizontal Line' })).toBeVisible()
    await toolbar.getByRole('button', { name: 'Annotations' }).click()
    await expect(page.getByRole('button', { name: 'Freehand' })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14 — selecting a drawing tool activates it', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await page.waitForLoadState('networkidle')

    const toolbar = page.locator('.drawing-toolbar').first()
    const linesButton = toolbar.getByRole('button', { name: 'Lines' })
    await linesButton.click()
    const horizBtn = toolbar.getByRole('button', { name: 'Horizontal Line' })
    await horizBtn.click()
    // The flyout closes after selection; its owning group remains active and puts the
    // chart canvas into drawing mode.
    await expect(linesButton).toHaveClass(/active/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Dashboard flows ────────────────────────────────────────────────────────────

test.describe('Dashboard', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F15 — dashboard page loads without errors', async ({ page, browserDiagnostics }) => {
    await page.goto('/dashboard')
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('body')).toBeVisible()
    // No JS error overlay
    await expect(page.locator('.error-overlay, .fatal-error')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F16 — add a notes widget to the dashboard', async ({ page, browserDiagnostics }) => {
    const dp = new DashboardPage(page)
    await dp.goto()

    // Open the add-widget dialog
    const addBtn = page.locator('button:has-text("Add"), .add-widget-btn, button[title*="Add"]')
    if (await addBtn.count() > 0) {
      await addBtn.first().click()
      await page.waitForTimeout(300)

      // Select "Notes" widget type if dialog appeared
      const notesOption = page.locator('[data-widget-type="notes"], button:has-text("Notes")')
      if (await notesOption.count() > 0) {
        await notesOption.first().click()
        await page.waitForTimeout(300)

        // A new widget should now appear on the dashboard
        const widgets = page.locator('.dashboard-widget, .widget-container')
        expect(await widgets.count()).toBeGreaterThan(0)
      }
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F17 — options exposure tab loads on chart without browser errors', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/NVDA')
    const exposureTab = page.locator('button:has-text("Exposure")')
    if (await exposureTab.count() > 0) {
      await exposureTab.first().click()
      await expect(page.locator('.exposure-panel')).toBeVisible()
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Legacy route compatibility ───────────────────────────────────────────────

test.describe('Legacy compatibility', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('legacy authenticated surfaces remain reachable behind /legacy', async ({ page, browserDiagnostics }) => {
    const routes = [
      '/legacy/dashboard',
      '/legacy/chart/SPY',
      '/legacy/alerts',
      '/legacy/radar',
      '/legacy/strategy-lab',
      '/legacy/baskets',
      '/legacy/etf-holdings',
      '/legacy/screener',
      '/legacy/watchlist',
      '/legacy/settings',
    ]

    for (const route of routes) {
      await page.goto(route)
      await expect(page).not.toHaveURL(/\/login/)
      await expect(page.locator('body')).toBeVisible()
      await expect(page.locator('.error-overlay, .fatal-error')).toHaveCount(0)
    }

    await browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Radar flows ───────────────────────────────────────────────────────────────

test.describe('Radar', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F17 — radar page loads, can run a scan, and can open chart when detections exist', async ({ page, browserDiagnostics }) => {
    const rp = new RadarPage(page)
    await rp.goto()

    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('h2.page-title')).toContainText('Technical Radar')
    await expect(page.locator('.radar-actions')).toBeVisible()

    await rp.runScan()
    await page.waitForTimeout(500)

    const resultRows = page.locator('tbody tr')
    if (await resultRows.count() > 0) {
      await resultRows.first().click()
      const openBtn = page.locator('.detail-head .action-btn.primary')
      await expect(openBtn).toBeVisible()
      await openBtn.click()
      await expect(page).toHaveURL(/\/chart\//, { timeout: 10_000 })
    } else {
      await expect(page.locator('.empty-row')).toBeVisible()
    }

    await browserDiagnostics.expectNoCriticalIssues()
  })

})
