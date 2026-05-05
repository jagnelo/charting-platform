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
      .mockResolvedValueOnce([{ id: 2, instrument_symbol: 'AAPL', score: 0.8 }])

    const store = useRadarStore()
    await store.loadRuns()
    await store.loadDetections()

    expect(store.runs[0].id).toBe(1)
    expect(store.detections[0].instrument_symbol).toBe('AAPL')
  })

  it('loads a detection detail and chart overlays', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 2, instrument_symbol: 'AAPL', evidence: { overlays: [], metrics: {}, structures: [] } })
      .mockResolvedValueOnce([
        { id: 3, setup_type: 'breakdown', observed_at: '2026-05-05T11:00:00Z', evidence: { overlays: [{ kind: 'zone' }], metrics: { signal_time: 1746435600 }, structures: [{ last_touch_time: 1746435600 }] } },
        { id: 2, setup_type: 'approaching_resistance', observed_at: '2026-05-05T11:00:00Z', evidence: { overlays: [{ kind: 'zone' }], metrics: { signal_time: 1746424800 }, structures: [{ last_touch_time: 1746424800 }] } },
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
      { id: 7, setup_type: 'breakdown', observed_at: '2026-05-05T12:00:00Z', evidence: { overlays: [], metrics: { signal_time: 1746435600 }, structures: [{ last_touch_time: 1746435600 }] } },
      { id: 5, setup_type: 'approaching_support', observed_at: '2026-05-05T12:00:00Z', evidence: { overlays: [], metrics: { signal_time: 1746424800 }, structures: [{ last_touch_time: 1746424800 }] } },
    ])

    const store = useRadarStore()
    await store.loadChartDetections(77)

    expect(store.chartDetections.map(detection => detection.id)).toEqual([5, 7])
    expect(store.activeChartDetectionIds).toEqual([])
    expect(store.focusedChartDetectionId).toBeNull()
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
