/**
 * Shared Playwright helpers and fixtures.
 * Import these instead of @playwright/test directly.
 */
import { test as base, expect, type Page } from '@playwright/test'

const USER  = process.env.TEST_USER ?? 'e2euser'
const EMAIL = process.env.TEST_EMAIL ?? 'e2e@charting.test'
const PASS  = process.env.TEST_PASS  ?? 'E2ePassword123!'

export { expect }

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
    await this.page.fill('input[placeholder*="Screener"], input[placeholder*="name"]', name)
    await this.page.click('button:has-text("Create")')
    await this.page.waitForTimeout(300)
  }
}

// ── Custom test fixture ────────────────────────────────────────────────────────

type Fixtures = {
  loginPage:   LoginPage
  chartPage:   ChartPage
  screenerPage: ScreenerPage
  loggedIn:    void
}

export const test = base.extend<Fixtures>({
  loginPage:    async ({ page }, use) => use(new LoginPage(page)),
  chartPage:    async ({ page }, use) => use(new ChartPage(page)),
  screenerPage: async ({ page }, use) => use(new ScreenerPage(page)),

  loggedIn: async ({ page }, use) => {
    const lp = new LoginPage(page)
    // Try register first, if it fails (user exists) just login
    try {
      await lp.registerAndLogin()
    } catch {
      await lp.loginAs()
    }
    await use()
  },
})
