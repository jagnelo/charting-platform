import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import IndicatorPanel from '@/components/chart/IndicatorPanel.vue'
import { api } from '@/lib/api'
import { useAlertsStore } from '@/stores/alerts'
import { useDrawingsStore } from '@/stores/drawings'
import { usePanelStore } from '@/stores/chart'
import { usePresetsStore } from '@/stores/presets'
import { useRadarStore } from '@/stores/radar'
import { useWatchlistStore } from '@/stores/watchlist'

const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

describe('IndicatorPanel section disclosures', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    routerPush.mockReset()
  })

  it('exposes keyboard-operable controls linked to each visible section body', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('p0')
    chartStore.instrument = { id: 7, symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', is_active: true }
    const alertsStore = useAlertsStore()
    alertsStore.alerts = []
    alertsStore.indicatorAlerts = []
    const drawingsStore = useDrawingsStore()
    drawingsStore.drawings = []
    usePresetsStore().presets = []
    useRadarStore().chartDetections = []
    vi.spyOn(api, 'get').mockResolvedValue({
      watchlists: [{ id: 1, name: 'Core', is_managed: false }],
      screeners: [{ id: 2, name: 'Momentum', in_current_results: true }],
    } as never)

    const wrapper = mount(IndicatorPanel, {
      props: { panelId: 'p0' },
      global: {
        plugins: [pinia],
        stubs: {
          AlertForm: { template: '<div />' },
          HoverTooltip: { template: '<span><slot /></span>' },
          InstrumentInfoPanel: { template: '<div />' },
          TextPromptModal: { template: '<div />' },
          VueDraggable: { template: '<div><slot /></div>' },
          WorkstationGlyph: { template: '<span />' },
        },
      },
    })

    await Promise.resolve()
    await Promise.resolve()
    await nextTick()
    await nextTick()

    const panelToggle = wrapper.get('.panel-toggle')
    expect(panelToggle.attributes('type')).toBe('button')
    expect(panelToggle.attributes('aria-label')).toBe('Hide indicator panel')
    expect(panelToggle.attributes('aria-expanded')).toBe('true')
    await panelToggle.trigger('click')
    expect(panelToggle.attributes('aria-label')).toBe('Show indicator panel')
    expect(panelToggle.attributes('aria-expanded')).toBe('false')

    expect(api.get).toHaveBeenCalledWith('/instruments/7/membership')
    const watchlistRow = wrapper.get('.membership-row[aria-label="Open watchlist Core"]')
    expect(watchlistRow.element.tagName).toBe('BUTTON')
    expect(watchlistRow.attributes('type')).toBe('button')
    expect(watchlistRow.attributes('role')).toBeUndefined()
    await watchlistRow.trigger('click')
    expect(useWatchlistStore().focusRequest).toBe(1)

    const screenerRow = wrapper.get('.membership-row[aria-label="Open screener Momentum"]')
    expect(screenerRow.element.tagName).toBe('BUTTON')
    expect(screenerRow.attributes('type')).toBe('button')
    expect(screenerRow.attributes('role')).toBeUndefined()
    await screenerRow.trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/screener?selectedId=2')

    const headers = wrapper.findAll('.section-header')
    expect(headers).toHaveLength(6)
    for (const header of headers) {
      expect(header.element.tagName).toBe('BUTTON')
      expect(header.attributes('type')).toBe('button')
      expect(header.attributes('role')).toBeUndefined()
      const bodyId = header.attributes('aria-controls')
      expect(bodyId).toMatch(/^v-\d+-(watchlists|screeners|radar|indicators|drawings|alerts)$/)
      expect(header.attributes('aria-expanded')).toMatch(/^(true|false)$/)
      if (header.attributes('aria-expanded') === 'true') {
        expect(wrapper.find(`[id="${bodyId}"]`).exists()).toBe(true)
      }
    }

    const indicatorHeader = headers.find(header => header.text().includes('Indicators'))!
    const indicatorBodyId = indicatorHeader.attributes('aria-controls')
    expect(indicatorHeader.attributes('aria-expanded')).toBe('false')
    await indicatorHeader.trigger('click')
    expect(indicatorHeader.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find(`[id="${indicatorBodyId}"]`).exists()).toBe(true)

    const addButton = wrapper.get('.add-bar .add-btn')
    const pickerId = addButton.attributes('aria-controls')
    expect(addButton.attributes('type')).toBe('button')
    expect(addButton.attributes('aria-expanded')).toBe('false')
    expect(pickerId).toMatch(/^v-\d+-indicator-picker$/)
    await addButton.trigger('click')
    expect(addButton.attributes('aria-expanded')).toBe('true')
    const picker = wrapper.get(`#${pickerId}`)
    expect(picker.attributes('role')).toBe('group')
    expect(picker.attributes('aria-label')).toBe('Add indicator')
    expect(picker.findAll('button').every(button => button.attributes('type') === 'button')).toBe(true)
    await addButton.trigger('click')
    expect(addButton.attributes('aria-expanded')).toBe('false')

    await indicatorHeader.trigger('click')
    expect(indicatorHeader.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find(`[id="${indicatorBodyId}"]`).exists()).toBe(false)
    wrapper.unmount()
  })
})
