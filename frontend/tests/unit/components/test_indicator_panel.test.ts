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

  it('uses native selection buttons with separate row-action controls', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('p0')
    chartStore.instrument = { id: 7, symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', is_active: true }
    chartStore.indicators = [{ type: 'rsi', params: { period: 14 }, style: { color: '#fff', lineWidth: 1 }, pane: 'separate' }] as any
    const drawingsStore = useDrawingsStore()
    drawingsStore.drawings = [{
      id: 3,
      instrument_id: 7,
      drawing_type: 'trendline',
      data: { points: [] },
      style: {},
      is_visible: true,
      is_locked: false,
      pin_to_all: false,
      position: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }] as any
    const alertsStore = useAlertsStore()
    alertsStore.alerts = [{
      id: 4,
      instrument_id: 7,
      instrument_currency: 'USD',
      instrument_symbol: 'SPY',
      condition: 'crosses_above',
      threshold_price: 200,
      status: 'active',
      repeat: false,
      show_projection: false,
      trigger_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }] as any
    alertsStore.indicatorAlerts = [{
      id: 5,
      instrument_id: 7,
      indicator_a_type: 'rsi',
      indicator_a_params: { period: 14 },
      condition: 'crosses_above',
      threshold_value: 70,
      status: 'active',
      repeat: false,
      trigger_count: 0,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }] as any
    const radarStore = useRadarStore()
    radarStore.chartDetections = [{
      id: 9,
      instrument_id: 7,
      setup_type: 'rejection',
      state: 'confirmed',
      score: 0.8,
      signal_at: '2026-01-01T00:00:00Z',
      observed_at: '2026-01-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
      summary: 'Rejected resistance',
      score_factors: {},
      evidence: { metrics: {}, structures: [] },
    }] as any
    radarStore.activeChartDetectionIds = []
    radarStore.focusedChartDetectionId = null

    const selectIndicator = vi.spyOn(chartStore, 'selectIndicator')
    const selectDrawing = vi.spyOn(drawingsStore, 'selectDrawing')
    const selectAlert = vi.spyOn(alertsStore, 'selectAlert')
    const toggleDetection = vi.spyOn(radarStore, 'toggleChartDetection')
    vi.spyOn(api, 'get').mockResolvedValue({ watchlists: [], screeners: [] } as never)

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
    await nextTick()
    const radarHeader = wrapper.findAll('.section-header').find(header => header.text().includes('Radar'))!
    if (radarHeader.attributes('aria-expanded') === 'false') {
      await radarHeader.trigger('click')
      await nextTick()
    }
    const drawingsHeader = wrapper.findAll('.section-header').find(header => header.text().includes('Drawings'))!
    if (drawingsHeader.attributes('aria-expanded') === 'false') {
      await drawingsHeader.trigger('click')
      await nextTick()
    }

    const rows = wrapper.findAll('.list-row__select')
    expect(rows).toHaveLength(5)
    for (const row of rows) {
      expect(row.element.tagName).toBe('BUTTON')
      expect(row.attributes('type')).toBe('button')
      expect(row.attributes('role')).toBeUndefined()
      expect(row.attributes('tabindex')).toBeUndefined()
      expect(row.attributes('aria-label')).toMatch(/^Select /)
      expect(row.find('button').exists()).toBe(false)
    }

    await wrapper.get('.radar-row__select').trigger('click')
    await wrapper.find('.ind-list .list-row__select[aria-label^="Select indicator"]').trigger('click')
    await wrapper.find('.ind-list .list-row__select[aria-label^="Select drawing"]').trigger('click')
    await wrapper.find('.alert-row .list-row__select[aria-label^="Select price alert"]').trigger('click')
    await wrapper.find('.alert-row .list-row__select[aria-label^="Select indicator alert"]').trigger('click')

    expect(toggleDetection).toHaveBeenCalledWith(9)
    expect(selectIndicator).toHaveBeenCalledWith(0)
    expect(selectDrawing).toHaveBeenCalledWith(3)
    expect(selectAlert).toHaveBeenNthCalledWith(1, 4)
    expect(selectAlert).toHaveBeenNthCalledWith(2, 5)
    wrapper.unmount()
  })
})
