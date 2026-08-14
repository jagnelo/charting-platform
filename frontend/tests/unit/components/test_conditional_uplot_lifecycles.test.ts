import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import uPlot from 'uplot'
import StudySeriesUPlot from '@/components/workstation/StudySeriesUPlot.vue'
import StudyHistogramUPlot from '@/components/workstation/StudyHistogramUPlot.vue'
import StudyRangeUPlot from '@/components/workstation/StudyRangeUPlot.vue'
import StudyBarsUPlot from '@/components/workstation/StudyBarsUPlot.vue'
import BreadthHistoryUPlot from '@/components/workstation/BreadthHistoryUPlot.vue'

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
})
