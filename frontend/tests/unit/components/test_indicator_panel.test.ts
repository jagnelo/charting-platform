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

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

describe('IndicatorPanel section disclosures', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
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
    const headers = wrapper.findAll('.section-header')
    expect(headers).toHaveLength(6)
    for (const header of headers) {
      expect(header.attributes('role')).toBe('button')
      expect(header.attributes('tabindex')).toBe('0')
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
    await indicatorHeader.trigger('keydown', { key: 'Enter' })
    expect(indicatorHeader.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find(`[id="${indicatorBodyId}"]`).exists()).toBe(true)
    await indicatorHeader.trigger('keydown', { key: ' ' })
    expect(indicatorHeader.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find(`[id="${indicatorBodyId}"]`).exists()).toBe(false)
    wrapper.unmount()
  })
})
