import { expect, test } from './helpers'

test('secondary route aliases land on their canonical authenticated surfaces', async ({ page, loggedIn, browserDiagnostics }) => {
  const aliases = [
    ['/study-lab', '/', '.workspace-layout-host'],
    ['/dashboard', '/legacy/dashboard', '.dashboard-view'],
    ['/alerts', '/legacy/alerts', '.alerts-view'],
    ['/radar', '/legacy/radar', '.radar-view'],
    ['/strategy-lab', '/legacy/strategy-lab', '.strategy-lab-view'],
    ['/strategy-lab-v2', '/legacy/strategy-lab-v2', '.strategy-lab-v2'],
    ['/baskets', '/legacy/baskets', '.basket-view'],
    ['/etf-holdings', '/legacy/etf-holdings', '.holdings-view'],
    ['/screener', '/legacy/screener', '.screener-view'],
    ['/watchlist', '/legacy/watchlist', '.watchlist-view'],
    ['/settings', '/legacy/settings', '.settings-view'],
  ] as const

  for (const [alias, canonical, surface] of aliases) {
    await page.goto(alias)
    await expect(page).toHaveURL(new RegExp(`${canonical.replaceAll('/', '\\/')}(?:[?#]|$)`))
    await expect(page.locator(surface)).toBeVisible()
    await expect(page.locator('.error-overlay, .fatal-error')).toHaveCount(0)
  }
  await browserDiagnostics.expectNoCriticalIssues()
})

test('Strategy Lab v2 reads resource tabs and refreshes without dispatching work', async ({ page, loggedIn, browserDiagnostics }) => {
  const reads: string[] = []
  const writes: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (!url.pathname.startsWith('/api/v1/strategy-lab/v2/')) return
    if (request.method() === 'GET') reads.push(url.pathname)
    else writes.push(`${request.method()} ${url.pathname}`)
  })

  await page.goto('/legacy/strategy-lab-v2')
  await expect(page.getByRole('heading', { name: 'Strategy Lab v2' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Execution boundary' })).toContainText('Read-only boundary')
  await expect.poll(() => reads.some(path => path.endsWith('/strategies'))).toBe(true)

  for (const [label, endpoint] of [['Trials', '/trials'], ['Artifacts', '/artifacts']] as const) {
    await page.getByRole('button', { name: new RegExp(`^${label}`) }).click()
    await expect.poll(() => reads.some(path => path.endsWith(endpoint))).toBe(true)
  }

  await page.getByRole('button', { name: 'Strategies' }).click()
  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect.poll(() => reads.filter(path => path.endsWith('/strategies')).length).toBeGreaterThan(1)
  expect(writes).toEqual([])
  await browserDiagnostics.expectNoCriticalIssues()
})
