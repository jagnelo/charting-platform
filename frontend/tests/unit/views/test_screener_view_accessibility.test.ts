import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }))

import ScreenerView from '@/views/ScreenerView.vue'

describe('ScreenerView accessible actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/screeners') return [{
        id: 4,
        name: 'Large cap leaders',
        timeframe: 'D1',
        universe_type: 'custom',
        universe_instrument_ids: [17],
        conditions: { conditions: [] },
      }]
      if (path === '/screeners/4/results') return [{
        id: 8,
        run_at: '2026-11-07T10:00:00Z',
        duration_ms: 120,
        matched_ids: [17],
        result_data: { '17': { close: 100, price_change: 0.01 } },
      }]
      if (path === '/instruments/browse') return { items: [{ id: 17, symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust' }] }
      if (path === '/instruments/filter-options') return { sectors: [], industries: [], countries: [], exchanges: [], currencies: [] }
      return []
    })
  })

  it('names the screener alert and watchlist actions and keeps the alert panel associated', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/legacy/screener', component: ScreenerView },
        { path: '/chart/:symbol?', component: defineComponent({ template: '<main />' }) },
      ],
    })
    await router.push('/legacy/screener?selectedId=4')
    await router.isReady()
    const wrapper = mount(ScreenerView, {
      global: {
        plugins: [router],
        stubs: {
          VueDraggable: { template: '<div><slot /></div>' },
          Sparkline: true,
          SparkTfSelector: true,
          TechnicalConditionEditor: true,
          TextPromptModal: true,
        },
      },
      attachTo: document.body,
    })
    await flushPromises()

    const alertToggle = wrapper.get('.btn-alert-bell')
    expect(alertToggle.attributes('aria-label')).toBe('Create screener alert')
    expect(alertToggle.attributes('aria-expanded')).toBe('false')
    await alertToggle.trigger('click')
    expect(alertToggle.attributes('aria-expanded')).toBe('true')
    const alertSettings = wrapper.get('[role="group"][aria-label="Screener alert settings"]')
    expect(alertToggle.attributes('aria-controls')).toBe(alertSettings.attributes('id'))
    expect(alertSettings.get('button.ap-close').attributes('aria-label')).toBe('Close screener alert settings')

    const addToWatchlist = wrapper.get('.results-table button.btn-add-wl')
    expect(addToWatchlist.attributes('aria-label')).toBe('Add SPY to a watchlist')
    addToWatchlist.element.focus()
    expect(document.activeElement).toBe(addToWatchlist.element)
    wrapper.unmount()
  })
})
