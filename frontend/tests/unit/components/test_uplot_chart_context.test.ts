import { mount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import uPlot from 'uplot'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UPlotChart from '@/components/chart/UPlotChart.vue'
import { api } from '@/lib/api'
import { useChartStore } from '@/stores/chart'

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}

describe('UPlotChart readout context', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(uPlot).mockClear()
    vi.spyOn(api, 'get').mockResolvedValue([] as never)
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
  })

  it('clears the prior candle readout immediately when selection changes to an empty chart', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chart = useChartStore()
    chart.symbol = 'SPY'
    chart.timeframe = 'M1'
    chart.bars = [{
      ts: '2025-12-29T15:00:00Z', open: 516.6911, high: 520.8329,
      low: 514.6244, close: 518.7579, volume: 1_200_000, is_adjusted: true,
    }]

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mount(UPlotChart, {
      props: { chartSettings: { date_pointer_mode: 'on_with_values' } },
      global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] },
    })
    try {
      await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledOnce())
      const instance = vi.mocked(uPlot).mock.results[0]?.value as uPlot
      const options = vi.mocked(uPlot).mock.calls[0]?.[0] as {
        hooks?: { setCursor?: Array<(plot: uPlot) => void> }
      }
      instance.cursor.idx = 0
      options.hooks?.setCursor?.[0]?.(instance)
      await nextTick()
      expect(wrapper.get('.ohlcv-info').text()).toContain('518.7579')

      // The application changes the selected symbol before its empty local
      // result settles. The previous instrument's numbers must disappear at
      // that transition, not wait for a later uPlot data callback.
      chart.symbol = 'TCNEW'
      await nextTick()
      expect(wrapper.find('.ohlcv-info').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('518.7579')

      chart.bars = []
      await nextTick()
      expect(wrapper.find('.ohlcv-info').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('2025-12-29')
    } finally {
      wrapper.unmount()
      queryClient.clear()
      vi.restoreAllMocks()
      vi.unstubAllGlobals()
    }
  })
})
