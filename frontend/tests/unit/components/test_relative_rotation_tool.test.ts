import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
import uPlot from 'uplot'
import RelativeRotationTool from '@/components/workstation/RelativeRotationTool.vue'

let resize: (() => void) | null = null
let observedHost: Element | null = null
class ResizeObserverMock {
  constructor(callback: () => void) { resize = callback }
  observe(element: Element) { observedHost = element }
  disconnect() { observedHost = null }
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('RelativeRotationTool', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset().mockResolvedValue({
      request_id: 'rrg-ready', status: 'ready', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, dependencies: [], completed: 1, total: 1, last_progress_at: '2026-11-06T12:00:00Z',
    })
    vi.mocked(uPlot).mockClear()
    resize = null
    observedHost = null
  })

  function mountTool(options: Record<string, any> = {}, queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })) {
    return mount(RelativeRotationTool, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
  }

  it('resizes the existing uPlot instance instead of recreating it', async () => {
    vi.mocked(api.get).mockResolvedValue({
      freshness: 'current',
      rows: [{ instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, heading: 63, distance: 0.224, velocity: 0.02, transition: 'improving->leading', time_in_state: 3, coverage: 1, tail: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }] }],
    })
    const wrapper = mountTool()
    expect(wrapper.find('[role="region"][aria-label="Relative rotation vs SPY"]').exists()).toBe(true)
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    await vi.waitFor(async () => { await nextTick(); expect(wrapper.text()).toContain('XLK') })
    await nextTick()
    expect(wrapper.text()).toContain('improving->leading')
    expect(wrapper.text()).toContain('63°')
    expect(wrapper.get('.rotation-tool__plot').attributes('role')).toBe('group')
    expect(wrapper.get('.rotation-tool__plot').attributes('tabindex')).toBe('0')
    expect(wrapper.get('.rotation-tool__plot').attributes('aria-label')).toBe('Relative rotation trend and momentum plane')
    expect(wrapper.get('.rotation-tool__plot').attributes('aria-describedby')).toBe(wrapper.get('.rotation-tool__sr-only').attributes('id'))
    expect(wrapper.get('.rotation-tool__plot').attributes('aria-keyshortcuts')).toContain('ArrowRight')
    expect(wrapper.get('.rotation-tool').attributes('tabindex')).toBe('0')
    expect(wrapper.get('.rotation-tool__settings > summary').text()).toBe('Settings')
    expect(wrapper.get('.rotation-tool__settings').attributes('open')).toBeUndefined()
    expect(wrapper.get('.rotation-tool__rows-disclosure > summary').text()).toBe('Rows · 1')
    expect(wrapper.get('.rotation-tool__rows-disclosure').attributes('open')).toBeUndefined()
    expect(wrapper.find('.rotation-tool__plot-shell .compact-status').exists()).toBe(false)
    expect(wrapper.get('.rotation-tool__table').exists()).toBe(true)
    expect(wrapper.get('.rotation-tool__warning-heading').text()).toBe('Warnings')
    expect(observedHost).toBe(wrapper.get('.rotation-tool__plot').element)
    resize?.()
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    resize?.()
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    expect(chart.setData).toHaveBeenCalled()
    expect(chart.setSize).toHaveBeenCalled()
  })

  it('builds numeric domains from finite ratio points and draws quadrant labels and XY markers', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.12, momentum: 0.2, coverage: 1, tail: [], history: [
        { timestamp: '2026-01-01', trend: 0.12, momentum: 0.2 },
        { timestamp: '2026-01-02', trend: -0.05, momentum: -0.14 },
      ] },
      { instrument_id: 2, symbol: 'XLE', state: 'improving', trend: 0.04, momentum: 0.05, coverage: 1, tail: [], history: [
        { timestamp: '2026-01-02', trend: 0.04, momentum: 0.05 },
      ] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLE'))
    await nextTick()
    resize?.()
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))

    const [options, data] = vi.mocked(uPlot).mock.calls.at(-1)!
    expect(options.scales?.x?.time).toBe(false)
    expect(options.scales?.y?.auto).toBe(true)
    expect(data[0]).toEqual([-0.05, 0.04, 0.12])
    expect(data[1]).toEqual([-0.14, 0.05, 0.2])
    const xRange = options.scales?.x?.range as () => [number, number]
    const yRange = options.scales?.y?.range as () => [number, number]
    expect(xRange()[0]).toBeLessThan(-0.05)
    expect(xRange()[1]).toBeGreaterThan(0.12)
    expect(yRange()[0]).toBeLessThan(-0.14)
    expect(yRange()[1]).toBeGreaterThan(0.2)
    expect(xRange()[0]).toBeLessThan(0)
    expect(xRange()[1]).toBeGreaterThan(0)
    expect(yRange()[0]).toBeLessThan(0)
    expect(yRange()[1]).toBeGreaterThan(0)

    const chart = vi.mocked(uPlot).mock.results[0].value
    const draw = options.plugins?.[0].hooks.draw[0]
    draw(chart)
    expect(chart.ctx.fillText.mock.calls.map(([label]) => label)).toEqual(['Leading', 'Weakening', 'Improving', 'Lagging', 'XLK', 'XLE'])
    expect(chart.ctx.arc).toHaveBeenCalledTimes(3)
    expect(Math.min(...chart.ctx.arc.mock.invocationCallOrder)).toBeGreaterThan(Math.max(...chart.ctx.fillRect.mock.invocationCallOrder))
    expect(chart.ctx.stroke).toHaveBeenCalled()
    expect(chart.valToPos).toHaveBeenCalledWith(0, 'x', true)
    expect(chart.valToPos).toHaveBeenCalledWith(0, 'y', true)
    expect(chart.valToPos).toHaveBeenCalledWith(0.12, 'x', true)
    chart.ctx.canvas.width = 1125
    Object.defineProperty(chart, 'width', { value: 900 })
    Object.defineProperty(chart, 'bbox', { value: { left: 20, top: 30, width: 850, height: 440 } })
    draw(chart)
    expect(chart.ctx.arc.mock.calls.at(-1)?.[2]).toBe(4.375)
    wrapper.unmount()
  })

  it('reserves a compact XY data plane while keeping accurate RRG axes', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [{
      instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1,
      tail: [], history: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }],
    }] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))

    const [options] = vi.mocked(uPlot).mock.calls.at(-1)!
    expect(options.legend).toEqual({ show: false })
    expect(options.padding).toEqual([2, 4, 2, 4])
    expect(options.axes?.[0]).toMatchObject({ label: 'Relative trend', size: 14, gap: 1, labelSize: 10, labelGap: 1 })
    expect(options.axes?.[1]).toMatchObject({ label: 'Relative momentum', labelSize: 10, labelGap: 1 })
    const formatPercent = options.axes?.[0].values as (chart: any, values: number[]) => string[]
    expect(formatPercent({}, [-0.1, 0.1])).toEqual(['-10.0%', '10.0%'])
    const measuredWidth = options.axes?.[1].size as (chart: any, values: string[] | null, axisIndex: number, cycle: number) => number
    const measureText = vi.fn((value: string) => ({ width: value.length * 6 }))
    expect(measuredWidth({ ctx: { measureText } }, null, 1, 0)).toBe(6)
    expect(measuredWidth({ ctx: { measureText } }, ['0.0%', '-120.0%'], 1, 0)).toBe(48)
    expect(measureText).toHaveBeenCalledWith('-120.0%')
    expect(wrapper.get('.rotation-tool__plot').attributes('aria-label')).toBe('Relative rotation trend and momentum plane')
    wrapper.unmount()
  })

  it('sizes the RRG canvas to a short dock host instead of imposing a taller minimum', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [{
      instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1,
      tail: [], history: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }],
    }] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.find('.rotation-tool__plot').exists()).toBe(true))
    const host = wrapper.get('.rotation-tool__plot').element
    Object.defineProperty(host, 'clientHeight', { configurable: true, value: 96 })

    resize?.()

    const chart = vi.mocked(uPlot).mock.results.at(-1)?.value
    expect(chart?.setSize).toHaveBeenLastCalledWith(expect.objectContaining({ height: 96 }))
    expect(wrapper.get('.rotation-tool__settings > summary').text()).toBe('Settings')
    expect(wrapper.get('.rotation-tool__rows-disclosure > summary').text()).toBe('Rows · 1')
    wrapper.unmount()
  })

  it('keeps near-coincident latest marker centers visible above symbol label backdrops', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'weakening', coverage: 1, tail: [], history: [{ timestamp: '2026-01-01', trend: 0.00023907524, momentum: -0.00010455282 }] },
      { instrument_id: 2, symbol: 'XLY', state: 'weakening', coverage: 1, tail: [], history: [{ timestamp: '2026-01-01', trend: 0.00023907530, momentum: -0.00010455269 }] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLY'))
    await nextTick()
    resize?.()
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))

    const [options] = vi.mocked(uPlot).mock.calls.at(-1)!
    const chart = vi.mocked(uPlot).mock.results.at(-1)!.value
    options.plugins?.[0].hooks.draw[0](chart)

    expect(chart.ctx.fillRect).toHaveBeenCalledTimes(2)
    expect(chart.ctx.fillText.mock.calls.slice(-2).map(([label]) => label)).toEqual(['XLK', 'XLY'])
    const [firstLabel, secondLabel] = chart.ctx.fillRect.mock.calls
    const overlapWidth = Math.max(0, Math.min(firstLabel[0] + firstLabel[2], secondLabel[0] + secondLabel[2]) - Math.max(firstLabel[0], secondLabel[0]))
    const overlapHeight = Math.max(0, Math.min(firstLabel[1] + firstLabel[3], secondLabel[1] + secondLabel[3]) - Math.max(firstLabel[1], secondLabel[1]))
    expect(overlapWidth * overlapHeight, 'crowded labels occupy separate visible space').toBe(0)
    expect(Math.min(...chart.ctx.arc.mock.invocationCallOrder)).toBeGreaterThan(Math.max(...chart.ctx.fillRect.mock.invocationCallOrder))
    expect(chart.ctx.arc).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('draws every historical marker before latest markers across rows', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', coverage: 1, tail: [], history: [
        { timestamp: '2026-01-02', trend: 0.1, momentum: 0.2 },
      ] },
      { instrument_id: 2, symbol: 'XLY', state: 'lagging', coverage: 1, tail: [], history: [
        { timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 },
        { timestamp: '2026-01-02', trend: 0.2, momentum: 0.3 },
      ] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLY'))
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))

    const [options] = vi.mocked(uPlot).mock.calls.at(-1)!
    const chart = vi.mocked(uPlot).mock.results.at(-1)!.value
    chart.valToPos.mockImplementation((value: number) => value * 1000)
    const markerPaintOrder: Array<{ x: number; y: number; radius: number; color: unknown }> = []
    chart.ctx.arc.mockImplementation((x: number, y: number, radius: number) => {
      markerPaintOrder.push({ x, y, radius, color: chart.ctx.fillStyle })
    })

    options.plugins?.[0].hooks.draw[0](chart)

    expect(markerPaintOrder).toEqual([
      { x: 100, y: 200, radius: 2, color: '#df8181' },
      { x: 100, y: 200, radius: 3.5, color: '#61c58c' },
      { x: 200, y: 300, radius: 3.5, color: '#df8181' },
    ])
    wrapper.unmount()
  })

  it('hit-tests against the plot-area origin rather than the host origin', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', coverage: 1, tail: [], history: [
        { timestamp: '2026-01-01', trend: -0.14, momentum: -0.18 },
        { timestamp: '2026-01-02', trend: -0.13, momentum: -0.17 },
      ] },
      { instrument_id: 2, symbol: 'XLV', state: 'leading', coverage: 1, tail: [], history: [
        { timestamp: '2026-01-01', trend: 0.15, momentum: 0.16 },
        { timestamp: '2026-01-02', trend: 0.16, momentum: 0.17 },
      ] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))

    const chart = vi.mocked(uPlot).mock.results[0].value
    chart.rect = { left: 50, top: 75, width: 220, height: 100, right: 270, bottom: 175 }
    chart.valToPos.mockImplementation((value, scale) => value < 0 ? (scale === 'x' ? 20 : 30) : (scale === 'x' ? 100 : 120))
    const host = wrapper.get('.rotation-tool__plot').element
    Object.defineProperty(host, 'getBoundingClientRect', { value: () => ({ left: 0, top: 0, width: 300, height: 200, right: 300, bottom: 200 }) })

    await wrapper.get('.rotation-tool__plot-shell').trigger('mousemove', { clientX: 150, clientY: 195 })

    expect(wrapper.get('.rotation-tool__tooltip').text()).toContain('XLV')
    await wrapper.get('.rotation-tool__plot').trigger('focus')
    await wrapper.get('.rotation-tool__plot-shell').trigger('click')
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['XLV', 2])
    expect(chart.syncRect).toHaveBeenCalled()
    expect(chart.valToPos).toHaveBeenCalledWith(0.16, 'x')
    expect(chart.valToPos).toHaveBeenCalledWith(0.17, 'y')
    wrapper.unmount()
  })

  it('replaces both scale bounds when a later timeframe returns disjoint plotted values', async () => {
    let releaseWeeklyResponse: ((value: any) => void) | null = null
    let weeklyReads = 0
    const oldPayload = { freshness: 'current', rows: [{ instrument_id: 1, symbol: 'OLD', state: 'leading', coverage: 1, tail: [], history: [
        { timestamp: '2026-01-01', trend: -0.1, momentum: -0.2 },
        { timestamp: '2026-01-02', trend: 0.1, momentum: 0.2 },
      ] }] }
    const newPayload = { freshness: 'current', rows: [{ instrument_id: 2, symbol: 'NEW', state: 'improving', coverage: 1, tail: [], history: [
      { timestamp: '2026-02-01', trend: 100, momentum: 300 },
      { timestamp: '2026-02-02', trend: 200, momentum: 500 },
    ] }] }
    vi.mocked(api.get).mockImplementation((_path, params) => {
      if (params?.timeframe !== 'W1') return Promise.resolve(oldPayload)
      weeklyReads += 1
      if (weeklyReads === 1) return new Promise(resolve => { releaseWeeklyResponse = resolve })
      return Promise.resolve(newPayload)
    })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('OLD'))
    await nextTick()
    resize?.()
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))
    const [options] = vi.mocked(uPlot).mock.calls[0]
    const chart = vi.mocked(uPlot).mock.results[0].value
    const initialPlotHost = wrapper.get('.rotation-tool__plot').element
    expect((options.scales?.y?.range as () => [number, number])()[1]).toBeLessThan(1)

    vi.mocked(api.get).mockClear()
    await wrapper.get('select[aria-label="Rotation timeframe"]').setValue('W1')
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ timeframe: 'W1' }), expect.any(Object)))
    expect(wrapper.get('.rotation-tool__plot').element).toBe(initialPlotHost)
    expect(wrapper.get('.rotation-tool__status .compact-status__detail').text()).toContain('Updating sp500-sectors · W1')
    expect(wrapper.get('.rotation-tool__status .compact-status__detail').text()).toContain('Showing sp500-sectors · D1')
    releaseWeeklyResponse?.(newPayload)
    await vi.waitFor(() => expect(wrapper.text()).toContain('NEW'))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
    expect(uPlot).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(chart.setData).toHaveBeenCalled())

    expect(chart.setScale.mock.calls.slice(-2)).toEqual([
      ['x', { min: -16, max: 216 }],
      ['y', { min: -40, max: 540 }],
    ])
    expect((options.scales?.x?.range as () => [number, number])()).toEqual([-16, 216])
    expect((options.scales?.y?.range as () => [number, number])()).toEqual([-40, 540])
    wrapper.unmount()
  })

  it('persists and sends transparent rotation controls', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'stale', rows: [] })
    const wrapper = mountTool({ props: { configuration: { group_key: 'us-benchmarks', benchmark: 'QQQ', timeframe: 'W1', sampling: 3, lookback: 12, tail_length: 4, as_of: '2024-04-30', adjusted: false } } })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/data/ensure', expect.objectContaining({
      target: { kind: 'market_group', group_key: 'us-benchmarks' }, datasets: ['identity', 'history'], timeframe: 'W1',
      adjusted: false, end_at: '2024-04-30T23:59:59Z',
      analysis: { kind: 'rrg', lookback: 12, sampling: 3, tail_length: 4, history_length: 0, benchmark_symbol: 'QQQ' },
    }), expect.any(Object))
    expect(api.get).toHaveBeenLastCalledWith('/analysis/groups/us-benchmarks/relative-rotation', { benchmark: 'QQQ', timeframe: 'W1', adjusted: false, sampling: 3, lookback: 12, tail_length: 4, history_length: 0, as_of: '2024-04-30T23:59:59Z' }, expect.any(Object))
    await wrapper.get('input[aria-label="Rotation benchmark"]').setValue('IWM')
    await vi.waitFor(() => expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ group_key: 'us-benchmarks', benchmark: 'IWM', timeframe: 'W1', sampling: 3, lookback: 12, tail_length: 4, as_of: '2024-04-30', adjusted: false })))
  })

  it('requests and persists bounded historical rotation curves', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [{ instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1, tail: [], history: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }] }] })
    const wrapper = mountTool({ props: { configuration: { history_length: 120 } } })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/relative-rotation', expect.objectContaining({ history_length: 120 }), expect.any(Object)))
    expect(wrapper.find('input[aria-label="Rotation history length"]').element).toHaveProperty('value', '120')
    expect(wrapper.text()).toContain('120 history points')
  })

  it('draws the current local RRG result while data preparation is still pending', async () => {
    let releasePreparation!: (value: unknown) => void
    vi.mocked(api.post).mockReturnValueOnce(new Promise(resolve => { releasePreparation = resolve }) as any)
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [{
      instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1,
      tail: [], history: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }],
    }] })
    const wrapper = mountTool()

    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    await vi.waitFor(() => expect(uPlot).toHaveBeenCalledTimes(1))
    expect(wrapper.get('.rotation-tool__plot').exists()).toBe(true)
    expect(wrapper.get('.rotation-tool__status .compact-status__detail').text()).toBe('Updating ratios…')
    releasePreparation({
      request_id: 'rrg-unavailable', status: 'unavailable', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, completed: 1, total: 2, last_progress_at: '2026-11-06T12:00:00Z', dependencies: [{
        dependency_id: 'history:1:D1', depends_on: [], instrument_id: 1, symbol: 'XLK', dataset: 'history', status: 'unavailable',
        requested_start: null, requested_end: null, covered_start: null, covered_end: null,
        covered_ranges: [], reason_code: 'source_history_unavailable', retry_at: null, updated_at: '2026-11-06T12:00:00Z',
      }],
    })
    await vi.waitFor(() => expect(wrapper.get('.rotation-tool__status .compact-status__detail').text()).toContain('reviewed data source'))
    expect(wrapper.text()).toContain('XLK')
    expect(uPlot).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps a successful local RRG result when the preparation request fails', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('provider_quota_admission_denied'))
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [{
      instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1,
      tail: [], history: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }],
    }] })
    const wrapper = mountTool()

    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    await vi.waitFor(() => expect(wrapper.get('.rotation-tool__status .compact-status__detail').text()).toContain('showing available local results'))
    expect(wrapper.text()).not.toContain('provider_quota_admission_denied')
    expect(uPlot).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('refreshes after successive partial RRG versions when a later history chunk adds usable bars', async () => {
    const progressResponse = (status: 'partial' | 'ready', version: number, coveredEnd: string) => ({
      request_id: 'rrg-progress', status, created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version, target: { kind: 'market_group', group_key: 'sp500-sectors' }, completed: status === 'ready' ? 1 : 0,
      total: 1, last_progress_at: '2026-11-06T12:00:00Z', dependencies: [{
        dependency_id: 'history:group:sp500-sectors:MN', depends_on: [], instrument_id: 1, symbol: null, dataset: 'history', status,
        requested_start: '2024-11-01T00:00:00Z', requested_end: '2026-11-06T00:00:00Z',
        covered_start: '2025-11-01T00:00:00Z', covered_end: coveredEnd,
        covered_ranges: [{ start_at: '2025-11-01T00:00:00Z', end_at: coveredEnd, data_source_id: 1, market_series_id: 1,
          adjustment_basis: 'split_and_dividend_adjusted', adjustment_version: '1', is_adjusted: true }],
        reason_code: null, retry_at: null, updated_at: `2026-11-06T12:00:0${version}Z`,
      }],
    })
    const progress = [
      progressResponse('partial', 2, '2025-11-15T00:00:00Z'),
      progressResponse('partial', 3, '2025-12-15T00:00:00Z'),
      progressResponse('ready', 4, '2026-11-05T00:00:00Z'),
    ]
    let progressReads = 0
    let analysisReads = 0
    vi.mocked(api.post).mockResolvedValue({
      request_id: 'rrg-progress', status: 'running', created_at: '2026-11-06T12:00:00Z', updated_at: '2026-11-06T12:00:00Z',
      version: 1, target: {}, dependencies: [], completed: 0, total: 1, last_progress_at: '2026-11-06T12:00:00Z',
    })
    vi.mocked(api.get).mockImplementation((path) => {
      if (path.startsWith('/data/requests/')) return Promise.resolve(progress[progressReads++])
      analysisReads += 1
      return Promise.resolve(analysisReads < 3 ? { freshness: 'partial', rows: [] } : {
        freshness: 'partial', rows: [{ instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.12, momentum: 0.2,
          coverage: 1, tail: [{ timestamp: '2026-01-02', trend: 0.12, momentum: 0.2 }],
          history: [{ timestamp: '2026-01-02', trend: 0.12, momentum: 0.2 }] }],
      })
    })
    const wrapper = mountTool()

    await vi.waitFor(() => expect(analysisReads).toBe(1))
    await vi.waitFor(() => expect(progressReads).toBe(1), { timeout: 2_000 })
    await vi.waitFor(() => expect(analysisReads).toBe(2))
    expect(wrapper.find('.rotation-tool__row').exists()).toBe(false)

    await vi.waitFor(() => expect(progressReads).toBe(2), { timeout: 2_000 })
    await vi.waitFor(() => expect(analysisReads).toBe(3))
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    expect(uPlot).toHaveBeenCalledTimes(1)

    await vi.waitFor(() => expect(progressReads).toBe(3), { timeout: 2_000 })
    await vi.waitFor(() => expect(analysisReads).toBe(4))
    expect(wrapper.get('.rotation-tool__row').text()).toContain('XLK')
    expect(vi.mocked(uPlot).mock.calls.at(-1)?.[1][0]).toEqual([0.12])
    wrapper.unmount()
  })

  it('accepts an extended history window above the former thousand-point cap', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [] })
    const wrapper = mountTool({ props: { configuration: { history_length: 1200 } } })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/relative-rotation', expect.objectContaining({ history_length: 1200 }), expect.any(Object)))
    expect(wrapper.find('input[aria-label="Rotation history length"]').element).toHaveProperty('value', '1200')
  })

  it('uses the benchmark-family role rotation contract without borrowing SPY', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'coverage_limited', benchmark: 'MDY', roles: [
      { role: 'cap_weight', instrument_id: 1, symbol: 'MDY', label: 'MDY', verification_state: 'verified', available: true, state: 'leading', trend: 0, momentum: 0, coverage: 1, tail: [] },
      { role: 'equal_weight', instrument_id: null, symbol: null, label: 'No verified mapped proxy', verification_state: 'not_verified', available: false, state: null, trend: null, momentum: null, coverage: 0, tail: [], warnings: [{ code: 'role_mapping_unavailable', message: 'No equal proxy' }] },
    ] })
    const wrapper = mountTool({ props: { configuration: { group_key: 'sp400', benchmark: 'SPY' } } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('MDY'))
    expect(wrapper.find('[role="region"][aria-label="Relative rotation vs MDY"]').exists()).toBe(true)
    expect(api.post).toHaveBeenCalledWith('/data/ensure', expect.objectContaining({
      target: { kind: 'family', family_key: 'sp400' }, timeframe: 'D1',
      analysis: expect.objectContaining({ kind: 'rrg', lookback: 20, sampling: 1 }),
    }), expect.any(Object))
    expect(api.get).toHaveBeenCalledWith('/analysis/benchmark-families/sp400/relative-rotation', expect.not.objectContaining({ benchmark: 'SPY' }), expect.any(Object))
    expect(wrapper.text()).toContain('No verified mapped proxy')
  })

  it('sorts the companion table from its headers', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.1, distance: 0.14, coverage: 1, tail: [] },
      { instrument_id: 2, symbol: 'XLE', state: 'lagging', trend: -0.1, momentum: -0.1, distance: 0.14, coverage: 1, tail: [] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    const sectorHeader = wrapper.findAll('.rotation-tool__head button').find(button => button.text().startsWith('Sector'))
    await sectorHeader?.trigger('click')
    const rowSymbols = wrapper.findAll('.rotation-tool__row').map(row => row.find('strong').text())
    expect(rowSymbols).toEqual(['XLE', 'XLK'])
  })

  it('exposes sortable headers and row context to assistive technology', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, distance: 0.14, coverage: 1, tail: [] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))

    expect(wrapper.get('.rotation-tool__table').attributes('role')).toBe('region')
    expect(wrapper.get('.rotation-tool__head').attributes('aria-label')).toBe('Sort relative rotation rows')
    const distanceHeader = wrapper.get('.rotation-tool__head button[aria-label="Sort by distance, currently descending"]')
    expect(distanceHeader.exists()).toBe(true)
    const symbolHeader = wrapper.get('.rotation-tool__head button[aria-label="Sort by sector"]')

    const row = wrapper.get('.rotation-tool__row')
    expect(row.attributes('aria-label')).toContain('XLK, leading, trend 10.00%')
    expect(row.attributes('aria-label')).toContain('coverage 100.00%')

    await symbolHeader.trigger('click')
    expect(symbolHeader.attributes('aria-label')).toBe('Sort by sector, currently ascending')
    expect(wrapper.get('.rotation-tool__head button[aria-label="Sort by distance"]').exists()).toBe(true)
    await symbolHeader.trigger('click')
    expect(symbolHeader.attributes('aria-label')).toBe('Sort by sector, currently descending')
  })

  it('shows a plot-level tail tooltip and selects the hovered symbol', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, distance: 0.22, coverage: 1, tail: [{ timestamp: '2026-01-02', trend: 0.1, momentum: 0.2 }] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    await nextTick()
    resize?.()
    const plot = wrapper.get('.rotation-tool__plot-shell')
    await plot.trigger('mousemove', { clientX: 100, clientY: 100 })
    expect(wrapper.text()).toContain('2026-01-02')
    await plot.trigger('click')
    expect(wrapper.emitted('select')).toEqual([['XLK', 1]])
  })

  it('lets keyboard users inspect and select the latest points in the rotation plot', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, distance: 0.22, coverage: 1, tail: [
        { timestamp: '2026-01-01', trend: 0.09, momentum: 0.18 },
        { timestamp: '2026-01-02', trend: 0.1, momentum: 0.2 },
      ] },
      { instrument_id: 2, symbol: 'XLE', state: 'lagging', trend: -0.1, momentum: -0.2, distance: 0.22, coverage: 1, tail: [
        { timestamp: '2026-01-02', trend: -0.1, momentum: -0.2 },
      ] },
    ] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLE'))
    await nextTick()
    resize?.()

    const plot = wrapper.get('.rotation-tool__plot')
    await plot.trigger('focus')
    const tooltip = wrapper.get('.rotation-tool__tooltip')
    expect(tooltip.text()).toContain('XLK')
    expect(tooltip.text()).toContain('2026-01-02')

    await plot.trigger('keydown', { key: 'ArrowRight' })
    expect(tooltip.text()).toContain('XLE')
    await plot.trigger('keydown', { key: 'Home' })
    expect(tooltip.text()).toContain('XLK')
    await plot.trigger('keydown', { key: 'End' })
    expect(tooltip.text()).toContain('XLE')
    await plot.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')).toEqual([['XLE', 2]])
  })

  it('deduplicates identical rotation requests across linked windows', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [] })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = mountTool({}, queryClient)
    const second = mountTool({}, queryClient)
    await vi.waitFor(() => expect(first.get('.rotation-tool__status .compact-status__detail').text()).toContain('No sector rotation rows are available.'))
    await vi.waitFor(() => expect(second.get('.rotation-tool__status .compact-status__detail').text()).toContain('No sector rotation rows are available.'))
    expect(first.get('.rotation-tool__status [role="status"]').attributes('aria-live')).toBe('polite')
    expect(first.get('.rotation-tool__status [role="status"]').attributes('aria-atomic')).toBe('true')
    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('does not publish a late rotation response after the tool unmounts', async () => {
    let resolveRotation!: (value: unknown) => void
    vi.mocked(api.get).mockReturnValue(new Promise(resolve => { resolveRotation = resolve }))
    const wrapper = mountTool()
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    wrapper.unmount()

    resolveRotation({ freshness: 'current', rows: [{ instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, coverage: 1, tail: [] }] })
    await flushPromises()

    expect((wrapper.vm as unknown as { rows: unknown[] }).rows).toEqual([])
  })

  it('surfaces backend coverage and insufficient-history warnings on the row', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'coverage_limited', rows: [{ instrument_id: 1, symbol: 'XLK', state: null, trend: null, momentum: null, coverage: 0.2, tail: [], warnings: [{ code: 'insufficient_history', message: 'Relative rotation requires 41 sampled observations.' }] }] })
    const wrapper = mountTool()
    await vi.waitFor(() => expect(wrapper.get('.rotation-tool__warning').text()).toContain('1'))
    expect(wrapper.get('.rotation-tool__warning .workstation-glyph--warning').exists()).toBe(true)
    expect(wrapper.text()).toContain('Coverage limited')
    expect(wrapper.get('.rotation-tool__row').get('[title*="requires 41"]').exists()).toBe(true)
  })
})
