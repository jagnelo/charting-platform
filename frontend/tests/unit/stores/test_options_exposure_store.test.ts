import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useOptionsExposureStore } from '@/stores/optionsExposure'

const exposurePayload = {
  symbol: 'NVDA',
  spot: 900,
  expirations: ['2026-06-19', '2026-07-17'],
  active_expirations: ['2026-06-19', '2026-07-17'],
  computed_at: '2026-04-26T00:00:00Z',
  ladder: [
    {
      strike: 900,
      call_gex: 10,
      put_gex: -8,
      net_gex: 2,
      call_dex: 5,
      put_dex: -4,
      net_dex: 1,
      call_oi: 100,
      put_oi: 80,
      call_iv: 0.5,
      put_iv: 0.6,
      call_mark: 20,
      put_mark: 19,
      by_expiry: {
        '2026-06-19': { call_gex: 6, put_gex: -5, net_gex: 1, call_dex: 3, put_dex: -2, net_dex: 1, call_oi: 60, put_oi: 50 },
        '2026-07-17': { call_gex: 4, put_gex: -3, net_gex: 1, call_dex: 2, put_dex: -2, net_dex: 0, call_oi: 40, put_oi: 30 },
      },
    },
  ],
  key_levels: { call_wall: 920, put_wall: 880, gamma_flip: 905, max_pain: 900 },
  pcr_oi: 0.8,
  pcr_volume: 0.9,
  implied_move_pct: 0.03,
  total_gex: 2,
  total_net_dex: 1,
}

describe('useOptionsExposureStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('loads exposure data and initializes enabled expirations', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ symbol: 'NVDA' })
      .mockResolvedValueOnce(exposurePayload)
      .mockResolvedValueOnce([{ expiration: '2026-06-19', dte: 54, total_call_oi: 100, total_put_oi: 80, pcr_oi: 0.8, total_gex: 2 }])

    const store = useOptionsExposureStore()
    await store.load('NVDA')

    expect(store.symbol).toBe('NVDA')
    expect(store.availableExpirations).toEqual(['2026-06-19', '2026-07-17'])
    expect([...store.enabledExpirations]).toEqual(['2026-06-19', '2026-07-17'])
    expect(store.expirationSummaries).toHaveLength(1)
  })

  it('filters ladder by enabled expirations and strike range', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ symbol: 'NVDA' })
      .mockResolvedValueOnce(exposurePayload)
      .mockResolvedValueOnce([])

    const store = useOptionsExposureStore()
    await store.load('NVDA')
    store.enabledExpirations = new Set(['2026-06-19'])
    store.setStrikeRange(890, 910)

    expect(store.visibleLadder).toHaveLength(1)
    expect(store.filteredLadder[0].call_gex).toBe(6)
    expect(store.filteredLadder[0].put_gex).toBe(-5)
    expect(store.filteredLadder[0].call_oi).toBe(60)
  })

  it('can toggle and reset state', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ symbol: 'NVDA' })
      .mockResolvedValueOnce(exposurePayload)
      .mockResolvedValueOnce([])

    const store = useOptionsExposureStore()
    await store.load('NVDA')
    store.toggleExpiration('2026-07-17')
    expect(store.enabledExpirations.has('2026-07-17')).toBe(false)

    store.setAllExpirations(false)
    expect(store.enabledExpirations.size).toBe(0)

    store.reset()
    expect(store.symbol).toBeNull()
    expect(store.data).toBeNull()
    expect(store.error).toBeNull()
  })

  it('returns a clean message for unknown instruments', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error(`API GET /instruments/CSCOII → 404: {"detail":"Instrument 'CSCOII' not found"}`),
    )
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const store = useOptionsExposureStore()
    await store.load('CSCOII')

    consoleSpy.mockRestore()
    expect(store.error).toBe('Options exposure "CSCOII" is not available.')
    expect(store.data).toBeNull()
  })
})
