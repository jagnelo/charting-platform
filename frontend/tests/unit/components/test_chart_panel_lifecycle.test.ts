import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ChartPanel from '@/components/chart/ChartPanel.vue'
import { useAlertsStore } from '@/stores/alerts'
import { useDrawingsStore } from '@/stores/drawings'
import { useLayoutStore } from '@/stores/layout'
import { usePanelStore } from '@/stores/chart'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('ChartPanel lifecycle fencing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('does not hydrate drawings or alerts after the panel unmounts during a symbol load', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''

    const panelStore = usePanelStore('p0')
    const drawStore = useDrawingsStore()
    const alertsStore = useAlertsStore()
    let resolveBars!: () => void
    const barsLoaded = new Promise<void>(resolve => { resolveBars = resolve })
    vi.spyOn(panelStore, 'loadBars').mockImplementation(async (symbol: string) => {
      await barsLoaded
      panelStore.symbol = symbol
      panelStore.instrument = { id: 7, symbol, name: 'Tesla', is_active: true, currency: 'USD' }
    })
    const loadDrawingsSpy = vi.spyOn(drawStore, 'loadDrawings').mockImplementation(async () => {})
    const loadAlertsSpy = vi.spyOn(alertsStore, 'loadAlerts').mockImplementation(async () => {})

    const wrapper = mount(ChartPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: {
          TimeframeSelector: { template: '<div />' },
          UPlotChart: { template: '<div />' },
        },
      },
    })

    const selection = (wrapper.vm as unknown as { onSymbolSelect: (symbol: string) => Promise<void> }).onSymbolSelect('TSLA')
    await Promise.resolve()
    wrapper.unmount()
    resolveBars()
    await selection
    await flushPromises()

    expect(loadDrawingsSpy).not.toHaveBeenCalled()
    expect(loadAlertsSpy).not.toHaveBeenCalled()
  })

  it('does not let an older symbol selection hydrate drawings after a newer selection starts', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''

    const panelStore = usePanelStore('p0')
    const drawStore = useDrawingsStore()
    const alertsStore = useAlertsStore()
    const pending = new Map<string, () => void>()
    const waits = new Map<string, Promise<void>>()
    for (const symbol of ['AAPL', 'MSFT']) {
      waits.set(symbol, new Promise<void>(resolve => { pending.set(symbol, resolve) }))
    }
    vi.spyOn(panelStore, 'loadBars').mockImplementation(async (symbol: string) => {
      await waits.get(symbol)
      panelStore.symbol = symbol
      panelStore.instrument = { id: symbol === 'MSFT' ? 8 : 7, symbol, name: symbol, is_active: true, currency: 'USD' }
    })
    const loadDrawingsSpy = vi.spyOn(drawStore, 'loadDrawings').mockImplementation(async () => {})
    const loadAlertsSpy = vi.spyOn(alertsStore, 'loadAlerts').mockImplementation(async () => {})

    const wrapper = mount(ChartPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: {
          TimeframeSelector: { template: '<div />' },
          UPlotChart: { template: '<div />' },
        },
      },
    })

    const vm = wrapper.vm as unknown as { onSymbolSelect: (symbol: string) => Promise<void> }
    const firstSelection = vm.onSymbolSelect('AAPL')
    await Promise.resolve()
    const currentSelection = vm.onSymbolSelect('MSFT')
    await Promise.resolve()
    pending.get('AAPL')?.()
    await firstSelection
    expect(loadDrawingsSpy).not.toHaveBeenCalled()
    pending.get('MSFT')?.()
    await currentSelection

    expect(loadDrawingsSpy).toHaveBeenCalledWith(8, 'D1')
    expect(loadAlertsSpy).toHaveBeenCalledWith(8)
    wrapper.unmount()
  })
})
