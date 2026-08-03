import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
import { api } from '@/lib/api'
import uPlot from 'uplot'
import RelativeRotationTool from '@/components/workstation/RelativeRotationTool.vue'

let resize: (() => void) | null = null
class ResizeObserverMock {
  constructor(callback: () => void) { resize = callback }
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('RelativeRotationTool', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(uPlot).mockClear()
    resize = null
  })

  it('resizes the existing uPlot instance instead of recreating it', async () => {
    vi.mocked(api.get).mockResolvedValue({
      freshness: 'current',
      rows: [{ instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, heading: 63, distance: 0.224, velocity: 0.02, transition: 'improving->leading', time_in_state: 3, coverage: 1, tail: [{ timestamp: '2026-01-01', trend: 0.1, momentum: 0.2 }] }],
    })
    const wrapper = mount(RelativeRotationTool)
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    await vi.waitFor(async () => { await nextTick(); expect(wrapper.text()).toContain('XLK') })
    await nextTick()
    expect(wrapper.text()).toContain('improving->leading')
    expect(wrapper.text()).toContain('63°')
    resize?.()
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    resize?.()
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    expect(chart.setData).toHaveBeenCalled()
    expect(chart.setSize).toHaveBeenCalled()
  })

  it('persists and sends transparent rotation controls', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'stale', rows: [] })
    const wrapper = mount(RelativeRotationTool, { props: { configuration: { group_key: 'us-benchmarks', benchmark: 'QQQ', timeframe: 'W1', sampling: 3, lookback: 12, tail_length: 4, as_of: '2024-04-30', adjusted: false } } })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalled())
    expect(api.get).toHaveBeenLastCalledWith('/analysis/groups/us-benchmarks/relative-rotation', { benchmark: 'QQQ', timeframe: 'W1', adjusted: false, sampling: 3, lookback: 12, tail_length: 4, as_of: '2024-04-30T23:59:59Z' })
    await wrapper.get('input[aria-label="Rotation benchmark"]').setValue('IWM')
    await vi.waitFor(() => expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ group_key: 'us-benchmarks', benchmark: 'IWM', timeframe: 'W1', sampling: 3, lookback: 12, tail_length: 4, as_of: '2024-04-30', adjusted: false })))
  })

  it('sorts the companion table from its headers', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.1, distance: 0.14, coverage: 1, tail: [] },
      { instrument_id: 2, symbol: 'XLE', state: 'lagging', trend: -0.1, momentum: -0.1, distance: 0.14, coverage: 1, tail: [] },
    ] })
    const wrapper = mount(RelativeRotationTool)
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    const sectorHeader = wrapper.findAll('.rotation-tool__head button').find(button => button.text().startsWith('Sector'))
    await sectorHeader?.trigger('click')
    const rowSymbols = wrapper.findAll('.rotation-tool__row').map(row => row.find('strong').text())
    expect(rowSymbols).toEqual(['XLE', 'XLK'])
  })

  it('shows a plot-level tail tooltip and selects the hovered symbol', async () => {
    vi.mocked(api.get).mockResolvedValue({ freshness: 'current', rows: [
      { instrument_id: 1, symbol: 'XLK', state: 'leading', trend: 0.1, momentum: 0.2, distance: 0.22, coverage: 1, tail: [{ timestamp: '2026-01-02', trend: 0.1, momentum: 0.2 }] },
    ] })
    const wrapper = mount(RelativeRotationTool)
    await vi.waitFor(() => expect(wrapper.text()).toContain('XLK'))
    await nextTick()
    resize?.()
    const plot = wrapper.get('.rotation-tool__plot-shell')
    await plot.trigger('mousemove', { clientX: 100, clientY: 100 })
    expect(wrapper.text()).toContain('2026-01-02')
    await plot.trigger('click')
    expect(wrapper.emitted('select')).toEqual([['XLK']])
  })
})
