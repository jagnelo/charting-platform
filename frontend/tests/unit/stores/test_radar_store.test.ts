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
      .mockResolvedValueOnce([{ id: 2, evidence: { overlays: [{ kind: 'zone' }], metrics: {}, structures: [] } }])

    const store = useRadarStore()
    await store.loadDetection(2)
    await store.loadChartDetections(7, 2)

    expect(store.selectedDetection?.id).toBe(2)
    expect(store.chartDetections).toHaveLength(1)
    expect(store.overlayEnabled).toBe(true)
  })

  it('runs a scan and refreshes overlays toggles locally', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 5, status: 'completed' })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const store = useRadarStore()
    const run = await store.runScan()
    store.setOverlayEnabled(false)
    store.clearChartDetections()

    expect(run.id).toBe(5)
    expect(store.overlayEnabled).toBe(false)
    expect(store.chartDetections).toEqual([])
  })
})
