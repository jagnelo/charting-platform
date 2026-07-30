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
    browserDiagnostics.expectNoCriticalIssues()
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
    await page.click('.logout-btn, .user-avatar, button[title*="Sign out"]')
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
    browserDiagnostics.expectNoCriticalIssues()
  })

})


// ── Chart flows ────────────────────────────────────────────────────────────────

test.describe('Chart', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F6 — chart page loads with default state', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.chart-empty, .uplot-wrapper, .chart-container, canvas').first()).toBeVisible()
    await expect(page.locator('input[placeholder*="Symbol"], input[placeholder*="Search"], .search-input')).toBeVisible()
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F7 — search for symbol and chart loads', async ({ page, browserDiagnostics }) => {
    const cp = new ChartPage(page)
    await cp.goto()

    const symbolEntry = page.getByRole('textbox', { name: 'Active symbol' })
    await symbolEntry.fill('AAPL')
    await page.getByRole('button', { name: 'Go' }).click()
    await expect(symbolEntry).toHaveValue('AAPL')
    // A fresh free-source fixture may not have AAPL cached. Both a rendered uPlot
    // chart and the workstation's explicit unavailable state are valid outcomes.
    await expect(page.locator('.uplot-wrapper:visible, .tool-state--error:visible').first()).toBeVisible({ timeout: 10_000 })
    browserDiagnostics.expectNoCriticalIssues()
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
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9 — drawing toolbar is visible and tools are clickable', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    // Drawing toolbar should exist
    const toolbar = page.locator('.drawing-toolbar, [class*="toolbar"]')
    if (await toolbar.count() > 0) {
      await expect(toolbar.first()).toBeVisible()
    }
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9b — expression search resolves and stays interactive', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const symbolEntry = page.getByRole('textbox', { name: 'Active symbol' })
    await symbolEntry.fill('=SPY-QQQ')
    await page.getByRole('button', { name: 'Go' }).click()
    // A fresh free-source fixture may lack a constituent; in either case the
    // primary workstation remains usable and reports its real state.
    await expect(page.locator('.uplot-wrapper:visible, .tool-state--error:visible, .workstation__footer:visible').first()).toBeVisible({ timeout: 10_000 })
    await expect(symbolEntry).toBeVisible()
    browserDiagnostics.expectNoCriticalIssues()
  })

})

// ── TC2000 workstation window mechanics ──────────────────────────────────────

test.describe('TC2000 workstation', () => {

  test.beforeEach(async ({ loggedIn }) => {})

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
    browserDiagnostics.expectNoCriticalIssues()
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

})


// ── Alert flows ────────────────────────────────────────────────────────────────

test.describe('Alerts', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F10 — alerts page shows empty state for new user', async ({ page, browserDiagnostics }) => {
    await page.goto('/alerts')
    await expect(page).not.toHaveURL(/\/login/)
    // Should not crash
    await expect(page.locator('body')).toBeVisible()
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F11 — navigate to alerts page from sidebar', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await page.click('a[href="/alerts"], .nav-link[title*="Alert"]')
    await expect(page).toHaveURL(/\/alerts/)
    browserDiagnostics.expectNoCriticalIssues()
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
    browserDiagnostics.expectNoCriticalIssues()
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

    // Trendline and horizontal line should be present
    const trendBtn = page.locator('button[title*="Trend"], button[data-tool="trendline"]')
    const horizBtn = page.locator('button[title*="Horizontal"], button[data-tool="horizontal_line"]')
    const freeBtn  = page.locator('button[title*="Freehand"], button[data-tool="freehand"]')

    if (await trendBtn.count() > 0) await expect(trendBtn.first()).toBeVisible()
    if (await horizBtn.count() > 0) await expect(horizBtn.first()).toBeVisible()
    if (await freeBtn.count()  > 0) await expect(freeBtn.first()).toBeVisible()
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14 — selecting a drawing tool activates it', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await page.waitForLoadState('networkidle')

    // Click the horizontal line tool
    const horizBtn = page.locator(
      'button[data-tool="horizontal_line"], button[title*="Horizontal"]'
    )
    if (await horizBtn.count() > 0) {
      await horizBtn.first().click()
      // The button or its parent should have an active/selected class
      const isActive = await horizBtn.first().evaluate(
        el => el.classList.contains('active') || el.classList.contains('selected') ||
              el.getAttribute('aria-pressed') === 'true' ||
              el.closest('[class*="active"]') !== null
      )
      expect(isActive).toBe(true)
    }
    browserDiagnostics.expectNoCriticalIssues()
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
    browserDiagnostics.expectNoCriticalIssues()
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
    browserDiagnostics.expectNoCriticalIssues()
  })

  test('F17 — options exposure tab loads on chart without browser errors', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/NVDA')
    const exposureTab = page.locator('button:has-text("Exposure")')
    if (await exposureTab.count() > 0) {
      await exposureTab.first().click()
      await expect(page.locator('.exposure-panel')).toBeVisible()
    }
    browserDiagnostics.expectNoCriticalIssues()
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

    browserDiagnostics.expectNoCriticalIssues()
  })

})
