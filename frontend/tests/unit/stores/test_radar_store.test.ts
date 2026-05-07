import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useRadarStore } from '@/stores/radar'

function detection(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    run_id: 1,
    instrument_id: 7,
    instrument_symbol: 'AAPL',
    instrument_name: 'Apple',
    timeframe: 'D1',
    setup_type: 'rejection',
    state: 'confirmed',
    score: 0.7,
    observed_at: '2026-05-05T12:00:00Z',
    signal_at: '2026-05-05T12:00:00Z',
    context_at: '2026-05-04T12:00:00Z',
    fresh_until: '2026-05-10T12:00:00Z',
    thread_id: 11,
    thread_event_index: 1,
    key_level_price: 182.4,
    entry_price: 182.1,
    invalidation_price: 184.2,
    target_price: 176.0,
    outcome_status: 'open',
    outcome_last_evaluated_at: '2026-05-05T12:00:00Z',
    bars_since_signal: 0,
    max_favorable_excursion_pct: null,
    max_adverse_excursion_pct: null,
    target_hit_at: null,
    invalidated_at: null,
    summary: 'Radar detection summary',
    invalidation_hint: 'Invalidate above 184.20',
    score_factors: { normalized_score: 0.7 },
    evidence: { overlays: [], metrics: {}, structures: [] },
    ...overrides,
  }
}

describe('useRadarStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    localStorage.clear()
  })

  it('loads runs and detections', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: 1, status: 'completed' }])
      .mockResolvedValueOnce([
        detection({ id: 3, setup_type: 'rejection', score: 0.7, thread_event_index: 2 }),
        detection({
          id: 2,
          setup_type: 'approaching_resistance',
          state: 'developing',
          score: 0.8,
          signal_at: '2026-05-05T10:00:00Z',
          thread_event_index: 1,
        }),
      ])

    const store = useRadarStore()
    await store.loadRuns()
    await store.loadDetections()

    expect(store.runs[0].id).toBe(1)
    expect(store.detections.map(detection => detection.id)).toEqual([2, 3])
  })

  it('loads a detection detail and chart overlays', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(
        detection({
          id: 2,
          setup_type: 'approaching_resistance',
          state: 'developing',
          signal_at: '2026-05-05T10:00:00Z',
        }),
      )
      .mockResolvedValueOnce([
        detection({
          id: 3,
          thread_id: 8,
          thread_event_index: 2,
          setup_type: 'breakdown',
          observed_at: '2026-05-05T11:00:00Z',
          signal_at: '2026-05-05T11:00:00Z',
          evidence: {
            overlays: [{ kind: 'zone' }],
            metrics: { signal_time: 1746435600 },
            structures: [{ last_touch_time: 1746435600 }],
          },
        }),
        detection({
          id: 2,
          thread_id: 8,
          thread_event_index: 1,
          setup_type: 'approaching_resistance',
          state: 'developing',
          observed_at: '2026-05-05T11:00:00Z',
          signal_at: '2026-05-05T08:00:00Z',
          evidence: {
            overlays: [{ kind: 'zone' }],
            metrics: { signal_time: 1746424800 },
            structures: [{ last_touch_time: 1746424800 }],
          },
        }),
      ])

    const store = useRadarStore()
    await store.loadDetection(2)
    await store.loadChartDetections(7, 'D1', 2)

    expect(store.selectedDetection?.id).toBe(2)
    expect(store.chartDetections.map(detection => detection.id)).toEqual([2, 3])
    expect(store.activeChartDetectionIds).toEqual([2])
    expect(store.focusedChartDetectionId).toBe(2)
  })

  it('loads chart detections disabled by default on direct chart entry', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      detection({
        id: 7,
        setup_type: 'breakdown',
        observed_at: '2026-05-05T12:00:00Z',
        signal_at: '2026-05-05T11:00:00Z',
        evidence: {
          overlays: [],
          metrics: { signal_time: 1746435600 },
          structures: [{ last_touch_time: 1746435600 }],
        },
      }),
      detection({
        id: 5,
        setup_type: 'approaching_support',
        state: 'developing',
        observed_at: '2026-05-05T12:00:00Z',
        signal_at: '2026-05-05T08:00:00Z',
        evidence: {
          overlays: [],
          metrics: { signal_time: 1746424800 },
          structures: [{ last_touch_time: 1746424800 }],
        },
      }),
    ])

    const store = useRadarStore()
    await store.loadChartDetections(77, 'D1')

    expect(store.chartDetections.map(detection => detection.id)).toEqual([5, 7])
    expect(store.activeChartDetectionIds).toEqual([])
    expect(store.focusedChartDetectionId).toBeNull()
  })

  it('uses thread event order when detections share a thread and signal date', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      detection({ id: 31, thread_id: 4, thread_event_index: 2 }),
      detection({
        id: 30,
        thread_id: 4,
        thread_event_index: 1,
        setup_type: 'approaching_resistance',
        state: 'developing',
      }),
    ])

    const store = useRadarStore()
    await store.loadChartDetections(12, 'D1')

    expect(store.chartDetections.map(detection => detection.id)).toEqual([30, 31])
  })

  it('keeps cross-symbol ranking while preserving same-symbol chronology', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      detection({ id: 60, instrument_id: 2, instrument_symbol: 'MSFT', instrument_name: 'Microsoft', setup_type: 'breakout', score: 0.95 }),
      detection({ id: 31, instrument_id: 1, thread_id: 4, thread_event_index: 2, score: 0.72 }),
      detection({
        id: 30,
        instrument_id: 1,
        thread_id: 4,
        thread_event_index: 1,
        setup_type: 'approaching_resistance',
        state: 'developing',
        score: 0.79,
        signal_at: '2026-05-05T10:00:00Z',
      }),
    ])

    const store = useRadarStore()
    await store.loadDetections()

    expect(store.detections.map(detection => detection.id)).toEqual([60, 30, 31])
  })

  it('queues and consumes chart detections only for the matching instrument context', () => {
    const store = useRadarStore()
    const queuedDetection = {
      id: 9,
      instrument_id: 77,
      instrument_symbol: 'TSLA',
      timeframe: 'D1',
    }

    store.queueChartDetection(queuedDetection)

    expect(store.consumeChartDetectionForInstrument(77, 'AAPL')).toBeNull()
    expect(store.pendingChartDetection).toEqual({
      detectionId: 9,
      instrumentId: 77,
      instrumentSymbol: 'TSLA',
      timeframe: 'D1',
    })

    expect(store.consumeChartDetectionForInstrument(77, 'TSLA')).toBe(9)
    expect(store.pendingChartDetection).toBeNull()
  })

  it('runs a scan and toggles chart detections locally', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 5, status: 'completed' })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const store = useRadarStore()
    const run = await store.runScan('D1')
    store.toggleChartDetection(11)
    store.toggleChartDetection(11)
    store.clearChartDetections()

    expect(run.id).toBe(5)
    expect(store.activeChartDetectionIds).toEqual([])
    expect(store.chartDetections).toEqual([])
  })

  it('loads instrument history and outcome summary', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([detection({ id: 12 })])
      .mockResolvedValueOnce([
        {
          timeframe: 'D1',
          setup_type: 'breakout',
          total: 4,
          open_count: 1,
          target_hit_count: 2,
          invalidated_count: 1,
          expired_count: 0,
          target_hit_rate: 0.5,
          invalidated_rate: 0.25,
          avg_mfe_pct: 6.2,
          avg_mae_pct: -2.1,
        },
      ])

    const store = useRadarStore()
    const history = await store.loadInstrumentHistory(7, 'D1')
    const summary = await store.loadOutcomeSummary('D1')

    expect(history).toHaveLength(1)
    expect(history[0].id).toBe(12)
    expect(summary[0].setup_type).toBe('breakout')
    expect(summary[0].target_hit_rate).toBe(0.5)
  })

  it('supports radar watchlist and alert workflows', async () => {
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        watchlist_id: 3,
        watchlist_name: 'Radar Discoveries',
        item_id: 88,
      })
      .mockResolvedValueOnce({
        id: 71,
        instrument_id: 7,
        instrument_symbol: 'AAPL',
        instrument_currency: 'USD',
        condition: 'crosses_above',
        threshold_price: 182.1,
        reference_price: 182.1,
        price_field: 'close',
        within_percent: null,
        status: 'active',
        repeat: false,
        show_projection: false,
        notes: 'Radar breakout',
        triggered_at: null,
        trigger_count: 0,
        last_known_price: null,
        created_at: '2026-05-05T12:00:00Z',
        updated_at: '2026-05-05T12:00:00Z',
      })

    const store = useRadarStore()
    const watchlistResult = await store.addDetectionToWatchlist(42, 3)
    const alertResult = await store.createDetectionPriceAlert(42)

    expect(watchlistResult.watchlist_name).toBe('Radar Discoveries')
    expect(alertResult.condition).toBe('crosses_above')
  })

  it('persists saved radar views in local storage', () => {
    const store = useRadarStore()
    store.saveView('Breakouts', {
      setup_type: 'breakout',
      state: 'confirmed',
      min_score: 0.7,
      fresh_only: true,
    })

    const reloadedStore = useRadarStore()
    reloadedStore.loadSavedViews()

    expect(reloadedStore.savedViews).toEqual([
      {
        name: 'Breakouts',
        filters: {
          timeframe: undefined,
          setup_type: 'breakout',
          state: 'confirmed',
          min_score: 0.7,
          fresh_only: true,
        },
      },
    ])
  })
})
