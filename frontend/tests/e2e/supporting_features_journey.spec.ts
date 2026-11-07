import { test, expect } from './helpers'
import type { Page } from '@playwright/test'

async function openApplicationMenuItem(page: Page, label: string) {
  const trigger = page.getByRole('button', { name: 'Open application navigation' })
  await trigger.focus()
  await trigger.press('Enter')
  const menu = page.getByRole('menu', { name: 'Application navigation' })
  await expect(menu).toBeVisible()
  const item = menu.getByRole('menuitem', { name: label, exact: true })
  await item.focus()
  await item.press('Enter')
}

async function authorizationHeaders(page: Page): Promise<Record<string, string>> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'))
  expect(token, 'the isolated E2E account should have an authenticated session').toBeTruthy()
  return { Authorization: `Bearer ${token}` }
}

test('supporting notes — save, edit, reload, and return without leaking between symbols', async ({ page, loggedIn, browserDiagnostics }) => {
  void loggedIn
  await page.goto('/chart/SPY')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 15_000 })

  const initialNoteRead = page.waitForResponse(response =>
    /^\/api\/v1\/notes\/instruments\/\d+$/.test(new URL(response.url()).pathname)
    && response.request().method() === 'GET' && response.ok(),
  )
  await page.getByRole('button', { name: 'Add tool' }).click()
  await page.getByRole('menuitem', { name: 'Notes', exact: true }).click()
  const initialReadResponse = await initialNoteRead
  const instrumentId = Number(new URL(initialReadResponse.url()).pathname.split('/').at(-1))
  expect(Number.isInteger(instrumentId)).toBe(true)
  expect(await initialReadResponse.json()).toBeNull()
  const note = page.getByRole('region', { name: 'SPY notes' })
  const editor = note.getByRole('textbox', { name: 'Instrument note' })
  await expect(editor).toBeEnabled({ timeout: 10_000 })
  await expect(note.locator('.note-tool__status')).toContainText('No note')

  const firstDraft = `supporting-note-${Date.now().toString(36)}`
  const editedDraft = `${firstDraft}-edited`
  await editor.fill(firstDraft)
  await expect(note.locator('.note-tool__status')).toContainText('Saved', { timeout: 10_000 })
  await editor.fill(editedDraft)
  await expect(note.locator('.note-tool__status')).toContainText('Saved', { timeout: 10_000 })

  const headers = await authorizationHeaders(page)
  const saved = await page.request.get(`/api/v1/notes/instruments/${instrumentId}`, { headers })
  expect(saved.ok()).toBe(true)
  expect((await saved.json() as { content: string }).content).toBe(editedDraft)

  await page.reload()
  const reloadedNote = page.getByRole('region', { name: 'SPY notes' })
  await expect(reloadedNote.getByRole('textbox', { name: 'Instrument note' })).toHaveValue(editedDraft, { timeout: 15_000 })

  await page.goto('/chart/QQQ')
  const qqqNote = page.getByRole('region', { name: 'QQQ notes' })
  await expect(qqqNote.getByRole('textbox', { name: 'Instrument note' })).toHaveValue('', { timeout: 15_000 })
  await expect(qqqNote.locator('.note-tool__status')).toContainText('No note')

  await page.goto('/chart/SPY')
  await expect(page.getByRole('region', { name: 'SPY notes' }).getByRole('textbox', { name: 'Instrument note' })).toHaveValue(editedDraft, { timeout: 15_000 })
  await browserDiagnostics.expectNoCriticalIssues()
})

test('supporting watchlists — keyboard create, membership, rename recovery, reload, and confirmed delete', async ({ page, loggedIn, browserDiagnostics }) => {
  void loggedIn
  const nonce = `${test.info().workerIndex}_${Date.now().toString(36)}`
  const firstName = `journey-${nonce}-one`
  const secondName = `journey-${nonce}-two`
  const renamedName = `journey-${nonce}-renamed`

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await openApplicationMenuItem(page, 'Watchlist')
  await expect(page.locator('.watchlist-view')).toBeVisible({ timeout: 10_000 })

  const headers = await authorizationHeaders(page)
  const initialLists = await page.request.get('/api/v1/watchlists', { headers })
  expect(initialLists.ok()).toBe(true)
  const baselineLists = await initialLists.json() as Array<{ id: number; name: string }>
  const baselineListIds = baselineLists.map(list => list.id).sort((a, b) => a - b)

  await page.getByRole('button', { name: '+ New' }).click()
  const createName = page.getByPlaceholder('Name…')
  await createName.fill(`cancel-${nonce}`)
  await createName.press('Escape')
  await expect(page.getByPlaceholder('Name…')).toHaveCount(0)
  const afterCancel = await page.request.get('/api/v1/watchlists', { headers })
  expect((await afterCancel.json() as Array<{ id: number }>).map(list => list.id).sort((a, b) => a - b)).toEqual(baselineListIds)

  await page.getByRole('button', { name: '+ New' }).click()
  const createFirst = page.getByPlaceholder('Name…')
  await createFirst.fill(firstName)
  const createFirstResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/watchlists'
    && response.request().method() === 'POST',
  )
  await createFirst.press('Enter')
  const firstCreated = await createFirstResponse
  expect(firstCreated.status()).toBe(200)
  const firstList = await firstCreated.json() as { id: number; name: string }
  expect(firstList.name).toBe(firstName)

  await page.getByRole('button', { name: '+ New' }).click()
  const createSecond = page.getByPlaceholder('Name…')
  await createSecond.fill(secondName)
  const createSecondResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/watchlists'
    && response.request().method() === 'POST',
  )
  await createSecond.press('Enter')
  const secondCreated = await createSecondResponse
  expect(secondCreated.status()).toBe(200)
  const secondList = await secondCreated.json() as { id: number; name: string }
  expect(secondList.name).toBe(secondName)

  const firstItem = page.locator('.wls-item').filter({ hasText: firstName })
  await firstItem.getByRole('button', { name: 'More options' }).click()
  await firstItem.getByRole('button', { name: 'Rename', exact: true }).click()
  const rename = firstItem.locator('.wls-rename-input')
  await rename.fill(secondName)
  browserDiagnostics.allowExpectedWatchlistConflictResponses(1)
  const duplicateRename = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/watchlists/${firstList.id}`
    && response.request().method() === 'PATCH',
  )
  await rename.press('Enter')
  const rejectedRename = await duplicateRename
  expect(rejectedRename.status()).toBe(409)
  await expect(firstItem.locator('.wls-rename-error')).toContainText(/name|already|exists|unique|409/i)
  await rename.press('Escape')
  await expect(firstItem.locator('.wlsi-name')).toHaveText(firstName)

  const search = page.getByRole('textbox', { name: 'Symbol…' })
  await search.fill('SPY')
  const spyChoice = page.getByRole('option').filter({ hasText: /^SPY\b/ }).first()
  await expect(spyChoice).toBeVisible({ timeout: 10_000 })
  const addItemResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/watchlists/${secondList.id}/items`
    && response.request().method() === 'POST',
  )
  await spyChoice.click()
  const added = await addItemResponse
  expect(added.status()).toBe(200)
  await expect(page.locator('.wlm-item').filter({ hasText: 'SPY' })).toBeVisible()

  await page.reload()
  await expect(page.locator('.watchlist-view')).toBeVisible({ timeout: 10_000 })
  const refreshedSecond = page.locator('.wls-item').filter({ hasText: secondName })
  await expect(refreshedSecond).toBeVisible()
  await refreshedSecond.click()
  await expect(page.locator('.wlm-title')).toHaveText(secondName)
  await expect(page.locator('.wlm-item').filter({ hasText: 'SPY' })).toBeVisible()

  await refreshedSecond.getByRole('button', { name: 'More options' }).click()
  await refreshedSecond.getByRole('button', { name: 'Rename', exact: true }).click()
  const validRename = refreshedSecond.locator('.wls-rename-input')
  await validRename.fill(renamedName)
  const renameResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/watchlists/${secondList.id}`
    && response.request().method() === 'PATCH',
  )
  await validRename.press('Enter')
  expect((await renameResponse).ok()).toBe(true)
  const renamedItem = page.locator('.wls-item').filter({ hasText: renamedName })
  await expect(renamedItem).toBeVisible()

  await renamedItem.getByRole('button', { name: 'More options' }).click()
  await renamedItem.getByRole('button', { name: 'Delete', exact: true }).click()
  const confirmation = page.getByText(`Delete watchlist "${renamedName}"?`, { exact: true })
  await expect(confirmation).toBeVisible()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(renamedItem).toBeVisible()

  await renamedItem.getByRole('button', { name: 'More options' }).click()
  await renamedItem.getByRole('button', { name: 'Delete', exact: true }).click()
  const deleteResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/watchlists/${secondList.id}`
    && response.request().method() === 'DELETE',
  )
  await page.getByRole('button', { name: 'Delete', exact: true }).last().click()
  expect((await deleteResponse).ok()).toBe(true)
  const remaining = await page.request.get('/api/v1/watchlists', { headers })
  const remainingLists = await remaining.json() as Array<{ id: number; name: string }>
  expect(remainingLists.map(list => list.id)).toContain(firstList.id)
  expect(remainingLists.map(list => list.id)).not.toContain(secondList.id)

  const firstAgain = page.locator('.wls-item').filter({ hasText: firstName })
  await firstAgain.getByRole('button', { name: 'More options' }).click()
  await firstAgain.getByRole('button', { name: 'Delete', exact: true }).click()
  const deleteFirst = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/watchlists/${firstList.id}`
    && response.request().method() === 'DELETE',
  )
  await page.getByRole('button', { name: 'Delete', exact: true }).last().click()
  expect((await deleteFirst).ok()).toBe(true)
  const afterCleanup = await page.request.get('/api/v1/watchlists', { headers })
  expect((await afterCleanup.json() as Array<{ id: number }>).map(list => list.id).sort((a, b) => a - b)).toEqual(baselineListIds)
  if (baselineListIds.length === 0) await expect(page.getByText('No watchlists yet', { exact: true })).toBeVisible()
  await browserDiagnostics.expectNoCriticalIssues()
})

test('supporting alerts — create a non-triggering rule, edit, pause/resume, reload, and delete', async ({ page, loggedIn, browserDiagnostics }) => {
  void loggedIn
  await page.goto('/chart/SPY')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('combobox', { name: 'Active symbol' })).toHaveValue('SPY', { timeout: 15_000 })
  await page.getByRole('button', { name: 'Alerts', exact: true }).click()
  const alertTool = page.getByRole('region', { name: 'SPY alerts' })
  await expect(alertTool).toBeVisible({ timeout: 10_000 })
  const add = alertTool.getByRole('button', { name: 'Add', exact: true })
  await expect(add).toBeDisabled()

  const threshold = '999999999'
  await alertTool.getByRole('textbox', { name: 'Alert price' }).fill(threshold)
  const createResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/alerts/price'
    && response.request().method() === 'POST',
  )
  await add.click()
  const created = await createResponse
  expect(created.status()).toBe(201)
  const alert = await created.json() as { id: number; instrument_id: number; status: string; threshold_price: number }
  expect(alert.instrument_id).toBeGreaterThan(0)
  expect(alert.status).toBe('active')
  expect(Number(alert.threshold_price)).toBe(Number(threshold))

  await openApplicationMenuItem(page, 'Alerts')
  await expect(page.locator('.alerts-view')).toBeVisible({ timeout: 10_000 })
  const row = page.locator('.alerts-view .alerts-table tbody tr').filter({ hasText: 'SPY' })
  await expect(row).toHaveCount(1)
  const editedNote = `journey-alert-${Date.now().toString(36)}`
  const notes = row.locator('.td-notes input')
  await notes.fill(editedNote)
  const noteUpdate = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/alerts/price/${alert.id}`
    && response.request().method() === 'PATCH',
  )
  await notes.press('Tab')
  expect((await noteUpdate).ok()).toBe(true)

  const pause = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/alerts/price/${alert.id}`
    && response.request().method() === 'PATCH',
  )
  await row.getByRole('button', { name: 'Pause' }).click()
  expect((await pause).ok()).toBe(true)
  await expect(row.locator('.status-badge')).toHaveText('paused')

  await page.reload()
  const persistedRow = page.locator('.alerts-view .alerts-table tbody tr').filter({ hasText: 'SPY' })
  await expect(persistedRow).toHaveCount(1)
  await expect(persistedRow.locator('.td-notes input')).toHaveValue(editedNote)
  await expect(persistedRow.locator('.status-badge')).toHaveText('paused')

  const resume = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/alerts/price/${alert.id}`
    && response.request().method() === 'PATCH',
  )
  await persistedRow.getByRole('button', { name: 'Resume' }).click()
  expect((await resume).ok()).toBe(true)
  await expect(persistedRow.locator('.status-badge')).toHaveText('active')
  const deleteResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/v1/alerts/price/${alert.id}`
    && response.request().method() === 'DELETE',
  )
  await persistedRow.getByRole('button', { name: 'Delete' }).click()
  expect((await deleteResponse).status()).toBe(204)
  await expect(page.getByText('No price alerts', { exact: true })).toBeVisible()

  const headers = await authorizationHeaders(page)
  const remaining = await page.request.get('/api/v1/alerts/price', { headers })
  expect(remaining.ok()).toBe(true)
  expect((await remaining.json() as Array<{ id: number }>).some(item => item.id === alert.id)).toBe(false)
  await browserDiagnostics.expectNoCriticalIssues()
})

test('supporting settings — discover preferences, manage an isolated preset, and leave browser notifications untouched', async ({ page, loggedIn, browserDiagnostics }) => {
  void loggedIn
  const headers = await authorizationHeaders(page)
  const before = await page.request.get('/api/v1/presets', { headers })
  expect(before.ok()).toBe(true)
  const baselinePresets = await before.json() as Array<{ id: number; name: string; description: string | null; indicators: unknown[]; is_default: boolean }>
  const baselineDefault = baselinePresets.find(item => item.is_default)
  const presetName = `journey-preset-${Date.now().toString(36)}`

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await openApplicationMenuItem(page, 'Settings')
  await expect(page.locator('.settings-view')).toBeVisible({ timeout: 10_000 })
  if (baselinePresets.length === 0) {
    await expect(page.getByText('No presets saved yet. Create them from the chart view.', { exact: true })).toBeVisible()
  }

  await page.goto('/legacy/chart/SPY')
  await expect(page.locator('.chart-view')).toBeVisible({ timeout: 15_000 })
  const savePreset = page.getByRole('button', { name: 'Save indicator preset' })
  await expect(savePreset).toBeVisible({ timeout: 10_000 })
  await savePreset.click()
  const dialog = page.getByRole('dialog', { name: 'Save Indicator Preset' })
  await expect(dialog).toBeVisible()
  const canceledPresetName = `${presetName}-canceled`
  await dialog.getByRole('textbox', { name: 'Preset name' }).fill(canceledPresetName)
  await dialog.getByRole('textbox', { name: 'Preset name' }).press('Escape')
  await expect(dialog).toHaveCount(0)
  const afterCancel = await page.request.get('/api/v1/presets', { headers })
  expect((await afterCancel.json() as Array<{ name: string }>).some(item => item.name === canceledPresetName)).toBe(false)

  await savePreset.click()
  const saveDialog = page.getByRole('dialog', { name: 'Save Indicator Preset' })
  await expect(saveDialog).toBeVisible()
  await saveDialog.getByRole('textbox', { name: 'Preset name' }).fill(presetName)
  const createPresetResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/v1/presets'
    && response.request().method() === 'POST',
  )
  await saveDialog.getByRole('button', { name: 'Save', exact: true }).click()
  const createdResponse = await createPresetResponse
  expect(createdResponse.status()).toBe(200)
  const preset = await createdResponse.json() as { id: number; name: string; is_default: boolean }
  expect(preset.name).toBe(presetName)

  await page.goto('/chart')
  await expect(page.locator('.workspace-layout-host')).toBeVisible({ timeout: 15_000 })
  await openApplicationMenuItem(page, 'Settings')
  await expect(page.locator('.settings-view')).toBeVisible({ timeout: 10_000 })
  const presetRow = page.locator('.preset-row').filter({ hasText: presetName })
  await expect(presetRow).toBeVisible()
  await presetRow.getByRole('button', { name: 'Set Default' }).click()
  await expect(presetRow).toContainText('default')
  const persisted = await page.request.get('/api/v1/presets', { headers })
  const persistedPresets = await persisted.json() as Array<{ id: number; is_default: boolean }>
  expect(persistedPresets.find(item => item.id === preset.id)?.is_default).toBe(true)

  await page.reload()
  const reloadedRow = page.locator('.preset-row').filter({ hasText: presetName })
  await expect(reloadedRow).toContainText('default')
  await reloadedRow.getByRole('button', { name: 'Delete' }).click()
  const afterDelete = await page.request.get('/api/v1/presets', { headers })
  const afterDeletePresets = await afterDelete.json() as Array<{ id: number; name: string; description: string | null; indicators: unknown[]; is_default: boolean }>
  expect(afterDeletePresets.some(item => item.id === preset.id)).toBe(false)
  if (baselineDefault) {
    const previousDefaultRow = page.locator('.preset-row').filter({ hasText: baselineDefault.name })
    await previousDefaultRow.getByRole('button', { name: 'Set Default' }).click()
    await expect(previousDefaultRow).toContainText('default')
  }
  const restored = await page.request.get('/api/v1/presets', { headers })
  const restoredPresets = await restored.json() as Array<{ id: number; name: string; description: string | null; indicators: unknown[]; is_default: boolean }>
  expect(restoredPresets.map(({ id, name, description, indicators, is_default }) => ({ id, name, description, indicators, is_default })))
    .toEqual(baselinePresets.map(({ id, name, description, indicators, is_default }) => ({ id, name, description, indicators, is_default })))

  const notificationSetup = page.locator('.settings-advanced').filter({ hasText: 'Notification setup' })
  await notificationSetup.locator('summary').click()
  await expect(notificationSetup).toHaveAttribute('open', '')
  await expect(notificationSetup).toContainText('Not configured for this browser')
  await expect(page.locator('#onesignal-app-id')).toHaveValue('')
  expect(await page.evaluate(() => window.localStorage.getItem('onesignal_app_id'))).toBeNull()
  await expect(page.locator('script[data-onesignal-sdk]')).toHaveCount(0)
  await browserDiagnostics.expectNoCriticalIssues()
})
