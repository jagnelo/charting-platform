import type { Page } from '@playwright/test'

/** Cleanup only: preceding product assertions must already have succeeded. */
export async function closePopupWhenOpen(popup: Page) {
  if (popup.isClosed()) return
  // Observe first: the persisted-layout refresh can close this disposable page
  // during an ordinary click. Convert rejection to data immediately so an
  // unrelated click error cannot leave a late unhandled close-wait rejection.
  const closed = popup.waitForEvent('close', { timeout: 10_000 }).then(
    () => ({ ok: true as const }),
    (error: unknown) => ({ ok: false as const, error }),
  )
  try {
    await popup.locator('button[title="Close"]').click()
  } catch (error) {
    if (!popup.isClosed()) throw error
  }
  const outcome = await closed
  if (!outcome.ok && !popup.isClosed()) throw outcome.error
}
