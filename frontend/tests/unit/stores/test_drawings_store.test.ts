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
})
