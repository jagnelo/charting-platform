import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setQueuedApiRequestPriority: vi.fn(),
}))

import { api } from '@/lib/api'
import { AuthSessionChangedError } from '@/lib/authSession'
import { useAlertsStore } from '@/stores/alerts'

describe('useAlertsStore authentication-boundary handling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('resolves silently when logout aborts an in-flight alert read and allows a later reload', async () => {
    const store = useAlertsStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new AuthSessionChangedError())

    // Callers fire-and-forget this load; a rejection would be an unhandled
    // promise rejection (page error) during logout.
    await expect(store.loadAlerts(7, 'high')).resolves.toBeUndefined()

    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue([])
    await store.loadAlerts(7)
    expect(api.get).toHaveBeenCalledTimes(3)
  })

  it('still reports genuine alert load failures', async () => {
    const store = useAlertsStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'))

    await expect(store.loadAlerts(8)).rejects.toThrow('boom')
  })
})
