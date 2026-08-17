import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/lib/api'
import { useUserSettingsStore } from '@/stores/userSettings'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

describe('user settings market-map source preferences', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.resetAllMocks()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      marketMap: {
        followedSourceIds: ['market-group:sp500', 'market-group:sp500', 42, ''],
        pinnedSourceIds: ['etf-holdings:spy', 'etf-holdings:spy'],
      },
    })
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValue({})
  })

  afterEach(() => vi.useRealTimers())

  it('loads isolated deduplicated follow and pin preferences', async () => {
    const store = useUserSettingsStore()
    await store.loadSettings()

    expect(store.followedSourceIds).toEqual(['market-group:sp500'])
    expect(store.pinnedSourceIds).toEqual(['etf-holdings:spy'])
  })

  it('persists follow and pin changes without changing canonical membership', async () => {
    const store = useUserSettingsStore()
    await store.loadSettings()
    store.toggleFollowedSource('market-group:sp500')
    store.toggleFollowedSource('market-group:russell-2000')
    store.togglePinnedSource('etf-holdings:spy')
    store.togglePinnedSource('etf-holdings:qqq')
    await vi.advanceTimersByTimeAsync(350)

    expect(api.patch).toHaveBeenCalledWith('/auth/settings', {
      settings: expect.objectContaining({
        marketMap: {
          followedSourceIds: ['market-group:russell-2000'],
          pinnedSourceIds: ['etf-holdings:qqq'],
        },
      }),
    })
  })
})
