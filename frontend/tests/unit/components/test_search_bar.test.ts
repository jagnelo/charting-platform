import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import SearchBar from '@/components/common/SearchBar.vue'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import { api } from '@/lib/api'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
}

const mountedSearchBars: Array<{ unmount: () => void }> = []

function mountSearchBar(options: any = {}) {
  const wrapper = mount(SearchBar, options)
  mountedSearchBars.push(wrapper)
  return wrapper
}

describe('SearchBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    for (const wrapper of mountedSearchBars.splice(0)) wrapper.unmount()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('shows recently viewed instruments on focus with empty query', async () => {
    const recentStore = useRecentInstrumentsStore()
    recentStore.add('NVDA', 'NVIDIA')

    const wrapper = mountSearchBar({
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
        },
      },
    })
    await wrapper.vm.$nextTick()

    await wrapper.find('input').trigger('focus')
    expect(wrapper.text()).toContain('Recently viewed')
    expect(wrapper.text()).toContain('NVDA')
  })

  it('loads search results after debounce and emits selected symbol on click', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
    ])

    const wrapper = mountSearchBar({
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('input').setValue('AAPL')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'AAPL', canonical_only: true })
    expect(wrapper.text()).toContain('Apple Inc.')

    await wrapper.findAll('.result-item')[0].trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([
      'AAPL',
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
    ])
  })

  it('does not offer or emit a raw direct symbol when search returns no provider matches', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const wrapper = mountSearchBar({
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('input').setValue('TSLA')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await wrapper.find('input').trigger('keydown.enter')
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'TSLA', canonical_only: true })
    expect(wrapper.text()).not.toContain('Open chart for')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('can scope provider-backed results to specific instrument types', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
      { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', type: 'ETF' },
    ])

    const wrapper = mountSearchBar({
      props: {
        resultTypes: ['ETF', 'Fund'],
        allowExpressions: false,
      },
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('input').setValue('SP')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', {
      q: 'SP',
      canonical_only: true,
      types: 'ETF,Fund',
    })
    expect(wrapper.text()).toContain('SPDR S&P 500 ETF Trust')
    expect(wrapper.text()).not.toContain('Apple Inc.')
  })

  it('discovers only on explicit action, then resolves a candidate before emitting its canonical ID', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', status: 'complete',
        candidates: [{ symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF', provider: 'free-source', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', status: 'resolved',
        instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [],
      })

    const wrapper = mountSearchBar({
      props: { allowSourceDiscovery: true },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await wrapper.find('input').setValue('OIH')
    vi.advanceTimersByTime(260)
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'OIH', canonical_only: true })

    await wrapper.get('button').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/discover', {
      query: 'OIH', types: [], limit: 10, request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.text()).toContain('Resolve OIH')
    await wrapper.find('.search-source-candidate').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/acquire', {
      symbol: 'OIH', provider_candidate: { provider: 'free-source', symbol: 'OIH', exchange: 'NYSE Arca' },
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('OIH')
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ instrument_id: 43 })
  })

  it('opens a prefilled discovery-only query without local search and filters candidates to the requested equity scope', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post).mockResolvedValueOnce({
      request_id: 'r',
      status: 'complete',
      candidates: [
        { symbol: 'UNXQ', name: 'ETF-shaped collision', exchange: 'X', type: 'ETF', provider: 'source-a', instrument_id: null, identity_status: 'unresolved' },
        { symbol: 'UNXQ', name: 'Uncached Example Equity', exchange: 'XNYS', type: 'Common Stock', provider: 'source-b', instrument_id: null, identity_status: 'unresolved' },
      ],
      source_outcomes: [],
    })
    const wrapper = mountSearchBar({
      props: {
        modelValue: 'UNXQ',
        resultTypes: ['Equity', 'Stock'],
        allowSourceDiscovery: true,
        sourceDiscoveryOnly: true,
        readonly: true,
        openOnMount: true,
      },
      global: { stubs: { RouterLink: true } },
    })

    expect(wrapper.get('input').element.value).toBe('UNXQ')
    expect(wrapper.get('input').attributes('readonly')).toBeDefined()
    expect(wrapper.text()).toContain('Search free sources for UNXQ')
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()

    await wrapper.get('button').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    expect(api.post).toHaveBeenCalledWith('/instruments/discover', {
      query: 'UNXQ', types: ['Equity', 'Stock'], limit: 10, request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.text()).toContain('Uncached Example Equity')
    expect(wrapper.text()).not.toContain('ETF-shaped collision')
  })

  it('does not resolve or emit a candidate whose provider-verified symbol differs from the reported ticker', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        status: 'complete',
        candidates: [{ symbol: 'UNXQ', name: 'Example', exchange: 'X', type: 'Equity', provider: 'source', instrument_id: null, identity_status: 'unresolved' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        status: 'resolved', instrument: { instrument_id: 54, symbol: 'UNXQ.A', identity_status: 'verified' }, source_outcomes: [],
      })
    const wrapper = mountSearchBar({
      props: { modelValue: 'UNXQ', allowSourceDiscovery: true, sourceDiscoveryOnly: true, readonly: true, openOnMount: true, requiredResolvedSymbol: 'UNXQ' },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    await wrapper.get('.search-source-candidate').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('resolved canonical symbol does not match')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('keeps a same-symbol response nonpositive when the provider identity status is not verified', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        status: 'complete',
        candidates: [{ symbol: 'UNXQ', name: 'Example', exchange: 'X', type: 'Equity', provider: 'source', instrument_id: null, identity_status: 'unresolved' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        status: 'resolved', instrument: { instrument_id: 54, symbol: 'UNXQ', identity_status: 'candidate_only' }, source_outcomes: [],
      })
    const wrapper = mountSearchBar({
      props: { modelValue: 'UNXQ', allowSourceDiscovery: true, sourceDiscoveryOnly: true, readonly: true, openOnMount: true, requiredResolvedSymbol: 'UNXQ' },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    await wrapper.get('.search-source-candidate').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('did not verify this canonical identity')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('does not open a discovered candidate when identity resolution reports a conflict', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post)
      .mockResolvedValueOnce({ request_id: 'r', status: 'complete', candidates: [{ symbol: 'OIH', name: 'Oil Services ETF', exchange: 'X', type: 'ETF', provider: 'source', instrument_id: 999, identity_status: 'provider_candidate' }], source_outcomes: [] })
      .mockResolvedValueOnce({ request_id: 'r', status: 'identity_conflict', reason_code: 'conflict', instrument: null, source_outcomes: [] })
    const wrapper = mountSearchBar({
      props: { allowSourceDiscovery: true },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await wrapper.find('input').setValue('OIH')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    await wrapper.find('.search-source-candidate').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Identity conflict')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('resolves expression queries and emits the resulting symbol on enter', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ symbol: '=SPY-QQQ' })

    const wrapper = mountSearchBar({
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    const input = wrapper.find('input')
    await input.setValue('=SPY-QQQ')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/instruments/resolve-expression', {
      expression: '=SPY-QQQ',
    })
    expect(wrapper.emitted('select')?.[0]).toEqual(['=SPY-QQQ', undefined])
  })

  it('shows a hint and skips API calls for incomplete expressions', async () => {
    const wrapper = mountSearchBar({
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    const input = wrapper.find('input')
    await input.setValue('=')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Finish the expression to continue.')
  })

  it('resets picker-mode draft text back to the committed instrument on escape', async () => {
    const wrapper = mountSearchBar({
      props: {
        mode: 'picker',
        modelValue: 'SPY',
      },
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    const input = wrapper.find('input')
    await input.setValue('APPLE')
    await input.trigger('keydown.escape')
    await flushPromises()

    expect((input.element as HTMLInputElement).value).toBe('SPY')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
