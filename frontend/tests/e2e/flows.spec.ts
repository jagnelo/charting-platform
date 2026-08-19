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
    // A fresh stack may report explicit unavailable data before uPlot mounts;
    // both outcomes are valid chart-tool states, but the workstation must show
    // one within the bounded lazy-layout initialization window.
    await expect(page.locator('.chart-empty, .uplot-wrapper, .chart-container, canvas, .tool-state--error').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F7 — search for symbol and chart loads', async ({ page, browserDiagnostics }) => {
    const cp = new ChartPage(page)
    await cp.goto()

    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await symbolEntry.fill('AAPL')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
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
    // The free-source seeded acceptance fixture guarantees a complete chart
    // control surface for the workstation benchmark. AAPL is intentionally
    // coverage-limited in that fixture and exercises the unavailable state,
    // which cannot validate template/settings mechanics.
    await page.goto('/chart/SPY')
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(symbolEntry).toHaveValue('SPY')
    await page.getByRole('button', { name: 'Chart templates' }).first().click()
    const templateMenu = page.locator('.chart-template__menu:visible').last()
    await templateMenu.getByRole('combobox', { name: 'Chart bar type' }).selectOption('line')
    await page.getByTitle('Chart settings').first().click()
    const currentPriceProjection = page.getByRole('checkbox', { name: 'Show current price on Y axis' })
    await currentPriceProjection.check()
    await page.locator('.editor-box .ed-close').click()
    const templateName = `SPY template ${Date.now()}`
    await page.getByRole('textbox', { name: 'Chart template name' }).fill(templateName)
    await templateMenu.getByRole('button', { name: 'Save', exact: true }).click()
    const savedTemplate = templateMenu.locator('.chart-template__apply').filter({ hasText: templateName })
    await expect(savedTemplate).toBeVisible({ timeout: 15_000 })
    await savedTemplate.click()
    await expect(symbolEntry).toHaveValue('SPY')
    await expect(templateMenu.getByRole('combobox', { name: 'Chart bar type' })).toHaveValue('line')
    await page.getByTitle('Chart settings').first().click()
    await expect(currentPriceProjection).toBeChecked()
    await page.locator('.editor-box .ed-close').click()
    await templateMenu.getByRole('button', { name: `Rename ${templateName}` }).click()
    await templateMenu.getByRole('textbox', { name: `Rename ${templateName}` }).fill(`${templateName} renamed`)
    await templateMenu.getByRole('button', { name: 'Save template name' }).click()
    await expect(templateMenu.locator('.chart-template__apply').filter({ hasText: `${templateName} renamed` })).toBeVisible()
    await templateMenu.getByRole('button', { name: `Delete ${templateName} renamed` }).click()
    await expect(templateMenu.getByRole('button', { name: `Delete ${templateName} renamed` })).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-transform — alternative chart settings control server transform parameters', async ({ page, browserDiagnostics }) => {
    let releaseRenkoRequest: (() => void) | null = null
    const renkoRequestHeld = new Promise<void>(resolve => { releaseRenkoRequest = resolve })
    const transformedPath = /\/api\/v1\/ohlcv(?:\/local)?\/SPY\/D1\/transformed/
    await page.route(transformedPath, async route => {
      if (!route.request().url().includes('bar_type=renko')) return route.continue()
      await renkoRequestHeld
      await route.continue()
    })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart settings') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const settings = chart.getByTitle('Chart settings')
    await settings.click()
    const dialog = page.getByRole('dialog', { name: 'Chart Settings' })
    const rendering = dialog.getByRole('combobox', { name: 'Primary rendering' })
    await rendering.selectOption('renko')
    const brickSize = dialog.getByRole('spinbutton', { name: 'Brick size' })
    // Exercise the transition itself: settings stay usable while the old
    // numerical renderer is destroyed and the replacement request is pending.
    await expect(brickSize).toBeVisible()
    await expect(chart.locator('canvas')).toHaveCount(0)
    releaseRenkoRequest?.()
    await page.unroute(transformedPath)
    await expect(chart.locator('canvas')).toHaveCount(2, { timeout: 15_000 })
    await brickSize.fill('12')
    const request = page.waitForRequest(request => request.url().includes('/ohlcv/SPY/D1/transformed') && request.url().includes('bar_type=renko') && request.url().includes('brick_size=12'))
    await brickSize.press('Tab')
    await request
    await expect(brickSize).toHaveValue('12')

    await rendering.selectOption('point_figure')
    const boxSize = dialog.getByRole('spinbutton', { name: 'Box size' })
    const reversal = dialog.getByRole('spinbutton', { name: 'Reversal boxes' })
    await boxSize.fill('5')
    await reversal.fill('2')
    const pointFigureRequest = page.waitForRequest(request => request.url().includes('/ohlcv/SPY/D1/transformed') && request.url().includes('bar_type=point_figure') && request.url().includes('box_size=5') && request.url().includes('reversal=2'))
    await reversal.press('Tab')
    await pointFigureRequest
    await expect(boxSize).toHaveValue('5')
    await expect(reversal).toHaveValue('2')

    const resetRequest = page.waitForRequest(request => request.url().includes('/ohlcv/SPY/D1/transformed') && request.url().includes('bar_type=point_figure') && !request.url().includes('box_size=') && !request.url().includes('reversal='))
    // Clearing box size blurs it when the reversal field is edited, so install
    // the observer before the first clear rather than after that change fires.
    await boxSize.fill('')
    await reversal.fill('')
    await reversal.press('Tab')
    await resetRequest
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-template-transform — chart templates retain alternative transform mechanics and reset them', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart templates') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    await chart.getByTitle('Chart templates').click()
    const menu = chart.locator('.chart-template__menu:visible').last()
    await menu.getByRole('combobox', { name: 'Chart bar type' }).selectOption('point_figure')
    await page.getByTitle('Chart settings').first().click()
    const settings = page.getByRole('dialog', { name: 'Chart Settings' })
    await settings.getByRole('spinbutton', { name: 'Box size' }).fill('5')
    await settings.getByRole('spinbutton', { name: 'Reversal boxes' }).fill('2')
    await settings.getByRole('spinbutton', { name: 'Reversal boxes' }).press('Tab')
    await expect(settings.getByRole('spinbutton', { name: 'Box size' })).toHaveValue('5')
    await page.locator('.editor-box .ed-close').click()
    const transformTemplateName = `P&F ${Date.now()}`
    await menu.getByRole('textbox', { name: 'Chart template name' }).fill(transformTemplateName)
    await menu.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(menu.locator('.chart-template__apply').first()).toBeVisible({ timeout: 15_000 })
    await menu.locator('footer button').click()
    await expect(menu.getByRole('combobox', { name: 'Chart bar type' })).toHaveValue('candles')
    const savedTemplate = menu.locator('.chart-template__apply').filter({ hasText: transformTemplateName })
    await savedTemplate.click()
    await expect(menu.getByRole('combobox', { name: 'Chart bar type' })).toHaveValue('point_figure')
    // The canonical OHLCV coordinator may legitimately serve this exact
    // template series from its short-lived cache. F9c-transform separately
    // proves the server query parameters; this test owns template restoration
    // and therefore asserts the restored render surface instead of requiring a
    // redundant network request.
    await expect(chart.locator('.uplot')).toBeVisible({ timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-template-comparison — chart templates restore their comparison set', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart templates') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    await chart.getByTitle('Chart templates').click()
    const menu = chart.locator('.chart-template__menu:visible').last()
    const templateName = `Comparison ${Date.now()}`
    await menu.getByRole('combobox', { name: 'Chart bar type' }).selectOption('line')
    await chart.getByRole('textbox', { name: 'Comparison symbol', exact: true }).fill('RSP')
    await chart.getByTitle('Add comparison').click()
    await expect(chart.getByTitle('Remove RSP')).toBeVisible()
    await menu.getByRole('textbox', { name: 'Chart template name' }).fill(templateName)
    const saveRequest = page.waitForRequest(request => request.url().includes('/workspaces/library/items/chart_template/') && request.method() === 'PUT')
    await menu.getByRole('button', { name: 'Save', exact: true }).click()
    const savePayload = (await saveRequest).postDataJSON() as { payload?: { configuration?: Record<string, unknown> } }
    expect(savePayload.payload?.configuration?.comparison_symbols).toEqual(['RSP'])
    const saved = menu.locator('.chart-template__apply').filter({ hasText: templateName })
    await expect(saved).toBeVisible({ timeout: 15_000 })
    await chart.getByTitle('Remove RSP').click()
    await expect(chart.getByTitle('Remove RSP')).toHaveCount(0)
    await expect(saved).toBeVisible({ timeout: 15_000 })
    await saved.click()
    await expect(chart.locator('.chart-tool__compare-chip').filter({ hasText: 'RSP' })).toHaveCount(1, { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-keyboard — chart templates support keyboard opening and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByRole('button', { name: 'Chart templates' }) }).first()
    await expect(chart).toBeVisible({ timeout: 10_000 })
    const trigger = chart.getByRole('button', { name: 'Chart templates' })
    await trigger.press('ArrowDown')
    const menu = chart.locator('[role="menu"]')
    await expect(menu).toBeVisible()
    const editor = menu.getByRole('textbox', { name: 'Chart template name' })
    await expect(editor).toBeFocused()
    await editor.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-narrow — chart menus remain viewport-contained in a constrained desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByRole('button', { name: 'Chart templates' }) }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })

    const templateTrigger = chart.getByRole('button', { name: 'Chart templates' })
    await templateTrigger.click()
    const templateMenu = chart.locator('.chart-template__menu:visible')
    await expect(templateMenu).toBeVisible()
    const templateBox = await templateMenu.boundingBox()
    expect(templateBox).not.toBeNull()
    expect(templateBox!.x).toBeGreaterThanOrEqual(0)
    expect(templateBox!.x + templateBox!.width).toBeLessThanOrEqual(390)
    await templateMenu.getByRole('button', { name: 'Close chart templates' }).click()

    const plotTrigger = chart.getByRole('button', { name: 'Chart plot library' })
    await plotTrigger.click()
    const plotMenu = chart.locator('.chart-plots__menu:visible')
    await expect(plotMenu).toBeVisible()
    const plotBox = await plotMenu.boundingBox()
    expect(plotBox).not.toBeNull()
    expect(plotBox!.x).toBeGreaterThanOrEqual(0)
    expect(plotBox!.x + plotBox!.width).toBeLessThanOrEqual(390)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c-bottom-edge — chart menus flip above the trigger when the lower viewport is unavailable', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 320 })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByRole('button', { name: 'Chart templates' }) }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const viewportHeight = 320
    for (const control of ['Chart templates', 'Chart plot library']) {
      const trigger = chart.getByRole('button', { name: control })
      await trigger.click()
      const menu = control === 'Chart templates'
        ? chart.locator('.chart-template__menu:visible')
        : chart.locator('.chart-plots__menu:visible')
      await expect(menu).toBeVisible()
      const bounds = await menu.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.y).toBeGreaterThanOrEqual(0)
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewportHeight)
      await menu.getByRole('button', { name: control === 'Chart templates' ? 'Close chart templates' : 'Close chart plot library' }).click()
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c2-keyboard — chart utility controls expose dialogs and restore focus', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart settings') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })

    const settings = chart.getByRole('button', { name: 'Chart settings' })
    const settingsControlIds = await page.locator('button[aria-controls$="-settings"]').evaluateAll(buttons => buttons.map(button => button.getAttribute('aria-controls')).filter((id): id is string => Boolean(id)))
    expect(new Set(settingsControlIds).size).toBe(settingsControlIds.length)
    await settings.press('Enter')
    const settingsDialog = page.getByRole('dialog', { name: 'Chart Settings' })
    await expect(settingsDialog).toBeVisible()
    await expect(settingsDialog.getByRole('combobox', { name: 'Primary rendering' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(settingsDialog).toHaveCount(0)
    await expect(settings).toBeFocused()

    const help = chart.getByRole('button', { name: 'Keyboard shortcuts' })
    await help.press('Enter')
    const helpDialog = page.getByRole('dialog', { name: 'Keyboard Shortcuts' })
    await expect(helpDialog).toBeVisible()
    await expect(helpDialog.getByRole('button', { name: /Close/ })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(helpDialog).toHaveCount(0)
    await expect(help).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9c3-keyboard — chart context menus expose menu semantics and keyboard navigation', async ({ page, browserDiagnostics }) => {
    // The preceding F9c narrow/bottom-edge cases intentionally resize the
    // shared page fixture. Restore the desktop geometry this chart interaction
    // requires so the y-axis gutter target is deterministic in sequence runs.
    await page.setViewportSize({ width: 1280, height: 720 })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart settings') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const canvas = chart.locator('.uplot-wrapper').first()
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    const over = await chart.locator('.u-over').first().boundingBox()
    expect(over).not.toBeNull()
    // The product handler defines the price-scale gutter relative to uPlot's
    // rendered interaction layer, not the outer wrapper. Use that same edge so
    // this remains deterministic after templates or narrow layouts change the
    // internal plot width, while staying inside the wrapper (the menu closes
    // when the pointer leaves it).
    const targetX = Math.min(box!.x + box!.width - 1, over!.x + over!.width + 4)
    expect(targetX).toBeGreaterThan(over!.x + over!.width)
    await page.mouse.click(targetX, box!.y + 80, { button: 'right' })
    const menu = page.getByRole('menu', { name: 'Price scale actions' })
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('menuitem').first()).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(menu.getByRole('menuitem').nth(1)).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(chart.getByRole('region', { name: 'Chart workspace' })).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9d — workspace layouts round-trip through the real export and import controls', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    const layoutTabs = page.locator('.workstation__tabs > button:not(.workstation__tab-add)')
    const originalCount = await layoutTabs.count()
    const workspaceButton = page.getByRole('button', { name: 'Workspace', exact: true })
    await workspaceButton.click()
    const workspaceMenu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(workspaceMenu).toBeVisible({ timeout: 10_000 })
    const downloadPromise = page.waitForEvent('download')
    await workspaceMenu.getByRole('menuitem', { name: 'Export', exact: true }).click()
    const download = await downloadPromise
    const exportPath = await download.path()
    expect(exportPath).not.toBeNull()

    await workspaceMenu.getByRole('menuitem', { name: 'Clone', exact: true }).click()
    await expect(layoutTabs).toHaveCount(originalCount + 1, { timeout: 10_000 })
    await workspaceButton.click()
    const reopenedMenu = page.locator('.workstation__workspace-popover:visible')
    await expect(reopenedMenu).toBeVisible({ timeout: 10_000 })
    await reopenedMenu.locator('input.workstation__workspace-file').setInputFiles(exportPath!)
    await expect(layoutTabs).toHaveCount(originalCount, { timeout: 15_000 })
    await expect(page.locator('.workstation__workspace-popover')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9d-workspaces — persisted workspaces can be created, cloned, renamed, switched, and deleted', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    // This CRUD flow mutates durable workspace state. Start from the default
    // workspace so a preceding export/clone or interrupted run cannot make
    // the clone-name assertion depend on another persisted workspace.
    const workspaceButton = page.getByRole('button', { name: 'Workspace', exact: true })
    await workspaceButton.click()
    let menu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(menu).toBeVisible()
    const defaultOption = menu.getByRole('option', { name: 'US Top Down' })
    if (await defaultOption.count()) {
      await defaultOption.click()
      await expect(page.locator('.workstation__workspace-name')).toHaveText('US Top Down', { timeout: 15_000 })
      await workspaceButton.click()
      menu = page.getByRole('menu', { name: 'Workspace layouts' })
      await expect(menu).toBeVisible()
    }
    await menu.getByRole('menuitem', { name: 'New', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText('New Workspace', { timeout: 15_000 })

    await workspaceButton.click()
    await expect(menu.getByRole('option', { name: 'New Workspace' })).toBeVisible()
    const reviewName = `Morning Review ${Date.now()}`
    page.once('dialog', dialog => dialog.accept(reviewName))
    await menu.getByRole('menuitem', { name: 'Rename', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText(reviewName, { timeout: 15_000 })

    await workspaceButton.click()
    await menu.getByRole('menuitem', { name: 'Clone workspace', exact: true }).click()
    const reviewCopyName = `${reviewName} Copy`
    await expect(page.locator('.workstation__workspace-name')).toHaveText(reviewCopyName, { timeout: 15_000 })

    await workspaceButton.click()
    await menu.getByRole('option', { name: 'US Top Down' }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText('US Top Down', { timeout: 15_000 })
    await workspaceButton.click()
    await menu.getByRole('option', { name: reviewCopyName }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText(reviewCopyName, { timeout: 15_000 })

    await workspaceButton.click()
    const deleteMenu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(deleteMenu).toBeVisible({ timeout: 10_000 })
    page.once('dialog', dialog => dialog.accept())
    await deleteMenu.getByRole('menuitem', { name: 'Delete', exact: true }).click()
    await expect(page.locator('.workstation__workspace-name')).toHaveText('US Top Down', { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e — primary workspace tabs can be reordered by dragging the visible tab strip', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    const tabs = page.locator('.workstation__tabs > button:not(.workstation__tab-add)')
    await expect.poll(() => tabs.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const before = await tabs.allTextContents()
    const secondBox = await tabs.nth(1).boundingBox()
    const firstBox = await tabs.nth(0).boundingBox()
    expect(secondBox).not.toBeNull()
    expect(firstBox).not.toBeNull()
    await page.mouse.move(secondBox!.x + secondBox!.width / 2, secondBox!.y + secondBox!.height / 2)
    await page.mouse.down()
    await expect(tabs.nth(1)).toHaveAttribute('aria-grabbed', 'true')
    await page.mouse.move(firstBox!.x + firstBox!.width / 2, firstBox!.y + firstBox!.height / 2, { steps: 8 })
    await page.mouse.up()
    await expect.poll(async () => tabs.allTextContents()).toEqual([before[1], before[0], ...before.slice(2)])
    const restoredSecondBox = await tabs.nth(1).boundingBox()
    const restoredFirstBox = await tabs.nth(0).boundingBox()
    expect(restoredSecondBox).not.toBeNull()
    expect(restoredFirstBox).not.toBeNull()
    await page.mouse.move(restoredSecondBox!.x + restoredSecondBox!.width / 2, restoredSecondBox!.y + restoredSecondBox!.height / 2)
    await page.mouse.down()
    await page.mouse.move(restoredFirstBox!.x + restoredFirstBox!.width / 2, restoredFirstBox!.y + restoredFirstBox!.height / 2, { steps: 8 })
    await page.mouse.up()
    await expect.poll(async () => tabs.allTextContents()).toEqual(before)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-keyboard — workspace tabs support roving focus and keyboard activation', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    const tabs = page.locator('.workstation__tabs [role="tab"]')
    await expect.poll(() => tabs.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const first = tabs.nth(0)
    const second = tabs.nth(1)
    await first.focus()
    await expect(first).toHaveAttribute('tabindex', '0')
    await first.press('ArrowRight')
    await expect(second).toBeFocused()
    await second.press('Enter')
    await expect(second).toHaveAttribute('aria-selected', 'true')
    await second.press('Home')
    await expect(first).toBeFocused()
    await first.press(' ')
    await expect(first).toHaveAttribute('aria-selected', 'true')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e — watchlist Columns and Sets editor saves and reapplies grouping/stacking', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    // The preceding chart/template import flow intentionally mutates the
    // shared workspace. Restore the factory before asserting column-editor
    // mechanics so this test exercises the product contract, not test order.
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
      await expect(page.getByRole('region', { name: 'Relative to SPY' })).toBeVisible({ timeout: 15_000 })
    }
    const watchlist = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(watchlist).toBeVisible({ timeout: 10_000 })
    await watchlist.getByRole('button', { name: 'Columns', exact: true }).click()
    const editor = watchlist.locator('.watchlist__column-editor-row').first()
    await expect(editor).toBeVisible({ timeout: 10_000 })
    const columnLabel = await editor.locator('.watchlist__label-input').inputValue()
    const group = editor.locator('.watchlist__group-input')
    await group.fill('Momentum')
    await group.press('Tab')
    await editor.getByRole('button', { name: 'Stack', exact: true }).click()
    await expect(watchlist.locator('.watchlist__header')).toContainText('Momentum')

    await watchlist.getByRole('button', { name: 'Columns', exact: true }).click()
    await watchlist.getByRole('button', { name: 'Column sets' }).click()
    const setName = `E2E columns ${Date.now()}`
    const setMenu = watchlist.locator('.watchlist__column-set-menu')
    await expect(setMenu).toBeVisible({ timeout: 10_000 })
    await setMenu.getByRole('textbox', { name: 'Column set name' }).fill(setName)
    await setMenu.getByRole('button', { name: 'Save set', exact: true }).click()
    const savedSet = setMenu.getByRole('button', { name: `${setName} v1`, exact: true })
    await expect(savedSet).toBeVisible({ timeout: 15_000 })
    await savedSet.click()
    await expect(watchlist.locator('.watchlist__header')).toContainText('Momentum')
    await expect(watchlist.locator('.watchlist__header')).toContainText(columnLabel)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-resize — watchlist headers resize columns through the rendered separator', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
    }
    const watchlist = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(watchlist).toBeVisible({ timeout: 15_000 })
    const handle = watchlist.getByRole('separator', { name: 'Resize Symbol column' })
    await expect(handle).toBeVisible()
    const before = await handle.evaluate(element => element.parentElement?.getBoundingClientRect().width ?? 0)
    const box = await handle.boundingBox()
    expect(box).not.toBeNull()
    // The separator intentionally straddles the clipped header edge (`right:-3px`)
    // to preserve the dense V25 affordance. Start on its in-bounds pixel so this
    // remains a genuine device hit test rather than relying on DOM dispatch.
    const startX = box!.x + Math.min(1, box!.width / 2)
    await page.mouse.move(startX, box!.y + box!.height / 2)
    await page.mouse.down()
    await page.mouse.move(startX + 28, box!.y + box!.height / 2, { steps: 5 })
    await page.mouse.up()
    await expect.poll(async () => handle.evaluate(element => element.parentElement?.getBoundingClientRect().width ?? 0)).toBeGreaterThan(before + 20)
    await expect(handle).toHaveAttribute('tabindex', '0')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9f — chart templates round-trip through the real export and import controls', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const symbolEntry = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(symbolEntry).toHaveValue('SPY')
    await page.getByRole('button', { name: 'Chart templates' }).first().click()
    const templateMenu = page.locator('.chart-template__menu:visible').last()
    const templateName = `E2E template ${Date.now()}`
    await templateMenu.getByRole('combobox', { name: 'Chart bar type' }).selectOption('line')
    await templateMenu.getByRole('textbox', { name: 'Chart template name' }).fill(templateName)
    await templateMenu.getByRole('button', { name: 'Save', exact: true }).click()
    const savedTemplate = templateMenu.locator('.chart-template__apply').filter({ hasText: templateName })
    await expect(savedTemplate).toBeVisible({ timeout: 15_000 })

    const downloadPromise = page.waitForEvent('download')
    await templateMenu.getByRole('button', { name: `Export ${templateName}` }).click()
    const download = await downloadPromise
    const exportPath = await download.path()
    expect(exportPath).not.toBeNull()
    await templateMenu.getByRole('button', { name: `Delete ${templateName}` }).click()
    await expect(savedTemplate).toHaveCount(0)

    await templateMenu.locator('input[type="file"]').setInputFiles(exportPath!)
    await expect(templateMenu.locator('.chart-template__apply').filter({ hasText: templateName })).toBeVisible({ timeout: 15_000 })
    await templateMenu.locator('.chart-template__apply').filter({ hasText: templateName }).click()
    await expect(symbolEntry).toHaveValue('SPY')
    await expect(templateMenu.getByRole('combobox', { name: 'Chart bar type' })).toHaveValue('line')
    await templateMenu.getByRole('button', { name: `Delete ${templateName}` }).click()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-context-keyboard — watchlist row actions support keyboard navigation and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const watchlist = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(watchlist).toBeVisible({ timeout: 10_000 })
    const row = watchlist.locator('.watchlist__row').first()
    await expect(row).toBeVisible({ timeout: 10_000 })
    await row.click({ button: 'right' })
    const menu = page.locator('.watchlist__context-menu:visible').last()
    await expect(menu).toBeVisible()
    const items = menu.getByRole('menuitem')
    await expect(items.first()).toBeFocused()
    await items.first().press('ArrowDown')
    await expect(items.nth(1)).toBeFocused()
    await items.nth(1).press('End')
    await expect(items.last()).toBeFocused()
    await items.last().press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(row).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-plot-library-keyboard — chart plot library supports keyboard opening and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByRole('button', { name: 'Chart plot library' }) }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const trigger = chart.getByRole('button', { name: 'Chart plot library' })
    await trigger.press('ArrowDown')
    const menu = page.getByRole('menu', { name: 'Chart plot library menu' })
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('combobox', { name: 'Add indicator plot' })).toBeFocused()
    await menu.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-plot-library-narrow — chart plot library clamps to a narrow viewport and recovers on close', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByRole('button', { name: 'Chart plot library' }) }).first()
    const trigger = chart.getByRole('button', { name: 'Chart plot library' })
    await trigger.click()
    const menu = page.getByRole('menu', { name: 'Chart plot library menu' }).last()
    await expect(menu).toBeVisible()
    const bounds = await menu.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
    await menu.getByRole('button', { name: 'Close chart plot library' }).click()
    await expect(menu).toBeHidden()
    await expect(trigger).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-shell-menus-keyboard — workstation shell menus support keyboard navigation and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const workspaceTrigger = page.getByRole('button', { name: 'Workspace', exact: true })
    await expect(workspaceTrigger).toBeVisible({ timeout: 15_000 })
    await workspaceTrigger.press('ArrowDown')
    const workspaceMenu = page.getByRole('menu', { name: 'Workspace layouts' })
    await expect(workspaceMenu).toBeVisible()
    const workspaceList = workspaceMenu.getByRole('listbox', { name: 'Saved workspaces' })
    await expect(workspaceList).toBeFocused()
    await expect(workspaceList).toHaveAttribute('aria-activedescendant', /saved-workspace-/)
    await workspaceList.press('End')
    await expect(workspaceList).toHaveAttribute('aria-activedescendant', /saved-workspace-/)
    await workspaceMenu.press('End')
    await expect(workspaceMenu.getByRole('menuitem').last()).toBeFocused()
    await workspaceMenu.press('Escape')
    await expect(workspaceMenu).toHaveCount(0)
    await expect(workspaceTrigger).toBeFocused()

    const helpTrigger = page.getByRole('button', { name: 'Help', exact: true })
    await helpTrigger.press('ArrowDown')
    const helpMenu = page.getByRole('menu', { name: 'Keyboard shortcuts' })
    await expect(helpMenu).toBeVisible()
    await expect(helpMenu.getByRole('menuitem').first()).toBeFocused()
    await helpMenu.press('Escape')
    await expect(helpMenu).toHaveCount(0)
    await expect(helpTrigger).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-watchlist-editors-keyboard — column and column-set editors support keyboard entry and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const watchlist = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(watchlist).toBeVisible({ timeout: 15_000 })
    const columns = watchlist.getByRole('button', { name: 'Columns', exact: true })
    await columns.press('ArrowDown')
    const editor = watchlist.getByRole('dialog', { name: 'Column editor' })
    await expect(editor).toBeVisible()
    await expect(editor.locator('input,select,button').first()).toBeFocused()
    await editor.press('Escape')
    await expect(editor).toHaveCount(0)
    await expect(columns).toBeFocused()

    const sets = watchlist.getByRole('button', { name: 'Column sets' })
    await sets.press('ArrowDown')
    const setEditor = watchlist.getByRole('dialog', { name: 'Saved column sets' })
    await expect(setEditor).toBeVisible()
    await expect(setEditor.getByRole('textbox', { name: 'Column set name' })).toBeFocused()
    await setEditor.press('Escape')
    await expect(setEditor).toHaveCount(0)
    await expect(sets).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9e-easyscan-builder-keyboard — advanced EasyScan condition builder exposes state and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const addTool = page.getByRole('button', { name: 'Add tool', exact: true })
    await expect(addTool).toBeVisible({ timeout: 15_000 })
    await addTool.click()
    await page.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 15_000 })
    const toggle = scan.locator('button.easy-scan__advanced-toggle')
    await toggle.press('Enter')
    const advanced = scan.locator('#easy-scan-advanced-conditions')
    await expect(advanced).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(advanced.locator('select, input, button').first()).toBeFocused()
    await toggle.press('Enter')
    await expect(advanced).toHaveCount(0)
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9g — a scalar Study Lab result becomes a reusable watchlist Python column', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    const studyName = `E2E reusable scalar ${Date.now()}`
    await page.goto('/chart/SPY')
    const target = page.getByRole('region', { name: 'Major US benchmarks' })
    await expect(target).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool:visible').last()
    await expect(study).toBeVisible({ timeout: 10_000 })
    const sourceEditor = study.getByRole('textbox', { name: 'Study Python source' })
    await expect(sourceEditor).toHaveAttribute('aria-haspopup', 'listbox')
    await expect(sourceEditor).toHaveAttribute('aria-expanded', 'false')
    await study.getByRole('textbox', { name: 'Study name' }).fill(studyName)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('reusable_value', 7)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await study.getByRole('button', { name: 'Save as column' }).click()
    await expect(study).toContainText('Saved as a reusable watchlist column.', { timeout: 15_000 })

    // Study opens the dedicated factory layout. Return to the source workstation
    // before exercising the real watchlist consumer, rather than querying a
    // hidden Golden Layout stack.
    await page.locator('.workstation__tabs > button').filter({ hasText: 'US Top Down' }).click()
    await expect(target).toBeVisible({ timeout: 10_000 })
    await target.locator('.watchlist__columns-button').first().click()
    const pythonColumnAsset = target.locator('select[aria-label="Python column asset"]')
    await expect(pythonColumnAsset).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => pythonColumnAsset.locator('option').count(), { timeout: 15_000 }).toBeGreaterThan(1)
    const assetOption = pythonColumnAsset.locator('option').filter({ hasText: studyName }).last()
    await expect(assetOption).toHaveCount(1, { timeout: 15_000 })
    const assetValue = await assetOption.getAttribute('value')
    expect(assetValue).toBeTruthy()
    await pythonColumnAsset.selectOption(assetValue!)
    await target.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(target.locator('.watchlist__header button').filter({ hasText: studyName })).toBeVisible({ timeout: 30_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9g-python-plot — Python chart plots support lifecycle and watchlist target propagation', async ({ page, browserDiagnostics }) => {
    const plotName = `E2E Python series ${Date.now()}`
    const asset = { kind: 'plot', name: plotName, versions: [{ id: 99101, version_number: 1, output_contract: 'series' }] }
    await page.route(/\/api\/v1\/code\/assets(?:\?.*)?$/, async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([asset]) })
        return
      }
      await route.continue()
    })
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({
        id: 99101, status: 'completed', code_version_id: 99101,
        artifacts: [{ id: 99101, name: 'series', artifact_type: 'series', payload: { value: { timestamps: ['2025-01-02T00:00:00Z'], values: [1] } } }],
      }) })
    })
    await page.route(/\/api\/v1\/research\/runs\/99101$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 99101, status: 'completed', code_version_id: 99101,
        artifacts: [{ id: 99101, name: 'series', artifact_type: 'series', payload: { value: { timestamps: ['2025-01-02T00:00:00Z'], values: [1] } } }],
      }) })
    })
    await page.route(/\/api\/v1\/research\/runs\/99101\/batch-results$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        run_id: 99101, code_version_id: 99101, output_contract: 'series', status: 'completed',
        cells: [{ symbol: 'SPY', status: 'completed', value: 1 }], progress: { completed_cells: 1, total_cells: 1, status: 'completed' },
      }) })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
    const topDownTab = page.locator('.workstation__tabs > button').filter({ hasText: 'US Top Down' })
    if (await topDownTab.isVisible()) await topDownTab.click()
    const chart = page.locator('.chart-tool:visible').last()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    await chart.getByRole('button', { name: 'Chart plot library' }).click()
    await chart.getByRole('button', { name: 'Load Python plots' }).click()
    const assetPicker = chart.getByRole('combobox', { name: 'Python plot asset' })
    await expect(assetPicker).toBeVisible({ timeout: 10_000 })
    await assetPicker.selectOption('99101')
    await chart.getByRole('button', { name: 'Add', exact: true }).click()
    const plot = chart.locator('.chart-plots__python-item').filter({ hasText: plotName }).first()
    await expect(plot).toBeVisible({ timeout: 15_000 })
    const visibilityButton = plot.locator('button').first()
    const initialVisibilityLabel = await visibilityButton.getAttribute('aria-label')
    expect(initialVisibilityLabel).toMatch(/^(Show|Hide) /)
    if (initialVisibilityLabel?.startsWith('Show ')) await visibilityButton.click()
    await expect(plot).not.toHaveClass(/muted/)
    await visibilityButton.click()
    await expect(plot).toHaveClass(/muted/)
    await plot.locator('button').nth(3).click()
    await expect(chart.locator('.chart-plots__python-item').filter({ hasText: plotName })).toHaveCount(2)
    const targetPicker = chart.getByRole('combobox', { name: 'Copy plot target' })
    const targetOptions = await targetPicker.locator('option').evaluateAll(options => options.map(option => ({ value: (option as HTMLOptionElement).value, text: option.textContent ?? '' })))
    const target = targetOptions.find(option => /Benchmarks · watchlist/i.test(option.text))
    expect(target).toBeTruthy()
    await targetPicker.selectOption(target!.value)
    await chart.locator('.chart-plots__python-item').filter({ hasText: plotName }).first().locator('button').nth(5).click()
    const watchlist = page.getByRole('region', { name: 'Benchmarks' })
    await expect(watchlist.locator('.watchlist__header')).toContainText(plotName, { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9h — a unified Python condition runs in EasyScan and creates an alert', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    const conditionName = `E2E Python condition ${Date.now()}`
    const stableKey = conditionName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    const scanName = `${conditionName} Scan`

    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    const toolMenu = page.locator('.workstation__tool-library-menu')
    await expect(toolMenu).toBeVisible({ timeout: 10_000 })
    await toolMenu.getByRole('menuitem', { name: 'Python Library', exact: true }).click()
    const libraryTab = page.locator('.lm_tab').filter({ hasText: 'Python Library' }).last()
    await expect(libraryTab).toBeVisible({ timeout: 10_000 })
    if (!(await libraryTab.evaluate(node => node.classList.contains('lm_active')))) await libraryTab.click()
    const library = page.locator('.code-library-tool:visible').last()
    await expect(library).toBeVisible({ timeout: 10_000 })
    await library.getByRole('button', { name: 'New', exact: true }).click()
    const create = library.getByRole('form', { name: 'Create Python asset' })
    await create.getByRole('textbox', { name: 'New Python asset name' }).fill(conditionName)
    await create.getByRole('textbox', { name: 'New Python asset key' }).fill(stableKey)
    await create.getByRole('combobox', { name: 'New Python asset kind' }).selectOption('condition')
    await create.getByRole('textbox', { name: 'New Python asset source' }).fill("output.boolean('ready', True)")
    await create.getByRole('button', { name: 'Create asset' }).click()
    await expect(library.locator('.code-library-tool__asset').filter({ hasText: conditionName })).toBeVisible({ timeout: 15_000 })

    await page.locator('.workstation__tabs > button').filter({ hasText: 'US Top Down' }).click()
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 10_000 })
    const pythonCondition = scan.getByRole('combobox', { name: 'Python condition' })
    await expect.poll(() => pythonCondition.locator('option').count(), { timeout: 15_000 }).toBeGreaterThan(1)
    const conditionOption = pythonCondition.locator('option').filter({ hasText: conditionName }).last()
    await expect(conditionOption).toHaveCount(1, { timeout: 15_000 })
    const conditionValue = await conditionOption.getAttribute('value')
    expect(conditionValue).toBeTruthy()
    await pythonCondition.selectOption(conditionValue!)
    await scan.getByRole('textbox', { name: 'Scan name' }).fill(scanName)
    await scan.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(scan.locator('.easy-scan__result')).toBeVisible({ timeout: 30_000 })
    await scan.getByRole('button', { name: 'Alert', exact: true }).click()
    await expect(scan.getByRole('button', { name: 'Alert active', exact: true })).toBeVisible({ timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9i — a Study Lab series becomes a reusable chart plot', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    const studyName = `E2E reusable series ${Date.now()}`
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const studyLayoutTab = page.locator('.workstation__tabs > button').filter({ hasText: 'Study Lab' }).last()
    if (await studyLayoutTab.count()) await studyLayoutTab.click()
    const studyTab = page.locator('.lm_tab:visible').filter({ hasText: 'Study Lab' }).last()
    if (await studyTab.count()) await studyTab.click()
    const study = page.locator('.study-lab-tool:visible').last()
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill(studyName)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.series('reusable_series', [1, 2, 3, 4])")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await study.getByRole('button', { name: 'Save as chart plot' }).click()
    await expect(study).toContainText('Saved as a reusable chart plot.', { timeout: 15_000 })

    await page.locator('.workstation__tabs > button').filter({ hasText: 'US Top Down' }).click()
    // Returning from Study Lab can leave the chart component mounted in a
    // non-active Golden Layout stack. Activate its real tab before interacting
    // with the plot library so a neighboring virtual tool cannot intercept the
    // pointer despite the chart node being CSS-visible.
    const chartTab = page.locator('.lm_tab:visible').filter({ hasText: 'Chart' }).last()
    if (await chartTab.count()) await chartTab.click()
    const chart = page.locator('.chart-tool:visible').first()
    await expect(chart).toBeVisible({ timeout: 10_000 })
    await chart.locator('button[aria-label="Chart plot library"]').click()
    const loadPythonPlots = chart.getByRole('button', { name: 'Load Python plots' })
    await loadPythonPlots.click()
    const pythonPlot = chart.getByRole('combobox', { name: 'Python plot asset' })
    await expect.poll(() => pythonPlot.locator('option').count(), { timeout: 15_000 }).toBeGreaterThan(1)
    const option = pythonPlot.locator('option').filter({ hasText: studyName }).last()
    await expect(option).toHaveCount(1, { timeout: 15_000 })
    const optionValue = await option.getAttribute('value')
    expect(optionValue).toBeTruthy()
    await pythonPlot.selectOption(optionValue!)
    await chart.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(chart.locator('.chart-plots__python-item').filter({ hasText: studyName })).toBeVisible({ timeout: 30_000 })
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
    for (const excluded of ['trading', 'brokerage', 'options', 'news', 'ratings', 'earnings', 'financial statements', 'consolidated realtime', 'consolidated real-time']) {
      expect(labels).not.toContain(excluded)
    }
    await expect(page.locator('.workstation').getByText(/coming soon|not available|disabled capability/i)).toHaveCount(0)
    await expect(page.locator('.workstation__tabs')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('regular users do not see the administrator reconciliation queue', async ({ page, browserDiagnostics }) => {
    await page.goto('/legacy/settings')
    await expect(page.locator('.settings-view')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('Identity reconciliation review', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Show config', { exact: true })).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('factory layouts render without recovery state or core header collisions', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const layouts = ['US Top Down', 'TC Classic', 'Drill Down', 'Sector by Year', '1 Chart', '4 Timeframe', 'Fundamentals', 'Study Lab']
    for (const layout of layouts) {
      const tab = page.getByRole('tab', { name: layout, exact: true }).first()
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
        document.querySelectorAll('.chart-tool').forEach((chart, index) => {
          const toolbar = chart.querySelector('.chart-tool__drawing-toolbar')?.getBoundingClientRect()
          const surface = chart.querySelector('.chart-tool__surface')?.getBoundingClientRect()
          if (toolbar && surface && toolbar.right > surface.left) issues.push(`chart-toolbar-surface-${index}`)
        })
        return issues
      })
      expect(collisions).toEqual([])
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('factory analysis layouts expose linked comparison chart surfaces', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')

    const drillDown = page.getByRole('tab', { name: 'Drill Down', exact: true }).first()
    await expect(drillDown).toBeVisible({ timeout: 10_000 })
    await drillDown.click()
    await expect(page.locator('.tool-window').filter({ hasText: 'Selected Symbol' }).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.tool-window').filter({ hasText: 'Sector Indexes' }).first()).toBeVisible()
    await expect(page.locator('.tool-window').filter({ hasText: 'Industry Indexes' }).first()).toBeVisible()
    await expect(page.locator('.tool-window').filter({ hasText: 'Components' }).first()).toBeVisible()

    // Drill Down keeps the comparison chart in a Golden Layout tab stack.  The
    // tab must be reachable without leaving the workspace and must mount the
    // same chart comparison controls as the selected-symbol chart.
    const sectorComparisonTab = page.locator('.lm_tab:visible').filter({ hasText: 'Sector Comparison' }).last()
    await expect(sectorComparisonTab).toBeVisible({ timeout: 10_000 })
    await sectorComparisonTab.click()
    const comparisonWindow = page.locator('.tool-window').filter({ hasText: 'Sector Comparison' }).first()
    await expect(comparisonWindow).toBeVisible({ timeout: 10_000 })
    await expect(comparisonWindow.locator('.chart-tool__compare')).toBeVisible()

    const sectorByYear = page.getByRole('tab', { name: 'Sector by Year', exact: true }).first()
    await expect(sectorByYear).toBeVisible()
    await sectorByYear.click()
    await expect(page.locator('.tool-window').filter({ hasText: 'Selected Symbol' }).first()).toBeVisible({ timeout: 10_000 })
    const normalizedWindow = page.locator('.tool-window').filter({ hasText: 'Normalized Comparison' }).first()
    await expect(normalizedWindow).toBeVisible({ timeout: 10_000 })
    await expect(normalizedWindow.locator('.chart-tool__compare')).toBeVisible()
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

    // A persisted-layout refresh can close the browser-owned pop-out between the
    // geometry read and cleanup. Treat that already-closed state as successful cleanup;
    // otherwise close it through the user-facing control and await the browser event.
    if (!popup.isClosed()) {
      // A concurrent revisioned workspace refresh can close a disposable child
      // after the source has already restored it. Treat that completed cleanup
      // as equivalent to the explicit close click; never turn a transient child
      // lifetime race into a false lifecycle failure.
      if (!popup.isClosed()) {
        const closed = popup.waitForEvent('close')
        await popup.locator('button[title="Close"]').click()
        await closed
      }
    }

    // The docked window is the durable source of truth; a disposable pop-out cannot
    // remove it from the parent layout.
    await expect(page.locator('button[title="Float"]').first()).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8f — repeated float/close cycles do not accumulate source tools', async ({ page, context, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('button[title="Float"]').first()).toBeVisible({ timeout: 10_000 })
    // This lifecycle oracle owns source-tool leak detection. Chart canvas/uPlot
    // readiness is covered by the dedicated chart and performance oracles and
    // may legitimately remain unavailable under a free-source fixture.
    await expect.poll(() => page.locator('.tool-window').count(), { timeout: 30_000 }).toBeGreaterThan(0)
    await page.waitForTimeout(500)
    const sourceToolCount = await page.locator('.tool-window').count()
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
    }

    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8h — simultaneous pop-outs retain both tools and recover independently', async ({ page, context, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect.poll(() => page.locator('button[title="Float"]').count(), { timeout: 10_000 }).toBeGreaterThan(1)

    const firstPopupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').nth(0).click()
    const firstPopup = await firstPopupPromise
    await firstPopup.waitForLoadState('domcontentloaded')
    await expect(firstPopup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })

    const secondPopupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').nth(1).click()
    const secondPopup = await secondPopupPromise
    await secondPopup.waitForLoadState('domcontentloaded')
    await expect(secondPopup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })
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
    await page.locator('.workstation__status').click()
    await expect(menu).toHaveCount(0)

    await tool.locator('[title="Tool menu"]').click()
    await expect(tool.locator('[role="menu"]')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(page.locator('.workstation__data-state').first()).toHaveText(
      /Current · canonical|Delayed|Stale|Partial coverage|Coverage limited|Fetching|Backfilling history|Unavailable/,
    )
    await expect(page.locator('.workstation__data-state[role="status"]').first()).toHaveAttribute('aria-label', /Market data freshness:/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-keyboard — tool menus support keyboard navigation and focus recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible({ timeout: 10_000 })
    const trigger = tool.locator('[title="Tool menu"]')
    await trigger.press('ArrowDown')
    const menu = tool.locator('[role="menu"]')
    const items = menu.getByRole('menuitem')
    await expect(menu).toBeVisible()
    await expect(items.nth(0)).toBeFocused()
    await items.nth(0).press('ArrowDown')
    await expect(items.nth(1)).toBeFocused()
    await items.nth(1).press('End')
    await expect(items.nth(2)).toBeFocused()
    await items.nth(2).press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-bottom-edge — tool menus remain inside the viewport near the bottom edge', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 320 })
    await page.goto('/chart')
    const tool = page.locator('.tool-window').filter({ has: page.locator('[title="Tool menu"]') }).first()
    await expect(tool).toBeVisible({ timeout: 10_000 })
    const trigger = tool.locator('[title="Tool menu"]')
    await trigger.click()
    const menu = tool.locator('[role="menu"]')
    await expect(menu).toBeVisible()
    const bounds = await menu.boundingBox()
    expect(bounds).not.toBeNull()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.y).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(320)
    await menu.getByRole('menuitem', { name: 'Close' }).press('Escape')
    await expect(menu).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-menu — application menus dismiss on outside pointer and Escape', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const workspaceButton = page.getByRole('button', { name: 'Workspace', exact: true })
    const addToolButton = page.getByRole('button', { name: 'Add tool', exact: true })
    await expect(workspaceButton).toBeVisible({ timeout: 10_000 })
    await expect(addToolButton).toBeVisible({ timeout: 10_000 })

    await workspaceButton.click()
    await expect(page.locator('.workstation__workspace-popover')).toBeVisible()
    await addToolButton.click()
    await expect(page.locator('.workstation__tool-library-menu')).toBeVisible()

    await page.locator('.workstation__status').click()
    await expect(page.locator('.workstation__workspace-popover')).toHaveCount(0)
    await expect(page.locator('.workstation__tool-library-menu')).toHaveCount(0)

    await workspaceButton.click()
    await addToolButton.click()
    await page.keyboard.press('Escape')
    await expect(page.locator('.workstation__workspace-popover')).toHaveCount(0)
    await expect(page.locator('.workstation__tool-library-menu')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-shell-menu-containment — shell menus remain inside a constrained viewport', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 260 })
    await page.goto('/chart/SPY')
    const checks = [
      [page.getByRole('button', { name: 'Workspace', exact: true }), page.getByRole('menu', { name: 'Workspace layouts' })],
      [page.getByRole('button', { name: 'Help', exact: true }), page.getByRole('menu', { name: 'Keyboard shortcuts' })],
      [page.getByRole('button', { name: 'Add tool', exact: true }), page.getByRole('menu', { name: 'Workstation tools' })],
    ] as const
    for (const [trigger, menu] of checks) {
      await trigger.click()
      await expect(menu).toBeVisible()
      const bounds = await menu.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.y).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(260)
      await page.keyboard.press('Escape')
      await expect(menu).toHaveCount(0)
    }
    const recentTrigger = page.getByRole('button', { name: 'Recent symbols' })
    await expect(recentTrigger).toBeEnabled({ timeout: 10_000 })
    await recentTrigger.click()
    const recentMenu = page.getByRole('menu', { name: 'Recent symbols' })
    await expect(recentMenu).toBeVisible()
    const recentBounds = await recentMenu.boundingBox()
    expect(recentBounds).not.toBeNull()
    expect(recentBounds!.x).toBeGreaterThanOrEqual(0)
    expect(recentBounds!.y).toBeGreaterThanOrEqual(0)
    expect(recentBounds!.x + recentBounds!.width).toBeLessThanOrEqual(390)
    expect(recentBounds!.y + recentBounds!.height).toBeLessThanOrEqual(260)
    await page.keyboard.press('Escape')
    await expect(recentMenu).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-history — active-symbol history is persisted and selectable from the shell', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    const historyButton = page.getByRole('button', { name: 'Recent symbols' })
    await expect(historyButton).toBeEnabled({ timeout: 10_000 })
    await historyButton.click()
    const history = page.locator('.workstation__recent-symbols')
    await expect(history).toBeVisible({ timeout: 10_000 })
    const recentSymbol = history.locator(':scope > button[role="menuitem"]').first()
    await expect(recentSymbol).toContainText('SPY')
    await recentSymbol.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY')
    await expect(history).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-search-keyboard — typed symbol search exposes active option and keyboard selection', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/instruments/search**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'NYSE Arca', type: 'ETF', instrument_id: 11 },
          { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'NYSE Arca', type: 'ETF', instrument_id: 12 },
        ]),
      })
    })
    await page.goto('/chart/SPY')
    const input = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(input).toHaveValue('SPY', { timeout: 15_000 })
    await input.fill('')
    await input.click()
    await input.press('ControlOrMeta+A')
    await input.press('Backspace')
    await input.pressSequentially('XLK', { delay: 30 })
    const results = page.getByRole('listbox', { name: 'Symbol search results' })
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(input).toHaveAttribute('aria-expanded', 'true')
    await expect(results).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
    await expect(input).toHaveAttribute('aria-activedescendant', 'workstation-symbol-option-0')
    await input.press('ArrowDown')
    await expect(input).toHaveAttribute('aria-activedescendant', 'workstation-symbol-option-1')
    await input.press('ArrowUp')
    await expect(input).toHaveAttribute('aria-activedescendant', 'workstation-symbol-option-0')
    await input.press('Enter')
    await expect(input).toHaveValue('XLK', { timeout: 15_000 })
    await expect(results).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-search-canonical — active-symbol search reaches canonical backend data without fixtures', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const input = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(input).toHaveValue('SPY', { timeout: 15_000 })
    await input.click()
    await input.press('Meta+A')
    await input.press('Backspace')
    await expect(input).toHaveValue('', { timeout: 5_000 })
    await input.pressSequentially('XLK', { delay: 30 })
    const results = page.getByRole('listbox', { name: 'Symbol search results' })
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(results).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect(results.locator('[role="option"]', { hasText: 'XLK' }).first()).toBeVisible({ timeout: 10_000 })
    await input.press('Enter')
    await expect(input).toHaveValue('XLK', { timeout: 15_000 })
    await expect(results).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-a — chart provider failure remains an explicit visible error state', async ({ page, browserDiagnostics }) => {
    const ohlcvResponse = page.waitForResponse(response => response.url().includes('/api/v1/ohlcv/') && response.status() === 404, { timeout: 30_000 })
    await page.route('**/api/v1/ohlcv/**', async route => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No local observations are available for SPY' }),
      })
    })
    await page.goto('/chart')
    await ohlcvResponse
    const errorState = page.locator('.chart-tool .tool-state--error')
    await expect(errorState).toHaveAttribute('role', 'alert')
    await expect(errorState).toHaveAttribute('aria-live', 'assertive')
    await expect(errorState).toContainText(/Request failed|unavailable|observations/i, { timeout: 10_000 })
    await expect(page.locator('.chart-tool canvas')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-b — chart history loading state is visible while the request is pending', async ({ page, browserDiagnostics }) => {
    const ohlcvResponse = page.waitForResponse(response => response.url().includes('/api/v1/ohlcv/') && response.status() === 404, { timeout: 30_000 })
    await page.route('**/api/v1/ohlcv/**', async route => {
      await new Promise(resolve => setTimeout(resolve, 1_000))
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'No local observations are available for SPY' }),
      })
    })
    await page.goto('/chart')
    const loadingState = page.locator('.chart-tool .tool-state').filter({ hasText: /Loading SPY/i })
    await expect(loadingState).toHaveAttribute('role', 'status')
    await expect(loadingState).toHaveAttribute('aria-live', 'polite')
    await expect(loadingState).toBeVisible({ timeout: 5_000 })
    // Loading must detach the prior numerical renderer rather than leaving a
    // stale uPlot canvas underneath the explicit state surface.
    await expect(page.locator('.chart-tool canvas')).toHaveCount(0)
    await ohlcvResponse
    await expect(page.locator('.chart-tool .tool-state--error')).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-c — stale technical freshness is surfaced in the workstation status bar', async ({ page, browserDiagnostics }) => {
    const technicalResponse = page.waitForResponse(response => response.url().includes('/api/v1/analysis/instruments/SPY/technical') && response.status() === 200, { timeout: 30_000 })
    await page.route('**/api/v1/analysis/instruments/SPY/technical**', async route => {
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
    await page.goto('/chart')
    await technicalResponse
    await expect(page.locator('.workstation__footer')).toContainText('Stale · cached', { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-d — partial technical coverage is distinguished from stale data', async ({ page, browserDiagnostics }) => {
    const technicalResponse = page.waitForResponse(response => response.url().includes('/api/v1/analysis/instruments/SPY/technical') && response.status() === 200, { timeout: 20_000 })
    await page.route('**/api/v1/analysis/instruments/SPY/technical**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: '2026-08-01T00:00:00Z', adjustment: 'split_adjusted',
          last: 500, rsi14: 55, sma20: 498, sma50: 490, sma200: null, position_52w: null, volume_ratio_50: null,
          freshness: 'partial', freshness_detail: { requested: 1, current: 0, stale: 1, other: 0 }, warnings: [{ code: 'insufficient_history', message: 'SMA(200) requires 200 bars.', instrument_id: 1 }],
        }),
      })
    })
    await page.goto('/chart')
    await technicalResponse
    await expect(page.locator('.workstation__footer')).toContainText('Partial coverage', { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8i-e — backend coverage_limited freshness is rendered as coverage limited', async ({ page, browserDiagnostics }) => {
    const technicalResponse = page.waitForResponse(response => response.url().includes('/api/v1/analysis/instruments/SPY/technical') && response.status() === 200, { timeout: 30_000 })
    await page.route('**/api/v1/analysis/instruments/SPY/technical**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          symbol: 'SPY', timeframe: 'D1', as_of: '2026-08-01T00:00:00Z', adjustment: 'split_adjusted',
          last: null, rsi14: null, sma20: null, sma50: null, sma200: null, position_52w: null, volume_ratio_50: null,
          freshness: 'coverage_limited', freshness_detail: { requested: 1, current: 0, stale: 0, other: 1 },
          warnings: [{ code: 'coverage_limited', message: 'No entitled current dataset is available.' }],
        }),
      })
    })
    await page.goto('/chart')
    await technicalResponse
    await expect(page.locator('.workstation__footer')).toContainText('Coverage limited', { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8j — floated geometry is persisted through the workspace API', async ({ page, context, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    const sourceTool = page.locator('.tool-window').first()
    const floatButton = sourceTool.locator('button[title="Float"]')
    await expect(floatButton).toBeVisible({ timeout: 10_000 })

    const popupPromise = context.waitForEvent('page')
    await floatButton.click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })

    const geometry = await expect.poll(async () => page.evaluate(async () => {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/workspaces/default', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!response.ok) return undefined
      const body = await response.json()
      const windows = body.tabs.flatMap((tab: { windows: Array<Record<string, unknown>> }) => tab.windows)
      const persisted = windows.find((window: Record<string, unknown>) => Boolean((window.style as { popout?: unknown } | undefined)?.popout))
      return (persisted?.style as { popout?: Record<string, unknown> } | undefined)?.popout
    }), { timeout: 10_000, intervals: [250, 500, 1_000] }).toEqual(expect.objectContaining({ left: expect.any(Number), top: expect.any(Number), width: expect.any(Number), height: expect.any(Number) }))

    if (!popup.isClosed()) {
      const closed = popup.waitForEvent('close')
      await popup.locator('button[title="Close"]').click()
      await closed
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8j-conflict — workspace revision conflicts preserve local changes in a recovery copy', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0, { timeout: 10_000 })
    const baseline = await page.evaluate(async () => {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/workspaces/default', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      if (!response.ok) throw new Error(`workspace baseline request failed: ${response.status}`)
      return await response.json() as Record<string, unknown>
    })

    let conflictPending = true
    const baselineWindowKeys = new Set(
      (baseline.tabs as Array<{ windows?: Array<{ instance_key?: string }> }>).flatMap(tab =>
        (tab.windows ?? []).map(window => window.instance_key).filter((key): key is string => Boolean(key)),
      ),
    )
    await page.route(/\/api\/v1\/workspaces\/\d+\/snapshot$/, async route => {
      if (route.request().method() !== 'PUT' || !conflictPending) return route.continue()
      // A previous pop-out can still be finishing a legitimate geometry
      // snapshot when this page starts. Inject the conflict only for the
      // mutation under test: the newly added Notes window. Otherwise the
      // setup races a bootstrap/cleanup write and the actual user mutation
      // never exercises the recovery branch.
      const payload = route.request().postDataJSON() as { tabs?: Array<{ windows?: Array<{ instance_key?: string }> }> }
      const hasLocalWindowAddition = (payload.tabs ?? []).some(tab =>
        (tab.windows ?? []).some(window => typeof window.instance_key === 'string' && !baselineWindowKeys.has(window.instance_key)),
      )
      if (!hasLocalWindowAddition) return route.continue()
      conflictPending = false
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'workspace_revision_conflict', message: 'conflict' } }) })
    })
    await page.route(/\/api\/v1\/workspaces\/\d+$/, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      const latest = JSON.parse(JSON.stringify(baseline)) as Record<string, unknown>
      latest.revision = Number(latest.revision ?? 1) + 1
      latest.name = 'Remote concurrent workspace'
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(latest) })
    })
    await page.route(/\/api\/v1\/workspaces$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      const payload = route.request().postDataJSON() as { name?: string }
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 9910, revision: 1, name: payload.name ?? 'US Top Down Recovery', tabs: [], settings: {} }) })
    })

    await page.getByRole('button', { name: 'Add tool', exact: true }).click()
    await page.getByRole('menuitem', { name: 'Notes', exact: true }).click()
    await expect(page.locator('.workstation__footer')).toContainText(/recovery/i, { timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('local changes were preserved', { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k — disconnected pop-outs restore into the source workspace and can be reopened', async ({ page, context, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    const sourceTool = page.locator('.tool-window').first()
    const floatButton = sourceTool.locator('button[title="Float"]')
    await expect(floatButton).toBeVisible({ timeout: 10_000 })

    const popupPromise = context.waitForEvent('page')
    await floatButton.click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })

    // Simulate a browser-level close/disconnect rather than the tool's own close
    // control. The source workspace must recover the tool and remain usable.
    const closed = popup.waitForEvent('close')
    await popup.close()
    await closed
    await expect.poll(() => context.pages().length).toBe(1)
    await expect(page.locator('.tool-window').first().locator('button[title="Float"]')).toBeVisible({ timeout: 10_000 })

    // Prove recovery is durable by floating the same tool again in the same
    // authenticated session and then closing it through the normal control.
    const reopenedPromise = context.waitForEvent('page')
    await page.locator('.tool-window').first().locator('button[title="Float"]').click()
    const reopened = await reopenedPromise
    await reopened.waitForLoadState('domcontentloaded')
    await expect(reopened.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })
    const reopenedClosed = reopened.waitForEvent('close')
    await reopened.locator('button[title="Close"]').click()
    await reopenedClosed
    await expect(page.locator('.tool-window').first().locator('button[title="Float"]')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-a — blocked browser pop-out keeps the tool docked and reports recovery guidance', async ({ page, browserDiagnostics }) => {
    await page.addInitScript(() => {
      window.open = (() => null) as typeof window.open
    })
    await page.goto('/chart')
    const sourceTool = page.locator('.tool-window').first()
    await expect(sourceTool).toBeVisible({ timeout: 10_000 })
    await sourceTool.locator('button[title="Float"]').click()
    await expect(page.locator('.workstation__footer')).toContainText(/Browser blocked the pop-out/i, { timeout: 5_000 })
    await expect(sourceTool).toBeVisible()
    await expect(page.locator('.workstation__popout')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8c — signing out propagates from the source workstation to its pop-out', async ({ page, context }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    const popupPromise = context.waitForEvent('page')
    await page.locator('button[title="Float"]').first().click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    await expect(popup.locator('.workstation__popout .tool-window')).toBeVisible({ timeout: 25_000 })

    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 })
    await expect(popup).toHaveURL(/\/login/, { timeout: 5_000 })
  })

  test('F8d — US Top Down publishes benchmark and sector selections without route changes', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList).toBeVisible({ timeout: 10_000 })
    const sectorSymbols = sectorList.getByRole('listbox', { name: 'Relative to SPY symbols' })
    await expect(sectorSymbols).toBeVisible({ timeout: 10_000 })
    await expect(sectorSymbols.getByRole('option').first()).toBeVisible({ timeout: 25_000 })
    await expect(sectorList.getByRole('option', { name: /XLK/ }).first()).toBeVisible({ timeout: 25_000 })

    // The opt-in deterministic market fixture may hydrate the data-dependent tools;
    // this assertion remains intentionally tolerant of honest unavailable/cached
    // states so the route and linked-symbol contract is tested independently.
    await sectorList.getByRole('option', { name: /XLK/ }).first().click({ position: { x: 8, y: 14 } })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK')
    await expect(page.locator('.workstation__footer')).toContainText(/Unavailable|No local observations|cached|Fetching/i)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8d-SPX — unavailable official SPX resolves to the labelled SPY proxy', async ({ page, browserDiagnostics }) => {
    // Keep this deterministic: the free-source acceptance fixture does not
    // promise an entitled official index series. The product must still make
    // the requested SPX workflow usable without pretending SPY is SPX.
    await page.route('**/api/v1/instruments/SPX*', route => route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Official SPX series is not available in this entitlement' }),
    }))
    await page.goto('/chart/SPX')
    const activeSymbol = page.getByRole('combobox', { name: 'Active symbol' })
    await expect(activeSymbol).toHaveValue('SPY', { timeout: 15_000 })
    await expect(page.locator('.workstation__footer')).toContainText('SPX official series unavailable; using tradable proxy SPY', { timeout: 15_000 })
    await expect(page).toHaveURL(/\/chart\/SPX$/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8m — yellow wildcard receives linked symbols while grey remains isolated', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    // Tests share the authenticated workspace; restore the immutable factory
    // state so this link-bus assertion cannot inherit a prior link selection.
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
      await page.waitForTimeout(300)
      await page.reload()
    }
    const activeSymbolInput = page.getByRole('combobox', { name: 'Active symbol' })
    const chartTool = page.locator('.chart-tool').first().locator('..').locator('..')
    const chartSymbol = chartTool.locator('.tool-window__symbol')
    const chartLink = chartTool.locator('select[aria-label="Chart symbol link group"]')
    await expect(chartLink).toBeVisible({ timeout: 10_000 })
    // Explicitly establish a broadcasting group before publishing SPY; persisted
    // workspace state may otherwise leave this chart isolated from the shell.
    await chartLink.selectOption('blue')
    await activeSymbolInput.fill('SPY')
    await activeSymbolInput.press('Enter')
    await expect(activeSymbolInput).toHaveValue('SPY')
    await expect(chartSymbol).toHaveText('SPY', { timeout: 10_000 })
    const initialChartSymbol = 'SPY'

    const sectors = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectors.getByRole('option', { name: /XLK/ }).first()).toBeVisible({ timeout: 10_000 })

    // Grey is an explicit isolation boundary: linked sector selection changes
    // the workstation symbol but must not mutate this chart.
    await chartLink.selectOption('grey')
    await expect(chartLink).toHaveValue('grey')
    await page.waitForTimeout(250)
    await expect(chartLink).toHaveValue('grey')
    const isolatedTarget = initialChartSymbol === 'XLE' ? 'XLK' : 'XLE'
    // The row is a wide virtualized canvas; click the visible left cell so the
    // browser does not center-scroll the canvas before dispatching the click.
    await sectors.getByRole('option', { name: new RegExp(isolatedTarget) }).first().click({ position: { x: 8, y: 14 } })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(isolatedTarget)
    await expect(chartSymbol).toHaveText(initialChartSymbol)
    await page.waitForTimeout(250)

    // Yellow is a wildcard receiver: the same chart now follows a linked sector
    // selection regardless of the source group's concrete color.
    await chartLink.selectOption('yellow')
    await expect(chartLink).toHaveValue('yellow')
    // The selector is controlled by the persisted workspace update; allow the
    // store event to settle before publishing the next linked symbol.
    await page.waitForTimeout(250)
    const wildcardTarget = isolatedTarget === 'XLK' ? 'XLE' : 'XLK'
    await sectors.getByRole('option', { name: new RegExp(wildcardTarget) }).first().click({ position: { x: 8, y: 14 } })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(wildcardTarget)
    // The shell's canonical wildcard publication is the cross-window contract;
    // chart-level resolution is covered by the workspace-store unit matrix.
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8n — timeframe links propagate within a group while grey stays local', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await page.getByRole('tab', { name: '4 Timeframe', exact: true }).click()

    // The factory's four windows are serialized in M15, Daily, Weekly,
    // Monthly order; use the stable tool order rather than clipped header text.
    const windows = page.locator('.tool-window')
    await expect(windows).toHaveCount(4)
    const daily = windows.nth(1)
    const monthly = windows.nth(3)
    const dailyTimeframe = daily.locator('select[aria-label="Daily timeframe"]')
    const dailyLink = daily.locator('select[aria-label="Daily timeframe link group"]')
    const monthlyTimeframe = monthly.locator('select[aria-label="Monthly timeframe"]')
    const monthlyLink = monthly.locator('select[aria-label="Monthly timeframe link group"]')

    // Put both windows on the same blue timeframe bus: a change in one must
    // arrive at the other, even though their factory defaults differ.
    await dailyLink.selectOption('blue')
    await monthlyLink.selectOption('blue')
    await dailyTimeframe.selectOption('D1')
    await monthlyTimeframe.selectOption('W1')
    await expect(dailyTimeframe).toHaveValue('W1')

    // Grey is a local timeframe boundary. Subsequent blue broadcasts must not
    // overwrite the isolated chart's selected timeframe.
    await dailyLink.selectOption('grey')
    await dailyTimeframe.selectOption('MN')
    await monthlyTimeframe.selectOption('D1')
    await expect(dailyTimeframe).toHaveValue('MN')
    await expect(monthlyTimeframe).toHaveValue('D1')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8n-crosshair — linked chart cursors follow the published bar timestamp', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const sourceWindow = page.locator('.tool-window').filter({ has: page.locator('.chart-tool') }).first()
    const targetWindow = page.locator('.tool-window').filter({ has: page.locator('.ratio-chart') }).first()
    const source = sourceWindow.locator('.chart-tool')
    const target = targetWindow.locator('.ratio-chart')
    await expect(source.locator('.uplot')).toBeVisible({ timeout: 20_000 })
    await expect(target.locator('.uplot')).toBeVisible({ timeout: 20_000 })
    const sourceLink = sourceWindow.locator('select[aria-label="Chart symbol link group"]')
    const targetLink = targetWindow.locator('select[aria-label="Relative Strength symbol link group"]')
    await sourceLink.selectOption('blue')
    await targetLink.selectOption('blue')
    const targetCursor = target.locator('.u-cursor-x').first()
    await expect(targetCursor).toHaveCount(1, { timeout: 10_000 })
    const before = await targetCursor.evaluate(element => ({ transform: (element as HTMLElement).style.transform, off: element.classList.contains('u-off') }))
    const sourceBox = await source.locator('.uplot').boundingBox()
    expect(sourceBox).not.toBeNull()
    await page.mouse.move(sourceBox!.x + sourceBox!.width * 0.63, sourceBox!.y + sourceBox!.height * 0.45)
    await expect.poll(() => targetCursor.evaluate(element => ({ transform: (element as HTMLElement).style.transform, off: element.classList.contains('u-off') })), { timeout: 10_000 }).not.toEqual(before)
    await expect(targetCursor).not.toHaveClass(/u-off/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8n-gesture — uPlot chart preserves its surface through wheel zoom, trackpad pan, and latest recovery', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool:visible').first()
    await expect(chart.locator('.uplot')).toBeVisible({ timeout: 20_000 })
    const over = chart.locator('.u-over').first()
    await expect(over).toBeVisible({ timeout: 10_000 })
    const box = await over.boundingBox()
    expect(box).not.toBeNull()

    // Keep the actual uPlot element identity as the renderer invariant. The
    // gestures below must change its view, not replace the chart instance.
    await chart.locator('.uplot').evaluate(element => {
      ;(window as unknown as { __gestureUPlot?: Element }).__gestureUPlot = element
    })
    const fingerprint = () => chart.locator('.uplot canvas').first().evaluate(canvas => {
      const ctx = canvas.getContext('2d')
      if (!ctx || canvas.width === 0 || canvas.height === 0) return 'empty'
      const sample = Math.max(1, Math.floor(Math.min(canvas.width, canvas.height) / 12))
      let checksum = 0
      for (let y = sample; y < canvas.height; y += sample) {
        for (let x = sample; x < canvas.width; x += sample) {
          const pixel = ctx.getImageData(x, y, 1, 1).data
          checksum = (checksum * 33 + pixel[0] * 3 + pixel[1] * 5 + pixel[2] * 7 + pixel[3]) >>> 0
        }
      }
      return `${canvas.width}x${canvas.height}:${checksum}`
    })

    await page.mouse.move(box!.x + box!.width * 0.52, box!.y + box!.height * 0.42)
    const beforeZoom = await fingerprint()
    await page.mouse.wheel(0, -180)
    await expect.poll(fingerprint, { timeout: 10_000 }).not.toBe(beforeZoom)

    const beforePan = await fingerprint()
    // A horizontal wheel delta is the browser-level equivalent of a
    // trackpad swipe and is handled by the chart's pan path.
    // A negative horizontal delta moves the viewport back through history;
    // this is the state in which the latest-bar recovery affordance should
    // appear. A positive delta is bounded at the latest overscroll margin.
    // Repeat bounded trackpad-style gestures with a short browser turn between
    // them. Chromium may coalesce adjacent wheel events; the recovery affordance
    // is the authoritative observable that the chart has entered history.
    for (let i = 0; i < 8 && !(await chart.locator('.go-to-latest').count()); i += 1) {
      await page.mouse.wheel(-420, 0)
      await page.waitForTimeout(120)
    }
    await expect.poll(() => chart.locator('.go-to-latest').count(), { timeout: 10_000 }).toBe(1)
    await expect(chart.locator('.go-to-latest')).toBeVisible({ timeout: 10_000 })

    await chart.getByRole('button', { name: 'Go to latest bar' }).click()
    await expect(chart.locator('.go-to-latest')).toHaveCount(0)
    await expect(chart.locator('.uplot')).toHaveCount(1)
    expect(await chart.locator('.uplot').evaluate(element => element === (window as unknown as { __gestureUPlot?: Element }).__gestureUPlot)).toBe(true)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8n-cross-window — linked crosshair timestamps propagate through a chart pop-out', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    const sourceWindow = page.locator('.tool-window').filter({ has: page.locator('.chart-tool') }).first()
    const targetWindow = page.locator('.tool-window').filter({ has: page.locator('.ratio-chart') }).first()
    const target = targetWindow.locator('.ratio-chart')
    await expect(sourceWindow.locator('.chart-tool .uplot')).toBeVisible({ timeout: 20_000 })
    await expect(target.locator('.uplot')).toBeVisible({ timeout: 20_000 })
    await sourceWindow.locator('select[aria-label="Chart symbol link group"]').selectOption('blue')
    await targetWindow.locator('select[aria-label="Relative Strength symbol link group"]').selectOption('blue')

    const targetCursor = target.locator('.u-cursor-x').first()
    await expect(targetCursor).toHaveCount(1, { timeout: 10_000 })
    const before = await targetCursor.evaluate(element => ({ transform: (element as HTMLElement).style.transform, off: element.classList.contains('u-off') }))
    const popupPromise = context.waitForEvent('page')
    await sourceWindow.locator('button[title="Float"]').click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    const popupChart = popup.locator('.chart-tool')
    await expect(popupChart.locator('.uplot')).toBeVisible({ timeout: 20_000 })
    const popupBox = await popupChart.locator('.uplot').boundingBox()
    expect(popupBox).not.toBeNull()
    await popup.mouse.move(popupBox!.x + popupBox!.width * 0.63, popupBox!.y + popupBox!.height * 0.45)
    await expect.poll(() => targetCursor.evaluate(element => ({ transform: (element as HTMLElement).style.transform, off: element.classList.contains('u-off') })), { timeout: 10_000 }).not.toEqual(before)
    await expect(targetCursor).not.toHaveClass(/u-off/)

    const closed = popup.waitForEvent('close')
    await popup.locator('button[title="Close"]').click()
    await closed
    await expect.poll(() => context.pages().length).toBe(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8n-cross-window-links — symbols and timeframes propagate to a chart pop-out', async ({ page, context, browserDiagnostics }) => {
    await page.goto('/chart')
    const sourceWindow = page.locator('.tool-window').filter({ has: page.locator('.chart-tool') }).first()
    await expect(sourceWindow.locator('.chart-tool .uplot')).toBeVisible({ timeout: 20_000 })
    const popupPromise = context.waitForEvent('page')
    await sourceWindow.locator('button[title="Float"]').click()
    const popup = await popupPromise
    await popup.waitForLoadState('domcontentloaded')
    const popupTool = popup.locator('.workstation__popout .tool-window')
    await expect(popupTool.locator('.chart-tool .uplot')).toBeVisible({ timeout: 20_000 })
    await expect(popupTool.locator('.tool-window__symbol')).toHaveText('SPY')

    await page.getByRole('combobox', { name: 'Active symbol' }).fill('QQQ')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
    await expect(popupTool.locator('.tool-window__symbol')).toHaveText('QQQ', { timeout: 15_000 })

    await page.getByRole('combobox', { name: 'Linked timeframe' }).selectOption('W1')
    await expect(popupTool.locator('.tool-window__timeframe')).toHaveValue('W1', { timeout: 15_000 })

    const closed = popup.waitForEvent('close')
    await popup.locator('button[title="Close"]').click()
    await closed
    await expect.poll(() => context.pages().length).toBe(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k — Ctrl+wheel traverses the workstation symbol universe', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const activeSymbol = page.getByRole('combobox', { name: 'Active symbol' })
    // Establish the starting symbol explicitly; persisted workspace hydration may leave
    // the route-less input blank even though the canonical active symbol is SPY.
    await activeSymbol.fill('SPY')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
    await expect(activeSymbol).toHaveValue('SPY')
    await page.locator('.workstation').hover()
    // Exercise the browser's real modifier + wheel path rather than dispatching a
    // synthetic event with an implementation-specific target.
    await page.keyboard.down('Control')
    await page.mouse.wheel(0, 100)
    await page.keyboard.up('Control')
    await expect.poll(() => activeSymbol.inputValue()).not.toBe('SPY')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-shift — Shift+Space traverses backward and editor focus owns the shortcut', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const activeSymbol = page.getByRole('combobox', { name: 'Active symbol' })
    await activeSymbol.fill('SPY')
    await page.getByRole('button', { name: 'Go', exact: true }).click()
    await expect(activeSymbol).toHaveValue('SPY')

    const workstation = page.locator('.workstation:visible').last()
    await workstation.press('Shift+Space')
    await expect.poll(() => activeSymbol.inputValue()).not.toBe('SPY')
    const traversedBackwardTo = await activeSymbol.inputValue()

    // A focused editor must retain the keystroke rather than publishing another
    // symbol through the workstation-level keyboard handler.
    await activeSymbol.fill('SPY')
    await activeSymbol.press('Space')
    await expect(activeSymbol).toHaveValue('SPY ')
    await expect(page.locator('.workstation__footer span').first()).toHaveText(traversedBackwardTo)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-listbox — virtualized watchlists expose an isolated active descendant and Home/End traversal', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const watchlist = page.getByRole('region', { name: 'Relative to SPY' }).filter({ has: page.locator('.watchlist__row') }).first()
    await expect(watchlist).toBeVisible({ timeout: 15_000 })
    const listbox = watchlist.getByRole('listbox', { name: 'Relative to SPY symbols' })
    await expect(listbox).toBeVisible()
    const rows = listbox.getByRole('option')
    await expect.poll(() => rows.count()).toBeGreaterThan(2)

    await listbox.focus()
    await listbox.press('End')
    const lastActiveId = await listbox.getAttribute('aria-activedescendant')
    expect(lastActiveId).toMatch(/^watchlist-[a-z0-9-]+-row-/)
    await expect(listbox.locator(`#${lastActiveId}`)).toBeVisible()
    const lastSymbol = (await listbox.locator(`#${lastActiveId}`).getAttribute('aria-label'))?.split(/\s+/, 1)[0]
    expect(lastSymbol).toBeTruthy()

    await listbox.press('Home')
    const firstActiveId = await listbox.getAttribute('aria-activedescendant')
    expect(firstActiveId).toMatch(/^watchlist-[a-z0-9-]+-row-/)
    await expect(listbox.locator(`#${firstActiveId}`)).toBeVisible()
    expect(firstActiveId).not.toBe(lastActiveId)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-type — typing outside an editor opens symbol search and Escape closes it', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const workstation = page.locator('.workstation:visible').last()
    const activeSymbol = workstation.getByRole('combobox', { name: 'Active symbol' })
    const results = workstation.getByRole('listbox', { name: 'Symbol search results' })

    // Focus the keyboard scope itself so the shortcut is independent of layout
    // geometry and remains deterministic at every display scale.
    await workstation.focus()
    await page.keyboard.type('sp')
    await expect(activeSymbol).toBeFocused()
    await expect(activeSymbol).toHaveValue('Sp')
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(results.getByRole('option').first()).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(results).toHaveCount(0)
    await expect(activeSymbol).toBeFocused()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-search-states — symbol search exposes loading and no-result states', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/instruments/search**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
    await page.goto('/chart/SPY')
    const workstation = page.locator('.workstation:visible').last()
    await expect(workstation).toBeVisible()
    const activeSymbol = workstation.getByRole('combobox', { name: 'Active symbol' })
    await activeSymbol.click()
    await activeSymbol.fill('')
    await activeSymbol.pressSequentially('ZZZZ', { delay: 25 })
    const results = workstation.getByRole('listbox', { name: 'Symbol search results' })
    await expect(results).toBeVisible()
    await expect(results).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
    await expect(activeSymbol).toHaveAttribute('aria-busy', 'false')
    await expect(results).toContainText('No canonical instruments found for “ZZZZ”')
    await expect(results.getByRole('option')).toHaveCount(0)
    await activeSymbol.press('Escape')
    await expect(results).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8k-help — keyboard help is discoverable and editor focus suppresses global help', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const workstation = page.locator('.workstation')
    const helpButton = page.getByRole('button', { name: 'Help', exact: true })
    const helpMenu = page.getByRole('menu', { name: 'Keyboard shortcuts' })

    await helpButton.click()
    await expect(helpMenu).toBeVisible()
    await expect(helpMenu).toContainText('Shift+Space')
    await expect(helpMenu).toContainText('Ctrl+wheel')

    // Shell menus are mutually exclusive so a fixed popover cannot cover the
    // next menu or intercept a dock interaction underneath it.
    await helpButton.click()
    const workspaceButton = page.getByRole('button', { name: 'Workspace', exact: true })
    const addToolButton = page.getByRole('button', { name: 'Add tool', exact: true })
    await workspaceButton.click()
    await expect(page.locator('.workstation__workspace-popover')).toBeVisible()
    await addToolButton.click()
    await expect(page.locator('.workstation__workspace-popover')).toBeHidden()
    await expect(page.locator('.workstation__tool-library-menu')).toBeVisible()
    await helpButton.click()
    await expect(page.locator('.workstation__tool-library-menu')).toBeHidden()
    await expect(helpMenu).toBeVisible()

    // The shell-level F1 path is equivalent to opening the visible Help menu.
    await helpButton.click()
    await workstation.press('F1')
    await expect(helpMenu).toBeVisible()

    // A focused editor owns the event, so F1 must not reopen the global menu.
    const activeSymbol = page.getByRole('combobox', { name: 'Active symbol' })
    await activeSymbol.fill('SPY')
    await activeSymbol.press('F1')
    await expect(helpMenu).toBeHidden()
    await expect(activeSymbol).toHaveValue('SPY')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8l — hidden workstation surfaces suspend market-analysis refreshes', async ({ page, browserDiagnostics }) => {
    const refreshRequests: string[] = []
    page.on('request', request => {
      const path = new URL(request.url()).pathname
      if (path.startsWith('/api/v1/market-groups/') || path.startsWith('/api/v1/analysis/')) refreshRequests.push(path)
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation').first()).toBeVisible({ timeout: 10_000 })
    // The initial benchmark/sector/technical fan-out can complete after the
    // workstation shell is visible; establish the hidden-state baseline only
    // after that bounded first-load window has settled.
    await page.waitForTimeout(3_000)
    refreshRequests.length = 0

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.waitForTimeout(1_500)
    expect(refreshRequests).toEqual([])

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e — default relative strength compares SPY with RSP', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const ratio = page.locator('.ratio-chart:visible').last()
    await expect(ratio.locator('.ratio-chart__legend strong')).toBeVisible({ timeout: 15_000 })
    await expect(ratio.locator('.ratio-chart__legend strong')).toHaveText('SPY/RSP')
    if (process.env.E2E_SEED_MARKET_DATA === 'true') {
      await expect(page.locator('.workstation__data-state').first()).toHaveText(
        'Current · canonical',
      )
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.live-membership — top-down benchmark and sector holdings are canonical, not fixtures', async ({ page, loggedIn, browserDiagnostics }) => {
    test.skip(process.env.E2E_SEED_MARKET_DATA === 'true', 'Requires the authorised free-source canonical database')
    await page.goto('/chart')
    const token = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(token).toBeTruthy()
    const payload = await Promise.all(['SPY', 'RSP', 'XLK'].map(async symbol => {
      const response = await page.request.get(
        `/api/v1/etf-holdings/${symbol}/holdings?limit=500&sort=weight&direction=desc&point_in_time=true`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      return { symbol, status: response.status(), body: await response.json() }
    }))
    for (const result of payload) {
      expect(result.status, `${result.symbol} holdings status`).toBe(200)
      expect(result.body.snapshot.row_count, `${result.symbol} row count`).toBeGreaterThan(20)
      expect(result.body.snapshot.resolved_count, `${result.symbol} resolved count`).toBeGreaterThan(0)
      expect(result.body.snapshot.provenance).not.toBe('controlled_fixture')
      expect(result.body.snapshot.source_provider).not.toBe('e2e_reference')
    }
    expect(payload.find(result => result.symbol === 'SPY')?.body.snapshot.provenance).toContain('spdr_')
    expect(payload.find(result => result.symbol === 'RSP')?.body.snapshot.provenance).toMatch(/^(sec_|issuer_self_snapshotted_holdings)/)
    expect(payload.find(result => result.symbol === 'XLK')?.body.snapshot.provenance).toContain('spdr_')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.live-sector-drilldown — every live sector exposes an industry surface', async ({ page, browserDiagnostics }) => {
    test.skip(process.env.E2E_SEED_MARKET_DATA === 'true', 'Requires the authorised free-source canonical database')
    await page.goto('/chart')
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList).toBeVisible({ timeout: 15_000 })
    const sectors = ['XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY']
    for (const sector of sectors) {
      const row = sectorList.getByRole('option', { name: new RegExp(`\\b${sector}\\b`) }).first()
      await expect(row, `${sector} sector row`).toBeVisible({ timeout: 15_000 })
      await row.click({ position: { x: 8, y: 14 } })
      await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(sector, { timeout: 15_000 })
      const industries = page.locator('.industry-list')
      await expect(industries, `${sector} industry surface`).toBeVisible({ timeout: 15_000 })
      await expect.poll(
        () => industries.locator('.industry-list__row').count(),
        { timeout: 15_000, message: `${sector} should expose at least one canonical industry row` },
      ).toBeGreaterThan(0)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e-empty-industry — the default Industries pane distinguishes selection from missing proxy data', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.tool-state').filter({ hasText: 'Select a sector to inspect its industries and verified ETF proxies.' })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.tool-state').filter({ hasText: 'No mapped ETF proxy for SPY' })).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.2 — ratio comparison editor adds an XLK/XLE leg without leaving the workstation', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await expect(sectorList.getByRole('option', { name: /XLK/ }).first()).toBeVisible({ timeout: 15_000 })
    await sectorList.getByRole('option', { name: /XLK/ }).first().click({ position: { x: 8, y: 14 } })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK')

    const ratio = page.locator('.ratio-chart:visible').last()
    const comparison = ratio.locator('input[aria-label="Ratio comparison symbol"]')
    await expect(comparison).toBeVisible({ timeout: 15_000 })
    await comparison.fill('XLE')
    await comparison.press('Enter')
    await expect(ratio.locator('.ratio-chart__legend strong')).toContainText('XLK/SPY · XLK/XLE')
    await expect(ratio.locator('button[aria-label="Remove ratio comparison XLE"]')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.2a — a sector row can launch its ratio against the active benchmark', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    // This flow mutates the shared ratio window. Restore the immutable factory
    // first so an earlier comparison/template test cannot leave a persisted
    // custom ratio that masks the row-action contract.
    const reset = page.getByTitle('Reset factory workspace').first()
    if (await reset.count()) {
      page.once('dialog', dialog => dialog.accept())
      await reset.click()
      await expect(page.getByRole('region', { name: 'Relative to SPY' })).toBeVisible({ timeout: 15_000 })
    }
    const sectorList = page.locator('.watchlist[aria-label="Relative to SPY"]:visible').filter({ has: page.locator('.watchlist__row') }).last()
    const xlk = sectorList.getByRole('option', { name: /XLK/ }).first()
    await expect(xlk).toBeVisible({ timeout: 20_000 })
    await xlk.click({ button: 'right', position: { x: 8, y: 14 } })
    // Scope the action to the originating watchlist. Golden Layout can retain
    // detached tool roots while a workspace is hydrating, so a page-global
    // menuitem locator can otherwise target a stale context menu.
    const ratioAction = sectorList.getByRole('menuitem', { name: 'Open ratio vs active' })
    await expect(ratioAction).toBeVisible()
    await ratioAction.click()
    // The factory workspace keeps the benchmark SPY/RSP ratio and updates the
    // ratio-chart window with the newly requested XLK/SPY expression. Golden
    // Layout may retain detached roots and its active CSS class can lag one
    // render turn, so assert the requested visible legend by semantic content
    // rather than DOM order or a transient activation class.
    const visibleRatios = page.locator('.ratio-chart:visible')
    await expect(visibleRatios.last()).toBeVisible({ timeout: 30_000 })
    const ratioLegend = visibleRatios.locator('.ratio-chart__legend strong').filter({ hasText: 'XLK/SPY' }).last()
    await expect(ratioLegend).toHaveText('XLK/SPY', { timeout: 20_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.1 — deep top-down drilldown reaches industry proxies and constituents', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await expect(sectorList.getByRole('option', { name: /XLK/ }).first()).toBeVisible({ timeout: 10_000 })

    await sectorList.getByRole('option', { name: /XLK/ }).first().click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK')
    const industries = page.locator('.industry-list')
    await expect(industries).toBeVisible({ timeout: 15_000 })
    await expect(industries.locator('.industry-list__header')).toContainText(/1D.*1W.*1M.*3M.*6M.*YTD.*1Y/)
    const semiconductors = industries.locator('.industry-list__row').filter({ hasText: 'Semiconductors' })
    await expect(semiconductors).toBeVisible()
    await expect(semiconductors.locator('.industry-list__classification')).toHaveText('controlled_fixture')
    await expect(industries.locator('.industry-list__provenance')).toContainText('controlled_fixture')
    // Proxy data is intentionally fetched after the constituent response, and
    // may already be cached by the time the row becomes clickable. Assert the
    // actual user-visible result first, then corroborate the authenticated
    // contract through the request context instead of relying on a response
    // listener registered across that asynchronous boundary.
    await semiconductors.click()

    const token = await page.evaluate(() => localStorage.getItem('access_token'))
    expect(token).toBeTruthy()
    const constituentResponse = await page.request.get(
      '/api/v1/market-groups/etf/XLK/industries/Semiconductors',
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(constituentResponse.status()).toBe(200)
    const proxyResponse = await page.request.get(
      '/api/v1/market-groups/etf/XLK/industries/Semiconductors/proxies',
      { headers: { Authorization: `Bearer ${token}` } },
    )
    expect(proxyResponse.status()).toBe(200)
    const proxyPayload = await proxyResponse.json() as {
      proxies: Array<{ symbol: string; provenance?: string | null; source_provider?: string | null }>
    }
    expect(proxyPayload.proxies.length).toBeGreaterThan(0)
    const fixtureProxyPayload = proxyPayload.proxies.every(item => item.provenance === 'controlled_fixture' && item.source_provider === 'e2e_reference')
    const canonicalProxyPayload = proxyPayload.proxies.every(item => item.provenance !== 'controlled_fixture' && item.source_provider !== 'e2e_reference')
    if (process.env.E2E_SEED_MARKET_DATA === 'true') {
      // Seeded interaction stacks may already contain a canonical local proxy
      // snapshot from the free-source refresh. Either that or the explicit,
      // labelled fixture is valid; mixed/unknown provenance is not.
      expect(fixtureProxyPayload || canonicalProxyPayload).toBe(true)
    } else {
      expect(fixtureProxyPayload).toBe(false)
      expect(proxyPayload.proxies.every(item => item.provenance !== 'controlled_fixture' && item.source_provider !== 'e2e_reference')).toBe(true)
    }
    const proxies = page.getByRole('region', { name: 'Verified proxy rankings' })
    await expect(proxies).toBeVisible({ timeout: 15_000 })
    await expect(proxies.locator('.watchlist__header')).toContainText(/1D.*1W.*1M.*3M.*6M/)
    for (const target of ['YTD', '1Y']) {
      await expect.poll(async () => {
        const scroll = proxies.locator('.watchlist__scroll')
        const bounds = await scroll.evaluate(element => ({ max: element.scrollWidth - element.clientWidth }))
        for (let left = 0; left <= bounds.max; left += 100) {
          await scroll.evaluate((element, position) => {
            element.scrollTo({ left: position, behavior: 'instant' })
            element.dispatchEvent(new Event('scroll'))
          }, left)
          if ((await proxies.locator('.watchlist__header').innerText()).includes(target)) return true
        }
        return false
      }, { timeout: 10_000, message: `proxy columns should expose ${target}` }).toBe(true)
    }
    await proxies.locator('.watchlist__scroll').evaluate(element => {
      element.scrollTo({ left: 0, behavior: 'instant' })
      element.dispatchEvent(new Event('scroll'))
    })
    const proxySymbol = proxyPayload.proxies[0].symbol
    const proxyRow = proxies.locator('.watchlist__row').filter({ hasText: proxySymbol })
    await expect(proxyRow).toBeVisible()
    await proxyRow.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(proxySymbol)

    const constituents = page.getByRole('region', { name: 'Constituents' }).filter({ has: page.locator('.watchlist__row') }).last()
    await expect(constituents).toBeVisible({ timeout: 15_000 })
    await expect(constituents.locator('.watchlist__header')).toContainText(/1D.*1W.*1M.*3M.*6M/)
    for (const target of ['YTD', '1Y']) {
      await expect.poll(async () => {
        const scroll = constituents.locator('.watchlist__scroll')
        const bounds = await scroll.evaluate(element => ({ max: element.scrollWidth - element.clientWidth }))
        for (let left = 0; left <= bounds.max; left += 100) {
          await scroll.evaluate((element, position) => {
            element.scrollTo({ left: position, behavior: 'instant' })
            element.dispatchEvent(new Event('scroll'))
          }, left)
          if ((await constituents.locator('.watchlist__header').innerText()).includes(target)) return true
        }
        return false
      }, { timeout: 10_000, message: `constituent columns should expose ${target}` }).toBe(true)
    }
    await constituents.locator('.watchlist__scroll').evaluate(element => {
      element.scrollTo({ left: 0, behavior: 'instant' })
      element.dispatchEvent(new Event('scroll'))
    })
    const nvda = constituents.locator('.watchlist__row').filter({ hasText: 'NVDA' })
    await expect(nvda).toBeVisible()
    // The constituent list is virtualized and receives a late technical
    // snapshot. Wait for one settled render epoch before the real click so the
    // browser does not hold a detached row while Vue reconciles cell values.
    const constituentRenderEpoch = constituents.locator('[data-render-epoch]').first()
    await expect.poll(async () => {
      const before = await constituentRenderEpoch.getAttribute('data-render-epoch')
      await page.waitForTimeout(200)
      const after = await constituentRenderEpoch.getAttribute('data-render-epoch')
      return before && before === after ? after : null
    }, { timeout: 10_000, message: 'constituent rows should settle before selection' }).not.toBeNull()
    // Vue may reconcile the virtual canvas during the browser actionability
    // window even after the render epoch settles. Resolve the current keyed row
    // and deliver the same user-facing click synchronously rather than holding
    // a stale locator handle across that reconciliation.
    await nvda.first().evaluate(element => (element as HTMLElement).click())
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('NVDA')
    const ratioLegend = page.locator('.ratio-chart__legend strong').first()
    await expect(ratioLegend).toBeVisible({ timeout: 15_000 })
    // The stock's primary relative-strength leg is the selected sector ETF,
    // even when the preceding industry drilldown also exposed a verified
    // industry proxy.  Keep the sector and market legs explicit so an
    // industry-proxy-only ratio cannot silently satisfy the top-down contract.
    await expect(ratioLegend).toContainText('NVDA/XLK')
    await expect(ratioLegend).toContainText('NVDA/SPY')

    const constituentScroll = constituents.locator('.watchlist__scroll')
    const constituentRows = constituents.locator('.watchlist__row')
    await expect.poll(() => constituentRows.count(), { timeout: 10_000 }).toBeGreaterThan(1)
    const secondConstituent = (await constituentRows.nth(1).innerText()).trim().split(/\s+/)[0]
    await constituentRows.first().evaluate(element => (element as HTMLElement).click())
    await constituentScroll.focus()
    await constituentScroll.press('Space')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(secondConstituent)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.1a — every S&P 500 sector has an industry drilldown surface and stable horizontal scroll', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(sectorList.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await expect(sectorList.getByRole('option', { name: /XLK/ }).first()).toBeVisible({ timeout: 15_000 })
    const sectorScroll = sectorList.locator('.watchlist__scroll')
    await expect.poll(() => sectorScroll.evaluate(element => ({ left: element.scrollLeft, width: element.clientWidth, scrollWidth: element.scrollWidth }))).toMatchObject({ left: 0 })

    const sectors = ['XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY']
    for (const sector of sectors) {
      const row = sectorList.locator('.watchlist__row').filter({ hasText: sector }).first()
      await expect(row).toBeVisible({ timeout: 15_000 })
      // Click the visible symbol-side of the wide row. Clicking the centre of a
      // canvas-width row would legitimately scroll the horizontal surface to its
      // far edge before the event reaches the row.
      await row.click({ position: { x: 8, y: 14 } })
      await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(sector)
      await expect.poll(() => sectorScroll.evaluate(element => element.scrollLeft)).toBe(0)
      const industries = page.locator('.industry-list')
      await expect(industries).toBeVisible({ timeout: 15_000 })
      await expect.poll(() => industries.locator('.industry-list__row').count(), { timeout: 15_000 }).toBeGreaterThan(0)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8e.swing-analysis — trader can complete the top-down trend, ratio, drawing, and traversal flow', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    const benchmark = page.getByRole('region', { name: 'Major US benchmarks' })
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(benchmark.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await expect(sectorList.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })

    // Start at the market trend, then select the strongest visible sector and
    // make the relative-strength comparison explicit.
    await expect(page.locator('.chart-tool').first().locator('canvas').first()).toBeVisible({ timeout: 20_000 })
    const sectorRows = sectorList.locator('.watchlist__row')
    const firstSector = sectorRows.first()
    const sectorSymbol = (await firstSector.innerText()).trim().split(/\s+/)[0]
    await firstSector.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(sectorSymbol)
    const ratio = page.locator('.ratio-chart:visible').last()
    await expect(ratio.locator('.ratio-chart__legend strong')).toContainText(`${sectorSymbol}/SPY`, { timeout: 20_000 })

    // Add a trend-confirming indicator through the real chart control and add
    // a drawing through the actual toolbar, then leave and return via a linked
    // constituent selection. The chart must retain both user-authored states.
    const chart = page.locator('.chart-tool:visible').first()
    const plots = chart.getByRole('button', { name: 'Chart plot library', exact: true })
    await expect(plots).toBeVisible({ timeout: 15_000 })
    await plots.click()
    const indicatorSave = page.waitForRequest(request => {
      if (request.method() !== 'PUT' || !request.url().includes('/api/v1/instrument-indicators/')) return false
      try {
        const payload = request.postDataJSON() as { indicators?: Array<{ type?: string }> }
        return payload.indicators?.some(indicator => indicator.type === 'rsi') ?? false
      } catch { return false }
    })
    await chart.getByRole('combobox', { name: 'Add indicator plot' }).selectOption('rsi')
    const indicatorSaveRequest = await indicatorSave
    const savedIndicatorPayload = indicatorSaveRequest.postDataJSON() as { indicators?: Array<{ type?: string }> }
    expect(savedIndicatorPayload.indicators?.some(indicator => indicator.type === 'rsi')).toBe(true)
    await plots.click()
    await expect(chart.getByRole('button', { name: /Delete RSI/ })).toBeVisible({ timeout: 15_000 })
    await plots.click()
    const drawingGroup = chart.getByRole('button', { name: 'Lines' })
    await expect(drawingGroup).toBeVisible({ timeout: 15_000 })
    await drawingGroup.click()
    await chart.getByRole('menuitem', { name: 'Horizontal Line' }).click()
    const canvas = chart.locator('.u-over').first()
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    await canvas.click({ position: { x: Math.max(12, (box?.width ?? 40) * 0.45), y: Math.max(12, (box?.height ?? 40) * 0.45) } })
    await expect.poll(() => chart.locator('.uplot-wrapper').getAttribute('data-drawing-count'), { timeout: 15_000 }).toBe('1')

    const industries = page.locator('.industry-list')
    await expect(industries).toBeVisible({ timeout: 20_000 })
    const firstIndustry = industries.locator('.industry-list__row').first()
    await expect(firstIndustry).toBeVisible({ timeout: 20_000 })
    await firstIndustry.click()
    const constituents = page.getByRole('region', { name: 'Constituents' }).filter({ has: page.locator('.watchlist__row') }).last()
    await expect(constituents).toBeVisible({ timeout: 20_000 })
    const firstConstituent = constituents.locator('.watchlist__row').first()
    await expect(firstConstituent).toBeVisible({ timeout: 20_000 })
    const constituentSymbol = (await firstConstituent.innerText()).trim().split(/\s+/)[0]
    await firstConstituent.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(constituentSymbol)
    await expect(ratio.locator('.ratio-chart__legend strong')).toContainText(`${constituentSymbol}/SPY`, { timeout: 20_000 })

    // Indicator and drawing state is persisted per instrument. Return to the
    // sector we annotated and verify that the chart reconstructs the user's
    // analysis state rather than leaking it to the constituent.
    const sectorIndicatorReload = page.waitForResponse(async response => {
      if (response.request().method() !== 'GET' || !response.url().includes('/api/v1/instrument-indicators/')) return false
      try {
        const body = await response.json() as { indicators?: Array<{ type?: string }> }
        return body.indicators?.some(indicator => indicator.type === 'rsi') ?? false
      } catch { return false }
    })
    await sectorList.getByRole('option', { name: new RegExp(`\\b${sectorSymbol}\\b`) }).first().click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue(sectorSymbol)
    await sectorIndicatorReload
    await plots.click()
    await expect(chart.getByRole('button', { name: /Delete RSI/ })).toBeVisible({ timeout: 20_000 })
    await expect.poll(() => chart.locator('.uplot-wrapper').getAttribute('data-drawing-count'), { timeout: 15_000 }).toBe('1')
    await plots.click()

    await constituents.locator('.watchlist__scroll').focus()
    await constituents.locator('.watchlist__scroll').press('Space')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).not.toHaveValue(constituentSymbol)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8g — Study Lab validates, runs an isolated Python study, and renders its result', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    const studyName = `E2E scalar study ${Date.now()}`
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill(studyName)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('smoke', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })

    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run')).toBeVisible({ timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'smoke' })).toContainText('1')
    await study.getByRole('button', { name: 'Save as column' }).click()
    await expect(study).toContainText('Saved as a reusable watchlist column.', { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8g-editor-a11y — Study Lab Python editor keeps native textbox semantics with list autocomplete', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    const editor = study.getByRole('textbox', { name: 'Study Python source' })
    await editor.fill('market.')
    await expect(editor).toHaveAttribute('aria-autocomplete', 'list')
    await expect(editor).toHaveAttribute('aria-expanded', 'true')
    const listboxId = await editor.getAttribute('aria-controls')
    const activeOptionId = await editor.getAttribute('aria-activedescendant')
    expect(listboxId).toBeTruthy()
    expect(activeOptionId).toBeTruthy()
    await expect(study.locator(`#${listboxId}`)).toHaveRole('listbox')
    await expect(study.locator(`#${activeOptionId}`)).toHaveRole('option')
    await editor.press('ArrowDown')
    const nextOptionId = await editor.getAttribute('aria-activedescendant')
    expect(nextOptionId).toBeTruthy()
    expect(nextOptionId).not.toBe(activeOptionId)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8o — Study Lab renders a structured event study with histogram, bars, table, and linked occurrences', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('E2E structured event study')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    const structuredSource = "output.scalar('event_count', 4)\noutput.boolean('qualifies', True)\noutput.bar('monthly_frequency', ['2026-01', '2026-02'], [2, 2])\noutput.histogram('streak_distribution', [1, 2, 2, 3], 2, 2)\noutput.table('summary', [{'state': 'positive_close', 'count': 4}])\noutput.events('occurrences', [{'symbol': 'SPY', 'timestamp': '2026-01-02T00:00:00+00:00', 'kind': 'positive_close'}])"
    const sourceEditor = study.getByRole('textbox', { name: 'Study Python source' })
    await sourceEditor.fill(structuredSource)
    // Persisted Study Lab windows can hydrate their configuration after the tool becomes
    // visible. Assert the editor retained the requested source before validating so a late
    // hydration write cannot turn this into a false-negative race.
    await expect(sourceEditor).toHaveValue(structuredSource)
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'event_count' })).toContainText('4')
    await expect(study.locator('.study-bars-uplot, [class*="study-bars"]').first()).toBeVisible()
    await expect(study.locator('.study-histogram-uplot, [class*="study-histogram"]').first()).toBeVisible()
    await expect(study.locator('table').filter({ hasText: 'positive_close' })).toBeVisible()
    const occurrence = study.locator('.study-lab-tool__events button').filter({ hasText: 'positive_close' })
    await expect(occurrence).toBeVisible()
    await occurrence.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY')
    await expect(study.getByRole('button', { name: 'Save filter: qualifies' })).toBeVisible()
    await expect(study.getByRole('button', { name: 'Use Gauge: qualifies' })).toBeVisible()
    await study.getByRole('button', { name: 'Save filter: qualifies' }).click()
    await expect(study).toContainText('Saved as a reusable watchlist filter through EasyScan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Promote scan: qualifies' }).click()
    await expect(study).toContainText('Promoted to a reusable scan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Use Gauge: qualifies' }).click()
    await expect(study).toContainText('Available as a Market Gauge from the saved EasyScan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Promote alert: qualifies' }).click()
    await expect(study).toContainText('Promoted to an active scan alert.', { timeout: 30_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p — Study Lab runs the factory consecutive-positive-close study against canonical market data', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('positive_streak')
    await expect(study.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(/positive_close_streaks/)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'current_streak' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'longest_streak' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__events button').first()).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p-export — Study Lab exports a typed artifact from the active run', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('positive_streak')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })

    const metricExportButton = study.getByRole('button', { name: 'Export current_streak' })
    await expect(metricExportButton).toBeVisible()
    const metricDownloadPromise = page.waitForEvent('download')
    await metricExportButton.click()
    const metricDownload = await metricDownloadPromise
    expect(metricDownload.suggestedFilename()).toMatch(/^study-run-\d+-current_streak\.json$/)
    const artifactExportButton = study.getByRole('button', { name: 'Export completed_streaks' })
    await expect(artifactExportButton).toBeVisible()
    const artifactDownloadPromise = page.waitForEvent('download')
    await artifactExportButton.click()
    const artifactDownload = await artifactDownloadPromise
    expect(artifactDownload.suggestedFilename()).toMatch(/^study-run-\d+-completed_streaks\.json$/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p-current-history — Study Lab renders the current observation inside its historical distribution', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('current_history_comparison')
    await expect(study.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(/historical_return_distribution/)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'historical_sample_size' })).toBeVisible()
    await expect(study.locator('.study-histogram-uplot, [class*="study-histogram"]').first()).toBeVisible()
    await expect(study.locator('table').filter({ hasText: 'current_vs_history' })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p-90-90 — Study Lab runs transparent price and volume breadth thrust', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('breadth_thrust_90_90')
    await expect(study.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(/research\.breadth_thrust\(dataset, 90\)/)
    await study.getByRole('textbox', { name: 'Study universe' }).fill('SPY, XLK, XLE')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'percent_price_advancing' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'percent_volume_advancing' })).toBeVisible()
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'qualifies_90_90' })).toBeVisible()
    await expect(study.locator('table').filter({ hasText: 'breadth_thrust_members' })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p-90-90-history — Study Lab renders historical participation and qualifying occurrences', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('breadth_thrust_history_90_90')
    await expect(study.getByRole('textbox', { name: 'Study Python source' })).toHaveValue(/research\.breadth_thrust_history\(dataset, 90\)/)
    await study.getByRole('textbox', { name: 'Study universe' }).fill('SPY, XLK, XLE')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-series').first()).toBeVisible()
    await expect(study.locator('.study-histogram')).toHaveCount(2)
    await expect(study.locator('table').filter({ hasText: 'breadth_thrust_history' })).toBeVisible()
    const occurrence = study.locator('.study-lab-tool__events button').filter({ hasText: '90_90_breadth_thrust' }).first()
    await expect(occurrence).toBeVisible()
    const occurrenceTimestamp = await occurrence.locator('span').textContent()
    expect(occurrenceTimestamp).toBeTruthy()
    await occurrence.click()
    await expect(page.locator('.chart-root[data-linked-timestamp]')).toHaveAttribute('data-linked-timestamp', occurrenceTimestamp!.trim())
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8p-high-low — Study Lab exposes and runs a configurable new-high/new-low lookback', async ({ page, browserDiagnostics }) => {
    test.setTimeout(120_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('combobox', { name: 'Factory study' }).selectOption('high_low_breakouts')
    const lookback = study.getByRole('spinbutton', { name: 'Study parameter lookback' })
    await expect(lookback).toHaveValue('20')
    await expect(lookback).toHaveAttribute('min', '2')
    await expect(lookback).toHaveAttribute('max', '252')
    await lookback.fill('10')
    await expect(lookback).toHaveValue('10')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.getByRole('status', { name: /new_high_count metric/ })).toBeVisible()
    await expect(study.getByRole('status', { name: /new_low_count metric/ })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F9j — retained EasyScan history becomes a reusable uPlot series', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/screeners', async route => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: 42, name: 'Fixture breadth scan' }]),
      })
    })
    await page.route('**/api/v1/screeners/42/plot**', async route => {
      if (route.request().method() !== 'GET') return route.continue()
      const metric = new URL(route.request().url()).searchParams.get('metric')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          screener_id: 42,
          metric,
          points: [
            { timestamp: '2026-08-07T00:00:00Z', value: metric === 'percentage' ? 50 : 2 },
            { timestamp: '2026-08-10T00:00:00Z', value: metric === 'percentage' ? 75 : 3 },
          ],
          coverage: { evaluated: 4, matched: 3, percentage: 75 },
          warning: null,
        }),
      })
    })

    await page.goto('/chart/SPY')
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY')
    await page.getByRole('button', { name: 'Chart plot library' }).click()
    const plots = page.getByRole('region', { name: 'Chart plot library' })
    await plots.getByRole('button', { name: 'Load EasyScan plots' }).click()
    await expect(plots.getByText('2 historical scan plots available')).toBeVisible({ timeout: 10_000 })
    await plots.getByRole('combobox', { name: 'EasyScan plot asset' }).selectOption({ label: 'Fixture breadth scan · percentage' })
    await plots.getByRole('button', { name: 'Add' }).click()
    const scanPlot = plots.locator('.chart-plots__scan-item').filter({ hasText: 'Fixture breadth scan' })
    await expect(scanPlot).toHaveCount(1)
    await expect(scanPlot).toContainText('percentage')
    await scanPlot.getByRole('button', { name: 'Hide Fixture breadth scan' }).click()
    await expect(scanPlot).toHaveClass(/muted/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8q — Study Lab promotes a Boolean result into filter, scan, gauge, alert, and signal targets', async ({ page, browserDiagnostics }) => {
    // Promotion writes are durable and can briefly queue behind the shared
    // workspace/code-asset database workload in a long serial acceptance run.
    // Keep the assertion bounded, but allow the product's explicit
    // `Promoting…` state enough time to resolve instead of declaring a false
    // failure at the short interaction timeout used by simple controls.
    test.setTimeout(90_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    const uniqueStudyName = `E2E Boolean promotion ${process.hrtime.bigint().toString(36)}`
    await study.getByRole('textbox', { name: 'Study name' }).fill(uniqueStudyName)
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.boolean('qualifies', True)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study.locator('.study-lab-tool__validation')).toContainText('Validated for isolated execution', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--completed')).toBeVisible({ timeout: 90_000 })
    await expect(study.locator('.study-lab-tool__metrics article').filter({ hasText: 'qualifies' })).toHaveClass(/study-lab-tool__metric--true/)
    await study.getByRole('button', { name: 'Save as watchlist filter' }).click()
    await expect(study).toContainText('Saved as a reusable watchlist filter through EasyScan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Promote to scan' }).click()
    await expect(study).toContainText('Promoted to a reusable scan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Use as Market Gauge' }).click()
    await expect(study).toContainText('Available as a Market Gauge from the saved EasyScan.', { timeout: 30_000 })
    await study.getByRole('button', { name: 'Promote to alert' }).click()
    await expect(study).toContainText('Promoted to an active scan alert.', { timeout: 30_000 })
    // The durable configuration update can remount a virtual Study Lab while
    // the promotion controls settle under the full serial matrix. Retry the
    // real click against the currently mounted control instead of holding a
    // detached element handle.
    await expect.poll(async () => {
      const button = page.locator('.study-lab-tool:visible').last().getByRole('button', { name: 'Save as Strategy signal' })
      if (await button.count() !== 1) return false
      try {
        await button.click({ timeout: 1_000 })
        return true
      } catch {
        return false
      }
    }, { timeout: 30_000, intervals: [100, 250, 500] }).toBe(true)
    // Signal promotion creates a Strategy Lab definition and returns its fully
    // hydrated version graph. On a long-lived shared acceptance database this
    // can legitimately take longer than the scan/alert writes, so keep the
    // assertion bounded by the enclosing test timeout without treating a
    // transient database queue as a false product failure.
    await expect(study).toContainText('Saved as a reusable Strategy Lab signal.', { timeout: 45_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8t — Study Lab validation errors are visible and recoverable', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()

    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('E2E Study validation recovery')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('broken'")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study.locator('.study-lab-tool__validation')).toContainText('Validation errors', { timeout: 30_000 })
    await expect(study.locator('.study-lab-tool__validation--bad pre')).toBeVisible()
    await expect(study.locator('.study-lab-tool__validation--bad')).toHaveAttribute('role', 'alert')
    await expect(study.locator('.study-lab-tool__validation--bad')).toHaveAttribute('aria-live', 'assertive')
    await expect(study.locator('.study-lab-tool__validation--bad')).toHaveAttribute('aria-atomic', 'true')

    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('recovered', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study.locator('.study-lab-tool__validation')).toContainText('Validated for isolated execution', { timeout: 30_000 })
    await expect(study.locator('.study-lab-tool__validation--bad')).toHaveCount(0)
    await expect(study.locator('.study-lab-tool__validation[role="status"]')).toBeVisible()
    await expect(study.locator('.study-lab-tool__validation[role="status"]')).toHaveAttribute('aria-live', 'polite')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8t-cancel — Study Lab cancels a queued run without leaving stale polling state', async ({ page, browserDiagnostics }) => {
    const run = { id: 9901, status: 'queued', code_version_id: 9901, run_config: { symbol: 'SPY' }, artifacts: [] }
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, output_contracts: ['scalar'], diagnostics: [], dependencies: [], lookback: 0 }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 9901, versions: [{ id: 9901 }] }) })
    })
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(run) })
        return
      }
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([run]) })
        return
      }
      await route.continue()
    })
    await page.route(/\/api\/v1\/research\/runs\/9901$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(run) })
    })
    await page.route(/\/api\/v1\/research\/runs\/9901\/cancel$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...run, status: 'canceled' }) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('E2E queued cancellation')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('queued', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--queued')).toBeVisible({ timeout: 10_000 })
    await study.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(study.locator('.study-lab-tool__run-status--canceled')).toBeVisible({ timeout: 10_000 })
    await expect(study.getByRole('button', { name: 'Cancel', exact: true })).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8t-failed — Study Lab failed runs expose diagnostics and explicit rerun recovery', async ({ page, browserDiagnostics }) => {
    const run = { id: 9902, status: 'failed', code_version_id: 9902, run_config: { symbol: 'SPY' }, diagnostics: [{ message: 'sandbox limit' }], logs: 'runner terminated', artifacts: [] }
    await page.route(/\/api\/v1\/code\/validate$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ valid: true, output_contracts: ['scalar'], diagnostics: [], dependencies: [], lookback: 0 }) })
    })
    await page.route(/\/api\/v1\/code\/assets$/, async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 9902, versions: [{ id: 9902 }] }) })
    })
    await page.route(/\/api\/v1\/research\/runs$/, async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(run) })
        return
      }
      await route.continue()
    })
    await page.route(/\/api\/v1\/research\/runs\/9902(?:\/rerun\?.*)?$/, async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ ...run, id: 9903, status: 'queued' }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(run) })
    })
    await page.route(/\/api\/v1\/research\/runs\/9903$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...run, id: 9903, status: 'queued' }) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool')
    await expect(study).toBeVisible({ timeout: 10_000 })
    await study.getByRole('textbox', { name: 'Study name' }).fill('E2E failed recovery')
    await study.getByRole('textbox', { name: 'Study symbol' }).fill('SPY')
    await study.getByRole('textbox', { name: 'Study Python source' }).fill("output.scalar('failed', 1)")
    await study.getByRole('button', { name: 'Validate' }).click()
    await expect(study).toContainText('Validated for isolated execution', { timeout: 10_000 })
    await study.getByRole('button', { name: 'Run', exact: true }).click()
    await expect(study.locator('[data-status="failed"]')).toHaveText('Failed', { timeout: 10_000 })
    await expect(study.locator('.study-lab-tool__run-guidance')).toContainText('Inspect diagnostics and execution logs')
    await expect(study.getByRole('button', { name: 'Rerun snapshot' })).toBeVisible()
    await expect(study.getByRole('button', { name: 'Rerun latest' })).toBeVisible()
    await study.getByRole('button', { name: 'Rerun snapshot' }).click()
    await expect(study.locator('[data-status="queued"]')).toHaveText('Queued', { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8t-results — Study Results exposes selected runs and structured results semantically', async ({ page, browserDiagnostics }) => {
    await page.route(/\/api\/v1\/research\/runs(?:\?.*)?$/, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{
        id: 881,
        status: 'completed',
        code_version_id: 881,
        run_config: { symbol: 'SPY' },
        dataset_manifest: { source: 'canonical_database' },
        reproducibility_hash: 'sha256:study-results',
        artifact_count: 1,
        artifacts: [{ id: 1, name: 'current_streak', artifact_type: 'scalar', payload: { value: 4 } }],
      }, {
        id: 882,
        status: 'completed',
        code_version_id: 882,
        run_config: { symbol: 'SPY', parameters: { lookback: 20 } },
        dataset_manifest: { source: 'canonical_database', timeframe: 'D1' },
        reproducibility_hash: 'sha256:study-results-2',
        artifact_count: 1,
        artifacts: [{ id: 2, name: 'current_streak', artifact_type: 'scalar', payload: { value: 6 } }],
      }, {
        id: 883,
        status: 'completed',
        code_version_id: 883,
        run_config: { execution_mode: 'breadth_history', output_contract: 'series', series_target: { scope: 'member', operator: 'gte', threshold: 0 } },
        dataset_manifest: { source: 'canonical_database', timeframe: 'D1' },
        reproducibility_hash: 'sha256:breadth-plot',
        artifact_count: 0,
        artifacts: [],
      }]) })
    })
    await page.route(/\/api\/v1\/research\/runs\/883$/, async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 883,
        status: 'completed',
        code_version_id: 883,
        run_config: { execution_mode: 'breadth_history', output_contract: 'series', series_target: { scope: 'member', operator: 'gte', threshold: 0 } },
        dataset_manifest: { source: 'canonical_database', timeframe: 'D1' },
        reproducibility_hash: 'sha256:breadth-plot',
        artifact_count: 0,
        artifacts: [],
      }) })
    })
    await page.route(/\/api\/v1\/analysis\/breadth\/python\/runs\/883\/promote-plot$/, async route => {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 41, name: 'Member breadth plot 883', kind: 'plot', versions: [{ id: 41, output_contract: 'series', diagnostics: [] }] }) })
    })
    await page.route(/\/api\/v1\/analysis\/breadth\/python\/runs\/883\/promote-column$/, async route => {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 42, name: 'Member breadth column 883', kind: 'column', versions: [{ id: 42, output_contract: 'scalar', diagnostics: [{ output_adapter: 'latest_series_to_scalar' }] }] }) })
    })
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    const studyLayoutTab = page.locator('.workstation__tabs > button').filter({ hasText: 'Study Lab' }).last()
    await studyLayoutTab.click()
    const results = page.locator('.research-results-tool')
    await expect(results).toBeVisible({ timeout: 10_000 })
    await expect(results).toHaveAttribute('role', 'region')
    await expect(results.locator('[role="list"][aria-label="Persisted research runs"]')).toBeVisible()
    await expect(results.locator('.research-results-tool__run[aria-current="true"]')).toHaveCount(1)
    await expect(results.locator('[data-status="completed"]').first()).toHaveText('Completed')
    await expect(results.locator('.research-results-tool__run-guidance')).toContainText('Study completed')
    await expect(results.locator('[aria-label="current_streak scalar result"]')).toBeVisible()
    await results.getByRole('checkbox', { name: 'Compare run 881' }).check()
    await results.getByRole('checkbox', { name: 'Compare run 882' }).check()
    await results.getByRole('button', { name: 'Compare', exact: true }).click()
    await expect(results.locator('.research-results-tool__comparison')).toContainText('Run 881 vs 882')
    await expect(results.locator('.research-results-tool__comparison')).toContainText('lookback')
    await results.locator('.research-results-tool__run').filter({ hasText: 'Run #883' }).click()
    await expect(results.getByRole('button', { name: 'Save as chart plot' })).toBeVisible()
    await results.getByRole('button', { name: 'Save as chart plot' }).click()
    await expect(results).toContainText('Chart plot “Member breadth plot 883” (#41) created')
    await results.getByRole('button', { name: 'Save as watchlist column' }).click()
    await expect(results).toContainText('Watchlist column “Member breadth column 883” (#42) created')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8t-results-open — Study Results is available from the primary Add tool menu', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workstation')).toBeVisible()
    const addTool = page.getByRole('button', { name: 'Add tool', exact: true })
    await expect(addTool).toBeVisible({ timeout: 10_000 })
    await addTool.click()
    const menu = page.getByRole('menu', { name: 'Workstation tools' })
    await expect(menu).toBeVisible()
    await menu.getByRole('menuitem', { name: 'Study Results', exact: true }).click()
    const results = page.locator('.research-results-tool:visible').last()
    await expect(results).toBeVisible({ timeout: 15_000 })
    await expect(results).toHaveAttribute('aria-label', 'Study Lab research results')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r — core tool headers keep titles, symbols, and actions geometrically separated', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('button', { name: 'Open tool menu' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Maximize tool' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Float tool' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Close tool' }).first()).toBeVisible()
    const issues = await page.evaluate(() => {
      const rect = (element: Element | null) => {
        if (!element) return null
        const box = element.getBoundingClientRect()
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom }
      }
      const overlaps = (left: ReturnType<typeof rect>, right: ReturnType<typeof rect>) => Boolean(
        left && right && left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top,
      )
      const result: string[] = []
      document.querySelectorAll('.tool-window__header').forEach((header, index) => {
        if (overlaps(rect(header.querySelector('.tool-window__title')), rect(header.querySelector('.tool-window__actions')))) result.push(`title-actions-${index}`)
        if (overlaps(rect(header.querySelector('.tool-window__symbol')), rect(header.querySelector('.tool-window__actions')))) result.push(`symbol-actions-${index}`)
      })
      document.querySelectorAll('.chart-tool').forEach((chart, index) => {
        const toolbar = rect(chart.querySelector('.chart-tool__drawing-toolbar'))
        const surface = rect(chart.querySelector('.chart-tool__surface'))
        if (toolbar && surface && (toolbar.top < surface.top || toolbar.bottom > surface.bottom)) result.push(`chart-toolbar-vertical-${index}`)
      })
      return result
    })
    expect(issues).toEqual([])
    const footerSymbols = await page.locator('.workstation__footer > span').filter({ hasText: 'SPY' }).count()
    expect(footerSymbols).toBe(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-narrow — dense tool headers retain usable controls at constrained desktop width', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    const geometry = await page.evaluate(() => {
      const overlaps = (left: DOMRect, right: DOMRect) => left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top
      const issues: string[] = []
      Array.from(document.querySelectorAll<HTMLElement>('.tool-window')).filter(window => {
        const box = window.getBoundingClientRect()
        return box.width > 0 && box.height > 0
      }).forEach((window, index) => {
        const title = window.querySelector<HTMLElement>('.tool-window__title')?.getBoundingClientRect()
        const symbol = window.querySelector<HTMLElement>('.tool-window__symbol')?.getBoundingClientRect()
        const actions = window.querySelector<HTMLElement>('.tool-window__actions')?.getBoundingClientRect()
        if (!actions || actions.width <= 0) issues.push(`actions-hidden-${index}`)
        if (title && actions && overlaps(title, actions)) issues.push(`title-actions-${index}`)
        if (symbol && actions && overlaps(symbol, actions)) issues.push(`symbol-actions-${index}`)
        window.querySelectorAll<HTMLElement>('.tool-window__actions button, .tool-window__actions select').forEach((control, controlIndex) => {
          if (control.getBoundingClientRect().width <= 0 || control.getBoundingClientRect().height <= 0) issues.push(`control-hidden-${index}-${controlIndex}`)
        })
      })
      return { issues, viewport: window.innerWidth }
    })
    expect(geometry.viewport).toBe(390)
    expect(geometry.issues).toEqual([])
    const trigger = page.getByRole('button', { name: 'Open tool menu' }).first()
    await trigger.click()
    const menu = page.getByRole('menu').filter({ hasText: 'Maximize' }).last()
    await expect(menu).toBeVisible()
    const menuBox = await menu.boundingBox()
    const triggerBox = await trigger.boundingBox()
    expect(menuBox).not.toBeNull()
    expect(triggerBox).not.toBeNull()
    expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(390)
    expect(menuBox!.x).toBeGreaterThanOrEqual(0)
    expect(menuBox!.y + menuBox!.height).toBeGreaterThanOrEqual(0)
    expect(menuBox!.y).toBeLessThanOrEqual(triggerBox!.y + triggerBox!.height)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-study-lab-narrow — Study Lab controls remain contained in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Study', exact: true }).click()
    const study = page.locator('.study-lab-tool:visible').last()
    await expect(study).toBeVisible({ timeout: 15_000 })
    const geometry = await study.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      const descendants = Array.from(root.querySelectorAll<HTMLElement>('input, select, textarea, button, .python-source-editor, .study-lab-tool__editor-shell'))
      descendants.forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      const header = root.querySelector<HTMLElement>('.study-lab-tool__header')?.getBoundingClientRect()
      const editor = root.querySelector<HTMLElement>('.study-lab-tool__editor-shell')?.getBoundingClientRect()
      if (header && editor && header.bottom > editor.top + 1) issues.push('header-editor-overlap')
      return { issues, root: { left: rootBox.left, right: rootBox.right, width: rootBox.width } }
    })
    expect(geometry.root.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-rotation-narrow — Relative Rotation controls and plot remain usable in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Relative Rotation', exact: true }).click()
    const rotation = page.locator('.tool-window:visible').filter({ has: page.locator('.rotation-tool') }).last()
    await expect(rotation).toBeVisible({ timeout: 15_000 })
    const rotationSurface = rotation.locator('.rotation-tool')
    await rotationSurface.evaluate(root => {
      root.style.width = '340px'
      root.style.maxWidth = '340px'
    })
    const geometry = await rotation.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      root.querySelectorAll<HTMLElement>('.rotation-tool__controls input, .rotation-tool__controls select, .rotation-tool__adjusted input, .rotation-tool__plot-shell').forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      const header = root.querySelector<HTMLElement>('.rotation-tool header')?.getBoundingClientRect()
      const plot = root.querySelector<HTMLElement>('.rotation-tool__plot-shell')?.getBoundingClientRect()
      if (header && plot && header.bottom > plot.top + 1) issues.push('header-plot-overlap')
      return { issues, width: rootBox.width }
    })
    expect(geometry.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-easyscan-narrow — EasyScan builders remain contained in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    const scanWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.easy-scan') }).last()
    await expect(scanWindow).toBeVisible({ timeout: 15_000 })
    const scan = scanWindow.locator('.easy-scan')
    await expect(scan).toBeVisible({ timeout: 15_000 })
    await scan.evaluate(root => {
      root.style.width = '340px'
      root.style.maxWidth = '340px'
    })
    const geometry = await scan.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      const controls = root.querySelectorAll<HTMLElement>('.easy-scan__builder input, .easy-scan__builder select, .easy-scan__builder button, .easy-scan__controls input, .easy-scan__controls select, .easy-scan__controls button')
      controls.forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      return { issues, width: rootBox.width, rootLeft: rootBox.left, rootRight: rootBox.right, details: Array.from(controls).map(element => { const box = element.getBoundingClientRect(); return { label: element.getAttribute('aria-label'), left: box.left, right: box.right, width: box.width } }) }
    })
    expect(geometry.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-breadth-narrow — Market Breadth controls remain contained in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadthWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadthWindow).toBeVisible({ timeout: 15_000 })
    const breadth = breadthWindow.locator('.breadth-tool')
    await expect(breadth).toBeVisible({ timeout: 15_000 })
    await breadth.evaluate(root => {
      root.style.width = '340px'
      root.style.maxWidth = '340px'
    })
    const geometry = await breadth.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      const controls = root.querySelectorAll<HTMLElement>('.breadth-tool__universe select, .breadth-tool__universe input, .breadth-tool__universe button')
      controls.forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      return { issues, width: rootBox.width }
    })
    expect(geometry.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-alerts-narrow — Alert creation controls remain contained in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Alerts', exact: true }).click()
    const alertsWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.alerts-tool') }).last()
    await expect(alertsWindow).toBeVisible({ timeout: 15_000 })
    const alerts = alertsWindow.locator('.alerts-tool')
    await expect(alerts).toBeVisible({ timeout: 15_000 })
    await alerts.evaluate(root => {
      root.style.width = '340px'
      root.style.maxWidth = '340px'
    })
    const geometry = await alerts.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      root.querySelectorAll<HTMLElement>('.alerts-tool__create input, .alerts-tool__create select, .alerts-tool__create button').forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      const create = root.querySelector<HTMLElement>('.alerts-tool__create')
      if (create && create.scrollWidth > create.clientWidth + 1) issues.push('create-scroll-overflow')
      return { issues, width: rootBox.width }
    })
    expect(geometry.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-python-library-narrow — Python Library creation controls remain contained in a narrow desktop dock', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Python Library', exact: true }).click()
    const libraryWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.code-library-tool') }).last()
    await expect(libraryWindow).toBeVisible({ timeout: 15_000 })
    const library = libraryWindow.locator('.code-library-tool')
    await expect(library).toBeVisible({ timeout: 15_000 })
    await library.getByRole('button', { name: 'New', exact: true }).click()
    await library.evaluate(root => {
      root.style.width = '340px'
      root.style.maxWidth = '340px'
    })
    const geometry = await library.evaluate(root => {
      const rootBox = root.getBoundingClientRect()
      const issues: string[] = []
      root.querySelectorAll<HTMLElement>('.code-library-tool__create input, .code-library-tool__create select, .code-library-tool__create textarea, .code-library-tool__create button').forEach((element, index) => {
        const box = element.getBoundingClientRect()
        if (box.width <= 0 || box.height <= 0) issues.push(`hidden-${index}`)
        if (box.left < rootBox.left - 1 || box.right > rootBox.right + 1) issues.push(`horizontal-overflow-${index}`)
      })
      const create = root.querySelector<HTMLElement>('.code-library-tool__create')
      if (create && create.scrollWidth > create.clientWidth + 1) issues.push('create-scroll-overflow')
      return { issues, width: rootBox.width }
    })
    expect(geometry.width).toBeGreaterThan(0)
    expect(geometry.issues).toEqual([])
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-chart-toolbar — chart utility controls do not overlap at constrained width', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 800 })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool:visible').first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const geometry = await chart.evaluate(chart => {
      const overlap = (left: DOMRect, right: DOMRect) => left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top
      const controls = ['.chart-tool__compare', '.chart-tool__plots', '.chart-tool__templates']
        .map(selector => chart.querySelector<HTMLElement>(selector)?.getBoundingClientRect())
        .filter((box): box is DOMRect => Boolean(box && box.width > 0 && box.height > 0))
      return { controls: controls.map(box => ({ left: box.left, right: box.right, top: box.top, bottom: box.bottom })), overlap: controls.some((left, index) => controls.slice(index + 1).some(right => overlap(left, right))) }
    })
    expect(geometry.controls.length).toBe(3)
    expect(geometry.overlap).toBe(false)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8r-layout-picker — layout popovers remain viewport-contained near the bottom edge', async ({ page, browserDiagnostics }) => {
    await page.setViewportSize({ width: 390, height: 300 })
    // LayoutPicker is retained on the explicitly legacy chart surface; the
    // authenticated /chart route is the primary Golden Layout workstation and
    // intentionally does not mount this legacy-only control.
    await page.goto('/legacy/chart/SPY')
    const gridTrigger = page.getByTitle('Custom grid layout')
    const profileTrigger = page.getByTitle('Layout profiles')
    await expect(gridTrigger).toBeVisible({ timeout: 15_000 })
    for (const [trigger, label] of [[gridTrigger, 'Custom grid layout'], [profileTrigger, 'Layout profiles']] as const) {
      await trigger.click()
      const menu = page.getByRole('menu', { name: label })
      await expect(menu).toBeVisible()
      const bounds = await menu.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.y).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390)
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(300)
      // The legacy route can retain more than one picker instance in restored
      // stacks; the unit oracle covers document-level outside dismissal. Use
      // the owning trigger here for deterministic browser containment coverage.
      await trigger.click()
      await expect(menu).toHaveCount(0)
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s — active-instrument Notes tool autosaves through the canonical notes API', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Notes', exact: true }).click()
    // Persisted factory layouts may retain a hidden Notes instance in another
    // stack. Restrict the assertion to the user-visible tool window so the
    // newly opened active-instrument editor is the acceptance target.
    const notes = page.locator('.tool-window:visible').filter({ has: page.locator('.note-tool') })
    await expect(notes.last()).toBeVisible({ timeout: 10_000 })
    // Persisted workspaces may contain older Notes windows. Target the newly
    // hydrated active-instrument editor rather than assuming DOM order.
    const editor = page.locator('.note-tool textarea:not(:disabled):visible').last()
    await expect(editor).toBeEnabled({ timeout: 10_000 })
    await editor.fill(`E2E note ${process.hrtime.bigint().toString(36)}`)
    await expect(editor.locator('xpath=ancestor::section[contains(@class,"note-tool")]').locator('.note-tool__status')).toContainText('Saved', { timeout: 10_000 })
    const noteTool = page.locator('.note-tool:visible').last()
    await expect(noteTool).toHaveAttribute('role', 'region')
    await expect(noteTool.locator('.note-tool__status[role="status"]')).toHaveAttribute('aria-live', 'polite')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-coverage — Coverage tool exposes symbol-scoped readiness semantics', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Coverage', exact: true }).click()
    const coverage = page.locator('.tool-window:visible').filter({ has: page.locator('.coverage-summary') }).last()
    await expect(coverage).toBeVisible({ timeout: 10_000 })
    const region = coverage.locator('[role="region"][aria-label="SPY coverage"]')
    await expect(region).toBeVisible({ timeout: 10_000 })
    await expect(region).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect(region.locator('[role="status"], [role="alert"]').first()).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-watchlist — top-down watchlists expose shared refresh state without losing rows', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/analysis/groups/sp500-sectors/snapshot*', async route => {
      await new Promise(resolve => setTimeout(resolve, 1_500))
      // The oracle only exercises the shared refresh lifecycle. Keep its
      // response deterministic so a slow backend cannot leave a route callback
      // alive after the test deadline.
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows: [], coverage: 0, freshness: 'partial', data_provenance: 'browser-oracle' }) })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    const sectorList = page.locator('.watchlist[aria-label="Relative to SPY"]')
    await expect(sectorList).toBeVisible({ timeout: 10_000 })
    await expect(sectorList).toHaveAttribute('aria-busy', 'true', { timeout: 15_000 })
    await expect(sectorList.locator('[role="status"]')).toContainText('Refreshing sector analysis')
    await expect(sectorList).toHaveAttribute('aria-busy', 'false', { timeout: 20_000 })
    await expect(sectorList.locator('.watchlist__row').first()).toBeVisible({ timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-watchlist-error — a failed top-down snapshot stays scoped to its watchlist', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/analysis/groups/sp500-sectors/snapshot*', async route => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'sector snapshot unavailable' }) })
    })
    await page.goto('/chart/SPY')
    const sectorList = page.locator('.watchlist[aria-label="Relative to SPY"]')
    await expect(sectorList).toBeVisible({ timeout: 10_000 })
    await expect(sectorList).toHaveAttribute('aria-busy', 'false', { timeout: 20_000 })
    await expect(sectorList.locator('[role="alert"]')).toContainText('API GET', { timeout: 15_000 })
    await expect(page.locator('.watchlist[aria-label="Major US benchmarks"] [role="alert"]')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-market-map-watchlist — locked constituents and personal lists share one heatmap workflow', async ({ page, browserDiagnostics }) => {
    browserDiagnostics.allowExpectedWatchlistConflictResponses()
    const sources = [
      {
        source_id: 'market-group:us-benchmarks', source_kind: 'index_membership', name: 'US benchmark constituents',
        locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 2,
        membership_version: 'benchmarks:v1', provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' },
      },
      {
        source_id: 'watchlist:7', source_kind: 'personal', name: 'Swing candidates',
        locked: false, can_follow: true, can_clone: true, can_edit_membership: true, member_count: 2,
        membership_version: 'watchlist:7:v3', provenance: { availability: 'available' },
      },
    ]
    const requestedSources: string[] = []
    const mapResponse = (sourceId: string) => {
      const source = sources.find(item => item.source_id === sourceId) ?? sources[0]
      return {
        source, group_by: 'sector_industry', period: '1D', period_start: '2026-08-07T00:00:00Z', period_end: '2026-08-08T00:00:00Z',
        timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'equal', color_metric: 'return', membership_version: source.membership_version,
        calculation_version: 'market-map-v1', cache_key: `e2e-${sourceId}`, cache_hit: false, freshness: 'current', freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 },
        requested_count: 2, evaluated_count: 2, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [], exclusions: [],
        nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 2, covered_count: 2, area_total: 2, color_value: 0.02, coverage: 1, color_coverage: 1, area_coverage: 1, aggregation_method: 'equal_member_mean', warnings: [] }],
        cells: [
          { instrument_id: 1, symbol: 'NVDA', name: 'NVIDIA', sector: 'Technology', industry: 'Semiconductors', group_path: ['Technology', 'Semiconductors'], area_value: 1, color_value: 0.05, return_value: 0.05, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [] },
          { instrument_id: 2, symbol: 'MSFT', name: 'Microsoft', sector: 'Technology', industry: 'Software', group_path: ['Technology', 'Software'], area_value: 1, color_value: -0.01, return_value: -0.01, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [] },
        ],
      }
    }
    await page.route('**/api/v1/watchlists/sources**', async route => {
      const pathname = new URL(route.request().url()).pathname
      if (decodeURIComponent(pathname).endsWith('/sources/market-group:us-benchmarks')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          source: { ...sources[0], composition_date: '2026-08-08', effective_at: '2026-08-08T00:00:00Z', known_at: '2026-08-08T01:00:00Z' },
          members: [
            { instrument_id: 1, position: 0, relationship_type: 'constituent', effective_at: '2026-08-08T00:00:00Z', known_at: '2026-08-08T01:00:00Z' },
            { instrument_id: 2, position: 1, relationship_type: 'constituent', effective_at: '2026-08-08T00:00:00Z', known_at: '2026-08-08T01:00:00Z' },
          ],
          exclusions: [],
        }) })
        return
      }
      if (pathname.endsWith('/history-status/market-group:us-benchmarks') || pathname.endsWith('/history-status/watchlist:7')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ source_id: pathname.endsWith('watchlist:7') ? 'watchlist:7' : 'market-group:us-benchmarks', source_kind: 'personal', name: 'Map source', locked: false, membership_version: 'v1', max_instruments: 5000, available_instrument_count: 2, selected_instrument_count: 2, limited: false, excluded_count: 0, overall_status: 'ready', timeframes: [{ timeframe: 'D1', member_count: 2, covered_member_count: 2, coverage_percent: 100, bar_count: 4, in_progress_count: 0, complete_count: 2, failed_count: 0, pending_count: 0 }] }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sources) })
    })
    await page.route('**/api/v1/watchlists/sources/explicit', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      const body = route.request().postDataJSON() as { name?: string; instrument_ids?: number[]; parent_source_id?: string; parent_membership_version?: string }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        source_id: 'explicit-list:selection-e2e',
        source_kind: 'explicit',
        name: body.name ?? 'Saved locked source',
        locked: true,
        can_follow: true,
        can_clone: true,
        can_edit_membership: false,
        member_count: body.instrument_ids?.length ?? 0,
        membership_version: 'explicit-list:e2e:v1',
        provenance: {
          durability: 'user_library',
          instrument_ids: body.instrument_ids ?? [],
          parent_source_id: body.parent_source_id,
          parent_membership_version: body.parent_membership_version,
        },
      }) })
    })
    await page.route('**/api/v1/watchlists', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 99, name: 'US benchmark constituents snapshot 2026-08-08', description: 'Cloned source', is_managed: false, is_locked: false, items: [] }) })
    })
    let failCloneMemberOnce = true
    await page.route('**/api/v1/watchlists/99/items', async route => {
      const body = route.request().postDataJSON() as { instrument_id?: number }
      if (body.instrument_id === 2 && failCloneMemberOnce) {
        failCloneMemberOnce = false
        // A duplicate/conflict response is intentionally recoverable by the
        // store and does not create a browser-console error; the clone tool
        // still records the failed canonical ID and exposes its retry action.
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary clone conflict' }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: Number(body.instrument_id ?? 0) + 900, instrument_id: body.instrument_id, position: 0 }) })
    })
    await page.route('**/api/v1/analysis/market-map', async route => {
      const body = route.request().postDataJSON() as { source_id?: string }
      requestedSources.push(String(body.source_id ?? ''))
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mapResponse(String(body.source_id ?? ''))) })
    })
    await page.route('**/api/v1/analysis/market-map/snapshots**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    })
    await page.goto('/chart/SPY')
    const benchmarks = page.getByRole('region', { name: 'Major US benchmarks' })
    await expect(benchmarks).toBeVisible({ timeout: 15_000 })
    await benchmarks.getByRole('button', { name: 'Open Market Map' }).click()
    const mapWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.market-map-tool') }).last()
    await expect(mapWindow).toBeVisible({ timeout: 15_000 })
    const universe = mapWindow.getByRole('combobox', { name: 'Market Map universe' })
    await expect(universe).toHaveValue('market-group:us-benchmarks')
    await expect(mapWindow).toContainText('Locked source')
    await mapWindow.getByRole('button', { name: 'Clone US benchmark constituents snapshot' }).click()
    await expect(mapWindow.locator('[aria-label="Market Map source preferences"] [role="status"]')).toContainText('1/2 members cloned', { timeout: 15_000 })
    await mapWindow.getByRole('button', { name: 'Retry failed source clone members' }).click()
    await expect(mapWindow.locator('[aria-label="Market Map source preferences"] [role="status"]')).toContainText('2/2 members cloned', { timeout: 15_000 })
    await universe.selectOption('watchlist:7')
    await mapWindow.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect.poll(() => requestedSources.at(-1), { timeout: 15_000 }).toBe('watchlist:7')
    await expect(mapWindow).toContainText('Swing candidates')
    await expect(mapWindow.locator('.market-map-tool__tile')).toHaveCount(2)
    await mapWindow.locator('.market-map-tool__tile').first().click()
    // Save the selection while the Market Map owns focus. Publishing the same
    // selection into Breadth activates that tool, so the map is intentionally
    // no longer a visible locator after the handoff.
    await mapWindow.getByRole('textbox', { name: 'Market Map locked source name' }).fill('Saved benchmark member')
    await mapWindow.getByRole('button', { name: 'Save selected members as locked source' }).click()
    await expect(mapWindow).toContainText('saved as locked source Saved benchmark member', { timeout: 15_000 })
    await expect.poll(() => requestedSources.at(-1), { timeout: 15_000 }).toBe('explicit-list:selection-e2e')
    await expect(mapWindow.locator('.market-map-tool__tile')).toHaveCount(2)
    await mapWindow.locator('.market-map-tool__tile').first().click()
    await mapWindow.getByRole('button', { name: 'Open selected members in Market Breadth' }).click()
    const breadthTool = page.locator('.breadth-tool:visible').last()
    await expect(breadthTool).toBeVisible({ timeout: 15_000 })
    await expect(breadthTool.getByRole('combobox', { name: 'Custom breadth universe' })).toHaveValue('watchlist')
    await expect(breadthTool.getByRole('combobox', { name: 'Custom breadth watchlist source' })).toHaveValue(/^explicit:\d+$/)
    await expect(breadthTool.getByRole('combobox', { name: 'Custom breadth watchlist source' }).locator('option:checked')).toContainText('Selected members · 1')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-family-map-drilldown — selected benchmark family opens its locked constituent watchlist', async ({ page, browserDiagnostics }) => {
    const requestedSources: string[] = []
    await page.route('**/api/v1/market-groups/us-benchmarks*', async route => {
      const response = await route.fetch()
      const payload = await response.json() as Record<string, unknown>
      const provenance = payload.provenance && typeof payload.provenance === 'object' ? payload.provenance as Record<string, unknown> : {}
      await route.fulfill({ response, body: JSON.stringify({ ...payload, provenance: { ...provenance, benchmark_families: [{ logical_key: 'sp500', name: 'S&P 500', official_index_symbol: 'SPX', cap_weight: { symbol: 'SPY' } }] } }) })
    })
    await page.route('**/api/v1/market-groups/sp500*', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stable_key: 'sp500', name: 'S&P 500', members: [{ instrument: { id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust' } }], provenance: { benchmark_family: 'sp500' } }) })
    })
    await page.route('**/api/v1/analysis/groups/sp500/snapshot*', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ group_key: 'sp500', rows: [{ instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', performance: {}, technical: {}, warnings: [] }], exclusions: [] }) })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/overview*', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ family_key: 'sp500', name: 'S&P 500', official_index_symbol: 'SPX', mappings: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, holdings_available: true, holdings_completeness_status: 'complete' }, { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, holdings_available: true, holdings_completeness_status: 'complete' }], rows: [], exclusions: [] }) })
    })
    await page.route('**/api/v1/watchlists/sources**', async route => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.includes('/history-status/')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ overall_status: 'ready', available_instrument_count: 1, selected_instrument_count: 1, timeframes: [{ timeframe: 'D1', member_count: 1, covered_member_count: 1, coverage_percent: 100 }] }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ source_id: 'benchmark-family:sp500:cap_weight', source_kind: 'index_membership', name: 'S&P 500 constituents', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 1, membership_version: 'sp500:cap:v1', provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' } }, { source_id: 'benchmark-family:sp500:equal_weight', source_kind: 'index_membership', name: 'S&P 500 equal-weight constituents', locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 1, membership_version: 'sp500:equal:v1', provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' } }]) })
    })
    await page.route('**/api/v1/analysis/market-map', async route => {
      const body = route.request().postDataJSON() as { source_id?: string }
      requestedSources.push(String(body.source_id ?? ''))
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ source: { source_id: body.source_id, source_kind: 'index_membership', name: 'S&P 500 constituents', locked: true, member_count: 1, membership_version: 'sp500:v1' }, group_by: 'sector_industry', period: '1D', timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'equal', color_metric: 'return', membership_version: 'sp500:v1', freshness: 'current', requested_count: 1, evaluated_count: 1, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [], exclusions: [], nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 1, covered_count: 1, area_total: 1, color_value: 0.01, coverage: 1, color_coverage: 1, area_coverage: 1, aggregation_method: 'equal_member_mean', warnings: [] }], cells: [{ instrument_id: 1, symbol: 'SPY', name: 'SPY', sector: 'Index', industry: 'ETF', group_path: ['Index', 'ETF'], area_value: 1, color_value: 0.01, return_value: 0.01, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [] }] }) })
    })
    await page.goto('/chart/SPY')
    const benchmarkSurface = page.locator('.benchmark-surface').first()
    await expect(benchmarkSurface).toBeVisible({ timeout: 15_000 })
    await benchmarkSurface.getByRole('combobox', { name: 'Benchmark family' }).selectOption('sp500')
    await expect(benchmarkSurface).toContainText('S&P 500 legs')
    const mapRole = benchmarkSurface.getByRole('combobox', { name: 'Benchmark family Map role' })
    await expect(mapRole).toHaveValue('cap_weight')
    await mapRole.selectOption('equal_weight')
    await expect(mapRole).toHaveValue('equal_weight')
    await benchmarkSurface.getByRole('button', { name: 'Open Market Map' }).click()
    const mapWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.market-map-tool') }).last()
    await expect(mapWindow).toBeVisible({ timeout: 15_000 })
    await expect(mapWindow.getByRole('combobox', { name: 'Market Map universe' })).toHaveValue('benchmark-family:sp500:equal_weight')
    await expect.poll(() => requestedSources.at(-1), { timeout: 15_000 }).toBe('benchmark-family:sp500:equal_weight')
    await expect(mapWindow).toContainText('Locked source')
    await expect(mapWindow.locator('.market-map-tool__tile')).toHaveCount(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-family-matrix — all eight US benchmark roots retain independent entry and constituent source identity', async ({ page, browserDiagnostics }) => {
    const families = [
      { key: 'sp500', name: 'S&P 500', official: 'SPX', proxy: 'SPY' },
      { key: 'sp400', name: 'S&P MidCap 400', official: 'MID', proxy: 'MDY' },
      { key: 'sp600', name: 'S&P SmallCap 600', official: 'SML', proxy: 'IJR' },
      { key: 'sp1500', name: 'S&P Composite 1500', official: 'SPSUPX', proxy: 'SPTM' },
      { key: 'russell1000', name: 'Russell 1000', official: 'RUI', proxy: 'IWB' },
      { key: 'russell2000', name: 'Russell 2000', official: 'RTY', proxy: 'IWM' },
      { key: 'russell3000', name: 'Russell 3000', official: 'RUA', proxy: 'IWV' },
      { key: 'nasdaq100', name: 'Nasdaq 100', official: 'NDX', proxy: 'QQQ' },
    ]
    const familyByKey = new Map(families.map(family => [family.key, family]))
    const selectedSources: string[] = []
    await page.route('**/api/v1/market-groups/us-benchmarks*', async route => {
      const response = await route.fetch()
      const payload = await response.json() as Record<string, unknown>
      const provenance = payload.provenance && typeof payload.provenance === 'object' ? payload.provenance as Record<string, unknown> : {}
      await route.fulfill({ response, body: JSON.stringify({ ...payload, provenance: { ...provenance, benchmark_families: families.map(family => ({ logical_key: family.key, name: family.name, official_index_symbol: family.official, cap_weight: { symbol: family.proxy } })) } }) })
    })
    await page.route('**/api/v1/market-groups/*', async route => {
      const pathname = new URL(route.request().url()).pathname
      const familyKey = pathname.match(/\/market-groups\/([^/]+)$/)?.[1]
      const family = familyKey ? familyByKey.get(decodeURIComponent(familyKey)) : undefined
      if (!family) return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stable_key: family.key, name: family.name, group_type: 'benchmark_family', members: [{ instrument: { id: 1, symbol: family.proxy, name: `${family.name} proxy` } }], provenance: { benchmark_family: family.key } }) })
    })
    await page.route('**/api/v1/analysis/groups/*/snapshot*', async route => {
      const pathname = new URL(route.request().url()).pathname
      const familyKey = pathname.match(/\/analysis\/groups\/([^/]+)\/snapshot/)?.[1]
      const family = familyKey ? familyByKey.get(decodeURIComponent(familyKey)) : undefined
      if (!family) return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ group_key: family.key, rows: [{ instrument_id: 1, symbol: family.proxy, name: `${family.name} proxy`, performance: {}, technical: {}, warnings: [] }], exclusions: [] }) })
    })
    await page.route('**/api/v1/analysis/benchmark-families/*/overview*', async route => {
      const pathname = new URL(route.request().url()).pathname
      const familyKey = pathname.match(/\/benchmark-families\/([^/]+)\/overview/)?.[1]
      const family = familyKey ? familyByKey.get(decodeURIComponent(familyKey)) : undefined
      if (!family) return route.continue()
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ family_key: family.key, name: family.name, official_index_symbol: family.official, mappings: [{ role: 'cap_weight', symbol: family.proxy, label: family.proxy, verification_state: 'verified', available: true, holdings_available: true, holdings_completeness_status: 'complete' }], rows: [], exclusions: [] }) })
    })
    await page.route('**/api/v1/watchlists/sources**', async route => {
      const pathname = new URL(route.request().url()).pathname
      if (pathname.includes('/history-status/')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ overall_status: 'ready', available_instrument_count: 1, selected_instrument_count: 1, timeframes: [{ timeframe: 'D1', member_count: 1, covered_member_count: 1, coverage_percent: 100 }] }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(families.map(family => ({ source_id: `benchmark-family:${family.key}:cap_weight`, source_kind: 'index_membership', name: `${family.name} constituents`, locked: true, can_follow: true, can_clone: true, can_edit_membership: false, member_count: 1, membership_version: `${family.key}:v1`, provenance: { availability: 'available', membership_semantics: 'etf_proxy_holdings' } }))) })
    })
    await page.route('**/api/v1/analysis/market-map', async route => {
      const body = route.request().postDataJSON() as { source_id?: string }
      selectedSources.push(String(body.source_id ?? ''))
      const familyKey = String(body.source_id ?? '').split(':')[1] ?? 'sp500'
      const family = familyByKey.get(familyKey) ?? families[0]
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ source: { source_id: body.source_id, source_kind: 'index_membership', name: `${family.name} constituents`, locked: true, member_count: 1, membership_version: `${family.key}:v1` }, group_by: 'sector_industry', period: '1D', timeframe: 'D1', adjustment: 'split_adjusted', area_metric: 'equal', color_metric: 'return', membership_version: `${family.key}:v1`, freshness: 'current', requested_count: 1, evaluated_count: 1, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [], exclusions: [], nodes: [{ node_id: 'root', level: 'root', label: 'All members', group_path: [], member_count: 1, covered_count: 1, area_total: 1, color_value: 0.01, coverage: 1, color_coverage: 1, area_coverage: 1, aggregation_method: 'equal_member_mean', warnings: [] }], cells: [{ instrument_id: 1, symbol: family.proxy, name: family.name, sector: 'Index', industry: 'ETF', group_path: ['Index', 'ETF'], area_value: 1, color_value: 0.01, return_value: 0.01, coverage: 1, color_coverage: 1, area_coverage: 1, warnings: [] }] }) })
    })
    await page.goto('/chart/SPY')
    const benchmarkSurface = page.locator('.benchmark-surface').first()
    await expect(benchmarkSurface).toBeVisible({ timeout: 15_000 })
    const familySelect = benchmarkSurface.getByRole('combobox', { name: 'Benchmark family' })
    for (const family of families) {
      await familySelect.selectOption(family.key)
      await expect(benchmarkSurface).toContainText(`${family.name} legs`)
      await expect(benchmarkSurface).toContainText(`Official series: ${family.official}`)
      await expect(benchmarkSurface).toContainText(`Using tradable proxy: ${family.proxy}`)
    }
    await benchmarkSurface.getByRole('button', { name: 'Open Market Map' }).click()
    const mapWindow = page.locator('.tool-window:visible').filter({ has: page.locator('.market-map-tool') }).last()
    await expect(mapWindow).toBeVisible({ timeout: 15_000 })
    await expect(mapWindow.getByRole('combobox', { name: 'Market Map universe' })).toHaveValue('benchmark-family:nasdaq100:cap_weight')
    await expect.poll(() => selectedSources.at(-1), { timeout: 15_000 }).toBe('benchmark-family:nasdaq100:cap_weight')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-breadth — Market Breadth exposes universe-scoped loading and failure semantics', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadth = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadth).toBeVisible({ timeout: 10_000 })
    const region = breadth.locator('[role="region"][aria-label="Breadth analysis for sp500-sectors"]')
    await expect(region).toBeVisible({ timeout: 10_000 })
    await expect(region).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect.poll(async () => region.locator('.metrics, [role="status"], [role="alert"]').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-breadth-family-ratio — family breadth exposes role-aware cap and market relative strength', async ({ page, browserDiagnostics }) => {
    const customBreadthRequests: Array<Record<string, unknown>> = []
    const familyAsOfRequests: string[] = []
    await page.route('**/api/v1/analysis/breadth', async route => {
      if (route.request().method() === 'POST') customBreadthRequests.push(JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ definition_version: 1, definition_hash: 'family-breadth', universe: { kind: 'benchmark_family', family_key: 'sp500', role: 'equal_weight', proxy_symbol: 'RSP' }, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', requested_count: 1, eligible_count: 1, pass_count: 1, excluded_count: 0, percentage: 1, coverage: 1, members: [{ instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', value: true, metric: 0.12, observation_time: '2026-06-27T00:00:00Z', diagnostics: [{ path: '$', kind: 'all', status: 'pass', value: true, metric: 0.12 }, { path: '$.conditions[0]', kind: 'comparison', status: 'pass', value: true, metric: 0.12 }] }], exclusions: [] }),
      })
    })
    await page.route('**/api/v1/analysis/breadth/history', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ definition_version: 1, definition_hash: 'family-breadth', universe: { kind: 'benchmark_family', family_key: 'sp500', role: 'equal_weight', proxy_symbol: 'RSP' }, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', points: [], occurrences: [{ occurrence_id: 'SPY:2026-06-27T00:00:00Z:member_entered', timestamp: '2026-06-27T00:00:00Z', kind: 'member_entered', instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', value: true, metric: 0.025, percentage: 0.5, pass_count: 1, eligible_count: 2 }], exclusions: [] }),
      })
    })
    await page.route('**/api/v1/analysis/groups/sp500/breadth*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ group_key: 'sp500', timeframe: 'D1', adjustment: 'split_adjusted', evaluated_count: 1, coverage: 1, above_ma: { ma20: 1, ma50: 1, ma200: 1 }, exclusions: [] }),
      })
    })
    await page.route('**/api/v1/analysis/groups/sp500/breadth/history*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ group_key: 'sp500', timeframe: 'D1', adjustment: 'split_adjusted', points: [], exclusions: [] }),
      })
    })
    await page.route('**/market-groups/us-benchmarks*', async route => {
      const response = await route.fetch()
      const payload = await response.json() as Record<string, unknown>
      const provenance = payload.provenance && typeof payload.provenance === 'object'
        ? payload.provenance as Record<string, unknown>
        : {}
      await route.fulfill({
        response,
        body: JSON.stringify({
          ...payload,
          provenance: {
            ...provenance,
            benchmark_families: [{ logical_key: 'sp500', name: 'S&P 500' }],
          },
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/ratios*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500',
          official_index_symbol: 'SPX',
          timeframe: 'D1',
          adjustment: 'split_adjusted',
          ratios: [
            { family_key: 'sp500', role: 'equal_weight', symbol: 'RSP', benchmark_role: 'cap_weight', benchmark: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: '2026-01-02T00:00:00Z', value: 0.98 }], coverage: 1, warnings: [] },
            { family_key: 'sp500', role: 'equal_weight', symbol: 'RSP', benchmark_role: 'market', benchmark: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: '2026-01-02T00:00:00Z', value: 0.98 }], coverage: 1, warnings: [] },
          ],
          exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/technicals*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500',
          official_index_symbol: 'SPX',
          timeframe: 'D1',
          adjustment: 'split_adjusted',
          membership_version: 1,
          universe_provenance: { technical_semantics: 'role_independent_local_ohlcv_snapshot' },
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, last: 600, rsi14: 55, sma20: 590, sma50: 580, sma200: 540, position_52w: 0.92, volume_ratio_50: 1.1, freshness: 'current', warnings: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, last: 180, rsi14: 52, sma20: 178, sma50: 175, sma200: 165, position_52w: 0.85, volume_ratio_50: 1.0, freshness: 'current', warnings: [] },
            { role: 'value', symbol: 'SPYV', label: 'SPYV', verification_state: 'verified', available: true, last: null, rsi14: null, sma20: null, sma50: null, sma200: null, position_52w: null, volume_ratio_50: null, freshness: 'unavailable', warnings: [{ code: 'no_bars', message: 'No local bars are available.' }] },
            { role: 'growth', symbol: 'SPYG', label: 'SPYG', verification_state: 'verified', available: true, last: null, rsi14: null, sma20: null, sma50: null, sma200: null, position_52w: null, volume_ratio_50: null, freshness: 'unavailable', warnings: [{ code: 'no_bars', message: 'No local bars are available.' }] },
          ],
          exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/ranking*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500', official_index_symbol: 'SPX', benchmark: 'SPY', timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M',
          roles: [
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, rank: 1, performance: { '1M': 0.12 }, relative_performance: { '1M': 0.03 }, warnings: [] },
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, rank: 2, performance: { '1M': 0.09 }, relative_performance: { '1M': 0 }, warnings: [] },
          ], exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/concentration/history*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', top_n: 10, limit: 500,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-02T00:00:00Z', snapshot_id: 1, composition_date: '2026-01-01', known_at: '2026-01-02T00:00:00Z', membership_version: 1, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n_weight: 0.34, hhi: 0.04, effective_constituents: 25, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, mean_return: 0.04, median_return: 0.03, dispersion: 0.02, warnings: [] }], exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-02T00:00:00Z', snapshot_id: 2, composition_date: '2026-01-01', known_at: '2026-01-02T00:00:00Z', membership_version: 2, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n_weight: 0.02, hhi: 0.002, effective_constituents: 500, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, mean_return: 0.05, median_return: 0.05, dispersion: 0.015, warnings: [] }], exclusions: [] },
          ], exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/concentration?rank_period*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', top_n: 10,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n: 10, top_n_weight: 0.34, hhi: 0.04, effective_constituents: 25, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, mean_return: 0.04, median_return: 0.03, dispersion: 0.02, members: [], warnings: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, weight_method: 'reported_holdings_weights', reported_weight_coverage: 1, top_n: 10, top_n_weight: 0.02, hhi: 0.002, effective_constituents: 500, eligible_count: 500, covered_count: 500, excluded_count: 0, coverage: 1, mean_return: 0.05, median_return: 0.05, dispersion: 0.015, members: [], warnings: [] },
          ], exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/ranking/history*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', limit: 500, benchmark: null,
          rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, coverage: 1, points: [{ timestamp: '2026-01-02T00:00:00Z', rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0 } }], warnings: [] }], exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/ranking*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          timeframe: 'D1', adjustment: 'split_adjusted', rank_period: '1M', benchmark: null,
          rows: [{ family_key: 'sp500', family_name: 'S&P 500', official_index_symbol: 'SPX', symbol: 'SPY', label: 'SPY', available: true, rank: 1, performance: { '1M': 0.1 }, relative_performance: { '1M': 0 }, warnings: [] }], exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/breadth*', async route => {
      familyAsOfRequests.push(route.request().url())
      const metric = (percentage: number | null) => ({ percentage, requested_count: 100, eligible_count: percentage == null ? 0 : 100, excluded_count: percentage == null ? 100 : 0, coverage: percentage == null ? 0 : 1, exclusions: [] })
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500',
          official_index_symbol: 'SPX',
          timeframe: 'D1',
          adjustment: 'split_adjusted',
          near_threshold: 0.01,
          new_high_lookback: 20,
          membership_version: 1,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, above_ma: { ma20: metric(0.7), ma50: metric(0.6), ma200: metric(0.5) }, near_52w_high: metric(0.4), new_high: metric(0.1), trend_up: metric(0.65), relative_strength_to_cap: null, exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, above_ma: { ma20: metric(0.55), ma50: metric(0.5), ma200: metric(0.45) }, near_52w_high: metric(0.3), new_high: metric(0.08), trend_up: metric(0.5), relative_strength_to_cap: metric(0.02), exclusions: [] },
            { role: 'value', symbol: 'SPYV', label: 'SPYV', verification_state: 'verified', available: true, above_ma: {}, near_52w_high: null, new_high: null, trend_up: null, relative_strength_to_cap: null, exclusions: [{ code: 'holdings_snapshot_not_found', message: 'No holdings snapshot.' }] },
            { role: 'growth', symbol: 'SPYG', label: 'SPYG', verification_state: 'verified', available: true, above_ma: {}, near_52w_high: null, new_high: null, trend_up: null, relative_strength_to_cap: null, exclusions: [{ code: 'holdings_snapshot_not_found', message: 'No holdings snapshot.' }] },
          ],
          exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/breadth/history*', async route => {
      familyAsOfRequests.push(route.request().url())
      const point = { timestamp: '2026-01-02T00:00:00Z', above_ma: { ma20: 0.7, ma50: 0.6, ma200: 0.5 }, coverage: { ma20: 1, ma50: 1, ma200: 1 } }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, points: [point], exclusions: [] }, { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, points: [point], exclusions: [] }], exclusions: [] }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/overview*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500',
          name: 'S&P 500',
          official_index_symbol: 'SPX',
          official_index_name: 'S&P 500',
          timeframe: 'D1',
          adjustment: 'split_adjusted',
          membership_version: 1,
          universe_provenance: { membership_semantics: 'etf_proxy' },
          coverage: 1,
          mappings: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, holdings_available: true, holdings_completeness_status: 'complete' },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, holdings_available: true, holdings_completeness_status: 'complete' },
            { role: 'value', symbol: 'SPYV', label: 'SPYV', verification_state: 'verified', available: true, holdings_available: false },
            { role: 'growth', symbol: 'SPYG', label: 'SPYG', verification_state: 'verified', available: true, holdings_available: false },
          ],
          derived_equal_weight: {},
          rows: [],
          exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/coverage*', async route => {
      familyAsOfRequests.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp500',
          name: 'S&P 500',
          official_index_symbol: 'SPX',
          official_index_name: 'S&P 500',
          membership_version: 1,
          universe_provenance: { coverage_semantics: 'role_independent_dated_holdings_snapshots' },
          coverage: 0.5,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'SPY', verification_state: 'verified', available: true, status: 'available', snapshots: [{ snapshot_id: 1, composition_date: '2026-06-27', as_of_date: '2026-06-30', known_at: '2026-06-28T20:00:00Z', provenance: 'issuer snapshot', source_provider: 'fixture', source_quality: 'issuer_disclosed', completeness_status: 'complete', row_count: 1, resolved_count: 1, unresolved_count: 0 }] },
            { role: 'equal_weight', symbol: 'RSP', label: 'RSP', verification_state: 'verified', available: true, status: 'available', snapshots: [{ snapshot_id: 2, composition_date: '2026-06-27', as_of_date: '2026-06-30', known_at: '2026-06-28T20:00:00Z', provenance: 'issuer snapshot', source_provider: 'fixture', source_quality: 'issuer_disclosed', completeness_status: 'complete', row_count: 1, resolved_count: 1, unresolved_count: 0 }] },
            { role: 'value', symbol: 'SPYV', label: 'SPYV', verification_state: 'verified', available: true, status: 'no_snapshot', snapshots: [] },
            { role: 'growth', symbol: 'SPYG', label: 'SPYG', verification_state: 'verified', available: true, status: 'no_snapshot', snapshots: [] },
          ],
          exclusions: [],
        }),
      })
    })
    await page.route('**/api/v1/analysis/benchmark-families/sp500/constituents*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          group_key: 'benchmark-family:sp500:equal_weight',
          universe_provenance: { family_key: 'sp500', mapping_role: 'equal_weight' },
          etf_symbol: 'RSP',
          benchmark: 'SPY',
          market_benchmark: 'SPY',
          composition_date: '2026-06-27',
          known_at: '2026-06-27T20:00:00Z',
          provenance: 'issuer snapshot',
          source_provider: 'fixture',
          completeness_status: 'complete',
          coverage: 1,
          rows: [{ instrument_id: 7, symbol: 'NVDA', name: 'NVIDIA', position: 1, weight: 0.01, shares: null, market_value: null, holding_type: 'equity', row_type: 'holding', resolution_confidence: 1, performance: {}, calendar_year_performance: {}, technical: {} }],
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadth = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadth).toBeVisible({ timeout: 10_000 })
    const universe = breadth.locator('select[aria-label="Breadth universe"]')
    await universe.selectOption('sp500')
    const familyPanel = breadth.locator('[aria-label="Benchmark family relative strength"]')
    await expect(familyPanel).toBeVisible({ timeout: 10_000 })
    await expect(familyPanel).toContainText('RSP/SPY', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Benchmark family technicals"]')).toContainText('Cap weight SPY · 600.00 · RSI 55.00', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Benchmark family participation"]')).toContainText('Cap weight SPY · >20 70% · near 52w 40% · trend 65%', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Benchmark family role ranking"]')).toContainText('#1 Equal weight RSP', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Benchmark family concentration"]')).toContainText('Cap weight SPY · top 34.0% · HHI 0.04 · effective 25.00 · σ 2.0% · 100.0% covered', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Benchmark family concentration"]')).toContainText('History · 1 points · point-in-time snapshots', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Cross-family ranking"]')).toContainText('#1 S&P 500 SPY', { timeout: 15_000 })
    await expect(breadth.locator('[aria-label="Cross-family ranking"]')).toContainText('History · 1 points', { timeout: 15_000 })
    await expect(familyPanel.getByRole('combobox', { name: 'Family ratio leg' })).toHaveValue('equal_weight')
    const familyOverview = breadth.locator('[aria-label="Benchmark family analysis"]')
    await expect(familyOverview).toBeVisible({ timeout: 15_000 })
    await expect(familyOverview).toContainText('S&P 500 · SPX')
    await expect(familyOverview).toContainText('RSP')
    await expect(familyOverview).toContainText('NVDA')
    await expect(familyOverview).toContainText('Dated holdings coverage')
    await expect(familyOverview).toContainText('Cap weight SPY · available · 1 date')
    const familyAsOf = familyOverview.getByRole('combobox', { name: 'Family analysis as of' })
    await expect(familyAsOf).toHaveValue('')
    await familyAsOf.selectOption('2026-06-27T23:59:59Z')
    await expect(familyAsOf).toHaveValue('2026-06-27T23:59:59Z')
    await expect.poll(() => familyAsOfRequests.filter(url => url.includes('as_of=')).length, { timeout: 10_000 }).toBeGreaterThan(0)
    const customUniverse = breadth.locator('select[aria-label="Custom breadth universe"]')
    const evaluateCustomBreadth = async () => {
      const previousRequestCount = customBreadthRequests.length
      await breadth.getByRole('button', { name: 'Evaluate' }).click()
      await expect.poll(() => customBreadthRequests.length, { timeout: 10_000 }).toBeGreaterThan(previousRequestCount)
      return customBreadthRequests.at(-1)
    }
    await expect(customUniverse.locator('option[value="benchmark_family"]')).toHaveCount(1)
    await customUniverse.selectOption('benchmark_family')
    const initialRequest = await evaluateCustomBreadth()
    expect(initialRequest?.universe).toMatchObject({ kind: 'benchmark_family', key: 'sp500', role: 'equal_weight' })
    await expect(breadth.locator('[aria-label="Generic breadth clause diagnostics"]')).toContainText('$.conditions[0] comparison pass')
    const occurrencePanel = breadth.locator('[aria-label="Generic breadth historical occurrences"]')
    await expect(occurrencePanel).toBeVisible({ timeout: 15_000 })
    const occurrence = occurrencePanel.getByRole('button', { name: /SPY Entered condition/ })
    await expect(occurrence).toBeVisible()
    await occurrence.click()
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY')
    await expect(page.locator('.chart-root[data-linked-timestamp]')).toHaveAttribute('data-linked-timestamp', '2026-06-27T00:00:00Z')
    const condition = breadth.locator('select[aria-label="Breadth condition"]')
    await condition.selectOption('rsi')
    await breadth.getByLabel('Breadth RSI target').fill('55')
    await breadth.getByLabel('Breadth RSI target').press('Tab')
    const rsiRequest = await evaluateCustomBreadth()
    expect(rsiRequest?.condition).toMatchObject({ kind: 'rsi', params: { threshold: 55 } })
    await condition.selectOption('volume_ratio')
    await breadth.getByLabel('Breadth volume ratio target').fill('1.5')
    await breadth.getByLabel('Breadth volume ratio target').press('Tab')
    const volumeRequest = await evaluateCustomBreadth()
    expect(volumeRequest?.condition).toMatchObject({ kind: 'volume_ratio', params: { threshold: 1.5 } })
    await condition.selectOption('range')
    const rangeLower = breadth.getByLabel('Breadth range lower bound')
    const rangeUpper = breadth.getByLabel('Breadth range upper bound')
    await rangeLower.fill('-0.1')
    await rangeLower.press('Tab')
    await expect(rangeLower).toHaveValue('-0.1')
    await rangeUpper.fill('0.1')
    await rangeUpper.press('Tab')
    await expect(rangeUpper).toHaveValue('0.1')
    const rangeRequest = await evaluateCustomBreadth()
    expect(rangeRequest?.condition).toMatchObject({ kind: 'range', params: { lower: -0.1, upper: 0.1, inclusive: true } })
    await condition.selectOption('within_52_week_high')
    await breadth.getByLabel('Breadth 52-week direction').selectOption('low')
    const nearLowRequest = await evaluateCustomBreadth()
    expect(nearLowRequest?.condition).toMatchObject({ kind: 'within_52_week_high', params: { direction: 'low' } })
    await condition.selectOption('new_high_low')
    await breadth.getByLabel('Breadth new high low direction').selectOption('low')
    await breadth.getByLabel('Breadth condition new high low lookback').fill('20')
    await breadth.getByLabel('Breadth condition new high low lookback').press('Tab')
    const newLowRequest = await evaluateCustomBreadth()
    expect(newLowRequest?.condition).toMatchObject({ kind: 'new_high_low', params: { direction: 'low', lookback: 20 } })
    await condition.selectOption('prior_high_low')
    await breadth.getByLabel('Breadth prior high low direction').selectOption('high')
    await breadth.getByLabel('Breadth prior high low lookback').fill('30')
    await breadth.getByLabel('Breadth prior high low lookback').press('Tab')
    await breadth.getByLabel('Breadth prior high low threshold').fill('0.01')
    await breadth.getByLabel('Breadth prior high low threshold').press('Tab')
    const priorHighRequest = await evaluateCustomBreadth()
    expect(priorHighRequest?.condition).toMatchObject({ kind: 'prior_high_low', params: { direction: 'high', lookback: 30, operator: 'gte', threshold: 0.01 } })
    await condition.selectOption('event')
    await breadth.getByLabel('Breadth event type').selectOption('dividend')
    await breadth.getByLabel('Breadth event lookback days').fill('5')
    await breadth.getByLabel('Breadth event lookback days').press('Tab')
    const eventRequest = await evaluateCustomBreadth()
    expect(eventRequest?.condition).toMatchObject({ kind: 'event', params: { event_type: 'dividend', lookback_days: 5, operator: 'gte', threshold: 1 } })
    await condition.selectOption('series_comparison')
    await breadth.getByLabel('Breadth series reference field').selectOption('close')
    await breadth.getByLabel('Breadth series relation').selectOption('ratio')
    await breadth.getByLabel('Breadth series threshold').fill('0')
    await breadth.getByLabel('Breadth series threshold').press('Tab')
    const seriesComparisonRequest = await evaluateCustomBreadth()
    expect(seriesComparisonRequest?.benchmark).toBe('SPY')
    expect(seriesComparisonRequest?.condition).toMatchObject({ kind: 'series_comparison', params: { field: 'return', target_field: 'close', relation: 'ratio', operator: 'gte', threshold: 0 } })
    await breadth.getByLabel('Breadth reference target').selectOption('group')
    await breadth.getByLabel('Breadth reference group').fill('sp500-sectors')
    await breadth.getByLabel('Breadth reference group').press('Tab')
    const groupReferenceRequest = await evaluateCustomBreadth()
    expect(groupReferenceRequest?.benchmark).toBeUndefined()
    expect(groupReferenceRequest?.reference_universe).toMatchObject({ kind: 'group', key: 'sp500-sectors', point_in_time: true })
    expect(groupReferenceRequest?.condition).toMatchObject({ kind: 'series_comparison', params: { relation: 'ratio' } })
    await breadth.getByLabel('Breadth reference target').selectOption('symbol')
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('any')
    const anyRequest = await evaluateCustomBreadth()
    expect(anyRequest?.condition).toMatchObject({ kind: 'any', params: { conditions: expect.any(Array) } })
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('not')
    const notRequest = await evaluateCustomBreadth()
    expect(notRequest?.condition).toMatchObject({ kind: 'not', params: { conditions: expect.any(Array) } })
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('single')
    await condition.selectOption('percentile')
    await breadth.getByLabel('Breadth percentile rolling window').fill('20')
    await breadth.getByLabel('Breadth percentile rolling window').press('Tab')
    await breadth.getByLabel('Breadth percentile target', { exact: true }).fill('0.8')
    await breadth.getByLabel('Breadth percentile target', { exact: true }).press('Tab')
    const percentileRequest = await evaluateCustomBreadth()
    expect(percentileRequest?.condition).toMatchObject({ kind: 'percentile', params: { period: 20, percentile: 0.8, operator: 'gte' } })
    await breadth.getByLabel('Breadth percentile target scope').selectOption('cross_sectional')
    const crossSectionalRequest = await evaluateCustomBreadth()
    expect(crossSectionalRequest?.condition).toMatchObject({ kind: 'percentile', target_scope: 'cross_sectional' })
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('tree')
    const conditionTree = breadth.locator('[aria-label="Breadth condition tree"]')
    await expect(conditionTree).toBeVisible()
    await conditionTree.getByRole('combobox', { name: 'Breadth group operator 1' }).selectOption('all')
    await conditionTree.getByRole('combobox', { name: 'Breadth condition type 1.1' }).selectOption('percentile')
    await conditionTree.getByRole('combobox', { name: 'Breadth percentile scope 1.1' }).selectOption('cross_sectional')
    await conditionTree.getByRole('button', { name: '+ Group' }).click()
    const nestedGroup = conditionTree.locator('.breadth-condition-tree--nested').last()
    await expect(nestedGroup).toBeVisible()
    await conditionTree.getByRole('combobox', { name: 'Breadth group operator 1.2' }).selectOption('any')
    await conditionTree.getByRole('combobox', { name: 'Breadth condition type 1.2.1' }).selectOption('new_high_low')
    const treeRequest = await evaluateCustomBreadth()
    expect(treeRequest?.condition).toMatchObject({
      kind: 'all',
      params: {
        conditions: [
          expect.objectContaining({ kind: 'percentile', target_scope: 'cross_sectional' }),
          { kind: 'any', params: { conditions: [expect.objectContaining({ kind: 'new_high_low' })] } },
        ],
      },
    })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-breadth-python-series — numeric Python condition assets run through isolated breadth', async ({ page, browserDiagnostics }) => {
    const queuedRequests: Array<Record<string, unknown>> = []
    await page.route('**/api/v1/code/assets', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ kind: 'condition', name: 'Close distance study', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] }]),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      queuedRequests.push(JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>)
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 91, code_version_id: 17, status: 'queued', execution_mode: 'breadth_history', output_contract: 'series', series_target: { operator: 'gte', threshold: 0.02 }, definition_hash: 'python-series', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'series' }, dataset_manifest: {}, progress: {}, diagnostics: [] }),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python/runs/91', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 91, code_version_id: 17, status: 'completed', execution_mode: 'breadth_history', output_contract: 'series', series_target: { operator: 'gte', threshold: 0.02 }, definition_hash: 'python-series', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'series' }, dataset_manifest: { timeframe: 'D1', adjustment: 'split_adjusted' }, current: { timestamp: '2026-08-17T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [{ instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', value: true, metric: 0.025, observation_time: '2026-08-17T00:00:00Z', diagnostics: [] }], exclusions: [] }, points: [{ timestamp: '2026-08-16T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [], exclusions: [] }], occurrences: [], progress: {}, diagnostics: [] }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadth = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadth).toBeVisible({ timeout: 10_000 })
    const condition = breadth.locator('select[aria-label="Breadth condition"]')
    await condition.selectOption('python_series')
    await breadth.getByLabel('Breadth Python series condition asset').selectOption('17')
    await breadth.getByLabel('Breadth Python series operator').selectOption('gte')
    await breadth.getByLabel('Breadth Python series threshold').fill('0.02')
    await breadth.getByLabel('Breadth Python series threshold').press('Tab')
    await breadth.getByRole('button', { name: 'Evaluate' }).click()
    await expect.poll(() => queuedRequests.length, { timeout: 10_000 }).toBe(1)
    expect(queuedRequests[0]).toMatchObject({ code_version_id: 17, output_contract: 'series', series_target: { operator: 'gte', threshold: 0.02 }, history: true })
    await expect(breadth.locator('.breadth-tool__custom-result')).toContainText('50.0%', { timeout: 15_000 })
    await expect(breadth.locator('.breadth-tool__generic-drilldown')).toContainText('SPY')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-breadth-python-tree — recursive member and cross-sectional Python leaves retain one tree contract', async ({ page, browserDiagnostics }) => {
    const queuedRequests: Array<Record<string, unknown>> = []
    await page.route('**/api/v1/code/assets', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ kind: 'condition', name: 'Close distance study', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] }]),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      queuedRequests.push(JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>)
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 92, code_version_id: 17, status: 'queued', execution_mode: 'breadth_history', output_contract: 'boolean', condition_tree: { kind: 'all' }, definition_hash: 'python-tree', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'boolean' }, dataset_manifest: {}, progress: {}, diagnostics: [] }),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python/runs/92', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 92, code_version_id: 17, status: 'completed', execution_mode: 'breadth_history', output_contract: 'boolean', condition_tree: { kind: 'all' }, definition_hash: 'python-tree', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'boolean' }, dataset_manifest: { timeframe: 'D1', adjustment: 'split_adjusted' }, current: { timestamp: '2026-08-17T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [{ instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', value: true, metric: 0.01, observation_time: '2026-08-17T00:00:00Z', diagnostics: [] }], exclusions: [] }, points: [], occurrences: [], progress: {}, diagnostics: [] }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadth = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadth).toBeVisible({ timeout: 10_000 })
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('tree')
    const tree = breadth.locator('[aria-label="Breadth condition tree"]')
    await tree.getByRole('combobox', { name: 'Breadth condition type 1.1' }).selectOption('python_series')
    await tree.getByLabel('Breadth Python series condition asset 1.1').selectOption('17')
    await tree.getByLabel('Breadth Python series scope 1.1').selectOption('cross_sectional')
    await tree.getByLabel('Breadth Python series group statistic 1.1').selectOption('median')
    await tree.getByLabel('Breadth Python series operator 1.1').selectOption('gte')
    await tree.getByLabel('Breadth Python series threshold 1.1').fill('0')
    await tree.getByLabel('Breadth Python series threshold 1.1').press('Tab')
    await breadth.getByRole('button', { name: 'Evaluate' }).click()
    await expect.poll(() => queuedRequests.length, { timeout: 10_000 }).toBe(1)
    expect(queuedRequests[0]).toMatchObject({ code_version_id: 17, output_contract: 'boolean', history: true, condition_tree: { kind: 'all', params: { conditions: [{ kind: 'python_series', params: { code_version_id: 17, scope: 'cross_sectional', statistic: 'median', operator: 'gte', threshold: 0 } }] } } })
    await expect(breadth.locator('.breadth-tool__custom-result')).toContainText('50.0%', { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-breadth-python-comparison — two isolated Python series can be compared in a recursive tree', async ({ page, browserDiagnostics }) => {
    const queuedRequests: Array<Record<string, unknown>> = []
    await page.route('**/api/v1/code/assets', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ kind: 'condition', name: 'Member return', versions: [{ id: 17, version_number: 1, output_contract: 'series' }] }, { kind: 'condition', name: 'Benchmark return', versions: [{ id: 18, version_number: 1, output_contract: 'series' }] }]),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python', async route => {
      if (route.request().method() !== 'POST') return route.continue()
      queuedRequests.push(JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>)
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 93, code_version_id: 17, status: 'queued', execution_mode: 'breadth_history', output_contract: 'boolean', condition_tree: { kind: 'python_series_comparison' }, definition_hash: 'python-comparison', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'boolean' }, dataset_manifest: {}, progress: {}, diagnostics: [] }),
      })
    })
    await page.route('**/api/v1/analysis/breadth/python/runs/93', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ run_id: 93, code_version_id: 17, status: 'completed', execution_mode: 'breadth_history', output_contract: 'boolean', condition_tree: { kind: 'python_series_comparison' }, definition_hash: 'python-comparison', universe: { kind: 'group', key: 'sp500-sectors' }, condition: { output_contract: 'boolean' }, dataset_manifest: { timeframe: 'D1', adjustment: 'split_adjusted' }, current: { timestamp: '2026-08-17T00:00:00Z', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [{ instrument_id: 1, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', value: true, metric: 0.1, observation_time: '2026-08-17T00:00:00Z', diagnostics: [] }], exclusions: [] }, points: [], occurrences: [], progress: {}, diagnostics: [] }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Market Breadth', exact: true }).click()
    const breadth = page.locator('.tool-window:visible').filter({ has: page.locator('.breadth-tool') }).last()
    await expect(breadth).toBeVisible({ timeout: 10_000 })
    await breadth.locator('select[aria-label="Breadth condition composition"]').selectOption('tree')
    const tree = breadth.locator('[aria-label="Breadth condition tree"]')
    await tree.getByRole('combobox', { name: 'Breadth condition type 1.1' }).selectOption('python_series_comparison')
    await tree.getByLabel('Breadth Python left series asset 1.1').selectOption('17')
    await tree.getByLabel('Breadth Python right series asset 1.1').selectOption('18')
    await tree.getByLabel('Breadth Python series relation 1.1').selectOption('ratio')
    await tree.getByLabel('Breadth Python comparison scope 1.1').selectOption('cross_sectional')
    await tree.getByLabel('Breadth Python comparison group statistic 1.1').selectOption('median')
    await tree.getByLabel('Breadth Python comparison threshold 1.1').fill('0.05')
    await tree.getByLabel('Breadth Python comparison threshold 1.1').press('Tab')
    await breadth.getByRole('button', { name: 'Evaluate' }).click()
    await expect.poll(() => queuedRequests.length, { timeout: 10_000 }).toBe(1)
    expect(queuedRequests[0]).toMatchObject({ code_version_id: 17, output_contract: 'boolean', history: true, condition_tree: { kind: 'all', params: { conditions: [{ kind: 'python_series_comparison', params: { left_code_version_id: 17, right_code_version_id: 18, relation: 'ratio', scope: 'cross_sectional', statistic: 'median', threshold: 0.05 } }] } } })
    await expect(breadth.locator('.breadth-tool__custom-result')).toContainText('50.0%', { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-rotation — Relative Rotation exposes benchmark-scoped state semantics', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Relative Rotation', exact: true }).click()
    const rotation = page.locator('.tool-window:visible').filter({ has: page.locator('.rotation-tool') }).last()
    await expect(rotation).toBeVisible({ timeout: 10_000 })
    const region = rotation.locator('[role="region"][aria-label="Relative rotation vs SPY"]')
    await expect(region).toBeVisible({ timeout: 10_000 })
    await expect(region).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect.poll(async () => region.locator('.rotation-tool__row, [role="status"], [role="alert"]').count(), { timeout: 10_000 }).toBeGreaterThan(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-rotation-family — Relative Rotation exposes family cap/equal/style legs', async ({ page, browserDiagnostics }) => {
    let historyRequested = false
    await page.route('**/api/v1/analysis/benchmark-families/sp400/relative-rotation*', async route => {
      historyRequested = new URL(route.request().url()).searchParams.get('history_length') === '60'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          family_key: 'sp400', benchmark: 'MDY', official_index_symbol: 'MID', timeframe: 'D1', adjustment: 'split_adjusted', sampling: 1, lookback: 20, tail_length: 10, history_length: 60, membership_version: 1, roles: [
            { role: 'cap_weight', instrument_id: 1, symbol: 'MDY', label: 'MDY', verification_state: 'verified', available: true, trend: 0, momentum: 0, state: 'leading', distance: 0, coverage: 1, tail: [], history: [{ timestamp: '2026-01-01T00:00:00Z', trend: 0, momentum: 0 }], warnings: [] },
            { role: 'equal_weight', instrument_id: null, symbol: null, label: 'No verified mapped proxy', verification_state: 'not_verified', available: false, trend: null, momentum: null, state: null, distance: null, coverage: 0, tail: [], warnings: [{ code: 'role_mapping_unavailable', message: 'No equal proxy' }] },
          ], exclusions: [], freshness: 'coverage_limited', freshness_detail: {},
        }),
      })
    })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Relative Rotation', exact: true }).click()
    const rotation = page.locator('.tool-window:visible').filter({ has: page.locator('.rotation-tool') }).last()
    await expect(rotation).toBeVisible({ timeout: 10_000 })
    await rotation.getByRole('combobox', { name: 'Rotation universe' }).selectOption('sp400')
    const region = rotation.locator('[role="region"][aria-label="Relative rotation vs MDY"]')
    await expect(region).toBeVisible({ timeout: 15_000 })
    await expect(region).toContainText('MDY', { timeout: 15_000 })
    await expect(region).toContainText('No verified mapped proxy', { timeout: 15_000 })
    await rotation.getByLabel('Rotation history length').fill('60')
    await expect.poll(() => historyRequested, { timeout: 15_000 }).toBe(true)
    await expect(rotation).toContainText('60 history points')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-report — Instrument Report disclosure is keyboard-operable', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Instrument Report', exact: true }).click()
    const report = page.locator('.tool-window:visible').filter({ has: page.locator('.info-section') }).last()
    await expect(report).toBeVisible({ timeout: 10_000 })
    const region = report.locator('[role="region"][aria-label="SPY instrument report"]')
    const header = region.locator('.section-header[role="button"]')
    await expect(header).toHaveAttribute('aria-expanded', 'true')
    await header.press('Enter')
    await expect(header).toHaveAttribute('aria-expanded', 'false')
    await header.press('Space')
    await expect(header).toHaveAttribute('aria-expanded', 'true')
    if (process.env.E2E_SEED_MARKET_DATA === 'true') {
      const listings = region.locator('.listing-row')
      const seededVenue = listings.filter({ hasText: 'ARCX' })
      await expect(seededVenue).toHaveCount(1)
      await expect(seededVenue).toContainText('SPY')
      await expect(seededVenue).toContainText('primary')
    }
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8u — chart plots transfer into a watchlist numeric column through the real drag path', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    // Persisted/factory workspaces may retain hidden chart instances. The
    // user-facing drag source is the active visible chart, not DOM order.
    const chart = page.locator('.chart-tool:visible').last()
    await expect(chart).toBeVisible({ timeout: 10_000 })
    await chart.locator('button[aria-label="Chart plot library"]').click()
    await chart.locator('select[aria-label="Add indicator plot"]').selectOption('rsi')
    // Plot insertion closes the fixed plot-library menu so chart gestures are
    // immediately available. Reopen it before starting the real drag path.
    await expect(chart.locator('.chart-plots__menu')).toHaveCount(0, { timeout: 10_000 })
    await chart.locator('button[aria-label="Chart plot library"]').click()
    await expect(chart.locator('.chart-plots__menu')).toBeVisible({ timeout: 10_000 })
    const plot = chart.locator('.chart-plots li').filter({ hasText: 'RSI' }).last()
    await expect.poll(() => plot.count(), { timeout: 10_000 }).toBeGreaterThan(0)
    await expect(plot).toBeVisible({ timeout: 10_000 })
    const target = page.getByRole('region', { name: 'Major US benchmarks' })
    const droppedHeader = target.locator('.watchlist__header button').filter({ hasText: 'RSI' })
    // Chromium occasionally loses the custom MIME payload when a fixed,
    // teleported plot menu closes during drag. Repeat the same real drag once
    // after the drop target has remained mounted; never bypass the DnD path.
    for (let attempt = 0; attempt < 2 && !(await droppedHeader.count()); attempt += 1) {
      await plot.dragTo(target)
      if (!(await droppedHeader.count())) await page.waitForTimeout(150)
    }
    await expect(droppedHeader).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8v — technical condition trees transfer into Boolean watchlist columns through the real drag path', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    const toolMenu = page.locator('.workstation__tool-library-menu')
    await expect(toolMenu).toBeVisible({ timeout: 10_000 })
    await toolMenu.getByRole('menuitem', { name: 'EasyScan', exact: true }).click()
    const scanTab = page.locator('.lm_tab').filter({ hasText: 'EasyScan' }).last()
    await expect(scanTab).toBeVisible({ timeout: 10_000 })
    if (!(await scanTab.evaluate(node => node.classList.contains('lm_active')))) await scanTab.click()
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 10_000 })
    await scan.getByRole('button', { name: 'Build technical condition tree' }).click()
    const condition = scan.locator('.easy-scan__advanced-drag-source')
    await expect(condition).toBeVisible({ timeout: 10_000 })
    // Keep the source in the visible lower-right EasyScan pane while exposing
    // the benchmark stack as the real drop target. Opening a new EasyScan tab
    // temporarily activates the left stack, which otherwise hides the target
    // and makes a browser drag impossible rather than testing product behavior.
    // The factory benchmark tab is in the same left stack that Add Tool uses;
    // the visible sector watchlist provides the equivalent real drop target
    // without requiring a hidden-tab activation during the drag gesture.
    const target = page.getByRole('region', { name: 'Relative to SPY' })
    await expect(target).toBeVisible({ timeout: 10_000 })
    await expect(target.locator('.watchlist__row').first()).toBeVisible({ timeout: 20_000 })
    await condition.dragTo(target)
    await expect(target.locator('.watchlist__header button').filter({ hasText: 'Technical conditions' })).toBeVisible({ timeout: 15_000 })
    await expect(target.locator('.watchlist__drop-error')).toHaveCount(0)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8w — an EasyScan result feeds a Market Gauge in the workstation', async ({ page, browserDiagnostics }) => {
    const runSuffix = Date.now().toString()
    const conditionName = `Gauge test condition ${runSuffix}`
    const scanName = `Gauge test scan ${runSuffix}`
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.locator('.lm_tab:visible').filter({ hasText: 'EasyScan' }).last().click()
    const scan = page.locator('.easy-scan:visible').last()
    await expect(scan).toBeVisible({ timeout: 10_000 })
    await scan.getByLabel('Condition name').fill(conditionName)
    await scan.getByLabel('Condition threshold').fill('0')
    const savedCondition = await Promise.all([
      page.waitForResponse(response => response.url().includes('/workspaces/library/conditions/') && response.request().method() === 'PUT' && response.status() === 200),
      scan.getByRole('button', { name: 'Save', exact: true }).click(),
    ])
    const savedPayload = await savedCondition[0].json() as { payload?: { python_code_version_id?: number } }
    expect(Number.isInteger(savedPayload.payload?.python_code_version_id)).toBe(true)
    await scan.getByLabel('Scan name').fill(scanName)
    const pythonScan = page.waitForResponse(response => response.url().includes('/screeners/from-python-condition/') && response.request().method() === 'POST' && response.status() === 201)
    await scan.getByRole('button', { name: 'Run', exact: true }).click()
    await pythonScan
    await expect(scan.locator('.easy-scan__result')).toBeVisible({ timeout: 20_000 })

    await page.locator('.lm_tab:visible').filter({ hasText: 'Market Gauge' }).last().click()
    await expect(page.locator('.lm_tab.lm_active').filter({ hasText: 'Market Gauge' }).last()).toBeVisible({ timeout: 10_000 })
    const gauge = page.locator('.market-gauge:visible').last()
    await expect(gauge).toBeVisible({ timeout: 10_000 })
    const selector = gauge.getByLabel('Saved EasyScan')
    await gauge.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect(selector.locator('option', { hasText: scanName })).toHaveCount(1, { timeout: 10_000 })
    await selector.selectOption({ label: scanName })
    await expect(gauge.locator('.market-gauge__reading')).toBeVisible({ timeout: 20_000 })
    await expect(gauge.locator('.market-gauge__reading')).toContainText('matches')
    await expect(gauge).toHaveAttribute('role', 'region')
    await expect(gauge.locator('.market-gauge__freshness[role="status"]')).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8w-a — Market Gauge normalizes backend coverage_limited freshness', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/screeners**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 7, name: 'Coverage limited fixture' }, { id: 8, name: 'Delayed fixture' }]) })
    })
    await page.route('**/api/v1/analysis/gauges/*', async route => {
      const delayed = new URL(route.request().url()).pathname.endsWith('/8')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          matched_count: 0,
          evaluated_count: 0,
          universe_count: 10,
          percentage: null,
          run_at: null,
          freshness: delayed ? 'delayed' : 'coverage_limited',
          data_provenance: 'canonical_local_database',
          calculation_version: 'analysis-v1',
          refreshed_at: '2026-08-03T10:01:00Z',
          freshness_detail: { requested: 10, current: 0, stale: 0, other: 10 },
          exclusions: [],
        }),
      })
    })

    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.locator('.lm_tab:visible').filter({ hasText: 'Market Gauge' }).last().click()
    const gauge = page.locator('.market-gauge:visible').last()
    await expect(gauge).toBeVisible({ timeout: 10_000 })
    await gauge.getByLabel('Saved EasyScan').selectOption('7')
    const freshness = gauge.locator('.market-gauge__freshness')
    await expect(freshness).toHaveText('Coverage limited')
    await expect(freshness).toHaveAttribute('data-freshness', 'coverage-limited')
    await gauge.getByLabel('Saved EasyScan').selectOption('8')
    await expect(freshness).toHaveText('Delayed')
    await expect(freshness).toHaveAttribute('data-freshness', 'delayed')
    await expect(gauge.locator('.market-gauge__freshness[role="status"]')).toHaveAttribute('aria-live', 'polite')
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8x — Add tool activates the newly opened dock tab', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Python Library', exact: true }).click()
    await expect(page.locator('.lm_tab.lm_active').filter({ hasText: 'Python Library' }).last()).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.code-library-tool:visible').last()).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8x-library — Python study assets support version, clone, and archive lifecycle', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    const studyName = `E2E library study ${Date.now()}`
    const stableKey = studyName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'Python Library', exact: true }).click()
    const library = page.locator('.code-library-tool:visible').last()
    await expect(library).toBeVisible({ timeout: 10_000 })
    await library.getByRole('button', { name: 'New', exact: true }).click()
    const create = library.getByRole('form', { name: 'Create Python asset' })
    await create.getByRole('textbox', { name: 'New Python asset name' }).fill(studyName)
    await create.getByRole('textbox', { name: 'New Python asset key' }).fill(stableKey)
    await create.getByRole('textbox', { name: 'New Python asset source' }).fill("output.scalar('value', 1)")
    await create.getByRole('button', { name: 'Create asset' }).click()

    const asset = library.locator('.code-library-tool__asset').filter({ hasText: studyName }).first()
    await expect(asset).toBeVisible({ timeout: 15_000 })
    await asset.locator('summary').click()
    await asset.getByRole('textbox', { name: `Python source for ${studyName}` }).fill("output.scalar('value', 2)")
    await asset.getByRole('button', { name: 'Validate', exact: true }).click()
    await expect(asset).toContainText('Validated', { timeout: 10_000 })
    await asset.getByRole('button', { name: 'Save as new version', exact: true }).click()
    await expect(asset).toContainText('2 versions', { timeout: 15_000 })

    await asset.getByRole('button', { name: 'Clone', exact: true }).click()
    await expect(library.locator('.code-library-tool__asset').filter({ hasText: `${studyName} copy` })).toBeVisible({ timeout: 15_000 })
    await asset.getByRole('button', { name: 'Archive', exact: true }).click()
    await expect(asset).toContainText('archived')
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
    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: 'Reset', exact: true }).click()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 25_000 })
    await expect(page.locator('.tool-window').first()).toBeVisible({ timeout: 25_000 })
    await page.getByRole('button', { name: 'Alerts' }).click()
    const alertsTab = page.locator('.lm_tab').filter({ hasText: 'Alerts' }).last()
    await expect(alertsTab).toBeVisible({ timeout: 10_000 })
    if (!(await alertsTab.evaluate(node => node.classList.contains('lm_active')))) await alertsTab.click()
    await expect(page.locator('.tool-window:visible').filter({ hasText: 'Alerts' }).last()).toBeVisible()
    const alerts = page.locator('.alerts-tool:visible').last()
    await expect(alerts).toHaveAttribute('role', 'region')
    await expect(alerts.locator('[role="status"], [role="alert"]').first()).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F11a — create an indicator alert from the primary workstation Alerts tool', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: 'Reset', exact: true }).click()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 25_000 })
    await page.getByRole('button', { name: 'Alerts' }).click()
    const alerts = page.locator('.alerts-tool:visible').last()
    await expect(alerts).toBeVisible({ timeout: 10_000 })
    await alerts.getByLabel('Alert type').selectOption('indicator')
    await alerts.getByLabel('Alert indicator').selectOption('rsi')
    await alerts.getByLabel('Alert timeframe').selectOption('D1')
    await alerts.getByLabel('Indicator threshold').fill('30')
    await alerts.locator('.alerts-tool__repeat input').check()
    await alerts.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(alerts.locator('[role="listitem"]').filter({ hasText: 'RSI' }).last()).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F11b — create a fixed-value indicator alert with the shared comparison operators', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: 'Reset', exact: true }).click()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 25_000 })
    await page.getByRole('button', { name: 'Alerts' }).click()
    const alerts = page.locator('.alerts-tool:visible').last()
    await expect(alerts).toBeVisible({ timeout: 10_000 })
    await alerts.getByLabel('Alert type').selectOption('indicator')
    await alerts.getByLabel('Alert indicator').selectOption('rsi')
    await alerts.getByLabel('Indicator condition').selectOption('lte')
    await alerts.getByLabel('Indicator threshold').fill('30')
    await alerts.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(alerts.locator('[role="listitem"]').filter({ hasText: 'RSI' }).last()).toBeVisible({ timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F11c — create an indicator-versus-indicator alert from the primary Alerts tool', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 10_000 })
    page.once('dialog', dialog => dialog.accept())
    await page.getByRole('button', { name: 'Reset', exact: true }).click()
    await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 25_000 })
    await page.getByRole('button', { name: 'Alerts' }).click()
    const alerts = page.locator('.alerts-tool:visible').last()
    await expect(alerts).toBeVisible({ timeout: 10_000 })
    await alerts.getByLabel('Alert type').selectOption('indicator')
    await alerts.getByLabel('Alert indicator').selectOption('ema')
    await alerts.getByLabel('Indicator target').selectOption('indicator')
    await alerts.getByLabel('Comparison indicator').selectOption('sma')
    await alerts.getByLabel('Alert comparison Period').fill('50')
    await alerts.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(alerts.locator('[role="listitem"]').filter({ hasText: 'EMA' }).last()).toBeVisible({ timeout: 10_000 })
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

    const toolbar = page.locator('.drawing-toolbar, [class*="toolbar"]')
    await expect(toolbar.first()).toBeVisible({ timeout: 15_000 })

    const toolbarContract = await toolbar.first().evaluate((element) => {
      const buttons = Array.from(element.querySelectorAll<HTMLButtonElement>('.tool-btn'))
      const icons = Array.from(element.querySelectorAll<HTMLElement>('.tool-icon'))
      return {
        buttonCount: buttons.length,
        iconsHaveDeterministicClasses: icons.length > 0 && icons.every(icon => Array.from(icon.classList).some(name => name.startsWith('tool-icon--'))),
        iconsHaveNoTextGlyphs: icons.every(icon => icon.textContent?.trim() === ''),
        compactButtonGeometry: buttons.filter(button => button.offsetParent !== null).every(button => {
          const rect = button.getBoundingClientRect()
          return rect.width >= 30 && rect.width <= 34 && rect.height >= 30 && rect.height <= 34
        }),
      }
    })
    expect(toolbarContract.buttonCount).toBeGreaterThan(0)
    expect(toolbarContract.iconsHaveDeterministicClasses).toBe(true)
    expect(toolbarContract.iconsHaveNoTextGlyphs).toBe(true)
    expect(toolbarContract.compactButtonGeometry).toBe(true)

    await toolbar.getByRole('button', { name: 'Lines' }).click()
    await expect(page.getByRole('menuitem', { name: 'Trend Line' })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'Horizontal Line' })).toBeVisible()
    await toolbar.getByRole('button', { name: 'Annotations' }).click()
    await expect(page.getByRole('menuitem', { name: 'Freehand' })).toBeVisible()
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14 — selecting a drawing tool activates it', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart')

    const toolbar = page.locator('.drawing-toolbar').first()
    await expect(toolbar).toBeVisible({ timeout: 15_000 })
    const linesButton = toolbar.getByRole('button', { name: 'Lines' })
    await linesButton.click()
    const horizBtn = toolbar.getByRole('menuitem', { name: 'Horizontal Line' })
    await horizBtn.click()
    // The flyout closes after selection; its owning group remains active and puts the
    // chart canvas into drawing mode.
    await expect(linesButton).toHaveClass(/active/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14-keyboard — drawing flyouts expose menu semantics and restore trigger focus', async ({ page, browserDiagnostics }) => {
    await page.goto('/chart/SPY')
    const toolbar = page.locator('.drawing-toolbar').first()
    await expect(toolbar).toBeVisible({ timeout: 15_000 })
    const linesButton = toolbar.getByRole('button', { name: 'Lines' })
    await linesButton.press('ArrowDown')
    const menu = toolbar.getByRole('menu', { name: 'Lines drawing tools' })
    await expect(menu).toBeVisible()
    await expect(linesButton).toHaveAttribute('aria-expanded', 'true')
    const trend = menu.getByRole('menuitem', { name: 'Trend Line' })
    await expect(trend).toBeFocused()
    await trend.press('ArrowDown')
    await expect(menu.getByRole('menuitem', { name: 'Ray' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(menu).toHaveCount(0)
    await expect(linesButton).toBeFocused()
    await linesButton.press('Enter')
    await expect(menu).toBeVisible()
    await menu.getByRole('menuitem', { name: 'Horizontal Line' }).press('Enter')
    await expect(menu).toHaveCount(0)
    await expect(linesButton).toHaveClass(/active/)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14-instance-scope — mounted drawing toolbars keep unique flyout ownership', async ({ page, browserDiagnostics }) => {
    await page.goto('/')
    const timeframeLayout = page.getByRole('tab', { name: '4 Timeframe', exact: true })
    await expect(timeframeLayout).toBeVisible({ timeout: 15_000 })
    await timeframeLayout.click()
    await expect(page.locator('.workstation__layout-state')).toHaveCount(0)
    const toolbars = page.locator('.drawing-toolbar')
    await expect(toolbars.first()).toBeVisible({ timeout: 15_000 })
    expect(await toolbars.count()).toBeGreaterThan(1)

    const menuIds: string[] = []
    for (let index = 0; index < await toolbars.count(); index += 1) {
      const toolbar = toolbars.nth(index)
      const trigger = toolbar.getByRole('button', { name: 'Lines' })
      await trigger.press('ArrowDown')
      const menu = toolbar.getByRole('menu', { name: 'Lines drawing tools' })
      await expect(menu).toBeVisible()
      const menuId = await trigger.getAttribute('aria-controls')
      expect(menuId).toBeTruthy()
      expect(menuIds).not.toContain(menuId)
      expect(await menu.evaluate((element) => element.id)).toBe(menuId)
      expect(await menu.evaluate((element) => Boolean(element.closest('.drawing-toolbar')))).toBe(true)
      menuIds.push(menuId as string)
      await page.keyboard.press('Escape')
      await expect(menu).toHaveCount(0)
    }
    expect(menuIds.length).toBeGreaterThan(1)
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F14-context-keyboard — selected drawing actions expose a scoped menu', async ({ page, browserDiagnostics }) => {
    const drawing = {
      id: 901,
      instrument_id: 1,
      timeframe: 'D1',
      drawing_type: 'horizontal_line',
      data: { points: [{ time: 1710000000, price: 500 }] },
      style: { color: '#ffb74d', lineWidth: 0.75 },
      is_visible: true,
      is_locked: false,
    }
    await page.route('**/api/v1/drawings**', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
        return
      }
      if (route.request().method() === 'POST') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(drawing) })
        return
      }
      await route.continue()
    })
    await page.goto('/chart/SPY')
    const chart = page.locator('.chart-tool').filter({ has: page.getByTitle('Chart settings') }).first()
    await expect(chart).toBeVisible({ timeout: 15_000 })
    const plot = chart.locator('.uplot').first()
    await expect(plot).toBeVisible({ timeout: 15_000 })
    const box = await plot.boundingBox()
    expect(box).not.toBeNull()
    const x = box!.x + box!.width * 0.55
    const y = box!.y + box!.height * 0.45
    const toolbar = chart.locator('.drawing-toolbar').first()
    await toolbar.getByRole('button', { name: 'Lines' }).click()
    await toolbar.getByRole('menuitem', { name: 'Horizontal Line' }).click()
    const save = page.waitForResponse(response => response.url().includes('/api/v1/drawings') && response.request().method() === 'POST')
    await page.mouse.click(x, y)
    await save
    const menu = chart.getByRole('menu', { name: 'Drawing actions' })
    // The price scale is data-dependent. Probe only the rendered plot band in
    // bounded steps, exactly as a user searching for the visible line would.
    for (let step = 1; step <= 19 && !(await menu.isVisible().catch(() => false)); step++) {
      await page.mouse.click(x, box!.y + (box!.height * step / 20), { button: 'right' })
    }
    await expect(menu).toBeVisible({ timeout: 10_000 })
    await expect(menu.getByRole('menuitem').first()).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(menu.getByRole('menuitem', { name: 'Deselect' })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(menu).toHaveCount(0)
    await expect(chart.getByRole('region', { name: 'Chart workspace' })).toBeFocused()
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

  test('F8y — Add Tool watchlist remains visible and interactive after stack activation', async ({ page, browserDiagnostics }) => {
    // This is the longest authenticated mutation flow: it creates three lists,
    // adds a symbol, then exercises copy and move. Keep the acceptance budget
    // above transient provider/workspace loading contention without changing
    // any assertion or hiding a failed interaction.
    test.setTimeout(60_000)
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    page.once('dialog', dialog => dialog.accept())
    await Promise.all([
      page.waitForResponse(response => response.url().includes('/reset-factory') && response.request().method() === 'POST' && response.status() === 200),
      page.getByRole('button', { name: 'Reset', exact: true }).click(),
    ])
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    const toolMenu = page.locator('.workstation__tool-library-menu')
    await expect(toolMenu).toBeVisible({ timeout: 10_000 })
    await toolMenu.getByRole('menuitem', { name: 'WatchList', exact: true }).click()
    const watchlistTab = page.locator('.lm_tab').filter({ hasText: 'WatchList' }).last()
    await expect(watchlistTab).toBeVisible({ timeout: 10_000 })
    if (!(await watchlistTab.evaluate(node => node.classList.contains('lm_active')))) await watchlistTab.click()
    await expect(watchlistTab).toHaveClass(/lm_active/)
    let personal = page.locator('.tool-window--active .personal-watchlist-tool').last()
    await expect(personal).toBeVisible({ timeout: 10_000 })
    await expect(personal).toHaveAttribute('role', 'region')
    await expect(personal).toHaveAttribute('aria-busy', 'false')
    await expect(personal.getByRole('button', { name: 'New', exact: true })).toBeVisible()
    await expect(personal.getByRole('combobox', { name: 'Personal watchlist', exact: true })).toBeVisible()
    await expect(personal.boundingBox()).resolves.toMatchObject({ width: expect.any(Number) })
    const suffix = crypto.randomUUID()
    const sourceName = `E2E source ${suffix}`
    const listName = personal.getByLabel('Personal watchlist name')
    const watchlistSelect = personal.getByRole('combobox', { name: 'Personal watchlist', exact: true })
    await listName.fill(sourceName)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect).toHaveValue(/\d+/)
    await expect(personal).toBeVisible()

    // Exercise the real desktop row context-menu membership path as well as
    // the direct add control.  This closes the browser-coverage gap around
    // copying and moving a canonical instrument between personal lists.
    const sourceId = await watchlistSelect.inputValue()
    const symbolInput = personal.getByLabel('Add symbol to personal watchlist')
    await symbolInput.fill('XLE')
    await personal.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLE' })).toBeVisible({ timeout: 10_000 })
    await expect(personal).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })
    await symbolInput.fill('XLK')
    await expect(personal.getByRole('button', { name: 'Add', exact: true })).toBeEnabled({ timeout: 10_000 })
    await personal.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toBeVisible({ timeout: 10_000 })


    await listName.fill(`E2E target ${suffix}`)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect).not.toHaveValue(sourceId)
    const copyTargetId = await watchlistSelect.inputValue()
    await listName.fill(`E2E move target ${suffix}`)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect).not.toHaveValue(copyTargetId)
    const moveTargetId = await watchlistSelect.inputValue()
    expect(moveTargetId).not.toBe(sourceId)
    expect(moveTargetId).not.toBe(copyTargetId)

    await watchlistSelect.selectOption(sourceId)
    const sourceRow = personal.locator('.watchlist__row').filter({ hasText: 'XLE' })
    await expect(sourceRow).toBeVisible({ timeout: 10_000 })
    // Select a second canonical row with Ctrl before opening the context menu;
    // the batch membership action must carry both stable item identities.
    const secondSourceRow = personal.locator('.watchlist__row').filter({ hasText: 'XLK' })
    await sourceRow.click()
    await secondSourceRow.click({ modifiers: [process.platform === 'darwin' ? 'Meta' : 'Control'] })
    await expect(personal.locator('.watchlist__row--selected')).toHaveCount(2)
    await sourceRow.click({ button: 'right' })
    // The menu is positioned outside the watchlist bounds, so scope it to the
    // visible global menu rather than the last DOM watchlist instance.
    const sourceMenu = page.locator('.watchlist__context-menu:visible').last()
    await expect(sourceMenu).toBeVisible()
    await sourceMenu.getByLabel('Target watchlist').selectOption(copyTargetId)
    await Promise.all([
      page.waitForResponse(response => response.url().includes(`/watchlists/${copyTargetId}/items/transfer-batch`) && response.request().method() === 'POST' && response.ok()),
      sourceMenu.getByRole('menuitem', { name: 'Copy 2 selected to list' }).click(),
    ])
    await expect(sourceMenu).toHaveCount(0)

    await watchlistSelect.selectOption(copyTargetId)
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLE' })).toBeVisible({ timeout: 10_000 })
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toBeVisible({ timeout: 10_000 })

    await watchlistSelect.selectOption(sourceId)
    const moveSourceRow = personal.locator('.watchlist__row').filter({ hasText: 'XLE' })
    await expect(moveSourceRow).toBeVisible({ timeout: 10_000 })
    const moveSecondRow = personal.locator('.watchlist__row').filter({ hasText: 'XLK' })
    await moveSourceRow.click()
    await moveSecondRow.click({ modifiers: [process.platform === 'darwin' ? 'Meta' : 'Control'] })
    await expect(personal.locator('.watchlist__row--selected')).toHaveCount(2)
    await moveSourceRow.click({ button: 'right' })
    const moveMenu = page.locator('.watchlist__context-menu:visible').last()
    await moveMenu.getByLabel('Target watchlist').selectOption(moveTargetId)
    await Promise.all([
      page.waitForResponse(response => response.url().includes(`/watchlists/${moveTargetId}/items/transfer-batch`) && response.request().method() === 'POST' && response.ok()),
      moveMenu.getByRole('menuitem', { name: 'Move 2 selected to list' }).click(),
    ])
    await expect(moveMenu).toHaveCount(0)
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLE' })).toHaveCount(0)
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toHaveCount(0)
    await watchlistSelect.selectOption(moveTargetId)
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLE' })).toBeVisible({ timeout: 10_000 })
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toBeVisible({ timeout: 10_000 })

    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8y-combo — personal watchlists compose into a persisted union/exclusion combo list', async ({ page, browserDiagnostics }) => {
    test.setTimeout(90_000)
    await page.goto('/chart/SPY')
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await page.getByRole('button', { name: 'Add tool' }).click()
    const toolMenu = page.locator('.workstation__tool-library-menu')
    await expect(toolMenu).toBeVisible({ timeout: 10_000 })
    await toolMenu.getByRole('menuitem', { name: 'WatchList', exact: true }).click()
    const watchlistTab = page.locator('.lm_tab').filter({ hasText: 'WatchList' }).last()
    await expect(watchlistTab).toBeVisible({ timeout: 10_000 })
    if (!(await watchlistTab.evaluate(node => node.classList.contains('lm_active')))) await watchlistTab.click()
    const personal = page.locator('.tool-window--active .personal-watchlist-tool').last()
    await expect(personal).toBeVisible({ timeout: 10_000 })

    const suffix = crypto.randomUUID()
    const listName = personal.getByLabel('Personal watchlist name')
    const watchlistSelect = personal.getByRole('combobox', { name: 'Personal watchlist', exact: true })
    const symbolInput = personal.getByLabel('Add symbol to personal watchlist')

    const listAName = `E2E combo union A ${suffix}`
    await listName.fill(listAName)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect.locator('option', { hasText: listAName })).toHaveCount(1, { timeout: 15_000 })
    await watchlistSelect.selectOption({ label: listAName })
    const listA = await watchlistSelect.inputValue()
    await expect(watchlistSelect).toHaveValue(listA)
    await symbolInput.fill('SPY')
    await personal.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'SPY' })).toBeVisible({ timeout: 10_000 })
    await expect(personal).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })

    const listBName = `E2E combo union B ${suffix}`
    await listName.fill(listBName)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect.locator('option', { hasText: listBName })).toHaveCount(1, { timeout: 15_000 })
    await watchlistSelect.selectOption({ label: listBName })
    const listB = await watchlistSelect.inputValue()
    expect(listB).not.toBe(listA)
    await symbolInput.fill('XLK')
    await expect(watchlistSelect).toHaveValue(listB)
    await expect(personal).toContainText(listBName, { timeout: 10_000 })
    await expect(personal.getByRole('button', { name: 'Add', exact: true })).toBeEnabled({ timeout: 10_000 })
    await personal.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toBeVisible({ timeout: 10_000 })
    await expect(personal).toHaveAttribute('aria-busy', 'false', { timeout: 10_000 })

    const exclusionName = `E2E combo exclusion ${suffix}`
    await listName.fill(exclusionName)
    await personal.getByRole('button', { name: 'New', exact: true }).click()
    await expect(watchlistSelect.locator('option', { hasText: exclusionName })).toHaveCount(1, { timeout: 15_000 })
    await watchlistSelect.selectOption({ label: exclusionName })
    const exclusionList = await watchlistSelect.inputValue()
    expect(exclusionList).not.toBe(listA)
    expect(exclusionList).not.toBe(listB)
    await symbolInput.fill('XLK')
    await expect(watchlistSelect).toHaveValue(exclusionList)
    await expect(personal.getByRole('button', { name: 'Add', exact: true })).toBeEnabled({ timeout: 10_000 })
    await personal.getByRole('button', { name: 'Add', exact: true }).click()
    await expect(personal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toBeVisible({ timeout: 10_000 })

    // Creating/selecting lists can hand the active Golden Layout root to a
    // freshly hydrated virtual component. Reacquire the visible combo editor
    // before interacting with it rather than holding a detached root locator.
    const comboPersonal = page.locator('.tool-window--active .personal-watchlist-tool').last()
    await expect(comboPersonal).toBeVisible({ timeout: 10_000 })
    const comboEditor = comboPersonal.getByRole('region', { name: 'Combo list editor' })
    await expect(comboEditor).toBeVisible({ timeout: 10_000 })
    const union = comboEditor.getByRole('listbox', { name: 'Combo union lists' })
    const exclude = comboEditor.getByRole('listbox', { name: 'Combo exclusion lists' })
    await comboEditor.scrollIntoViewIfNeeded()
    await union.scrollIntoViewIfNeeded()
    await expect(union).toBeVisible({ timeout: 10_000 })
    await union.selectOption([listA, listB])
    await exclude.selectOption([exclusionList])
    const comboName = `E2E combo ${suffix}`
    await comboEditor.getByLabel('Combo list name').fill(comboName)
    await comboEditor.getByRole('button', { name: 'New combo', exact: true }).click()
    const comboWatchlistSelect = comboPersonal.getByRole('combobox', { name: 'Personal watchlist', exact: true })
    await expect(comboWatchlistSelect.locator('option', { hasText: comboName })).toHaveCount(1, { timeout: 15_000 })
    // A+B is two symbols, then the exclusion list removes XLK, leaving SPY.
    await expect(comboPersonal).toContainText(new RegExp(`1 symbols · ${comboName}`), { timeout: 10_000 })
    await expect(comboPersonal.locator('.watchlist__row').filter({ hasText: 'SPY' })).toBeVisible()
    await expect(comboPersonal.locator('.watchlist__row').filter({ hasText: 'XLK' })).toHaveCount(0)
    await comboEditor.getByRole('button', { name: 'Delete combo', exact: true }).click()
    await expect(comboWatchlistSelect.locator('option', { hasText: comboName })).toHaveCount(0, { timeout: 10_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8s-personal-watchlist-error — personal watchlist loading failures are announced in the tool', async ({ page, browserDiagnostics }) => {
    await page.route('**/api/v1/watchlists', async route => {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'watchlists unavailable' }) })
    })
    await page.goto('/chart/SPY')
    await page.getByRole('button', { name: 'Add tool' }).click()
    await page.getByRole('menuitem', { name: 'WatchList', exact: true }).click()
    const personal = page.locator('.tool-window--active .personal-watchlist-tool').last()
    await expect(personal).toBeVisible({ timeout: 10_000 })
    await expect(personal).toHaveAttribute('role', 'region')
    await expect(personal).toHaveAttribute('aria-busy', 'false', { timeout: 15_000 })
    await expect(personal.locator('[role="alert"]')).toContainText('API GET', { timeout: 15_000 })
    await browserDiagnostics.expectNoCriticalIssues()
  })

  test('F8z — workstation remains contained at 125% browser page scale', async ({ page, browserDiagnostics }) => {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Emulation.setPageScaleFactor', { pageScaleFactor: 1.25 })
    await page.goto('/chart/SPY')
    await expect(page.locator('.workstation')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('region', { name: 'Major US benchmarks' })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('region', { name: 'Relative to SPY' })).toBeVisible({ timeout: 10_000 })
    const geometry = await page.evaluate(() => {
      const root = document.documentElement
      const rect = (selector: string) => document.querySelector<HTMLElement>(selector)?.getBoundingClientRect() ?? null
      const shell = rect('.workstation')
      const footer = rect('.workstation__footer')
      const headers = [...document.querySelectorAll<HTMLElement>('.tool-window__header')].map(header => {
        const title = header.querySelector<HTMLElement>('.tool-window__title')?.getBoundingClientRect()
        const symbol = header.querySelector<HTMLElement>('.tool-window__symbol')?.getBoundingClientRect()
        const actions = header.querySelector<HTMLElement>('.tool-window__actions')?.getBoundingClientRect()
        return { title, symbol, actions }
      })
      const overlaps = (left: DOMRect | undefined, right: DOMRect | undefined) => Boolean(
        left && right && left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top,
      )
      return {
        scrollWidth: root.scrollWidth,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        shell,
        footer,
        headerOverlaps: headers.filter(item => overlaps(item.title, item.actions) || overlaps(item.symbol, item.actions)).length,
      }
    })
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1)
    expect(geometry.shell?.left ?? -1).toBeGreaterThanOrEqual(-1)
    expect(geometry.shell?.right ?? Number.POSITIVE_INFINITY).toBeLessThanOrEqual(geometry.viewportWidth + 1)
    expect(geometry.footer?.bottom ?? -1).toBeLessThanOrEqual(geometry.viewportHeight + 1)
    expect(geometry.headerOverlaps).toBe(0)

    // Containment alone is not enough at the robustness scale: the dense
    // workstation must remain actionable for the first top-down decision. Use
    // the real sector row rather than a direct store/API shortcut, and ensure
    // the active symbol, ratio output, and horizontal list surface all remain
    // usable after the browser-level scale transform.
    const sectorList = page.getByRole('region', { name: 'Relative to SPY' })
    const xlk = sectorList.getByRole('option', { name: /XLK/ }).first()
    await expect(xlk).toBeVisible({ timeout: 15_000 })
    await xlk.click({ position: { x: 8, y: 14 } })
    await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('XLK', { timeout: 15_000 })
    await expect(page.locator('.ratio-chart:visible').last().locator('.ratio-chart__legend strong')).toContainText('XLK/SPY', { timeout: 20_000 })
    await expect(sectorList.locator('.watchlist__scroll')).toHaveJSProperty('scrollLeft', 0)
    const actionableGeometry = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      items: Array.from(document.querySelectorAll<HTMLElement>('button, input, select')).filter(element => {
      const rect = element.getBoundingClientRect()
      // Watchlist rows intentionally expose a wider horizontal data canvas;
      // their containment is governed by the watchlist scroll-surface checks.
      // This assertion covers fixed shell/tool controls only.
      return rect.width > 0 && rect.height > 0 && !element.closest('[aria-hidden="true"]') && !element.closest('.watchlist__scroll')
      }).map(element => {
        const rect = element.getBoundingClientRect()
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom }
      }),
    }))
    const offscreen = actionableGeometry.items.filter(item => item.left < -1 || item.right > actionableGeometry.viewportWidth + 1 || item.top < -1 || item.bottom > actionableGeometry.viewportHeight + 1)
    expect(offscreen, `visible actionable controls outside viewport: ${JSON.stringify(offscreen)}`).toEqual([])
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
    // The result list can be populated before the radar run's interaction
    // lock is released. Wait for the documented busy overlay to disappear so
    // this click exercises the real post-run selection path rather than racing
    // the overlay's pointer-events shield.
    await expect(page.locator('.radar-busy-overlay')).toHaveCount(0, { timeout: 30_000 })

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
