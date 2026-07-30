import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import ChartPlotLibrary from '@/components/workstation/ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'

describe('ChartPlotLibrary', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('manages indicator plots without losing their serializable configuration', async () => {
    const chart = usePanelStore('plot-library-test')
    chart.setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { global: { provide: { panelId: 'plot-library-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Add indicator plot"]').setValue('ema')
    expect(chart.indicators).toHaveLength(2)

    await wrapper.get('[aria-label="Hide SMA(20)"]').trigger('click')
    expect(chart.indicators[0].hidden).toBe(true)
    await wrapper.get('[aria-label="Duplicate EMA(50)"]').trigger('click')
    expect(chart.indicators).toHaveLength(3)
    await wrapper.get('[aria-label="Move EMA(50) up"]').trigger('click')
    expect(chart.indicators[0].type).toBe('ema')
    await wrapper.findAll('[aria-label="Delete EMA(50)"]')[0].trigger('click')
    expect(chart.indicators).toHaveLength(2)
  })
})
