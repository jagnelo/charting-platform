/**
 * Unit tests for Pinia stores.
 * Each test creates a fresh Pinia instance and mocks all API calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useChartStore } from '@/stores/chart'
import { useAlertsStore } from '@/stores/alerts'

vi.mock('@/lib/api', () => ({
  api: {
    get:    vi.fn(),
    post:   vi.fn(),
    patch:  vi.fn(),
    delete: vi.fn(),
  },
  setTokens:  vi.fn(),
  clearTokens: vi.fn(),
}))

import { api, setTokens, clearTokens } from '@/lib/api'

// ── Auth store ────────────────────────────────────────────────────────────────

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('initial state — not logged in', () => {
    const store = useAuthStore()
    expect(store.isLoggedIn).toBe(false)
    expect(store.user).toBeNull()
  })

  it('login sets user after success', async () => {
    const mockUser = { id: 1, username: 'alice', email: 'alice@test.com', is_admin: false }
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ access_token: 'at', refresh_token: 'rt' })
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(mockUser)

    const store = useAuthStore()
    await store.login('alice', 'password123')

    expect(setTokens).toHaveBeenCalledWith('at', 'rt')
    expect(store.user).toEqual(mockUser)
    expect(store.isLoggedIn).toBe(true)
  })

  it('login throws on bad credentials', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('401'))
    const store = useAuthStore()
    await expect(store.login('bad', 'creds')).rejects.toThrow('401')
    expect(store.isLoggedIn).toBe(false)
  })

  it('logout clears user and tokens', async () => {
    const store = useAuthStore()
    store.user = { id: 1, username: 'alice', email: 'a@t.com', is_admin: false }
    store.logout()
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(clearTokens).toHaveBeenCalled()
  })

  it('loadMe sets user from /auth/me', async () => {
    const mockUser = { id: 2, username: 'bob', email: 'b@t.com', is_admin: false }
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockUser)
    const store = useAuthStore()
    await store.loadMe()
    expect(store.user).toEqual(mockUser)
  })

  it('loadMe sets null on error (unauthenticated)', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('401'))
    const store = useAuthStore()
    await store.loadMe()
    expect(store.user).toBeNull()
  })

  it('register calls /auth/register then logs in', async () => {
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({})  // register
      .mockResolvedValueOnce({ access_token: 'at', refresh_token: 'rt' })  // login
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 3, username: 'charlie', email: 'c@t.com', is_admin: false })

    const store = useAuthStore()
    await store.register('charlie', 'charlie@test.com', 'pass')
    expect(api.post).toHaveBeenCalledTimes(2)
    expect(store.isLoggedIn).toBe(true)
  })
})

// ── Chart store ───────────────────────────────────────────────────────────────

describe('useChartStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('initial state', () => {
    const store = useChartStore()
    expect(store.symbol).toBe('')
    expect(store.timeframe).toBe('D1')
    expect(store.bars).toEqual([])
    expect(store.indicators).toEqual([])
    expect(store.loading).toBe(false)
  })

  it('uplotData computed converts bars correctly', () => {
    const store = useChartStore()
    store.bars = [
      { ts: '2024-01-01T00:00:00Z', open: '100', high: '105', low: '95', close: '102', volume: '1000000' },
      { ts: '2024-01-02T00:00:00Z', open: '102', high: '108', low: '100', close: '106', volume: '2000000' },
    ] as any

    const data = store.uplotData
    expect(data).toHaveLength(6)           // [ts, o, h, l, c, vol]
    expect(data[0]).toHaveLength(2)        // 2 bars
    expect(typeof data[0][0]).toBe('number')  // timestamps are numbers
    expect(data[1][0]).toBeCloseTo(100)   // open
    expect(data[4][1]).toBeCloseTo(106)   // close bar 2
  })

  it('loadBars calls OHLCV endpoint', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])
    const store = useChartStore()
    store.symbol = 'AAPL'
    await store.loadBars()
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/ohlcv/AAPL'),
      expect.any(Object)
    )
  })

  it('addIndicator appends to indicators list', () => {
    const store = useChartStore()
    store.addIndicator({ type: 'sma', params: { period: 20 }, style: { color: '#fff' }, pane: 'main' })
    expect(store.indicators).toHaveLength(1)
    expect(store.indicators[0].type).toBe('sma')
  })

  it('removeIndicator removes by index', () => {
    const store = useChartStore()
    store.addIndicator({ type: 'sma', params: { period: 20 }, style: { color: '#fff' }, pane: 'main' })
    store.addIndicator({ type: 'ema', params: { period: 9  }, style: { color: '#aaa' }, pane: 'main' })
    store.removeIndicator(0)
    expect(store.indicators).toHaveLength(1)
    expect(store.indicators[0].type).toBe('ema')
  })
})

// ── Alerts store ──────────────────────────────────────────────────────────────

describe('useAlertsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('initial state', () => {
    const store = useAlertsStore()
    expect(store.alerts).toEqual([])
    expect(store.wsConnected).toBe(false)
  })

  it('loadAlerts populates alerts', async () => {
    const mockAlerts = [
      { id: 1, condition: 'crosses_above', threshold_price: '200', status: 'active' },
    ]
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce(mockAlerts)
    const store = useAlertsStore()
    await store.loadAlerts()
    expect(store.alerts).toEqual(mockAlerts)
  })

  it('createAlert appends to list', async () => {
    const newAlert = { id: 2, condition: 'crosses_below', threshold_price: '150', status: 'active' }
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(newAlert)
    const store = useAlertsStore()
    await store.createAlert({ instrument_id: 1, condition: 'crosses_below', threshold_price: '150' } as any)
    expect(store.alerts).toContainEqual(newAlert)
  })

  it('deleteAlert removes from list', async () => {
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)
    const store = useAlertsStore()
    store.alerts = [
      { id: 1, condition: 'crosses_above', threshold_price: '200', status: 'active' } as any,
      { id: 2, condition: 'crosses_below', threshold_price: '150', status: 'active' } as any,
    ]
    await store.deleteAlert(1)
    expect(store.alerts.map((a: any) => a.id)).not.toContain(1)
    expect(store.alerts).toHaveLength(1)
  })

  it('rearmAlert updates status to active', async () => {
    const rearmed = { id: 1, status: 'active', condition: 'crosses_above', threshold_price: '200' }
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(rearmed)
    const store = useAlertsStore()
    store.alerts = [
      { id: 1, status: 'triggered', condition: 'crosses_above', threshold_price: '200' } as any,
    ]
    await store.rearmAlert(1)
    expect(store.alerts[0].status).toBe('active')
  })
})
