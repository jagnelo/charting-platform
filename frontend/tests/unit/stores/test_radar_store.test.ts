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

describe('useRadarStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('loads runs and detections', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([{ id: 1, status: 'completed' }])
      .mockResolvedValueOnce([
        { id: 3, instrument_id: 7, instrument_symbol: 'AAPL', setup_type: 'rejection', score: 0.7, observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T12:00:00Z', thread_id: 11, thread_event_index: 2 },
        { id: 2, instrument_id: 7, instrument_symbol: 'AAPL', setup_type: 'approaching_resistance', score: 0.8, observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T10:00:00Z', thread_id: 11, thread_event_index: 1 },
      ])

    const store = useRadarStore()
    await store.loadRuns()
    await store.loadDetections()

    expect(store.runs[0].id).toBe(1)
    expect(store.detections.map(detection => detection.id)).toEqual([2, 3])
  })

  it('loads a detection detail and chart overlays', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 2, instrument_symbol: 'AAPL', signal_at: '2026-05-05T10:00:00Z', evidence: { overlays: [], metrics: {}, structures: [] } })
      .mockResolvedValueOnce([
        { id: 3, thread_id: 8, thread_event_index: 2, setup_type: 'breakdown', observed_at: '2026-05-05T11:00:00Z', signal_at: '2026-05-05T11:00:00Z', evidence: { overlays: [{ kind: 'zone' }], metrics: { signal_time: 1746435600 }, structures: [{ last_touch_time: 1746435600 }] } },
        { id: 2, thread_id: 8, thread_event_index: 1, setup_type: 'approaching_resistance', observed_at: '2026-05-05T11:00:00Z', signal_at: '2026-05-05T08:00:00Z', evidence: { overlays: [{ kind: 'zone' }], metrics: { signal_time: 1746424800 }, structures: [{ last_touch_time: 1746424800 }] } },
      ])

    const store = useRadarStore()
    await store.loadDetection(2)
    await store.loadChartDetections(7, 2)

    expect(store.selectedDetection?.id).toBe(2)
    expect(store.chartDetections.map(detection => detection.id)).toEqual([2, 3])
    expect(store.activeChartDetectionIds).toEqual([2])
    expect(store.focusedChartDetectionId).toBe(2)
  })

  it('loads chart detections disabled by default on direct chart entry', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: 7, setup_type: 'breakdown', observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T11:00:00Z', evidence: { overlays: [], metrics: { signal_time: 1746435600 }, structures: [{ last_touch_time: 1746435600 }] } },
      { id: 5, setup_type: 'approaching_support', observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T08:00:00Z', evidence: { overlays: [], metrics: { signal_time: 1746424800 }, structures: [{ last_touch_time: 1746424800 }] } },
    ])

    const store = useRadarStore()
    await store.loadChartDetections(77)

    expect(store.chartDetections.map(detection => detection.id)).toEqual([5, 7])
    expect(store.activeChartDetectionIds).toEqual([])
    expect(store.focusedChartDetectionId).toBeNull()
  })

  it('uses thread event order when detections share a thread and signal date', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: 31, thread_id: 4, thread_event_index: 2, setup_type: 'rejection', observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T12:00:00Z', evidence: { overlays: [], metrics: {}, structures: [] } },
      { id: 30, thread_id: 4, thread_event_index: 1, setup_type: 'approaching_resistance', observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T12:00:00Z', evidence: { overlays: [], metrics: {}, structures: [] } },
    ])

    const store = useRadarStore()
    await store.loadChartDetections(12)

    expect(store.chartDetections.map(detection => detection.id)).toEqual([30, 31])
  })

  it('keeps cross-symbol ranking while preserving same-symbol chronology', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { id: 60, instrument_id: 2, instrument_symbol: 'MSFT', setup_type: 'breakout', score: 0.95, observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T12:00:00Z' },
      { id: 31, instrument_id: 1, instrument_symbol: 'AAPL', setup_type: 'rejection', score: 0.72, observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T12:00:00Z', thread_id: 4, thread_event_index: 2 },
      { id: 30, instrument_id: 1, instrument_symbol: 'AAPL', setup_type: 'approaching_resistance', score: 0.79, observed_at: '2026-05-05T12:00:00Z', signal_at: '2026-05-05T10:00:00Z', thread_id: 4, thread_event_index: 1 },
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
    }

    store.queueChartDetection(queuedDetection)

    expect(store.consumeChartDetectionForInstrument(77, 'AAPL')).toBeNull()
    expect(store.pendingChartDetection).toEqual({
      detectionId: 9,
      instrumentId: 77,
      instrumentSymbol: 'TSLA',
    })

    expect(store.consumeChartDetectionForInstrument(77, 'TSLA')).toBe(9)
    expect(store.pendingChartDetection).toBeNull()
  })

  it('runs a scan and toggles chart detections locally', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 5, status: 'completed' })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const store = useRadarStore()
    const run = await store.runScan()
    store.toggleChartDetection(11)
    store.toggleChartDetection(11)
    store.clearChartDetections()

    expect(run.id).toBe(5)
    expect(store.activeChartDetectionIds).toEqual([])
    expect(store.chartDetections).toEqual([])
  })
})
