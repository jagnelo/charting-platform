import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  setQueuedApiRequestPriority: vi.fn(),
}))

import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'
import WatchlistView from '@/views/WatchlistView.vue'

const SearchBarStub = defineComponent({
  emits: ['select'],
  template: '<button type="button" aria-label="Add SPY" @click="$emit(\'select\', \'SPY\')">Select SPY</button>',
})

const VueDraggableStub = defineComponent({
  props: { modelValue: { type: Array, default: () => [] } },
  emits: ['update:modelValue', 'end'],
  template: '<div><slot /></div>',
})

function makeWatchlist(id: number, name: string) {
  return {
    id,
    name,
    is_default: false,
    is_managed: false,
    is_locked: false,
    position: id,
    items: [],
  }
}

describe('WatchlistView bootstrap selection', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
  })

  it('keeps the second newly-created list active when the delayed initial list read settles', async () => {
    let resolveInitialLoad!: (watchlists: ReturnType<typeof makeWatchlist>[]) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => {
      resolveInitialLoad = resolve
    }))
    const first = makeWatchlist(36, 'First list')
    const second = makeWatchlist(37, 'Second list')
    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(first)
      .mockResolvedValueOnce(second)

    const store = useWatchlistStore()
    store.fetchPrices = vi.fn()
    store.addBySymbol = vi.fn().mockResolvedValue(null)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: defineComponent({ template: '<div />' }) }],
    })
    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [router],
        stubs: {
          VueDraggable: VueDraggableStub,
          SearchBar: SearchBarStub,
          Sparkline: true,
          SparkTfSelector: true,
        },
      },
    })

    try {
      expect(store.loading).toBe(true)
      await wrapper.get('.wls-new-btn').trigger('click')
      await wrapper.get('input[aria-label="New watchlist name"]').setValue('First list')
      await wrapper.get('button[aria-label="Create watchlist"]').trigger('click')
      await flushPromises()

      await wrapper.get('.wls-new-btn').trigger('click')
      await wrapper.get('input[aria-label="New watchlist name"]').setValue('Second list')
      await wrapper.get('button[aria-label="Create watchlist"]').trigger('click')
      await flushPromises()

      expect(wrapper.get('.wlm-title').text()).toBe('Second list')
      expect(store.loading).toBe(true)

      resolveInitialLoad([first, second])
      await flushPromises()

      expect(wrapper.get('.wlm-title').text()).toBe('Second list')
      await wrapper.get('button[aria-label="Add SPY"]').trigger('click')
      expect(store.addBySymbol).toHaveBeenCalledWith(37, 'SPY')
    } finally {
      wrapper.unmount()
    }
  })

  it('still selects the first list when bootstrap finishes without a newer selection', async () => {
    const first = { ...makeWatchlist(36, 'First list'), items: [{ id: 1, instrument_id: 2, symbol: 'SPY', position: 0 }] }
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([first])
    const store = useWatchlistStore()
    store.fetchPrices = vi.fn()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: defineComponent({ template: '<div />' }) }],
    })
    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [router],
        stubs: {
          VueDraggable: VueDraggableStub,
          SearchBar: SearchBarStub,
          Sparkline: true,
          SparkTfSelector: true,
        },
      },
    })

    try {
      await flushPromises()
      expect(wrapper.get('.wlm-title').text()).toBe('First list')
      expect(store.fetchPrices).toHaveBeenCalledWith(['SPY'])
    } finally {
      wrapper.unmount()
    }
  })

  it('does not let a pending create steal a newer list selection or close a newer create form', async () => {
    const first = makeWatchlist(36, 'First list')
    const second = makeWatchlist(37, 'Second list')
    const created = makeWatchlist(38, 'Created list')
    let resolveCreate!: (watchlist: ReturnType<typeof makeWatchlist>) => void
    const createResponse = new Promise<ReturnType<typeof makeWatchlist>>(resolve => { resolveCreate = resolve })
    const store = useWatchlistStore()
    store.watchlists.push(first, second)
    store.loading = false
    store.loadWatchlists = vi.fn().mockResolvedValue(undefined)
    store.fetchPrices = vi.fn()
    store.createWatchlist = vi.fn(async () => {
      const result = await createResponse
      store.watchlists.push(result)
      return result
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: defineComponent({ template: '<div />' }) }],
    })
    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [router],
        stubs: {
          VueDraggable: VueDraggableStub,
          SearchBar: SearchBarStub,
          Sparkline: true,
          SparkTfSelector: true,
        },
      },
    })

    try {
      await flushPromises()
      await wrapper.get('.wls-new-btn').trigger('click')
      await wrapper.get('input[aria-label="New watchlist name"]').setValue('Created list')
      await wrapper.get('button[aria-label="Create watchlist"]').trigger('click')

      await wrapper.get('button[aria-label="Cancel watchlist creation"]').trigger('click')
      await wrapper.get('.wls-new-btn').trigger('click')
      await wrapper.get('input[aria-label="New watchlist name"]').setValue('Created list')
      await wrapper.findAll('.wls-item')[1]!.trigger('click')

      resolveCreate(created)
      await flushPromises()

      expect(wrapper.get('.wlm-title').text()).toBe('Second list')
      expect(wrapper.get('input[aria-label="New watchlist name"]').element.value).toBe('Created list')
      expect(wrapper.findAll('.wlsi-name').map(name => name.text())).toContain('Created list')
      expect(store.createWatchlist).toHaveBeenCalledWith('Created list')
    } finally {
      wrapper.unmount()
    }
  })

  it('does not let a pending copy steal a newer selection, but selects an acknowledged copy when no newer choice exists', async () => {
    const first = makeWatchlist(36, 'First list')
    const second = makeWatchlist(37, 'Second list')
    const lateCopy = makeWatchlist(38, 'Late copy')
    const immediateCopy = makeWatchlist(39, 'Immediate copy')
    let resolveCopy!: (watchlist: ReturnType<typeof makeWatchlist>) => void
    const copyResponse = new Promise<ReturnType<typeof makeWatchlist>>(resolve => { resolveCopy = resolve })
    const store = useWatchlistStore()
    store.watchlists.push(first, second)
    store.loading = false
    store.loadWatchlists = vi.fn().mockResolvedValue(undefined)
    store.fetchPrices = vi.fn()
    store.copyWatchlist = vi.fn()
      .mockImplementationOnce(async () => {
        const result = await copyResponse
        store.watchlists.push(result)
        return result
      })
      .mockImplementationOnce(async () => {
        store.watchlists.push(immediateCopy)
        return immediateCopy
      })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: defineComponent({ template: '<div />' }) }],
    })
    const wrapper = mount(WatchlistView, {
      global: {
        plugins: [router],
        stubs: {
          VueDraggable: VueDraggableStub,
          SearchBar: SearchBarStub,
          Sparkline: true,
          SparkTfSelector: true,
        },
      },
    })

    try {
      await flushPromises()
      await wrapper.findAll('.wlsi-menu-btn')[0]!.trigger('click')
      await wrapper.findAll('.wlsi-dd-item').find(item => item.text() === 'Copy')!.trigger('click')
      expect(store.copyWatchlist).toHaveBeenCalledWith(36)

      await wrapper.findAll('.wls-item')[1]!.trigger('click')
      resolveCopy(lateCopy)
      await flushPromises()
      expect(wrapper.get('.wlm-title').text()).toBe('Second list')
      expect(wrapper.findAll('.wlsi-name').map(name => name.text())).toContain('Late copy')

      await wrapper.findAll('.wlsi-menu-btn')[1]!.trigger('click')
      await wrapper.findAll('.wlsi-dd-item').find(item => item.text() === 'Copy')!.trigger('click')
      await flushPromises()
      expect(store.copyWatchlist).toHaveBeenCalledWith(37)
      expect(wrapper.get('.wlm-title').text()).toBe('Immediate copy')
    } finally {
      wrapper.unmount()
    }
  })
})
