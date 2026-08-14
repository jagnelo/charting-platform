import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import uPlot from 'uplot'
import StudyScatterUPlot from '@/components/workstation/StudyScatterUPlot.vue'

class ResizeObserverMock {
  constructor(_callback: () => void) {}
  observe() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverMock)

describe('StudyScatterUPlot', () => {
  beforeEach(() => vi.mocked(uPlot).mockClear())

  it('creates the initial chart after the conditional host mounts', async () => {
    const wrapper = mount(StudyScatterUPlot, { props: { name: 'Forward return', x: [1, 2], y: [3, 4] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    expect(wrapper.find('.study-scatter__host').exists()).toBe(true)
  })

  it('destroys an invalidated chart and recreates it when data becomes valid again', async () => {
    const wrapper = mount(StudyScatterUPlot, { props: { name: 'Forward return', x: [1, 2], y: [3, 4] } })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(1))
    const firstChart = vi.mocked(uPlot).mock.results[0]?.value

    await wrapper.setProps({ x: [], y: [] })
    await nextTick()
    await vi.waitFor(() => expect(firstChart.destroy).toHaveBeenCalledTimes(1))
    expect(wrapper.find('.study-scatter__state').text()).toContain('no aligned numeric points')

    await wrapper.setProps({ x: [5, 6], y: [7, 8] })
    await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledTimes(2))
    expect(vi.mocked(uPlot).mock.results[1]?.value).not.toBe(firstChart)
  })
})
