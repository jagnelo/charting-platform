import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPatch, apiDelete } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiDelete: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: apiPost, patch: apiPatch, delete: apiDelete } }))

import AlertsView from '@/views/AlertsView.vue'
import WatchlistView from '@/views/WatchlistView.vue'

describe('AlertsView creation path', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({})
    apiPatch.mockResolvedValue({})
    apiDelete.mockResolvedValue(undefined)
  })

  it('offers the existing chart alert form when a user has no alert definitions', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/legacy/alerts', component: AlertsView },
        { path: '/chart', component: defineComponent({ template: '<main>Chart workspace</main>' }) },
      ],
    })
    await router.push('/legacy/alerts')
    await router.isReady()
    const wrapper = mount(AlertsView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('.alerts-create-path').text()).toContain('Create price or indicator alerts from the chart workspace.')
    const destination = wrapper.get('.alerts-create-path a')
    expect(destination.attributes('href')).toBe('/chart')
    await destination.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/chart')

    wrapper.unmount()
  })

  it('exposes readable names for icon-only alert actions in all three definition tables', async () => {
    const price = {
      id: 1, instrument_id: 1, instrument_symbol: 'SPY', condition: 'above', threshold_price: 500,
      status: 'active', repeat: false, show_projection: false, trigger_count: 0, created_at: '2026-01-01', updated_at: '2026-01-01',
    }
    const indicator = {
      id: 2, instrument_id: 1, instrument_symbol: 'SPY', timeframe: 'D1', indicator_a_type: 'rsi', indicator_a_params: {},
      condition: 'above', threshold_value: 50, indicator_b_type: null, indicator_b_params: null, status: 'paused',
      repeat: true, notes: null, triggered_at: null, trigger_count: 0, last_value_a: 55, last_value_b: null,
      created_at: '2026-01-01', updated_at: '2026-01-01',
    }
    const screener = {
      id: 3, screener_id: 4, screener_name: 'Large cap', trigger_type: 'both', status: 'triggered', repeat: false,
      notes: null, created_at: '2026-01-01', updated_at: '2026-01-01',
    }
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/alerts/price') return [price]
      if (path === '/alerts/indicator') return [indicator]
      if (path === '/alerts/screener') return [screener]
      return []
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/legacy/alerts', component: AlertsView },
        { path: '/chart/:symbol?', component: defineComponent({ template: '<main />' }) },
        { path: '/screener', component: defineComponent({ template: '<main />' }) },
      ],
    })
    await router.push('/legacy/alerts')
    await router.isReady()
    const wrapper = mount(AlertsView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.findAll('button[aria-label="Pause"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="Resume"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="Rearm"]')).toHaveLength(1)
    expect(wrapper.findAll('button[aria-label="Delete"]')).toHaveLength(3)
    expect(wrapper.find('button[aria-label="Enable repeat"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Disable repeat"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('gives Watchlist row-menu and remove controls usable accessible names', async () => {
    const watchlist = {
      id: 7, name: 'Research list', is_default: false, is_managed: false, is_locked: false, position: 0,
      items: [{ id: 9, watchlist_id: 7, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', position: 0 }],
    }
    apiGet.mockImplementation(async (path: string) => path === '/watchlists' ? [watchlist] : [])
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/legacy/watchlists', component: WatchlistView }, { path: '/chart/:symbol?', component: defineComponent({ template: '<main />' }) }],
    })
    await router.push('/legacy/watchlists')
    await router.isReady()
    const wrapper = mount(WatchlistView, {
      global: { plugins: [router], stubs: { VueDraggable: { template: '<div><slot /></div>' }, SearchBar: true, Sparkline: true, SparkTfSelector: true } },
    })
    await flushPromises()

    const options = wrapper.get('button.wlsi-menu-btn')
    expect(options.attributes('aria-label')).toBe('More options')
    await options.trigger('click')
    expect(options.attributes('aria-expanded')).toBe('true')
    expect(options.attributes('aria-controls')).toBe(wrapper.get('.wlsi-dropdown').attributes('id'))
    expect(wrapper.get('button.wlmi-remove').attributes('aria-label')).toBe('Remove SPY from Research list')
    wrapper.unmount()
  })
})
