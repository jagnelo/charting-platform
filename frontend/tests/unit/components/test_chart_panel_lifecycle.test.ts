import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ChartPanel from '@/components/chart/ChartPanel.vue'
import { api } from '@/lib/api'
import { useAlertsStore } from '@/stores/alerts'
import { useDrawingsStore } from '@/stores/drawings'
import { useLayoutStore } from '@/stores/layout'
import { usePanelStore } from '@/stores/chart'

vi.mock('@/lib/onDemandAcquisition', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/onDemandAcquisition')>()
  return { ...actual, acquireSelectedHistory: vi.fn() }
})

import { acquireSelectedHistory } from '@/lib/onDemandAcquisition'

const routerLinkStub = { template: '<a><slot /></a>' }

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('ChartPanel lifecycle fencing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.mocked(acquireSelectedHistory).mockReset().mockResolvedValue({
      kind: 'already-covered',
      coverage: { status: 'ready', bar_count: 1, missing_slices: [] },
    })
  })

  afterEach(() => vi.unstubAllGlobals())

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
          RouterLink: routerLinkStub,
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
          RouterLink: routerLinkStub,
          RouterLink: routerLinkStub,
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
    const options = menu.findAll('button[role="menuitemradio"]')
    expect(options).toHaveLength(10)
    expect(options[0].text()).toContain('Blue')
    expect(options.at(-2)?.text()).toContain('Yellow')
    expect(options.at(-1)?.text()).toContain('Grey')
    expect(options[0].attributes('aria-checked')).toBe('true')
    expect(options.slice(1).every(option => option.attributes('aria-checked') === 'false')).toBe(true)

    await options.at(-1)?.trigger('click')
    expect(trigger.attributes('aria-label')).toBe('Symbol link group: grey')
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
          RouterLink: routerLinkStub,
        },
      },
    })

    const trigger = wrapper.get('.panel-sym-btn')
    expect(trigger.attributes('type')).toBe('button')
    expect(trigger.attributes('aria-haspopup')).toBe('listbox')
    await trigger.trigger('click')

    const input = wrapper.get('input[role="combobox"]')
    const resultsId = input.attributes('aria-controls')
    expect(input.attributes('aria-label')).toBe('Search chart symbol for panel p0')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(input.attributes('aria-expanded')).toBe('false')
    expect(resultsId).toMatch(/^chart-panel-search-results-p0$/)

    await input.setValue('SPY')
    await vi.waitFor(() => expect(wrapper.find(`#${resultsId}`).exists()).toBe(true))
    expect(input.attributes('aria-expanded')).toBe('true')
    const listbox = wrapper.get(`#${resultsId}`)
    await vi.waitFor(() => expect(listbox.find('[role="option"]').exists()).toBe(true))
    const option = listbox.get('[role="option"]')
    expect(listbox.attributes('aria-label')).toBe('Symbol search results')
    expect(option.attributes('aria-selected')).toBe('true')
    expect(input.attributes('aria-activedescendant')).toBe(option.attributes('id'))
    wrapper.unmount()
  })

  it('uses shared automatic discovery and starts bounded history only after a deliberate panel selection', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''
    const panelStore = usePanelStore('p0')
    vi.spyOn(panelStore, 'loadBars').mockImplementation(async (symbol: string, timeframe: any = 'D1') => {
      panelStore.symbol = symbol
      panelStore.timeframe = timeframe
      panelStore.instrument = { id: 23, symbol, name: symbol, is_active: true, currency: 'USD' }
    })
    vi.spyOn(useDrawingsStore(), 'loadDrawings').mockResolvedValue()
    vi.spyOn(useAlertsStore(), 'loadAlerts').mockResolvedValue()
    vi.spyOn(api, 'get').mockImplementation(async (path: string) => (
      path === '/instruments/search'
        ? [{ symbol: 'C', name: 'Example C', exchange: 'XNYS', type: 'Equity', instrument_id: 23 }]
        : []
    ) as never)

    const wrapper = mount(ChartPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: { TimeframeSelector: { template: '<div />' }, UPlotChart: { template: '<div />' }, RouterLink: routerLinkStub },
      },
    })
    await flushPromises()
    expect(acquireSelectedHistory).not.toHaveBeenCalled()

    await wrapper.get('.panel-sym-btn').trigger('click')
    const input = wrapper.get('input[role="combobox"]')
    await input.setValue('C')
    await vi.waitFor(() => expect(wrapper.find('.result-item').exists()).toBe(true))
    await wrapper.get('.search-option-list [role="option"]').trigger('click')
    await vi.waitFor(() => expect(acquireSelectedHistory).toHaveBeenCalledWith(
      'C', 'D1', true,
      expect.objectContaining({ timeframe: 'D1', adjusted: true, start: expect.any(String), end: expect.any(String) }),
      expect.any(Function), expect.any(Function), undefined,
      expect.objectContaining({ signal: expect.any(Object) }),
    ))
    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'C', canonical_only: true })
    wrapper.unmount()
  })

  it('discovers an absent ticker without a manual source-search step, then resolves and loads only its selected panel', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''
    const panelStore = usePanelStore('p0')
    const loadBars = vi.spyOn(panelStore, 'loadBars').mockImplementation(async (symbol: string, timeframe: any = 'D1') => {
      panelStore.symbol = symbol
      panelStore.timeframe = timeframe
      panelStore.instrument = { id: 43, symbol, name: symbol, is_active: true, currency: 'USD' }
    })
    vi.spyOn(useDrawingsStore(), 'loadDrawings').mockResolvedValue()
    vi.spyOn(useAlertsStore(), 'loadAlerts').mockResolvedValue()
    vi.spyOn(api, 'get').mockResolvedValue([] as never)
    let resolveDiscovery!: (value: unknown) => void
    vi.spyOn(api, 'post')
      .mockImplementationOnce(() => new Promise(resolve => { resolveDiscovery = resolve }) as never)
      .mockResolvedValueOnce({ request_id: 'resolve-c', status: 'resolved', instrument: { instrument_id: 43, symbol: 'C', identity_status: 'verified' }, source_outcomes: [] } as never)

    const wrapper = mount(ChartPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: { TimeframeSelector: { template: '<div />' }, UPlotChart: { template: '<div />' }, RouterLink: routerLinkStub },
      },
    })
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    expect(acquireSelectedHistory).not.toHaveBeenCalled()

    await wrapper.get('.panel-sym-btn').trigger('click')
    const input = wrapper.get('input[role="combobox"]')
    await input.setValue('C')
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'C', canonical_only: true }))
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/instruments/discover', {
      query: 'C', types: [], limit: 10, request_id: expect.any(String),
    }))
    expect(wrapper.text()).toContain('Checking ticker availability')
    expect(acquireSelectedHistory).not.toHaveBeenCalled()
    resolveDiscovery({ request_id: 'discover-c', status: 'complete', candidates: [{ symbol: 'C', name: 'Example C', exchange: 'XNYS', type: 'Equity', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }], source_outcomes: [] })
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    await wrapper.get('.search-source-candidate').trigger('click')
    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/instruments/acquire', {
      symbol: 'C', provider_candidate: { provider: 'fixture', symbol: 'C', exchange: 'XNYS' }, request_id: expect.any(String),
    }))
    await vi.waitFor(() => expect(acquireSelectedHistory).toHaveBeenCalledWith(
      'C', 'D1', true,
      expect.objectContaining({ timeframe: 'D1', adjusted: true, start: expect.any(String), end: expect.any(String) }),
      expect.any(Function), expect.any(Function), expect.any(Promise),
      expect.objectContaining({ signal: expect.any(Object) }),
    ))
    const panelHistoryCall = vi.mocked(acquireSelectedHistory).mock.calls.at(-1)!
    await expect(panelHistoryCall[6]).resolves.toMatchObject({
      status: 'resolved', instrument: { instrument_id: 43, symbol: 'C', identity_status: 'verified' },
    })
    expect(loadBars).toHaveBeenCalledTimes(1)
    expect(loadBars).toHaveBeenCalledWith('C', 'D1')
    wrapper.unmount()
  })

  it('keeps expression charts local instead of requesting provider history', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const layoutStore = useLayoutStore()
    layoutStore.layout = '1'
    layoutStore.panels[0].symbol = ''
    const panelStore = usePanelStore('p0')
    vi.spyOn(panelStore, 'loadBars').mockImplementation(async (symbol: string, timeframe: any = 'D1') => {
      panelStore.symbol = symbol
      panelStore.timeframe = timeframe
      panelStore.instrument = { id: 24, symbol, name: symbol, is_active: true, currency: 'USD' }
    })
    vi.spyOn(useDrawingsStore(), 'loadDrawings').mockResolvedValue()
    vi.spyOn(useAlertsStore(), 'loadAlerts').mockResolvedValue()

    const wrapper = mount(ChartPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: { TimeframeSelector: { template: '<div />' }, UPlotChart: { template: '<div />' }, RouterLink: routerLinkStub },
      },
    })
    const vm = wrapper.vm as unknown as { onSearchSelection: (symbol: string, result?: { type?: string }) => void }
    vm.onSearchSelection('=SPY-QQQ', { type: 'Synthetic' })
    await flushPromises()

    expect(panelStore.loadBars).toHaveBeenCalledWith('=SPY-QQQ', 'D1')
    expect(acquireSelectedHistory).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
