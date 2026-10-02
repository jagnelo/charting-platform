import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ChartPanel from '@/components/chart/ChartPanel.vue'
import { api } from '@/lib/api'
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

  it('exposes the symbol link menu as an accessible disclosure', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''

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

    const trigger = wrapper.get('.panel-link-btn')
    expect(trigger.attributes('type')).toBe('button')
    expect(trigger.attributes('aria-haspopup')).toBe('menu')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    const menuId = trigger.attributes('aria-controls')
    expect(menuId).toMatch(/^panel-link-menu-p0$/)
    expect(wrapper.find(`#${menuId}`).exists()).toBe(false)

    await trigger.trigger('click')
    const menu = wrapper.get(`#${menuId}`)
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(menu.attributes('role')).toBe('menu')
    expect(menu.attributes('aria-label')).toBe('Symbol link group')
    expect(menu.findAll('button[type="button"]').length).toBe(5)

    await menu.trigger('keydown', { key: 'Escape' })
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find(`#${menuId}`).exists()).toBe(false)
    wrapper.unmount()
  })

  it('exposes symbol search as a keyboard-targetable combobox and listbox', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''
    vi.spyOn(api, 'get').mockResolvedValue([
      { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', type: 'ETF' },
    ] as never)

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

    const trigger = wrapper.get('.panel-sym-btn')
    expect(trigger.attributes('type')).toBe('button')
    expect(trigger.attributes('aria-haspopup')).toBe('listbox')
    await trigger.trigger('click')

    const input = wrapper.get('input[role="combobox"]')
    const resultsId = input.attributes('aria-controls')
    expect(input.attributes('aria-label')).toBe('Search chart symbol')
    expect(input.attributes('aria-expanded')).toBe('true')
    expect(resultsId).toMatch(/^chart-panel-search-results-p0$/)

    await input.setValue('SPY')
    await vi.waitFor(() => expect(wrapper.find(`#${resultsId}`).exists()).toBe(true))
    const listbox = wrapper.get(`#${resultsId}`)
    const option = listbox.get('button[role="option"]')
    expect(listbox.attributes('aria-label')).toBe('Chart symbol search results')
    expect(option.attributes('type')).toBe('button')
    expect(option.attributes('aria-selected')).toBe('true')
    expect(input.attributes('aria-activedescendant')).toBe(option.attributes('id'))
    wrapper.unmount()
  })
})
