import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

import { api } from '@/lib/api'
import Sparkline from '@/components/common/Sparkline.vue'
import uPlot from 'uplot'

describe('Sparkline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders numerical points through uPlot without SVG geometry', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { close: 10 },
      { close: 12 },
      { close: 11 },
    ])

    const wrapper = mount(Sparkline, { props: { symbol: 'SPARK-RENDER' } })
    await flushPromises()

    expect(wrapper.find('.sparkline').exists()).toBe(true)
    expect(wrapper.find('svg').exists()).toBe(false)
    expect(uPlot).toHaveBeenCalledTimes(1)
    expect(uPlot).toHaveBeenCalledWith(
      expect.objectContaining({ width: 80, height: 32, axes: [] }),
      [[0, 1, 2], [10, 12, 11]],
      expect.any(HTMLElement),
    )

    const instance = (uPlot as unknown as { mock: { results: Array<{ value: { destroy: ReturnType<typeof vi.fn> } }> } }).mock.results[0].value
    wrapper.unmount()
    expect(instance.destroy).toHaveBeenCalledTimes(1)
  })

  it('keeps the empty state accessible without creating a chart', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue([{ close: 10 }])

    const wrapper = mount(Sparkline, { props: { symbol: 'SPARK-EMPTY' } })
    await flushPromises()

    expect(wrapper.find('.sparkline--empty').exists()).toBe(true)
    expect(uPlot).not.toHaveBeenCalled()
  })

  it('renders an already-materialized tile series without fetching', async () => {
    const wrapper = mount(Sparkline, {
      props: { symbol: 'SPARK-TILE', points: [4, 5, 3], width: 120, height: 28 },
    })
    await flushPromises()
    await nextTick()
    await nextTick()

    expect(api.get).not.toHaveBeenCalled()
    expect(uPlot).toHaveBeenCalledWith(
      expect.objectContaining({ width: 120, height: 28 }),
      [[0, 1, 2], [4, 5, 3]],
      expect.any(HTMLElement),
    )
    wrapper.unmount()
  })
})
