import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/lib/api'
import { useUserSettingsStore } from '@/stores/userSettings'

const setQueuedApiRequestPriority = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
  setQueuedApiRequestPriority,
}))

describe('user settings market-map source preferences', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.resetAllMocks()
    localStorage.setItem('access_token', 'test-access-token')
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

  it('promotes one pending settings read when a Market Map becomes foreground', async () => {
    let resolveSettings!: (value: any) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveSettings = resolve }))
    const store = useUserSettingsStore()

    const backgroundRead = store.loadSettings('low')
    const foregroundRead = store.loadSettings('high')

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith('/auth/settings', undefined, { priority: 'low', queueKey: 'user-settings:load' })
    expect(setQueuedApiRequestPriority).toHaveBeenCalledWith('user-settings:load', 'high')
    resolveSettings({ marketMap: { followedSourceIds: ['market-group:sp500'], pinnedSourceIds: [] } })
    await Promise.all([backgroundRead, foregroundRead])
    expect(store.followedSourceIds).toEqual(['market-group:sp500'])
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

  it('does not persist a debounced change after logout clears the access token', async () => {
    const store = useUserSettingsStore()
    await store.loadSettings()
    localStorage.removeItem('access_token')
    store.toggleFollowedSource('market-group:russell-2000')
    await vi.advanceTimersByTimeAsync(350)

    expect(api.patch).not.toHaveBeenCalled()
  })
})
