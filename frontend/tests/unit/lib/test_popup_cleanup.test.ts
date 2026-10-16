import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { closePopupWhenOpen } from '../../e2e/popup_cleanup'

function popupFixture(initiallyClosed = false) {
  let isClosed = initiallyClosed
  let resolveClose!: () => void
  let rejectClose!: (error: unknown) => void
  const closeEvent = new Promise<void>((resolve, reject) => {
    resolveClose = resolve
    rejectClose = reject
  })
  const close = () => { isClosed = true; resolveClose() }
  const click = vi.fn(async () => { close() })
  const waitForEvent = vi.fn(() => closeEvent)
  const locator = vi.fn(() => ({ click }))
  const popup = { isClosed: () => isClosed, locator, waitForEvent } as unknown as Page
  return { popup, close, click, waitForEvent, locator, rejectClose }
}

describe('popup cleanup observer', () => {
  it('keeps ordinary flow cleanup on the tested observer without replacing browser-disconnect coverage', () => {
    const flows = readFileSync('tests/e2e/flows.spec.ts', 'utf8')
    expect(flows).not.toContain('await popup.locator(\'button[title="Close"]\').click()')
    expect(flows).toContain('await closePopupWhenOpen(popup)')
    expect(flows).toContain('await popup.close()')
  })

  it('does nothing when the disposable popup is already closed', async () => {
    const fixture = popupFixture(true)
    await closePopupWhenOpen(fixture.popup)
    expect(fixture.waitForEvent).not.toHaveBeenCalled()
    expect(fixture.locator).not.toHaveBeenCalled()
  })

  it('observes close before performing the ordinary Close click', async () => {
    const fixture = popupFixture()
    await closePopupWhenOpen(fixture.popup)
    expect(fixture.waitForEvent).toHaveBeenCalledWith('close', { timeout: 10_000 })
    expect(fixture.locator).toHaveBeenCalledWith('button[title="Close"]')
    expect(fixture.click).toHaveBeenCalledOnce()
    expect(fixture.waitForEvent.mock.invocationCallOrder[0]).toBeLessThan(fixture.click.mock.invocationCallOrder[0])
  })

  it('accepts a popup that actually closes during the ordinary click', async () => {
    const fixture = popupFixture()
    fixture.click.mockImplementationOnce(async () => {
      fixture.close()
      throw new Error('Target page, context or browser has been closed')
    })
    await expect(closePopupWhenOpen(fixture.popup)).resolves.toBeUndefined()
  })

  it('handles closure between the precheck and event subscription', async () => {
    const fixture = popupFixture()
    fixture.waitForEvent.mockImplementationOnce(() => {
      fixture.close()
      return Promise.reject(new Error('Target page has been closed'))
    })
    fixture.click.mockRejectedValueOnce(new Error('Target page has been closed'))
    await expect(closePopupWhenOpen(fixture.popup)).resolves.toBeUndefined()
  })

  it('propagates an unrelated click error while the popup remains open', async () => {
    const fixture = popupFixture()
    const clickError = new Error('Close control is intercepted')
    fixture.click.mockRejectedValueOnce(clickError)
    await expect(closePopupWhenOpen(fixture.popup)).rejects.toBe(clickError)
    // The detached wait must stay handled even after the click error escapes.
    fixture.rejectClose(new Error('Late close wait timeout'))
    await Promise.resolve()
  })

  it('fails when the click completes but the page never closes', async () => {
    const fixture = popupFixture()
    fixture.click.mockResolvedValueOnce(undefined)
    const timeout = new Error('Close event timed out')
    const result = closePopupWhenOpen(fixture.popup)
    fixture.rejectClose(timeout)
    await expect(result).rejects.toBe(timeout)
  })

  it('does not hide a failed close wait when a live popup is still open', async () => {
    const fixture = popupFixture()
    fixture.click.mockResolvedValueOnce(undefined)
    const error = new Error('Browser event observer failed')
    fixture.waitForEvent.mockRejectedValueOnce(error)
    await expect(closePopupWhenOpen(fixture.popup)).rejects.toBe(error)
  })
})
