import { flushPromises, mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost } }))

function savedScan(id = 7, timeframe = 'W1') {
  return {
    id, name: 'Saved weekly scan', universe_type: 'watchlist', universe_watchlist_id: 12,
    universe_asset_class_id: null, universe_basket_id: null, universe_instrument_ids: null,
    timeframe, conditions: { field: 'close' }, schedule: null, updated_at: '2026-11-07T10:00:00Z',
  }
}

function readyPreparation(screenerId = 7) {
  const now = '2026-11-07T10:00:00Z'
  return {
    request_id: `saved-screener-${screenerId}`, status: 'ready', created_at: now, updated_at: now,
    version: 1, target: { kind: 'screener', screener_id: screenerId }, dependencies: [],
    completed: 1, total: 1, last_progress_at: now, has_pending_work: false,
  }
}

import MarketGaugeTool from '@/components/workstation/MarketGaugeTool.vue'

function mountTool(queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
  return mount(MarketGaugeTool, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
}

describe('MarketGaugeTool', () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPost.mockResolvedValue(readyPreparation()) })
  afterEach(() => Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }))

  it('loads retained scans, refreshes a selected gauge, and shows freshness lineage', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Above 50 day average' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan(7, 'D1'))
      return Promise.resolve({
        screener_id: 7,
        screener_name: 'Above 50 day average',
        matched_count: 4,
        evaluated_count: 8,
        universe_count: 10,
        percentage: 0.5,
        run_at: '2026-08-03T10:00:00Z',
        freshness: 'stale',
        data_provenance: 'canonical_local_database',
        calculation_version: 'analysis-v1',
        refreshed_at: '2026-08-03T10:01:00Z',
        freshness_detail: { requested: 10, current: 0, stale: 8, other: 2 },
        exclusions: [{ code: 'no_history', message: 'Two symbols have no local history.' }],
      })
    })

    const wrapper = mountTool()
    await flushPromises()
    expect(apiGet).toHaveBeenCalledWith('/screeners')

    await wrapper.find('select').setValue('7')
    await flushPromises()
    expect(apiGet).toHaveBeenCalledWith('/analysis/gauges/7')
    expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 7 }, datasets: ['history'], timeframe: 'D1',
    }, expect.any(Object))
    expect(wrapper.find('[role="region"][aria-label="Market Gauge"]').exists()).toBe(true)
    expect(wrapper.find('.market-gauge__freshness[role="status"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('Stale')
    expect(wrapper.text()).toContain('canonical_local_database')
    expect(wrapper.text()).toContain('Coverage warnings: 1')

    const callsBeforeRefresh = apiGet.mock.calls.length
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(apiGet.mock.calls.length).toBeGreaterThan(callsBeforeRefresh)
    expect(apiGet).toHaveBeenCalledWith('/analysis/gauges/7')
  })

  it('exposes empty and failed gauge states as status and alert regions', async () => {
    apiGet.mockImplementation((path: string) => path === '/screeners' ? Promise.resolve([]) : Promise.reject(new Error('gauge unavailable')))
    const wrapper = mountTool()
    await flushPromises()
    const emptyState = wrapper.find('.market-gauge__state[role="status"]')
    expect(emptyState.text()).toContain('Choose a retained EasyScan result')
    expect(emptyState.attributes('aria-live')).toBe('polite')
    expect(emptyState.attributes('aria-atomic')).toBe('true')

    apiGet.mockImplementation((path: string) => path === '/screeners' ? Promise.reject(new Error('scan list unavailable')) : Promise.resolve(undefined))
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('.market-gauge__error[role="alert"]').text()).toContain('scan list unavailable'))
  })

  it('does not fetch a selected gauge while the document is hidden', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    apiGet.mockResolvedValue([{ id: 7, name: 'Hidden gauge' }])
    const wrapper = mountTool()
    await flushPromises()

    await wrapper.find('select').setValue('7')
    await flushPromises()
    expect(apiGet).not.toHaveBeenCalledWith('/analysis/gauges/7')
    expect(apiPost).not.toHaveBeenCalledWith('/data/ensure', expect.anything(), expect.anything())
  })

  it('keeps a useful cached gauge visible while the saved universe prepares and uses its saved timeframe', async () => {
    let resolvePreparation!: (value: unknown) => void
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Saved weekly scan' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan())
      return Promise.resolve({
        matched_count: 3, evaluated_count: 6, universe_count: 8, percentage: 0.5,
        run_at: '2026-08-03T10:00:00Z', freshness: 'current', data_provenance: 'canonical_local_database',
        calculation_version: 'analysis-v1', refreshed_at: '2026-08-03T10:01:00Z',
        freshness_detail: { requested: 8, current: 6, stale: 0, other: 2 }, exclusions: [],
      })
    })
    apiPost.mockImplementation(() => new Promise(resolve => { resolvePreparation = resolve }))
    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/data/ensure', {
      target: { kind: 'screener', screener_id: 7 }, datasets: ['history'], timeframe: 'W1',
    }, expect.any(Object)))
    await vi.waitFor(() => expect(wrapper.text()).toContain('50.0%'))
    expect(wrapper.text()).toContain('3 matches')
    resolvePreparation(readyPreparation())
    await vi.waitFor(() => expect(wrapper.text()).toContain('Requested data is ready.'))
    wrapper.unmount()
  })

  it('fences an edited saved definition under the same ID and starts preparation for the new context', async () => {
    let definitionReads = 0
    const signals: AbortSignal[] = []
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Saved weekly scan' }])
      if (path === '/screeners/7') {
        definitionReads += 1
        return Promise.resolve(savedScan(7, definitionReads === 1 ? 'D1' : 'W1'))
      }
      if (path === '/analysis/gauges/7') return Promise.resolve({
        matched_count: 1, evaluated_count: 2, universe_count: 2, percentage: 0.5,
        run_at: '2026-08-03T10:00:00Z', freshness: 'current', data_provenance: 'canonical_local_database',
        calculation_version: 'analysis-v1', refreshed_at: '2026-08-03T10:01:00Z',
        freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, exclusions: [],
      })
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, _body?: unknown, options?: { signal?: AbortSignal }) => {
      if (path === '/data/ensure') {
        if (options?.signal) signals.push(options.signal)
        return new Promise(() => {})
      }
      return Promise.resolve(readyPreparation())
    })
    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path]) => path === '/data/ensure')).toHaveLength(1))
    await wrapper.find('button').trigger('click')
    await vi.waitFor(() => expect(apiPost.mock.calls.filter(([path]) => path === '/data/ensure')).toHaveLength(2))
    expect(signals[0]?.aborted).toBe(true)
    expect(wrapper.text()).toContain('50.0%')
    wrapper.unmount()
  })

  it('refreshes the current gauge on later durable preparation progress', async () => {
    const gaugeResult = {
      matched_count: 2, evaluated_count: 4, universe_count: 5, percentage: 0.5,
      run_at: '2026-08-03T10:00:00Z', freshness: 'current', data_provenance: 'canonical_local_database',
      calculation_version: 'analysis-v1', refreshed_at: '2026-08-03T10:01:00Z',
      freshness_detail: { requested: 5, current: 4, stale: 0, other: 1 }, exclusions: [],
    }
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Saved weekly scan' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan())
      if (path.startsWith('/data/requests/')) return Promise.resolve({ ...readyPreparation(), version: 2 })
      return Promise.resolve(gaugeResult)
    })
    apiPost.mockImplementation((path: string) => path === '/data/ensure'
      ? Promise.resolve({ ...readyPreparation(), status: 'queued', completed: 0, total: 1, has_pending_work: true })
      : Promise.resolve({}))
    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(apiGet.mock.calls.filter(([path]) => path === '/analysis/gauges/7').length).toBeGreaterThanOrEqual(2), { timeout: 2_500 })
    expect(wrapper.text()).toContain('2 matches')
    expect(wrapper.text()).toContain('50.0%')
    wrapper.unmount()
  })

  it('keeps the last completed gauge while the replacement scan is queued, then refreshes its terminal result', async () => {
    const previousGauge = {
      matched_count: 1, evaluated_count: 2, universe_count: 2, percentage: 0.5,
      run_at: '2026-08-03T10:00:00Z', freshness: 'current', data_provenance: 'canonical_local_database',
      calculation_version: 'analysis-v1', refreshed_at: '2026-08-03T10:01:00Z',
      freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, exclusions: [],
    }
    const completedGauge = { ...previousGauge, matched_count: 2, percentage: 1, run_at: '2026-08-03T10:02:00Z' }
    let latestResults: any[] = [{
      id: 10, run_at: previousGauge.run_at, matched_ids: [2], result_data: { _status: 'completed', _python_research_run_id: 15, _coverage: { evaluated_count: 2, universe_count: 2, excluded: [] } },
    }]
    let gaugeReads = 0
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Saved weekly scan' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan())
      if (path === '/screeners/7/results') return Promise.resolve(latestResults)
      if (path.startsWith('/data/requests/')) {
        latestResults = [{ id: 11, run_at: completedGauge.run_at, matched_ids: [], result_data: { _status: 'queued', _python_research_run_id: 16 } }, ...latestResults]
        return Promise.resolve({ ...readyPreparation(), status: 'partial', version: 2, has_pending_work: false })
      }
      if (path === '/analysis/gauges/7') return Promise.resolve(++gaugeReads === 1 ? previousGauge : completedGauge)
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => path === '/data/ensure'
      ? Promise.resolve({ ...readyPreparation(), status: 'queued', completed: 0, total: 1, has_pending_work: true })
      : Promise.resolve({}))

    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(wrapper.text()).toContain('50.0%'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('replacement scan is queued'))
    expect(wrapper.text()).toContain('1 matches')
    expect(gaugeReads).toBe(1)

    latestResults = [{
      id: 11, run_at: completedGauge.run_at, matched_ids: [2, 3], result_data: { _status: 'completed', _python_research_run_id: 16, _coverage: { evaluated_count: 2, universe_count: 2, excluded: [] } },
    }, ...latestResults.slice(1)]
    await vi.waitFor(() => expect(wrapper.text()).toContain('100.0%'), { timeout: 2_500 })
    expect(wrapper.text()).toContain('2 matches')
    expect(gaugeReads).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })

  it('drains an older in-flight gauge read before refreshing metrics for the newly completed result', async () => {
    const previousGauge = {
      matched_count: 1, evaluated_count: 2, universe_count: 2, percentage: 0.5,
      run_at: '2026-08-03T10:00:00Z', freshness: 'current', data_provenance: 'canonical_local_database',
      calculation_version: 'analysis-v1', refreshed_at: '2026-08-03T10:01:00Z',
      freshness_detail: { requested: 2, current: 2, stale: 0, other: 0 }, exclusions: [],
    }
    const completedGauge = { ...previousGauge, matched_count: 2, percentage: 1, run_at: '2026-08-03T10:02:00Z' }
    const queuedResult = { id: 11, run_at: completedGauge.run_at, result_data: { _status: 'queued' } }
    const completedResult = { ...queuedResult, matched_ids: [2, 3], result_data: { _status: 'completed' } }
    let latestResults: any[] = [{ id: 10, run_at: previousGauge.run_at, result_data: { _status: 'completed' } }]
    let gaugeReads = 0
    let resolveStaleGauge!: (value: typeof previousGauge) => void
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Saved weekly scan' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan())
      if (path === '/screeners/7/results') return Promise.resolve(latestResults)
      if (path === '/analysis/gauges/7') {
        gaugeReads += 1
        if (gaugeReads === 1) return Promise.resolve(previousGauge)
        if (gaugeReads === 2) return new Promise(resolve => { resolveStaleGauge = resolve })
        return Promise.resolve(completedGauge)
      }
      return Promise.resolve([])
    })

    const wrapper = mountTool(queryClient)
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(wrapper.text()).toContain('50.0%'))
    expect(gaugeReads).toBe(1)

    // This represents a refresh started while the previously completed result
    // is still selected; its response is delayed until after the new run ends.
    const staleRefresh = queryClient.refetchQueries({ queryKey: ['workstation', 'market-gauge', '7'], exact: true })
    await vi.waitFor(() => expect(gaugeReads).toBe(2))
    latestResults = [queuedResult, ...latestResults]
    await queryClient.refetchQueries({ queryKey: ['workstation', 'screener-history', '7'], exact: true })
    await vi.waitFor(() => expect(wrapper.text()).toContain('replacement scan is queued'))
    latestResults = [completedResult, ...latestResults.slice(1)]
    const completedResultRead = queryClient.refetchQueries({ queryKey: ['workstation', 'screener-history', '7'], exact: true })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Refreshing gauge metrics for the completed scan'))
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('1 matches')

    resolveStaleGauge({ ...previousGauge, matched_count: 0, percentage: 0 })
    await staleRefresh
    await completedResultRead
    await vi.waitFor(() => expect(gaugeReads).toBe(3))
    await vi.waitFor(() => expect(wrapper.text()).toContain('2 matches'))
    expect(wrapper.text()).toContain('100.0%')
    wrapper.unmount()
  })

  it('surfaces an empty gauge refresh without caching undefined', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Empty gauge' }])
      if (path === '/screeners/7') return Promise.resolve(savedScan(7))
      return Promise.resolve(undefined)
    })

    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Market gauge refresh returned no data'))
  })

  it.each([
    ['coverage_limited', 'Coverage limited', 'coverage-limited'],
    ['coverage-limited', 'Coverage limited', 'coverage-limited'],
    ['delayed', 'Delayed', 'delayed'],
  ])('normalizes %s freshness for the visible label and state styling', async (freshness, label, stateKey) => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 7, name: 'Coverage limited gauge' }])
      return Promise.resolve({
        matched_count: 0,
        evaluated_count: 0,
        universe_count: 10,
        percentage: null,
        run_at: null,
        freshness,
        data_provenance: 'canonical_local_database',
        calculation_version: 'analysis-v1',
        refreshed_at: '2026-08-03T10:01:00Z',
        freshness_detail: { requested: 10, current: 0, stale: 0, other: 10 },
        exclusions: [],
      })
    })

    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('select').setValue('7')
    await flushPromises()

    const state = wrapper.find('.market-gauge__freshness')
    expect(state.text()).toBe(label)
    expect(state.attributes('data-freshness')).toBe(stateKey)
  })
})
