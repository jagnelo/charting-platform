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
  static callback: ResizeObserverCallback | null = null
  constructor(callback: ResizeObserverCallback) { ResizeObserverMock.callback = callback }
  observe() {}
  disconnect() {}
  static trigger() { ResizeObserverMock.callback?.([], {} as ResizeObserver) }
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
      props: { chartType: 'candles' },
      attachTo: document.body,
      global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] },
    })
    try {
      await vi.waitFor(() => expect(vi.mocked(uPlot)).toHaveBeenCalledOnce())
      const instance = vi.mocked(uPlot).mock.results[0]?.value as uPlot
      const options = vi.mocked(uPlot).mock.calls[0]?.[0] as {
        hooks?: {
          ready?: Array<(plot: uPlot) => void>
          draw?: Array<(plot: uPlot) => void>
          setScale?: Array<(plot: uPlot, scale: string) => void>
          setCursor?: Array<(plot: uPlot) => void>
        }
        axes?: Array<{
          values?: (plot: uPlot, ticks: (number | null)[]) => string[]
          size?: (plot: uPlot, values: string[] | null | undefined) => number
        }>
        scales?: { y?: { range?: (plot: uPlot) => [number, number] } }
      }
      const plot = instance as uPlot & {
        destroy: ReturnType<typeof vi.fn>
        setData: ReturnType<typeof vi.fn>
        setSize: ReturnType<typeof vi.fn>
      }
      plot.setData.mockImplementation((data: number[][]) => {
        Object.assign(instance, { data })
      })
      const over = document.createElement('div')
      vi.spyOn(over, 'getBoundingClientRect').mockReturnValue({
        left: 0, top: 0, right: 320, bottom: 180, width: 320, height: 180,
        x: 0, y: 0, toJSON: () => ({}),
      } as DOMRect)
      Object.assign(instance, {
        over,
        root: over,
        scales: { x: { min: 0, max: 1 }, y: { min: 0, max: 1 } },
      })
      vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
        clearRect: vi.fn(),
        measureText: (value: string) => ({ width: value.length * 6 }),
      } as unknown as CanvasRenderingContext2D)

      // Exercise the same renderer-ready and draw/scale callbacks that keep
      // chart overlays synchronized with the chart instance.
      options.hooks?.ready?.[0]?.(instance)
      options.hooks?.draw?.[0]?.(instance)
      options.hooks?.setScale?.[0]?.(instance, 'x')
      ResizeObserverMock.trigger()
      expect(plot.setSize).toHaveBeenCalled()
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

      chart.bars = [{
        ts: '2026-11-03T15:01:00Z', open: 61, high: 63, low: 60, close: 62.5,
        volume: 2400, is_adjusted: true,
      }]
      await nextTick()
      expect(plot.setData).toHaveBeenCalled()
      instance.cursor.idx = 0
      options.hooks?.setCursor?.[0]?.(instance)
      await nextTick()
      expect(wrapper.get('.ohlcv-info').text()).toContain('62.5')

      const currentDateLabels = options.axes?.[0]?.values?.(instance, [0])
      expect(currentDateLabels).toEqual([expect.stringContaining('Nov 3')])
      expect(options.axes?.[1]?.values?.(instance, [60, 62.5, 63])).toEqual(['60.00', '62.50', '63.00'])
      expect(options.axes?.[1]?.size?.(instance, ['63.00', '-100000.00'])).toBe(74)
      const currentPriceRange = options.scales?.y?.range?.(instance)
      expect(currentPriceRange?.[0]).toBeLessThanOrEqual(60)
      expect(currentPriceRange?.[1]).toBeGreaterThanOrEqual(63)
      expect(currentPriceRange?.[1]).toBeLessThan(100)

      await wrapper.setProps({ linkedTimestamp: '2026-11-03T15:01:00Z' })
      await nextTick()
      expect(wrapper.get('.ohlcv-info').text()).toContain('62.5')
      expect(wrapper.get('.ohlcv-info').text()).not.toContain('518.7579')

      chart.timeframe = 'D1'
      await nextTick()
      expect(wrapper.find('.ohlcv-info').exists()).toBe(false)
      instance.cursor.idx = 0
      options.hooks?.setCursor?.[0]?.(instance)
      await nextTick()
      expect(wrapper.get('.ohlcv-info').text()).toContain('62.5')

      const chartRoot = wrapper.get('.chart-root')
      expect(chartRoot.attributes('data-date-pointer-mode')).toBe('on_with_values')
      await chartRoot.trigger('keydown', { key: '.' })
      await nextTick()
      expect(chartRoot.attributes('data-date-pointer-mode')).toBe('off')
      await chartRoot.trigger('keydown', { key: '.' })
      await chartRoot.trigger('keydown', { key: '.' })
      await nextTick()
      expect(chartRoot.attributes('data-date-pointer-mode')).toBe('on_with_values')

      const helpButton = wrapper.get('button[aria-label="Keyboard shortcuts"]')
      await helpButton.trigger('click')
      const helpDialog = wrapper.element.querySelector('[role="dialog"][aria-labelledby$="-shortcuts-title"]')
      expect(helpDialog?.textContent).toContain('Keyboard Shortcuts')
      const closeHelp = wrapper.element.querySelector<HTMLButtonElement>('.sc-close')
      expect(closeHelp).not.toBeNull()
      closeHelp?.click()
      await nextTick()
      await nextTick()
      expect(wrapper.element.querySelector('[role="dialog"][aria-labelledby$="-shortcuts-title"]')).toBeNull()
      expect(document.activeElement).toBe(helpButton.element)

      const settingsButton = wrapper.get('button[aria-label="Chart settings"]')
      await settingsButton.trigger('click')
      const settingsDialog = document.body.querySelector<HTMLElement>('.editor-backdrop[role="dialog"]')
      expect(settingsDialog).not.toBeNull()
      const chartType = settingsDialog?.querySelector<HTMLSelectElement>('select.ed-select')
      expect(chartType).not.toBeNull()
      await vi.waitFor(() => expect(document.activeElement).toBe(chartType))

      const priceProjection = settingsDialog?.querySelector<HTMLInputElement>('input[type="checkbox"]')
      expect(priceProjection).not.toBeNull()
      if (priceProjection) {
        priceProjection.checked = true
        priceProjection.dispatchEvent(new Event('change', { bubbles: true }))
      }
      expect(wrapper.get('.ohlcv-info').text()).toContain('62.5')

      if (chartType) {
        chartType.value = 'line'
        chartType.dispatchEvent(new Event('change', { bubbles: true }))
      }
      expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual({ bar_type: 'line' })
      // The parent applies the emitted chart-type choice to the panel store;
      // changing that rendered scope must clear the prior type's readout.
      chart.barType = 'line'
      await nextTick()
      expect(wrapper.find('.ohlcv-info').exists()).toBe(false)

      settingsDialog?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      await nextTick()
      await nextTick()
      expect(document.body.querySelector('.editor-backdrop[role="dialog"]')).toBeNull()
      expect(document.activeElement).toBe(settingsButton.element)

      const plotWrapper = wrapper.get('.uplot-wrapper')
      await plotWrapper.trigger('contextmenu', { clientX: 400, clientY: 12 })
      const priceMenu = wrapper.get('[role="menu"][aria-label="Price scale actions"]')
      const priceItems = priceMenu.findAll('[role="menuitem"]')
      expect(priceItems).toHaveLength(2)
      await priceItems[0].trigger('keydown', { key: 'ArrowDown' })
      expect(document.activeElement).toBe(priceItems[1].element)
      await chartRoot.trigger('keydown', { key: 'Escape' })
      await nextTick()
      expect(wrapper.find('[role="menu"][aria-label="Price scale actions"]').exists()).toBe(false)
      expect(document.activeElement).toBe(chartRoot.element)
    } finally {
      const plot = vi.mocked(uPlot).mock.results[0]?.value as { destroy: ReturnType<typeof vi.fn> } | undefined
      wrapper.unmount()
      expect(plot?.destroy).toHaveBeenCalled()
      queryClient.clear()
      vi.restoreAllMocks()
      vi.unstubAllGlobals()
    }
  })
})
