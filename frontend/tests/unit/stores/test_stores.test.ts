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
    put:    vi.fn(),
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
    localStorage.clear()
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

  it('clears this window when another same-origin window announces logout', () => {
    localStorage.setItem('access_token', 'at')
    localStorage.setItem('refresh_token', 'rt')
    const store = useAuthStore()
    store.user = { id: 1, username: 'alice', email: 'a@t.com', is_admin: false }

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'charting-platform-session:logout',
      newValue: 'remote-window',
    }))

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
    expect(data).toHaveLength(6)           // [barIndex, o, h, l, c, vol]
    expect(data[0]).toHaveLength(2)        // 2 bars
    expect(data[0][0]).toBe(0)
    expect(data[0][1]).toBe(1)
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

  it('workstation pagination stays on the local canonical OHLCV route', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/instruments/SPY') return Promise.resolve({ id: 42, symbol: 'SPY', stats: { week52_high: 1 } }) as any
      if (path === '/instrument-indicators/42') return Promise.resolve({ indicators: [] }) as any
      if (path.startsWith('/ohlcv/local/SPY/')) {
        return Promise.resolve([
          { ts: '2026-01-02T00:00:00Z', open: 2, high: 3, low: 1, close: 2, volume: 10 },
        ]) as any
      }
      return Promise.resolve([]) as any
    })
    const store = useChartStore()
    await store.loadBars('SPY', 'D1', 'candles', true)
    await store.loadMoreBars()

    expect(api.get).toHaveBeenCalledWith('/ohlcv/local/SPY/D1', expect.objectContaining({
      before: '2026-01-02T00:00:00Z',
      limit: 500,
    }))
    expect(api.get).not.toHaveBeenCalledWith('/ohlcv/SPY/D1', expect.anything())
  })

  it('passes alternative-bar transform parameters and refetches when they change', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/instruments/SPY') return Promise.resolve({ id: 42, symbol: 'SPY', stats: { week52_high: 1 } }) as any
      if (path === '/instrument-indicators/42') return Promise.resolve({ indicators: [] }) as any
      if (path.startsWith('/ohlcv/SPY/D1/transformed')) return Promise.resolve([{ ts: '2026-01-02T00:00:00Z', open: 2, high: 3, low: 1, close: 3, volume: 10 }]) as any
      return Promise.resolve([]) as any
    })
    const store = useChartStore()
    await store.loadBars('SPY', 'D1', 'renko', true, { brick_size: 4 })
    expect(api.get).toHaveBeenCalledWith('/ohlcv/SPY/D1/transformed', expect.objectContaining({
      bar_type: 'renko', brick_size: 4, local_only: true,
    }))
    await store.loadBars('SPY', 'D1', 'renko', true, { brick_size: 8 })
    expect(api.get).toHaveBeenCalledWith('/ohlcv/SPY/D1/transformed', expect.objectContaining({
      bar_type: 'renko', brick_size: 8, local_only: true,
    }))
  })

  it('late indicator hydration cannot replace a user plot added during loading', async () => {
    const store = useChartStore()
    let releaseIndicators!: (value: { indicators: any[] }) => void
    vi.spyOn(api, 'get').mockImplementation((path: string) => {
      if (path === '/instruments/SPY') return Promise.resolve({ id: 42, symbol: 'SPY' }) as any
      if (path === '/instrument-indicators/42') return new Promise(resolve => { releaseIndicators = resolve }) as any
      if (path.startsWith('/ohlcv/')) return Promise.resolve([{ ts: '2026-01-01T00:00:00Z', open: 1, high: 2, low: 1, close: 2, volume: 10 }]) as any
      return Promise.resolve([]) as any
    })
    const loading = store.loadBars('SPY', 'D1')
    await vi.waitFor(() => expect(releaseIndicators).toBeTypeOf('function'))
    store.addIndicator({ type: 'rsi', params: { period: 14 }, style: { color: '#fff' }, pane: 'separate' })
    releaseIndicators({ indicators: [] })
    await loading
    expect(store.indicators).toHaveLength(1)
    expect(store.indicators[0].type).toBe('rsi')
  })

  it('cancels a debounced indicator write when navigation changes the instrument', async () => {
    vi.useFakeTimers()
    try {
      ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
        if (path === '/instruments/SPY') return Promise.resolve({ id: 1, symbol: 'SPY' }) as any
        if (path === '/instruments/XLK') return Promise.resolve({ id: 2, symbol: 'XLK' }) as any
        if (path.startsWith('/instrument-indicators/')) return Promise.resolve({ indicators: [] }) as any
        if (path.startsWith('/ohlcv/')) return Promise.resolve([{ ts: '2026-01-01T00:00:00Z', open: 1, high: 2, low: 1, close: 2, volume: 10 }]) as any
        return Promise.resolve([]) as any
      })
      const store = useChartStore()
      await store.loadBars('SPY', 'D1')
      store.addIndicator({ type: 'rsi', params: { period: 14 }, style: { color: '#fff' }, pane: 'separate' })
      await Promise.resolve()
      await store.loadBars('XLK', 'D1')
      await vi.runAllTimersAsync()
      const writes = (api.put as ReturnType<typeof vi.fn>).mock.calls
      expect(writes.some(call => call[0] === '/instrument-indicators/1')).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('queues an indicator save requested before canonical instrument hydration', async () => {
    const store = useChartStore()
    store.indicators = [{ type: 'rsi', params: { period: 14 }, style: { color: '#fff' }, pane: 'separate' }] as any
    store.instrument = null
    await expect(store.saveIndicatorsForInstrument()).resolves.toBe(false)
    expect(api.put).not.toHaveBeenCalled()

    store.instrument = { id: 42, symbol: 'SPY' } as any
    await expect(store.saveIndicatorsForInstrument()).resolves.toBe(true)
    expect(api.put).toHaveBeenCalledWith('/instrument-indicators/42', {
      indicators: [expect.objectContaining({ type: 'rsi' })],
    })
  })

  it('loadBars can load synthetic basket OHLCV tokens', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      {
        ts: '2026-01-01T00:00:00Z',
        open: '100',
        high: '101',
        low: '99',
        close: '100.5',
        volume: '3000',
        is_adjusted: true,
      },
    ])
    const store = useChartStore()

    await store.loadBars('BASKET:42', 'D1')

    expect(api.get).toHaveBeenCalledWith('/baskets/42/ohlcv/D1', { adjusted: true, limit: 500 })
    expect(store.instrument).toBeNull()
    expect(store.bars[0].close).toBe(100.5)
    expect(store.hasReachedStart).toBe(true)
  })

  it('does not let a slower symbol load overwrite the current chart', async () => {
    let resolveFirst!: (value: unknown) => void
    const firstInstrument = new Promise(resolve => { resolveFirst = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/instruments/AAPL') return firstInstrument
      if (path === '/instruments/MSFT') return Promise.resolve({ id: 2, symbol: 'MSFT', stats: { week52_high: 500 } })
      if (path.startsWith('/instrument-indicators/')) return Promise.resolve({ indicators: [] })
      if (path.includes('/ohlcv/MSFT/')) return Promise.resolve([{ ts: '2026-08-01T00:00:00Z', open: 100, high: 105, low: 99, close: 104, volume: 1000 }])
      return Promise.resolve([])
    })
    const store = useChartStore()
    const firstLoad = store.loadBars('AAPL', 'D1')
    const currentLoad = store.loadBars('MSFT', 'D1')
    await currentLoad
    resolveFirst({ id: 1, symbol: 'AAPL', stats: { week52_high: 200 } })
    await firstLoad

    expect(store.symbol).toBe('MSFT')
    expect(store.instrument?.symbol).toBe('MSFT')
    expect(store.bars).toHaveLength(1)
    expect(store.bars[0].close).toBe(104)
    expect(store.loading).toBe(false)
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

  it('updateAlert patches alert in place', async () => {
    const updated = { id: 1, repeat: true, condition: 'crosses_above', threshold_price: '200', status: 'active' }
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(updated)
    const store = useAlertsStore()
    store.alerts = [{ id: 1, repeat: false, condition: 'crosses_above', threshold_price: '200', status: 'active' } as any]
    await store.updateAlert(1, { repeat: true })
    expect(store.alerts[0].repeat).toBe(true)
  })

  it('selectAlert and requestEditAlert set ids', () => {
    const store = useAlertsStore()
    store.selectAlert(42)
    expect(store.selectedAlertId).toBe(42)
    store.requestEditAlert(7)
    expect(store.editRequestAlertId).toBe(7)
    store.selectAlert(null)
    expect(store.selectedAlertId).toBeNull()
  })

  it('activeCountForInstrument and totalActiveCount reflect state', () => {
    const store = useAlertsStore()
    store.alerts = [
      { id: 1, instrument_id: 5, status: 'active' } as any,
      { id: 2, instrument_id: 5, status: 'triggered' } as any,
    ]
    expect(store.activeCountForInstrument(5)).toBe(1)
    expect(store.totalActiveCount).toBe(1)
  })

  it('unviewedCount reflects unviewed firing events', () => {
    const store = useAlertsStore()
    store.firingHistory = [
      { id: 1, is_viewed: false } as any,
      { id: 2, is_viewed: true } as any,
    ]
    expect(store.unviewedCount).toBe(1)
  })

  it('getAlertProjection returns show_projection value', () => {
    const store = useAlertsStore()
    store.alerts = [{ id: 3, show_projection: true } as any]
    expect(store.getAlertProjection(3)).toBe(true)
    expect(store.getAlertProjection(99)).toBe(false)
  })

  it('loadHistory fetches firing history', async () => {
    const events = [{ id: 1, is_viewed: false, alert_id: 1 }]
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce(events)
    const store = useAlertsStore()
    await store.loadHistory({ unviewedOnly: true })
    expect(store.firingHistory).toEqual(events)
  })

  it('loadInstrumentHistory returns events for instrument', async () => {
    const events = [{ id: 2, is_viewed: false }]
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce(events)
    const store = useAlertsStore()
    const result = await store.loadInstrumentHistory(10)
    expect(result).toEqual(events)
  })

  it('markViewed updates event in history', async () => {
    const viewed = { id: 1, is_viewed: true }
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(viewed)
    const store = useAlertsStore()
    store.firingHistory = [{ id: 1, is_viewed: false } as any]
    await store.markViewed(1)
    expect(store.firingHistory[0].is_viewed).toBe(true)
  })

  it('markAllViewed marks all events as viewed', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)
    const store = useAlertsStore()
    store.firingHistory = [{ id: 1, is_viewed: false } as any, { id: 2, is_viewed: false } as any]
    await store.markAllViewed()
    expect(store.firingHistory.every((e: any) => e.is_viewed)).toBe(true)
  })

  it('deleteFiringEvent removes event from history', async () => {
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)
    const store = useAlertsStore()
    store.firingHistory = [{ id: 1 } as any, { id: 2 } as any]
    await store.deleteFiringEvent(1)
    expect(store.firingHistory.map((e: any) => e.id)).not.toContain(1)
  })

  it('createIndicatorAlert, updateIndicatorAlert, deleteIndicatorAlert, rearmIndicatorAlert', async () => {
    const created = { id: 10, instrument_id: 1, timeframe: '1D', status: 'active' }
    const updated = { ...created, repeat: true }
    const rearmed = { ...created, status: 'active' }
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(created)
      .mockResolvedValueOnce(rearmed)
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(updated)
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    const store = useAlertsStore()
    await store.createIndicatorAlert({ instrument_id: 1, timeframe: '1D', indicator_a_type: 'rsi', indicator_a_params: {}, condition: 'crosses_above' })
    expect(store.indicatorAlerts[0].id).toBe(10)

    await store.updateIndicatorAlert(10, { repeat: true })
    expect(store.indicatorAlerts[0].repeat).toBe(true)

    store.indicatorAlerts = [{ id: 10, status: 'triggered' } as any]
    await store.rearmIndicatorAlert(10)
    expect(store.indicatorAlerts[0].status).toBe('active')

    await store.deleteIndicatorAlert(10)
    expect(store.indicatorAlerts.some((a: any) => a.id === 10)).toBe(false)
  })
})
