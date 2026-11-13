import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => ({
  store: {
    symbol: '',
    bars: [] as unknown[],
    error: null as string | null,
    isLoading: false,
    loadBars: vi.fn(),
    refreshLocalBars: vi.fn(),
  },
  ensure: vi.fn(),
  ensureCalls: [] as Array<{ request: unknown; options: { signal?: AbortSignal; onProgress?: (progress: unknown) => void }; resolve: (value: unknown) => void }>,
}))

vi.mock('@/stores/chart', () => ({
  usePanelStore: () => harness.store,
}))

vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: harness.ensure },
  instrumentHistoryPreparationRequest: (target: unknown, timeframe: string, adjusted: boolean) => ({
    target,
    datasets: ['identity', 'profile', 'history'],
    timeframe,
    adjusted,
  }),
  isPreparationTimeframe: (timeframe: string) => ['D1', 'W1', 'MN'].includes(timeframe),
  PreparationProgressRefreshQueue: class {
    request(_response: unknown, refresh: () => Promise<void>) { return refresh() }
  },
  preparationStatusMessage: () => 'History is temporarily unavailable; the preview remains visible.',
}))

import RadarDetailPreviewChart from '@/components/radar/RadarDetailPreviewChart.vue'
import type { RadarDetection } from '@/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function detection(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    instrument_id: 82,
    instrument_symbol: 'IGV',
    timeframe: 'W1',
    evidence: { indicator_visuals: [], drawing_visuals: [] },
    ...overrides,
  } as unknown as RadarDetection
}

function historyResponse(status: string, hasPendingWork: boolean, covered: boolean) {
  return {
    status,
    has_pending_work: hasPendingWork,
    dependencies: [{
      dataset: 'history',
      covered_ranges: covered ? [{ start_at: '2024-01-01T00:00:00Z', end_at: '2024-04-01T00:00:00Z' }] : [],
      covered_start: covered ? '2024-01-01T00:00:00Z' : null,
      covered_end: covered ? '2024-04-01T00:00:00Z' : null,
    }],
  }
}

describe('RadarDetailPreviewChart shared history preparation', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    harness.ensureCalls = []
    harness.store.symbol = ''
    harness.store.bars = []
    harness.store.error = null
    harness.store.isLoading = false
    harness.store.loadBars.mockImplementation(async (symbol: string) => { harness.store.symbol = symbol })
    harness.store.refreshLocalBars.mockResolvedValue(undefined)
    harness.ensure.mockImplementation((request: unknown, options: { signal?: AbortSignal; onProgress?: (progress: unknown) => void }) => {
      const pending = deferred<unknown>()
      harness.ensureCalls.push({ request, options, resolve: pending.resolve })
      return pending.promise
    })
  })

  it('shows local data immediately and refreshes it as the selected detection gains history', async () => {
    const wrapper = mount(RadarDetailPreviewChart, {
      props: { detection: detection() },
      global: { stubs: { UPlotChart: true } },
    })

    await vi.waitFor(() => expect(harness.ensureCalls).toHaveLength(1))
    expect(harness.store.loadBars).toHaveBeenCalledWith('IGV', 'W1', 'candles', true)
    expect(harness.ensureCalls[0].request).toEqual({
      target: { kind: 'instrument', instrument_id: 82 },
      datasets: ['identity', 'profile', 'history'],
      timeframe: 'W1',
      adjusted: true,
    })
    expect(wrapper.get('[role="status"]').text()).toContain('Checking saved W1 history for IGV')

    harness.ensureCalls[0].options.onProgress?.({
      response: historyResponse('partial', true, true),
      completed: 1,
      total: 2,
    })
    await vi.waitFor(() => expect(harness.store.refreshLocalBars).toHaveBeenCalledTimes(1))
    expect(wrapper.text()).toContain('Preparing W1 history for IGV')

    harness.ensureCalls[0].resolve(historyResponse('ready', false, true))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Local W1 history is ready for IGV.'))
    expect(harness.store.refreshLocalBars).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('cancels the previous detection observer and ignores its late progress after selection changes', async () => {
    const wrapper = mount(RadarDetailPreviewChart, {
      props: { detection: detection() },
      global: { stubs: { UPlotChart: true } },
    })
    await vi.waitFor(() => expect(harness.ensureCalls).toHaveLength(1))
    const prior = harness.ensureCalls[0]

    await wrapper.setProps({ detection: detection({ id: 10, instrument_id: 7, instrument_symbol: 'AAPL', timeframe: 'D1' }) })
    await vi.waitFor(() => expect(harness.ensureCalls).toHaveLength(2))
    expect(prior.options.signal?.aborted).toBe(true)
    expect(harness.ensureCalls[1].request).toMatchObject({ target: { kind: 'instrument', instrument_id: 7 }, timeframe: 'D1' })

    prior.options.onProgress?.({ response: historyResponse('partial', true, true), completed: 1, total: 2 })
    await Promise.resolve()
    expect(harness.store.refreshLocalBars).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Checking saved D1 history for AAPL')

    harness.ensureCalls[1].resolve(historyResponse('waiting', false, false))
    await vi.waitFor(() => expect(wrapper.text()).toContain('temporarily unavailable'))
    wrapper.unmount()
  })
})
