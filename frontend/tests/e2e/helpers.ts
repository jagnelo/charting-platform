/**
 * Shared Playwright helpers and fixtures.
 * Import these instead of @playwright/test directly.
 */
import { test as base, expect, type APIRequestContext, type Page, type TestInfo } from '@playwright/test'

const USER  = process.env.TEST_USER ?? 'e2euser'
const EMAIL = process.env.TEST_EMAIL ?? 'e2e@example.com'
const PASS  = process.env.TEST_PASS  ?? 'E2ePassword123!'

export { expect }

async function ensureUserExists(
  request: APIRequestContext,
  username: string,
  email: string,
  password: string,
) {
  const response = await request.post('/api/v1/auth/register', {
    data: { username, email, password },
  })
  if (response.status() === 201 || response.status() === 409) {
    return
  }
  throw new Error(`Failed to provision E2E user ${username}: ${response.status()} ${await response.text()}`)
}

class BrowserDiagnostics {
  consoleErrors: string[] = []
  consoleWarnings: string[] = []
  pageErrors: string[] = []
  requestFailures: string[] = []

  attach(page: Page) {
    page.on('console', (msg) => {
      const text = msg.text()
      if (msg.type() === 'error') this.consoleErrors.push(text)
      if (msg.type() === 'warning') this.consoleWarnings.push(text)
    })
    page.on('pageerror', (err) => {
      this.pageErrors.push(err.message)
    })
    page.on('requestfailed', (req) => {
      const errorText = req.failure()?.errorText ?? 'failed'
      if (errorText.includes('ERR_ABORTED')) {
        return
      }
      this.requestFailures.push(`${req.method()} ${req.url()} :: ${errorText}`)
    })
  }

  async record(testInfo: TestInfo) {
    if (this.consoleWarnings.length) {
      await testInfo.attach('browser-console-warnings.txt', {
        body: this.consoleWarnings.join('\n'),
        contentType: 'text/plain',
      })
    }
    if (this.consoleErrors.length || this.pageErrors.length || this.requestFailures.length) {
      const body = [
        this.consoleErrors.length ? `Console errors:\n${this.consoleErrors.join('\n')}` : '',
        this.pageErrors.length ? `Page errors:\n${this.pageErrors.join('\n')}` : '',
        this.requestFailures.length ? `Request failures:\n${this.requestFailures.join('\n')}` : '',
      ].filter(Boolean).join('\n\n')
      await testInfo.attach('browser-critical-issues.txt', {
        body,
        contentType: 'text/plain',
      })
    }
  }

  expectNoCriticalIssues() {
    expect(
      {
        consoleErrors: this.consoleErrors,
        pageErrors: this.pageErrors,
        requestFailures: this.requestFailures,
      },
      'unexpected browser console/page/request failures',
    ).toEqual({
      consoleErrors: [],
      pageErrors: [],
      requestFailures: [],
    })
  }
}

// ── Page object: LoginPage ────────────────────────────────────────────────────

export class LoginPage {
  constructor(private page: Page) {}

  async goto()                         { await this.page.goto('/login') }
  async fillUsername(u: string)        { await this.page.fill('input[type="text"]', u) }
  async fillEmail(e: string)           { await this.page.fill('input[type="email"]', e) }
  async fillPassword(p: string)        { await this.page.fill('input[type="password"]', p) }
  async clickSignIn()                  { await this.page.click('button[type="submit"]') }
  async switchToRegister()             { await this.page.click('button:has-text("Register")') }

  async loginAs(username = USER, password = PASS) {
    await this.goto()
    await this.fillUsername(username)
    await this.fillPassword(password)
    await this.clickSignIn()
    await this.page.waitForURL('**/chart**', { timeout: 10_000 })
  }

  async registerAndLogin(username = USER, email = EMAIL, password = PASS) {
    await this.goto()
    await this.switchToRegister()
    await this.fillUsername(username)
    await this.fillEmail(email)
    await this.fillPassword(password)
    await this.clickSignIn()
    await this.page.waitForURL('**/chart**', { timeout: 10_000 })
  }
}

// ── Page object: ChartPage ────────────────────────────────────────────────────

export class ChartPage {
  constructor(private page: Page) {}

  async goto(symbol?: string) {
    await this.page.goto(symbol ? `/chart/${symbol}` : '/chart')
    await this.page.waitForLoadState('networkidle')
  }

  async search(symbol: string) {
    await this.page.fill('.search-input, [placeholder*="Search"]', symbol)
    await this.page.waitForSelector('.search-results, .search-dropdown', { timeout: 5_000 })
    await this.page.keyboard.press('Enter')
    await this.page.waitForTimeout(500)
  }

  async selectTimeframe(tf: string) {
    await this.page.click(`button:has-text("${tf}")`)
    await this.page.waitForTimeout(500)
  }

  async openAlertForm() {
    await this.page.click('button[title*="Alert"], .alert-btn')
  }

  async createPriceAlert(price: string) {
    await this.openAlertForm()
    await this.page.fill('input[type="number"], .alert-price-input', price)
    await this.page.click('button:has-text("Create")')
  }
}

// ── Page object: ScreenerPage ─────────────────────────────────────────────────

export class ScreenerPage {
  constructor(private page: Page) {}

  async goto()                { await this.page.goto('/screener') }

  async createScreener(name: string) {
    await this.page.click('button:has-text("New")')
    await this.page.fill('.builder-panel input[placeholder*="RSI Oversold"]', name)
    await this.page.click('button:has-text("Save Screener"), button:has-text("Create")')
    await this.page.waitForTimeout(300)
  }
}

// ── Page object: DashboardPage ────────────────────────────────────────────────

export class DashboardPage {
  constructor(private page: Page) {}

  async goto()                { await this.page.goto('/dashboard') }

  async addWidget(type: string) {
    await this.page.click('button:has-text("Add Widget"), .add-widget-btn')
    await this.page.click(`[data-widget-type="${type}"], button:has-text("${type}")`)
    await this.page.waitForTimeout(300)
  }

  async openWidgetConfig(index = 0) {
    const widgets = this.page.locator('.dashboard-widget, .widget-container')
    await widgets.nth(index).hover()
    await widgets.nth(index).locator('button[title*="Configure"], .widget-config-btn').click()
    await this.page.waitForTimeout(200)
  }
}

// ── Page object: RadarPage ────────────────────────────────────────────────────

export class RadarPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/radar')
    await this.page.waitForLoadState('networkidle')
  }

  async runScan() {
    await this.page.click('button:has-text("Run scan")')
  }
}

// ── Custom test fixture ────────────────────────────────────────────────────────

type Fixtures = {
  loginPage:     LoginPage
  chartPage:     ChartPage
  screenerPage:  ScreenerPage
  dashboardPage: DashboardPage
  radarPage:     RadarPage
  browserDiagnostics: BrowserDiagnostics
  loggedIn:      void
}

export const test = base.extend<Fixtures>({
  browserDiagnostics: async ({ page }, use, testInfo) => {
    const diagnostics = new BrowserDiagnostics()
    diagnostics.attach(page)
    await use(diagnostics)
    await diagnostics.record(testInfo)
  },
  loginPage:     async ({ page }, use) => use(new LoginPage(page)),
  chartPage:     async ({ page }, use) => use(new ChartPage(page)),
  screenerPage:  async ({ page }, use) => use(new ScreenerPage(page)),
  dashboardPage: async ({ page }, use) => use(new DashboardPage(page)),
  radarPage:     async ({ page }, use) => use(new RadarPage(page)),

  loggedIn: async ({ page, request }, use, testInfo) => {
    const workerSuffix = testInfo.workerIndex ?? 0
    const username = `${USER}_${workerSuffix}`
    const email = EMAIL.replace('@', `+${workerSuffix}@`)
    const lp = new LoginPage(page)
    await ensureUserExists(request, username, email, PASS)
    await lp.loginAs(username, PASS)
    await use()
  },
})
