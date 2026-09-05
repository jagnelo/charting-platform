import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import uPlot from 'uplot'
import StudySeriesUPlot from '@/components/workstation/StudySeriesUPlot.vue'
import StudyHistogramUPlot from '@/components/workstation/StudyHistogramUPlot.vue'
import StudyRangeUPlot from '@/components/workstation/StudyRangeUPlot.vue'
import StudyBarsUPlot from '@/components/workstation/StudyBarsUPlot.vue'
import BreadthHistoryUPlot from '@/components/workstation/BreadthHistoryUPlot.vue'
import BenchmarkFamilyBreadthHistoryUPlot from '@/components/workstation/BenchmarkFamilyBreadthHistoryUPlot.vue'
import GenericBreadthHistoryUPlot from '@/components/workstation/GenericBreadthHistoryUPlot.vue'

class ResizeObserverMock {
  constructor(_callback: () => void) {}
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

const cases = [
  { name: 'series', component: StudySeriesUPlot, valid: { name: 'Series', timestamps: ['2026-01-01', '2026-01-02'], values: [1, 2] }, invalid: { timestamps: ['not-a-date'], values: [Number.NaN] } },
  { name: 'histogram', component: StudyHistogramUPlot, valid: { name: 'Histogram', bins: [{ start: 0, end: 1, count: 2 }] }, invalid: { bins: [] } },
  { name: 'range', component: StudyRangeUPlot, valid: { name: 'Range', timestamps: ['2026-01-01', '2026-01-02'], lower: [1, 2], upper: [2, 3] }, invalid: { timestamps: ['not-a-date'], lower: [1], upper: [2] } },
  { name: 'bars', component: StudyBarsUPlot, valid: { name: 'Bars', labels: ['A', 'B'], values: [1, -1] }, invalid: { labels: [], values: [] } },
  { name: 'breadth history', component: BreadthHistoryUPlot, valid: { history: { group_key: 'sp500-sectors', points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5, ma50: 0.4, ma200: 0.3 }, coverage: {} }] } }, invalid: { history: { group_key: 'sp500-sectors', points: [{ timestamp: 'not-a-date', above_ma: { ma20: Number.NaN, ma50: 0.4, ma200: 0.3 }, coverage: {} }] } } },
  { name: 'benchmark family breadth history', component: BenchmarkFamilyBreadthHistoryUPlot, valid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5 }, coverage: { ma20: 1 } }], exclusions: [] }], exclusions: [] } }, invalid: { history: { family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500, roles: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: 'not-a-date', above_ma: { ma20: Number.NaN }, coverage: {} }], exclusions: [] }], exclusions: [] } } },
  { name: 'generic breadth history', component: GenericBreadthHistoryUPlot, valid: { history: { definition_version: 1, definition_hash: 'hash', universe: {}, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: '2026-01-01', requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1, members: [], exclusions: [] }] } }, invalid: { history: { definition_version: 1, definition_hash: 'hash', universe: {}, condition: {}, timeframe: 'D1', adjustment: 'split_adjusted', points: [{ timestamp: 'not-a-date', requested_count: 2, eligible_count: 0, pass_count: 0, excluded_count: 2, percentage: Number.NaN, coverage: 0, members: [], exclusions: [] }] } } },
] as const

describe('conditional uPlot lifecycle contracts', () => {
  beforeEach(() => vi.mocked(uPlot).mockClear())

  it.each(cases)('$name renders its initial conditional chart host', async ({ component, valid }) => {
    const wrapper = mount(component, { props: valid as any })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    expect(wrapper.element.querySelector('[class$="__host"]')).not.toBeNull()
  })

  it.each(cases)('$name destroys its chart when the conditional data disappears', async ({ component, valid, invalid }) => {
    const wrapper = mount(component, { props: valid as any })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    await wrapper.setProps(invalid as any)
    await vi.waitFor(() => expect(chart.destroy).toHaveBeenCalledTimes(1))
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.get('[role="status"]').attributes('aria-atomic')).toBe('true')
    wrapper.unmount()
  })

  it('rejects malformed range timestamps before creating uPlot', async () => {
    const wrapper = mount(StudyRangeUPlot, {
      props: { name: 'Range', timestamps: ['not-a-date'], lower: [1], upper: [2] },
    })
    await nextTick()
    expect(vi.mocked(uPlot)).not.toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('no aligned finite bounds')
  })

  it('refreshes a histogram current marker without recreating its uPlot instance', async () => {
    const wrapper = mount(StudyHistogramUPlot, {
      props: { name: 'Histogram', bins: [{ start: 0, end: 1, count: 2 }], current: 0.25 },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const chart = vi.mocked(uPlot).mock.results[0]?.value
    chart.setData.mockClear()
    await wrapper.setProps({ current: 0.75 })
    await vi.waitFor(() => expect(chart.setData).toHaveBeenCalledTimes(1))
    expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('aligns benchmark-family role histories without forward-filling gaps', async () => {
    const wrapper = mount(BenchmarkFamilyBreadthHistoryUPlot, {
      props: {
        history: {
          family_key: 'sp500', official_index_symbol: 'SPX', timeframe: 'D1', adjustment: 'split_adjusted', limit: 500,
          roles: [
            { role: 'cap_weight', symbol: 'SPY', label: 'Cap weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-01', above_ma: { ma20: 0.5 }, coverage: { ma20: 1 } }, { timestamp: '2026-01-02', above_ma: { ma20: 0.6 }, coverage: { ma20: 1 } }], exclusions: [] },
            { role: 'equal_weight', symbol: 'RSP', label: 'Equal weight', verification_state: 'verified', available: true, points: [{ timestamp: '2026-01-02', above_ma: { ma20: 0.4 }, coverage: { ma20: 1 } }], exclusions: [] },
          ], exclusions: [],
        },
      },
    })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const call = vi.mocked(uPlot).mock.calls[0] as any
    expect(call[1][0]).toHaveLength(2)
    expect(call[1][1]).toEqual([0.5, 0.6])
    expect(call[1][2]).toEqual([null, 0.4])
    wrapper.unmount()
  })
})
