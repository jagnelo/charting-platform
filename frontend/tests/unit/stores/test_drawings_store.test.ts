import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useDrawingsStore } from '@/stores/drawings'
import { beginAuthSessionBoundary, clearUserScopedPiniaStores } from '@/lib/authSession'

describe('useDrawingsStore authentication-boundary handling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    localStorage.clear()
  })

  it('does not start a protected drawing request after logout clears the token', async () => {
    const store = useDrawingsStore()
    store.drawings = [{ id: 1, instrument_id: 7, drawing_type: 'trendline', data: { points: [] }, style: {}, is_visible: true, is_locked: false } as any]

    await store.loadDrawings(7, 'D1')

    expect(api.get).not.toHaveBeenCalled()
    expect(store.drawings).toEqual([])
  })

  it('suppresses the expected in-flight authentication race without logging a false drawing failure', async () => {
    localStorage.setItem('access_token', 'expired')
    const store = useDrawingsStore()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Authentication required'))

    await store.loadDrawings(7, 'D1')

    expect(consoleError).not.toHaveBeenCalled()
    consoleError.mockRestore()
  })

  it('reloads the same instrument after a user boundary instead of reusing the previous owner cache', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    localStorage.setItem('access_token', 'user-a')
    const first = useDrawingsStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{ id: 11, label: 'drawing-a' }])
    await first.loadDrawings(7, 'D1')
    expect(first.drawings).toEqual([{ id: 11, label: 'drawing-a' }])

    localStorage.removeItem('access_token')
    beginAuthSessionBoundary()
    clearUserScopedPiniaStores(pinia)
    localStorage.setItem('access_token', 'user-b')
    const second = useDrawingsStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{ id: 22, label: 'drawing-b' }])
    await second.loadDrawings(7, 'D1')

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(second.drawings).toEqual([{ id: 22, label: 'drawing-b' }])
    expect(second.drawings).not.toContainEqual(expect.objectContaining({ label: 'drawing-a' }))
  })
})
