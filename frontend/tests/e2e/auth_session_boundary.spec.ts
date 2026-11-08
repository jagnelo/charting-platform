import { test, expect, LoginPage } from './helpers'

const PASSWORD = process.env.TEST_PASS ?? 'E2ePassword123!'

function runFor(user: 'A' | 'B') {
  return {
    id: user === 'A' ? 91501 : 91502,
    created_at: '2026-11-06T12:00:00Z',
    status: 'completed',
    code_version_id: 1,
    run_config: {},
    dataset_manifest: {},
    artifact_count: 0,
    artifacts: [],
  }
}

function activeWorkspaceSnapshotContainsTools(value: unknown, toolTypes: string[], activeToolType?: string): boolean {
  if (!value || typeof value !== 'object') return false
  const snapshot = value as { settings?: { active_tab_key?: unknown }; tabs?: Array<{
    stable_key?: unknown
    active_window_key?: unknown
    windows?: Array<{ instance_key?: unknown; tool_type?: unknown }>
  }> }
  const activeKey = snapshot.settings?.active_tab_key
  const activeTab = snapshot.tabs?.find(tab => tab.stable_key === activeKey)
  if (!activeTab || !Array.isArray(activeTab.windows)) return false
  const required = new Set(toolTypes)
  const hasRequired = [...required].every(type => activeTab.windows?.some(window => window.tool_type === type))
  const activeWindow = activeTab.windows.find(window => window.instance_key === activeTab.active_window_key)
  return hasRequired && !!activeWindow && (!activeToolType || activeWindow.tool_type === activeToolType)
}

async function activateDockToolTab(page: import('@playwright/test').Page, title: string) {
  // GoldenLayout can leave an invisible duplicate tab node mounted in another
  // stack. Address the visible ordinary tab that the user can actually click.
  const tabs = page.locator(`.lm_tab[title="${title}"]:visible`)
  await expect(tabs).toHaveCount(1)
  const tab = tabs.first()
  await expect(tab).toBeVisible()
  if (!await tab.evaluate(element => element.classList.contains('lm_active'))) await tab.click()
  await expect(tab).toHaveClass(/lm_active/)
}

test('J12 session boundary isolates test-owned same-origin accounts, expired refresh, stores and late responses', async ({ page, request, loggedIn, browserDiagnostics }, testInfo) => {
  void loggedIn
  const nonce = `${testInfo.workerIndex}_${Date.now().toString(36)}`
  const userA = `session_a_${nonce}`
  const emailA = `session_a_${nonce}@example.com`
  const userB = `session_b_${nonce}`
  const emailB = `session_b_${nonce}@example.com`
  for (const account of [{ username: userA, email: emailA }, { username: userB, email: emailB }]) {
    const registered = await request.post('/api/v1/auth/register', { data: { ...account, password: PASSWORD } })
    expect([201, 409]).toContain(registered.status())
  }

  const context = page.context()
  let tokenA = ''
  let tokenB = ''
  let rejectNextAResearch = false
  let rejectNextRefresh = false
  let expiredResearchRequests = 0
  let expiredRefreshRequests = 0
  const drawingReadOwners: string[] = []
  const noteReadOwners: string[] = []
  let delayNextAResearch = false
  let releaseLateAResearch!: () => void
  let reportLateAResearchStarted!: () => void
  const lateAResearchStarted = new Promise<void>(resolve => { reportLateAResearchStarted = resolve })
  const lateAResearch = new Promise<void>(resolve => { releaseLateAResearch = resolve })

  await context.route('**/api/v1/auth/login', async route => {
    const credentials = route.request().postDataJSON() as { username?: string }
    const response = await route.fetch()
    const payload = await response.json() as { access_token?: string }
    if (credentials.username === userA) tokenA = payload.access_token ?? ''
    if (credentials.username === userB) tokenB = payload.access_token ?? ''
    await route.fulfill({ response, json: payload })
  })

  await context.route('**/api/v1/auth/refresh**', async route => {
    if (rejectNextRefresh) {
      rejectNextRefresh = false
      expiredRefreshRequests += 1
      return route.fulfill({ status: 401, json: { detail: 'Test-owned refresh expired' } })
    }
    return route.continue()
  })

  await context.route('**/api/v1/drawings**', async route => {
    if (route.request().method() !== 'GET') return route.continue()
    const authorization = route.request().headers().authorization ?? ''
    const owner = authorization === `Bearer ${tokenA}` ? 'A' : authorization === `Bearer ${tokenB}` ? 'B' : 'unknown'
    drawingReadOwners.push(owner)
    const instrumentId = Number(new URL(route.request().url()).searchParams.get('instrument_id'))
    await route.fulfill({ status: 200, json: [{
      id: owner === 'A' ? 41001 : 41002,
      instrument_id: instrumentId,
      timeframe: 'D1',
      drawing_type: 'horizontal_line',
      label: `private-drawing-${owner}`,
      data: { points: [{ time: 1_762_435_200, price: owner === 'A' ? 500 : 600 }] },
      style: { color: '#6bc0ef', lineWidth: 1 },
      is_visible: true,
      is_locked: false,
    }] })
  })

  await context.route('**/api/v1/notes/instruments/*', async route => {
    const authorization = route.request().headers().authorization ?? ''
    const owner = authorization === `Bearer ${tokenA}` ? 'A' : authorization === `Bearer ${tokenB}` ? 'B' : 'unknown'
    if (route.request().method() === 'GET') {
      noteReadOwners.push(owner)
      return route.fulfill({ status: 200, json: {
        content: `private-note-${owner}`,
        updated_at: '2026-11-06T12:00:00Z',
      } })
    }
    return route.fulfill({ status: 200, json: { updated_at: '2026-11-06T12:01:00Z' } })
  })

  await context.route('**/api/v1/research/runs**', async route => {
    if (route.request().method() !== 'GET' || new URL(route.request().url()).pathname !== '/api/v1/research/runs') {
      return route.continue()
    }
    const authorization = route.request().headers().authorization ?? ''
    if (authorization === `Bearer ${tokenA}` && rejectNextAResearch) {
      rejectNextAResearch = false
      expiredResearchRequests += 1
      return route.fulfill({ status: 401, json: { detail: 'Test-owned access token expired' } })
    }
    if (authorization === `Bearer ${tokenA}` && delayNextAResearch) {
      delayNextAResearch = false
      reportLateAResearchStarted()
      await lateAResearch
      try { await route.fulfill({ status: 200, json: [runFor('A')] }) } catch { /* the logged-out page may already have canceled this route */ }
      return
    }
    const user = authorization === `Bearer ${tokenA}` ? 'A' : authorization === `Bearer ${tokenB}` ? 'B' : 'A'
    await route.fulfill({ status: 200, json: [runFor(user)] })
  })

  // Both accounts are owned by this test. Enter A through the real login view;
  // the login response route captures its token before the shell mounts.
  const loginA = new LoginPage(page)
  await loginA.goto()
  await loginA.fillUsername(userA)
  await loginA.fillPassword(PASSWORD)
  await loginA.clickSignIn()
  await expect.poll(() => tokenA).toBeTruthy()
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await expect.poll(() => drawingReadOwners.includes('A')).toBe(true)

  await page.getByRole('button', { name: 'Add tool' }).click()
  const noteToolSnapshotA = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/v1\/workspaces\/\d+\/snapshot$/.test(new URL(response.url()).pathname)
    && activeWorkspaceSnapshotContainsTools(response.request().postDataJSON(), ['notes'], 'notes'))
  await page.getByRole('menuitem', { name: 'Notes', exact: true }).click()
  const acknowledgedNotesSnapshot = await noteToolSnapshotA
  expect(acknowledgedNotesSnapshot.ok()).toBe(true)
  expect(activeWorkspaceSnapshotContainsTools(await acknowledgedNotesSnapshot.json(), ['notes'], 'notes')).toBe(true)
  const notesA = page.getByRole('region', { name: /notes$/i })
  await expect(notesA).toBeVisible()
  await expect(notesA.getByRole('textbox', { name: 'Instrument note' })).toHaveValue('private-note-A')

  await page.getByRole('button', { name: 'Add tool' }).click()
  const resultsToolSnapshotA = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/v1\/workspaces\/\d+\/snapshot$/.test(new URL(response.url()).pathname)
    && activeWorkspaceSnapshotContainsTools(response.request().postDataJSON(), ['notes', 'research_results'], 'research_results'))
  await page.getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  const acknowledgedResultsSnapshot = await resultsToolSnapshotA
  expect(acknowledgedResultsSnapshot.ok()).toBe(true)
  const acknowledgedResultsBody = await acknowledgedResultsSnapshot.json()
  expect(activeWorkspaceSnapshotContainsTools(acknowledgedResultsBody, ['notes', 'research_results'], 'research_results')).toBe(true)
  const workspaceId = Number(new URL(acknowledgedResultsSnapshot.url()).pathname.match(/workspaces\/(\d+)\/snapshot$/)?.[1])
  expect(workspaceId).toBeGreaterThan(0)
  await expect(page.getByRole('status', { name: 'Workspace save status' })).toHaveText('Workspace saved')
  const persistedWorkspaceResponse = await request.get(`/api/v1/workspaces/${workspaceId}`, {
    headers: { authorization: `Bearer ${tokenA}` },
  })
  expect(persistedWorkspaceResponse.ok()).toBe(true)
  expect(activeWorkspaceSnapshotContainsTools(await persistedWorkspaceResponse.json(), ['notes', 'research_results'], 'research_results')).toBe(true)
  const resultsA = page.getByRole('region', { name: 'Study Lab research results' })
  await expect(resultsA).toBeVisible()
  await expect(resultsA).toContainText('Run #91501')

  // A failed refresh is one terminal session boundary: tokens clear, private
  // UI unmounts, and the app settles at login instead of looping unauthenticated
  // requests/remounts.
  browserDiagnostics.allowExpectedUnauthorizedResponses(2)
  rejectNextAResearch = true
  rejectNextRefresh = true
  await page.getByRole('region', { name: 'Study Lab research results' }).getByRole('button', { name: 'Refresh' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect.poll(() => expiredResearchRequests).toBe(1)
  await expect.poll(() => expiredRefreshRequests).toBe(1)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token'))).toBeNull()
  await expect(page.locator('.workspace-layout-host')).toHaveCount(0)

  await loginA.loginAs(userA, PASSWORD)
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  const restoredResultsA = page.getByRole('region', { name: 'Study Lab research results' })
  await expect(restoredResultsA).toBeVisible()
  await expect(restoredResultsA).toContainText('Run #91501')
  // Results is the saved active tab. Notes remains in the same saved stack and
  // must be activated as an ordinary dock tab before its editor is visible.
  await activateDockToolTab(page, 'Notes')
  await expect(page.getByRole('region', { name: /notes$/i }).getByRole('textbox', { name: 'Instrument note' }))
    .toHaveValue('private-note-A')
  const persistedResultsReactivation = page.waitForResponse(response => response.request().method() === 'PUT'
    && new URL(response.url()).pathname === `/api/v1/workspaces/${workspaceId}/snapshot`
    && activeWorkspaceSnapshotContainsTools(response.request().postDataJSON(), ['notes', 'research_results'], 'research_results'))
  await activateDockToolTab(page, 'Study Results')
  const resultsReactivationSnapshot = await persistedResultsReactivation
  expect(resultsReactivationSnapshot.ok()).toBe(true)
  expect(activeWorkspaceSnapshotContainsTools(await resultsReactivationSnapshot.json(), ['notes', 'research_results'], 'research_results')).toBe(true)
  await expect(restoredResultsA).toContainText('Run #91501')

  // A second same-origin window holds its own A session cache. Cross-window
  // logout must clear that cache and return it to the login route as well.
  const secondWindow = await context.newPage()
  await secondWindow.goto('/chart')
  await expect(secondWindow.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  const restoredResultsInSecondWindow = secondWindow.getByRole('region', { name: 'Study Lab research results' })
  await expect(restoredResultsInSecondWindow).toBeVisible()
  await expect(restoredResultsInSecondWindow).toContainText('Run #91501')
  await activateDockToolTab(secondWindow, 'Notes')
  await expect(secondWindow.getByRole('region', { name: /notes$/i }).getByRole('textbox', { name: 'Instrument note' }))
    .toHaveValue('private-note-A')
  await activateDockToolTab(secondWindow, 'Study Results')
  await expect(restoredResultsInSecondWindow).toBeVisible()
  await expect(restoredResultsInSecondWindow).toContainText('Run #91501')

  const firstWindowAuthenticatedUsers: string[] = []
  const firstWindowWorkspaceReads: Array<{ owner: 'A' | 'B'; workspaceId: number }> = []
  page.on('response', async response => {
    const url = new URL(response.url())
    if (!response.ok()) return
    const authorization = response.request().headers().authorization
    const owner = authorization === `Bearer ${tokenA}` ? 'A' : authorization === `Bearer ${tokenB}` ? 'B' : null
    if (url.pathname === '/api/v1/auth/me' && owner === 'B') {
      try {
        const payload = await response.json() as { username?: string }
        if (payload.username) firstWindowAuthenticatedUsers.push(payload.username)
      } catch {
        // The assertion below fails if the actual user profile was not readable.
      }
      return
    }
    if (url.pathname === '/api/v1/workspaces/default' && owner) {
      try {
        const payload = await response.json() as { id?: number }
        if (typeof payload.id === 'number' && Number.isSafeInteger(payload.id)) {
          firstWindowWorkspaceReads.push({ owner, workspaceId: payload.id })
        }
      } catch {
        // The owner-scoped workspace assertion below fails if no valid body arrived.
      }
    }
  })

  // Start a stale response while A's private results are visible.
  const refreshA = page.getByRole('region', { name: 'Study Lab research results' }).getByRole('button', { name: 'Refresh' })
  delayNextAResearch = true
  await refreshA.click()
  await lateAResearchStarted

  // Direct navigation to the public login route in another window is also an
  // account boundary. No explicit Sign out event is sent before B replaces
  // the shared browser tokens.
  browserDiagnostics.allowExpectedAuthSessionChangedAbortErrors(1)
  const workspaceReadsBeforeB = firstWindowWorkspaceReads.length
  const noteReadsBeforeB = noteReadOwners.length
  await secondWindow.goto('/login')
  await expect(secondWindow).toHaveURL(/\/login$/)
  const login = new LoginPage(secondWindow)
  await login.fillUsername(userB)
  await login.fillPassword(PASSWORD)
  await login.clickSignIn()
  await secondWindow.waitForFunction((priorToken: string) => {
    const token = localStorage.getItem('access_token')
    return Boolean(token && token !== priorToken)
  }, tokenA)
  tokenB = await secondWindow.evaluate(() => localStorage.getItem('access_token') ?? '')
  await secondWindow.waitForURL('**/chart**', { timeout: 10_000 })
  await expect.poll(() => firstWindowAuthenticatedUsers).toContain(userB)
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  expect(await secondWindow.evaluate(() => localStorage.getItem('access_token'))).not.toBe(tokenA)
  expect(tokenB).toBeTruthy()
  await expect.poll(() => firstWindowWorkspaceReads.slice(workspaceReadsBeforeB).some(read => read.owner === 'B')).toBe(true)
  const bWorkspaceReads = firstWindowWorkspaceReads.slice(workspaceReadsBeforeB).filter(read => read.owner === 'B')
  expect(bWorkspaceReads.at(-1)?.workspaceId).toBeGreaterThan(0)
  expect(bWorkspaceReads.at(-1)?.workspaceId).not.toBe(workspaceId)

  // B starts from a distinct workspace. Its factory layout already contains a
  // Notes pane, but that panel is hidden while Results is the saved active tab.
  // Activate it through the ordinary dock tab before requiring its lazy read.
  await expect(page.locator('.note-tool')).toHaveCount(1)
  await expect(page.getByText('private-note-A', { exact: true })).toHaveCount(0)
  await expect(page.locator('.research-results-tool')).toHaveCount(0)
  await activateDockToolTab(page, 'Notes')
  await expect.poll(() => noteReadOwners.slice(noteReadsBeforeB)).toContain('B')
  expect(noteReadOwners.slice(noteReadsBeforeB)).not.toContain('A')
  const notesB = page.getByRole('region', { name: /notes$/i })
  await expect(notesB.getByRole('textbox', { name: 'Instrument note' })).toHaveValue('private-note-B')
  await expect(notesB).not.toContainText('private-note-A')

  await page.getByRole('button', { name: 'Add tool' }).click()
  const resultsToolSnapshotB = page.waitForResponse(response => response.request().method() === 'PUT'
    && /\/api\/v1\/workspaces\/\d+\/snapshot$/.test(new URL(response.url()).pathname) && response.ok())
  await page.getByRole('menuitem', { name: 'Study Results', exact: true }).click()
  await resultsToolSnapshotB
  const resultsB = page.getByRole('region', { name: 'Study Lab research results' })
  await expect(resultsB).toContainText('Run #91502')

  releaseLateAResearch()
  await expect(resultsB).toContainText('Run #91502')
  await expect(resultsB).not.toContainText('Run #91501')
  await activateDockToolTab(page, 'Notes')
  await expect(notesB.getByRole('textbox', { name: 'Instrument note' })).toHaveValue('private-note-B')
  await expect.poll(() => drawingReadOwners.filter(owner => owner === 'B').length).toBeGreaterThan(0)
  await expect.poll(() => drawingReadOwners).toContain('B')
  await page.getByRole('button', { name: /Sign out/ }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(secondWindow).toHaveURL(/\/login$/, { timeout: 10_000 })
  await secondWindow.close()
})
