import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WatchlistPanel from '@/components/watchlist/WatchlistPanel.vue'
import { useWatchlistStore } from '@/stores/watchlist'

describe('WatchlistPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('expands a watchlist, fetches prices, and emits selected symbols', async () => {
    const store = useWatchlistStore()
    store.watchlists = [{
      id: 1,
      name: 'Momentum',
      is_default: false,
      is_managed: false,
      is_locked: false,
      position: 0,
      items: [{ id: 10, instrument_id: 44, symbol: 'NVDA', position: 0 }],
    }] as any
    const fetchSpy = vi.spyOn(store, 'fetchPrices').mockResolvedValue(undefined)

    const wrapper = mount(WatchlistPanel, {
      props: { currentSymbol: 'AAPL' },
      global: {
        stubs: {
          VueDraggable: {
            template: '<div><slot /></div>',
            props: ['modelValue'],
          },
          Sparkline: { template: '<div class="sparkline-stub" />' },
          SparkTfSelector: { template: '<div class="spark-tf-stub" />' },
          Teleport: true,
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('.wlp-section-hdr').trigger('click')
    await nextTick()

    expect(fetchSpy).toHaveBeenCalledWith(['NVDA'])
    expect(wrapper.find('.wlp-item').exists()).toBe(true)

    await wrapper.find('.wlp-item').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['NVDA']])
  })

  it('starts compact chart layouts collapsed while keeping the watchlist toggle usable', async () => {
    const store = useWatchlistStore()
    vi.spyOn(store, 'loadWatchlists').mockResolvedValue(undefined)
    const wrapper = mount(WatchlistPanel, {
      props: { compactDefault: true },
      global: {
        stubs: {
          VueDraggable: { template: '<div><slot /></div>', props: ['modelValue'] },
          Sparkline: { template: '<div />' },
          SparkTfSelector: { template: '<div />' },
          Teleport: true,
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await nextTick()
    const toggle = wrapper.get('.wlp-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.attributes('aria-label')).toBe('Show watchlists')

    await toggle.trigger('click')
    expect(wrapper.get('.wlp-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.wlp-toggle').attributes('aria-label')).toBe('Hide watchlists')
  })
})
