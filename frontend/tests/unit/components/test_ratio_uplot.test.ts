import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
import RatioUPlot from '@/components/workstation/RatioUPlot.vue'
import uPlot from 'uplot'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('RatioUPlot', () => {
  afterEach(() => Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }))

  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset().mockResolvedValue({
      request_id: 'ratio-ready', status: 'ready', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, dependencies: [], completed: 2, total: 2, last_progress_at: '2026-11-06T12:00:00Z',
    })
    vi.mocked(uPlot).mockClear()
  })

  function mountTool(options: Record<string, any>, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
    return mount(RatioUPlot, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
  }

  it('requests selected-sector and market ratios without filling their gaps', async () => {
    vi.mocked(api.get).mockImplementation(async (_path, options) => ({
      coverage: options?.benchmark === 'XLK' ? 0.8 : 0.6,
      points: [
        { timestamp: '2026-01-01T00:00:00Z', value: options?.benchmark === 'XLK' ? 1.1 : 0.9 },
        { timestamp: '2026-01-02T00:00:00Z', value: options?.benchmark === 'XLK' ? 1.2 : 1.0 },
      ],
      warnings: options?.benchmark === 'XLK' ? [{ message: 'Only intersecting timestamps were used.' }] : [],
    }))
    const wrapper = mountTool({ props: { symbol: 'NVDA', benchmarks: ['XLK', 'SPY'], timeframe: 'W1' } })
    await vi.waitFor(async () => {
      await nextTick()
      expect(wrapper.text()).toContain('XLK 80%')
      expect(wrapper.text()).toContain('SPY 60%')
    })

    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'XLK', timeframe: 'W1', adjusted: true,
    }, expect.any(Object))
    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'SPY', timeframe: 'W1', adjusted: true,
    }, expect.any(Object))
    expect(api.post).toHaveBeenCalledTimes(2)
    expect(api.post).toHaveBeenNthCalledWith(1, '/data/ensure', expect.objectContaining({
      target: { kind: 'instrument', symbol: 'NVDA' }, datasets: ['identity', 'history'], timeframe: 'W1', adjusted: true,
      analysis: { kind: 'ratio', legs: [{ symbol: 'NVDA' }, { symbol: 'XLK' }] },
    }), expect.any(Object))
    expect(api.post).toHaveBeenNthCalledWith(2, '/data/ensure', expect.objectContaining({
      analysis: { kind: 'ratio', legs: [{ symbol: 'NVDA' }, { symbol: 'SPY' }] },
    }), expect.any(Object))
    expect(wrapper.text()).toContain('NVDA/XLK')
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(wrapper.text()).toContain('Only intersecting timestamps were used.')
  })

  it('renders only timestamps shared by every requested ratio leg', async () => {
    vi.mocked(api.get).mockImplementation(async (_path, options) => ({
      coverage: 0.5,
      points: options?.benchmark === 'XLK'
        ? [
            { timestamp: '2026-01-01T00:00:00Z', value: 1.1 },
            { timestamp: '2026-01-03T00:00:00Z', value: 1.3 },
          ]
        : [
            { timestamp: '2026-01-02T00:00:00Z', value: 0.9 },
            { timestamp: '2026-01-03T00:00:00Z', value: 1.0 },
          ],
      warnings: [],
    }))
    mountTool({ props: { symbol: 'NVDA', benchmarks: ['XLK', 'SPY'] } })

    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalled())
    const data = vi.mocked(uPlot).mock.calls.at(-1)?.[1]
    expect(data?.[0]).toEqual([Date.parse('2026-01-03T00:00:00Z') / 1000])
    expect(data?.[1]).toEqual([1.3])
    expect(data?.[2]).toEqual([1.0])
  })

  it('announces the empty ratio state politely', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })

    const empty = wrapper.get('.ratio-chart__state')
    expect(empty.attributes('role')).toBe('status')
    expect(empty.attributes('aria-live')).toBe('polite')
    expect(empty.attributes('aria-atomic')).toBe('true')
  })

  it('reports an unavailable comparison without replacing other ratio curves', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('Ratio service unavailable'))
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('SPY: This comparison is unavailable'))
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.find('.ratio-chart__state--error').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Ratio service unavailable')
  })

  it('keeps the source-specific held reason visible while retaining cached ratio results', async () => {
    vi.mocked(api.post).mockResolvedValue({
      request_id: 'ratio-held', status: 'unavailable', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, completed: 1, total: 2, last_progress_at: '2026-11-06T12:00:00Z', dependencies: [{
        dependency_id: 'history:NVDA:W1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'unavailable',
        requested_start: null, requested_end: null, covered_start: null, covered_end: null,
        reason_code: 'source_credentials_not_configured', retry_at: null, updated_at: '2026-11-06T12:00:00Z',
      }],
    })
    vi.mocked(api.get).mockResolvedValue({ coverage: 0.6, points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1.2 }], warnings: [] })
    const wrapper = mountTool({ props: { symbol: 'NVDA', benchmarks: ['SPY'] } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('credentials are not available'))
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(wrapper.text()).not.toContain('source_credentials_not_configured')
    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', expect.objectContaining({ symbol: 'NVDA', benchmark: 'SPY' }), expect.any(Object))
  })

  it('renders local ratio data before a delayed preparation response and preserves it on failure', async () => {
    let releasePreparation!: (value: unknown) => void
    vi.mocked(api.post).mockReturnValueOnce(new Promise(resolve => { releasePreparation = resolve }) as any)
    vi.mocked(api.get).mockResolvedValue({
      coverage: 0.75,
      points: [{ timestamp: '2026-01-02T00:00:00Z', value: 1.25 }],
      warnings: [],
    })
    const wrapper = mountTool({ props: { symbol: 'NVDA', benchmarks: ['SPY'] } })

    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))
    expect(wrapper.get('.ratio-chart').attributes('aria-busy')).toBe('true')
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(wrapper.text()).toContain('Checking ratio inputs…')
    releasePreparation({
      request_id: 'ratio-held', status: 'unavailable', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, completed: 1, total: 2, last_progress_at: '2026-11-06T12:00:00Z', dependencies: [{
        dependency_id: 'history:NVDA:W1', depends_on: [], instrument_id: 1, dataset: 'history', status: 'unavailable',
        requested_start: null, requested_end: null, covered_start: null, covered_end: null,
        reason_code: 'history_provider_unavailable', retry_at: null, updated_at: '2026-11-06T12:00:00Z',
      }],
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('reviewed data source'))
    expect(uPlot).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('NVDA/SPY')
    wrapper.unmount()
  })

  it('keeps successful local ratio data visible when the preparation request fails', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('provider_quota_admission_denied'))
    vi.mocked(api.get).mockResolvedValue({
      coverage: 1,
      points: [{ timestamp: '2026-01-02T00:00:00Z', value: 1.25 }],
      warnings: [],
    })
    const wrapper = mountTool({ props: { symbol: 'NVDA', benchmarks: ['SPY'] } })

    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(wrapper.text()).toContain('available local results remain visible'))
    expect(wrapper.text()).not.toContain('provider_quota_admission_denied')
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(uPlot).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('reloads ratios using the active linked timeframe', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'], timeframe: 'D1' } })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true,
    }, expect.any(Object)))
    vi.mocked(api.get).mockClear()

    await wrapper.setProps({ timeframe: 'W1' })
    await vi.waitFor(() => {
      expect(api.get).toHaveBeenCalledTimes(1)
      expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
        symbol: 'XLK', benchmark: 'SPY', timeframe: 'W1', adjusted: true,
      }, expect.any(Object))
    })
  })

  it('suspends ratio requests while the browser document is hidden', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await nextTick()
    expect(api.get).not.toHaveBeenCalled()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true,
    }, expect.any(Object)))
    wrapper.unmount()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  it('passes a persisted point-in-time cutoff without changing the current-view request shape', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'], asOf: '2025-12-31T23:59:59Z' } })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true, as_of: '2025-12-31T23:59:59Z',
    }, expect.any(Object)))
  })

  it('persists the ratio cutoff from the tool control', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    const input = wrapper.get('input[aria-label="Ratio as of"]')
    await input.setValue('2025-12-31')
    expect(wrapper.emitted('configuration')).toContainEqual([{ as_of: '2025-12-31' }])
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true, as_of: '2025-12-31T23:59:59Z',
    }, expect.any(Object)))
  })

  it('lets the primary ratio tool add and remove arbitrary comparison legs', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'], editableBenchmarks: true } })
    const input = wrapper.get('input[aria-label="Ratio comparison symbol"]')
    await input.setValue('xle')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('configuration')).toContainEqual([{ ratio_benchmarks: ['SPY', 'XLE'] }])
    // The editor must reflect the edit before the debounced workspace snapshot
    // returns the updated serialized configuration.
    expect(wrapper.text()).toContain('XLK/SPY · XLK/XLE')
    expect(wrapper.get('button[aria-label="Remove ratio comparison XLE"]')).toBeTruthy()

    await wrapper.setProps({ benchmarks: ['SPY', 'XLE'] })
    expect(wrapper.text()).toContain('XLK/SPY · XLK/XLE')
    await wrapper.get('button[aria-label="Remove ratio comparison XLE"]').trigger('click')
    expect(wrapper.emitted('configuration')).toContainEqual([{ ratio_benchmarks: ['SPY'] }])
  })

  it('keeps a valid plotted pair when a newly added comparator is still loading and then unavailable', async () => {
    let failXle!: (error: Error) => void
    const xleRead = new Promise((_, reject) => { failXle = reject })
    vi.mocked(api.get).mockImplementation(async (_path, options) => {
      if (options?.benchmark === 'XLE') return xleRead
      return {
        coverage: 1,
        points: [{ timestamp: '2026-01-02T00:00:00Z', value: 1.25 }],
        warnings: [],
      }
    })
    const wrapper = mountTool({ props: { symbol: 'NVDA', benchmarks: ['SPY'], editableBenchmarks: true } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalled())
    const chart = vi.mocked(uPlot).mock.results.at(-1)?.value
    const validPairData = [
      [Math.floor(Date.parse('2026-01-02T00:00:00Z') / 1000)],
      [1.25],
    ]
    expect(vi.mocked(uPlot).mock.calls.at(-1)?.[1]).toEqual(validPairData)
    // Match the real uPlot series shape so the subsequent data update is
    // observable through setData in this canvas-free component test.
    chart.series = [{}, {}]

    await wrapper.setProps({ benchmarks: ['SPY', 'XLE'] })
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledTimes(3))
    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'XLE', timeframe: 'D1', adjusted: true,
    }, expect.any(Object))
    expect(wrapper.text()).toContain('NVDA/SPY · NVDA/XLE')
    expect(wrapper.get('.ratio-chart').attributes('aria-busy')).toBe('true')
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(chart.data).toEqual(validPairData)
    expect(chart.setData).not.toHaveBeenCalled()

    failXle(new Error('instrument_not_found'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLE: This comparison is unavailable'))

    expect(wrapper.find('.ratio-chart__state--error').exists()).toBe(false)
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(wrapper.text()).not.toContain('instrument_not_found')
    expect(chart.setData).toHaveBeenCalled()
    const lastData = chart.setData.mock.calls.at(-1)?.[0]
    expect(lastData).toEqual(validPairData)
    wrapper.unmount()
  })

  it('publishes ratio crosshair timestamps and consumes linked timestamps without echoing them', async () => {
    vi.mocked(api.get).mockResolvedValue({
      coverage: 1,
      points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1 }],
      warnings: [],
    })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalled())
    const options = vi.mocked(uPlot).mock.calls.at(-1)?.[0]
    const setCursor = options?.hooks?.setCursor?.[0]
    expect(setCursor).toBeDefined()

    setCursor?.({ cursor: { idx: 0 }, data: [[1767225600]] } as unknown as uPlot)
    expect(wrapper.emitted('cursorTimestamp')).toEqual([['2026-01-01T00:00:00.000Z']])

    const chart = vi.mocked(uPlot).mock.results.at(-1)?.value
    await wrapper.setProps({ linkedTimestamp: '2026-01-01T00:00:00Z' })
    expect(wrapper.get('.ratio-chart').attributes('data-linked-timestamp')).toBe('2026-01-01T00:00:00Z')
    expect(chart.setCursor).toHaveBeenCalled()
    setCursor?.({ cursor: { idx: 0 }, data: [[1767225600]] } as unknown as uPlot)
    expect(wrapper.emitted('cursorTimestamp')).toHaveLength(1)
    await wrapper.setProps({ linkedTimestamp: null })
    expect(wrapper.get('.ratio-chart').attributes('data-linked-timestamp')).toBeUndefined()
  })

  it('hides uPlot’s duplicate legend so compact windows keep the warning row clear', async () => {
    vi.mocked(api.get).mockResolvedValue({
      coverage: 1,
      points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1 }],
      warnings: [{ message: 'Only intersecting timestamps were used.' }],
    })
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalled())
    const options = vi.mocked(uPlot).mock.calls.at(-1)?.[0]
    expect(options?.legend).toEqual({ show: false })
    expect(wrapper.find('.ratio-chart__warning').exists()).toBe(true)
  })

  it('ignores a late ratio response after the active symbol changes', async () => {
    let resolveOld: ((value: unknown) => void) | undefined
    const oldResponse = new Promise(resolve => { resolveOld = resolve })
    vi.mocked(api.get).mockImplementation((_path, options) => options?.symbol === 'XLK'
      ? oldResponse as Promise<unknown>
      : Promise.resolve({ coverage: 1, points: [{ timestamp: '2026-02-01T00:00:00Z', value: 2 }], warnings: [] }))
    const wrapper = mountTool({ props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', expect.objectContaining({ symbol: 'XLK' }), expect.any(Object)))
    await wrapper.setProps({ symbol: 'XLE' })
    await vi.waitFor(() => expect(wrapper.text()).toContain('SPY 100%'))
    resolveOld?.({ coverage: 0.1, points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1 }], warnings: [] })
    await nextTick()
    expect(wrapper.text()).not.toContain('SPY 10%')
  })

  it('deduplicates identical ratio legs across linked windows', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = mountTool({ props: { symbol: 'NVDA', benchmarks: ['XLK', 'SPY'] } }, queryClient)
    const second = mountTool({ props: { symbol: 'NVDA', benchmarks: ['XLK', 'SPY'] } }, queryClient)
    await vi.waitFor(() => expect(first.text()).toContain('No aligned local bars.'))
    await vi.waitFor(() => expect(second.text()).toContain('No aligned local bars.'))
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
