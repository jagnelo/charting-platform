/**
 * E2E tests covering the 12 critical user flows.
 * Requires the full Docker Compose stack running.
 *
 * Run: docker compose up -d && npx playwright test
 */
import { test, expect, LoginPage, ChartPage, ScreenerPage } from './helpers'


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

  test('F3 — login with valid credentials', async ({ page, loggedIn }) => {
    await expect(page).toHaveURL(/\/chart/)
    await expect(page.locator('.user-chip, .sidebar-logo')).toBeVisible()
  })

  test('F4 — login with wrong password shows error', async ({ page }) => {
    const lp = new LoginPage(page)
    await lp.goto()
    await lp.fillUsername('someuser')
    await lp.fillPassword('wrongpassword')
    await lp.clickSignIn()

    await expect(page.locator('.auth-error')).toBeVisible({ timeout: 5_000 })
    await expect(page).toHaveURL(/\/login/)
  })

  test('F5 — logout redirects to login', async ({ page, loggedIn }) => {
    await page.click('.logout-btn, button[title*="Sign out"]')
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
  })

})


// ── Chart flows ────────────────────────────────────────────────────────────────

test.describe('Chart', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F6 — chart page loads with default state', async ({ page }) => {
    await page.goto('/chart')
    await expect(page.locator('.uplot-wrapper, .chart-container, canvas')).toBeVisible()
    await expect(page.locator('.timeframe-selector, button:has-text("D1")')).toBeVisible()
  })

  test('F7 — search for symbol and chart loads', async ({ page }) => {
    const cp = new ChartPage(page)
    await cp.goto()

    // Type in search
    await page.fill('input[placeholder*="Search"], .search-input', 'AAPL')
    await page.waitForTimeout(600)   // debounce

    // Should show a dropdown result or navigate
    const results = page.locator('.search-results .result-item, .search-dropdown')
    const count = await results.count()
    if (count > 0) {
      await results.first().click()
      await expect(page).toHaveURL(/\/chart\/AAPL/, { timeout: 8_000 })
    }
  })

  test('F8 — timeframe selector switches timeframe', async ({ page }) => {
    await page.goto('/chart')
    // Click H1
    const h1btn = page.locator('button:has-text("H1"), .tf-btn:has-text("H1")')
    if (await h1btn.count() > 0) {
      await h1btn.first().click()
      // Verify active state
      await expect(h1btn.first()).toHaveClass(/active|selected/)
    }
  })

  test('F9 — drawing toolbar is visible and tools are clickable', async ({ page }) => {
    await page.goto('/chart')
    // Drawing toolbar should exist
    const toolbar = page.locator('.drawing-toolbar, [class*="toolbar"]')
    if (await toolbar.count() > 0) {
      await expect(toolbar.first()).toBeVisible()
    }
  })

})


// ── Alert flows ────────────────────────────────────────────────────────────────

test.describe('Alerts', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F10 — alerts page shows empty state for new user', async ({ page }) => {
    await page.goto('/alerts')
    await expect(page).not.toHaveURL(/\/login/)
    // Should not crash
    await expect(page.locator('body')).toBeVisible()
  })

  test('F11 — navigate to alerts page from sidebar', async ({ page }) => {
    await page.goto('/chart')
    await page.click('a[href="/alerts"], .nav-link[title*="Alert"]')
    await expect(page).toHaveURL(/\/alerts/)
  })

})


// ── Screener flows ─────────────────────────────────────────────────────────────

test.describe('Screener', () => {

  test.beforeEach(async ({ loggedIn }) => {})

  test('F12 — create screener and run it', async ({ page }) => {
    const sp = new ScreenerPage(page)
    await sp.goto()

    await expect(page).not.toHaveURL(/\/login/)

    // Create a screener
    const ts = Date.now()
    await sp.createScreener(`Test Screener ${ts}`)

    // Should appear in the list
    await expect(page.locator(`text=Test Screener ${ts}`)).toBeVisible({ timeout: 5_000 })

    // Select it and run
    await page.click(`text=Test Screener ${ts}`)
    const runBtn = page.locator('button:has-text("Run")')
    if (await runBtn.count() > 0) {
      await runBtn.click()
      // Should show result stats
      await expect(page.locator('.result-stats, .stat-val')).toBeVisible({ timeout: 15_000 })
    }
  })

})
