import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
import RatioUPlot from '@/components/workstation/RatioUPlot.vue'
import uPlot from 'uplot'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('RatioUPlot', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(uPlot).mockClear()
  })

  it('requests selected-sector and market ratios without filling their gaps', async () => {
    vi.mocked(api.get).mockImplementation(async (_path, options) => ({
      coverage: options?.benchmark === 'XLK' ? 0.8 : 0.6,
      points: [
        { timestamp: '2026-01-01T00:00:00Z', value: options?.benchmark === 'XLK' ? 1.1 : 0.9 },
        { timestamp: '2026-01-02T00:00:00Z', value: options?.benchmark === 'XLK' ? 1.2 : 1.0 },
      ],
      warnings: options?.benchmark === 'XLK' ? [{ message: 'Only intersecting timestamps were used.' }] : [],
    }))
    const wrapper = mount(RatioUPlot, { props: { symbol: 'NVDA', benchmarks: ['XLK', 'SPY'], timeframe: 'W1' } })
    await vi.waitFor(async () => {
      await nextTick()
      expect(wrapper.text()).toContain('XLK 80%')
      expect(wrapper.text()).toContain('SPY 60%')
    })

    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'XLK', timeframe: 'W1', adjusted: true,
    })
    expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'NVDA', benchmark: 'SPY', timeframe: 'W1', adjusted: true,
    })
    expect(wrapper.text()).toContain('NVDA/XLK')
    expect(wrapper.text()).toContain('NVDA/SPY')
    expect(wrapper.text()).toContain('Only intersecting timestamps were used.')
  })

  it('reloads ratios using the active linked timeframe', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'], timeframe: 'D1' } })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true,
    }))
    vi.mocked(api.get).mockClear()

    await wrapper.setProps({ timeframe: 'W1' })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'W1', adjusted: true,
    }))
  })

  it('suspends ratio requests while the browser document is hidden', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await nextTick()
    expect(api.get).not.toHaveBeenCalled()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true,
    }))
    wrapper.unmount()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  it('passes a persisted point-in-time cutoff without changing the current-view request shape', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'], asOf: '2025-12-31T23:59:59Z' } })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true, as_of: '2025-12-31T23:59:59Z',
    }))
  })

  it('persists the ratio cutoff from the tool control', async () => {
    vi.mocked(api.get).mockResolvedValue({ coverage: 1, points: [], warnings: [] })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    const input = wrapper.get('input[aria-label="Ratio as of"]')
    await input.setValue('2025-12-31')
    expect(wrapper.emitted('configuration')).toContainEqual([{ as_of: '2025-12-31' }])
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/analysis/relative-strength', {
      symbol: 'XLK', benchmark: 'SPY', timeframe: 'D1', adjusted: true, as_of: '2025-12-31T23:59:59Z',
    }))
  })

  it('publishes ratio crosshair timestamps and consumes linked timestamps without echoing them', async () => {
    vi.mocked(api.get).mockResolvedValue({
      coverage: 1,
      points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1 }],
      warnings: [],
    })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalled())
    const options = vi.mocked(uPlot).mock.calls.at(-1)?.[0]
    const setCursor = options?.hooks?.setCursor?.[0]
    expect(setCursor).toBeDefined()

    setCursor?.({ cursor: { idx: 0 }, data: [[1767225600]] } as unknown as uPlot)
    expect(wrapper.emitted('cursorTimestamp')).toEqual([['2026-01-01T00:00:00.000Z']])

    const chart = vi.mocked(uPlot).mock.results.at(-1)?.value
    await wrapper.setProps({ linkedTimestamp: '2026-01-01T00:00:00Z' })
    expect(chart.setCursor).toHaveBeenCalled()
    setCursor?.({ cursor: { idx: 0 }, data: [[1767225600]] } as unknown as uPlot)
    expect(wrapper.emitted('cursorTimestamp')).toHaveLength(1)
  })

  it('ignores a late ratio response after the active symbol changes', async () => {
    let resolveOld: ((value: unknown) => void) | undefined
    const oldResponse = new Promise(resolve => { resolveOld = resolve })
    vi.mocked(api.get).mockImplementationOnce(() => oldResponse as Promise<unknown>)
      .mockResolvedValueOnce({ coverage: 1, points: [{ timestamp: '2026-02-01T00:00:00Z', value: 2 }], warnings: [] })
    const wrapper = mount(RatioUPlot, { props: { symbol: 'XLK', benchmarks: ['SPY'] } })
    await wrapper.setProps({ symbol: 'XLE' })
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLE/SPY'))
    resolveOld?.({ coverage: 0.1, points: [{ timestamp: '2026-01-01T00:00:00Z', value: 1 }], warnings: [] })
    await nextTick()
    expect(wrapper.text()).not.toContain('SPY 10%')
  })
})
