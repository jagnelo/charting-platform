import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import SearchBar from '@/components/common/SearchBar.vue'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'

const preparationMock = vi.hoisted(() => ({ ensure: vi.fn() }))

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: preparationMock.ensure },
  instrumentHistoryPreparationRequest: (target: unknown, timeframe: string, adjusted: boolean) => ({
    target, datasets: ['identity', 'profile', 'history'], timeframe, adjusted,
  }),
  preparationStatusMessage: (response: { status: string }) => response.status === 'ready'
    ? 'Requested data is ready.'
    : 'Data preparation is in progress.',
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
    preparationMock.ensure.mockResolvedValue({ status: 'ready' })
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

  it('submits the typed ticker on Enter instead of choosing a partial local result', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { symbol: 'FTI', name: 'TechnipFMC plc', exchange: 'NYSE', type: 'Common Stock' },
    ])

    const wrapper = mountSearchBar({
      props: { allowSourceDiscovery: true },
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('input').setValue('F')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('TechnipFMC plc')
    await wrapper.find('.result-item').trigger('mouseenter')
    await wrapper.find('input').trigger('keydown.enter')
    vi.advanceTimersByTime(300)
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'F', canonical_only: true })
    expect(wrapper.emitted('update:modelValue')).toEqual([['F']])
    expect(wrapper.emitted('select')).toEqual([['F', undefined]])
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/instruments/discover', expect.objectContaining({ query: 'F' }))
  })

  it('submits the exact local ticker even when it is not the first fuzzy result', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 88 },
      { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 89 },
    ])
    const wrapper = mountSearchBar({ global: { stubs: { RouterLink: true } } })

    await wrapper.get('input').setValue('XLE')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await wrapper.get('input').trigger('keydown.enter')

    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('XLE')
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'XLE', instrument_id: 89 })
  })

  it('prepares a selected known instrument through the shared coordinator by canonical ID', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'OIH', name: 'Oil Services ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 43 },
    ])
    const wrapper = mountSearchBar({ props: { mode: 'picker' }, global: { stubs: { RouterLink: true } } })
    await wrapper.get('input').setValue('OIH')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.result-item').exists()).toBe(true))
    await wrapper.get('.result-item').trigger('click')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(preparationMock.ensure).toHaveBeenCalledWith({
      target: { kind: 'instrument', instrument_id: 43 },
      datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true,
    }, expect.objectContaining({ onProgress: expect.any(Function) }))
    expect(wrapper.text()).toContain('Requested data is ready.')
  })

  it('does not let a superseded preparation response replace the newer query state', async () => {
    let finishPreparation!: (value: { status: string }) => void
    preparationMock.ensure.mockImplementationOnce(() => new Promise(resolve => { finishPreparation = resolve }))
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 89 },
    ])
    const wrapper = mountSearchBar({ props: { mode: 'picker' }, global: { stubs: { RouterLink: true } } })
    await wrapper.get('input').setValue('XLE')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.result-item').exists()).toBe(true))
    await wrapper.get('.result-item').trigger('click')
    expect(wrapper.text()).toContain('Preparing XLE history')

    await wrapper.get('input').setValue('NVDA')
    finishPreparation({ status: 'unavailable' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('unavailable')
    expect(wrapper.text()).not.toContain('Requested data is ready')
  })

  it('keeps picker Enter bound to the visible scoped result rather than submitting typed text', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'FTI', name: 'TechnipFMC plc', exchange: 'NYSE', type: 'Common Stock' },
    ])
    const wrapper = mountSearchBar({
      props: { mode: 'picker', resultTypes: ['Stock'] },
      global: { stubs: { RouterLink: true } },
    })

    await wrapper.get('input').setValue('F')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await wrapper.get('input').trigger('keydown.enter')

    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('FTI')
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'FTI', type: 'Common Stock' })
  })

  it('ignores a late local result after the user has typed a newer ticker', async () => {
    let resolveOld!: (value: unknown) => void
    vi.mocked(api.get)
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }) as ReturnType<typeof api.get>)
      .mockResolvedValueOnce([
        { symbol: 'NVDA', name: 'NVIDIA Corporation', exchange: 'NASDAQ', type: 'Common Stock', instrument_id: 44 },
      ])
    const wrapper = mountSearchBar({ global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')

    await input.setValue('F')
    vi.advanceTimersByTime(260)
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(1)

    await input.setValue('NVDA')
    expect(wrapper.text()).not.toContain('TechnipFMC')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('NVIDIA Corporation')

    resolveOld([{ symbol: 'FTI', name: 'TechnipFMC plc', exchange: 'NYSE', type: 'Common Stock', instrument_id: 17 }])
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).not.toContain('TechnipFMC plc')
    await input.trigger('keydown.enter')
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('NVDA')
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

  it('keeps Index ETF eligible while excluding ETN from a dedicated fund search', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'EVOL', name: 'Example vehicle', exchange: 'XNYS', type: 'ETV' },
      { symbol: 'INDEX', name: 'Broad market index fund', exchange: 'XNYS', type: 'Index ETF' },
      { symbol: 'NOTE', name: 'Example exchange traded note', exchange: 'XNYS', type: 'ETN' },
    ])
    const wrapper = mountSearchBar({
      props: { resultTypes: ['ETF', 'Fund', 'ETV', 'Exchange Traded Vehicle'], allowExpressions: false },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    await wrapper.find('input').setValue('EVOL')
    vi.advanceTimersByTime(260)
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', {
      q: 'EVOL', canonical_only: true, types: 'ETF,Fund,ETV,Exchange Traded Vehicle',
    })
    expect(wrapper.text()).toContain('Example vehicle')
    expect(wrapper.text()).toContain('Broad market index fund')
    expect(wrapper.text()).not.toContain('Example exchange traded note')
  })

  it('starts discovery for a new query while an older discovery is pending and ignores the stale candidate', async () => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn()
      .mockReturnValueOnce('11111111-1111-4111-8111-111111111111')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222') })
    vi.mocked(api.get).mockResolvedValue([])
    let finishOldDiscovery!: (value: unknown) => void
    const oldDiscovery = new Promise(resolve => { finishOldDiscovery = resolve })
    vi.mocked(api.post)
      .mockReturnValueOnce(oldDiscovery as ReturnType<typeof api.post>)
      .mockResolvedValueOnce({ request_id: 'new-query', status: 'no_match', candidates: [], source_outcomes: [] })

    const wrapper = mountSearchBar({
      props: { allowSourceDiscovery: true },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    const input = wrapper.find('input')
    await input.setValue('TCNEW')
    vi.advanceTimersByTime(260)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)

    await input.setValue('BWET')
    vi.advanceTimersByTime(260)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(api.post).toHaveBeenLastCalledWith('/instruments/discover', expect.objectContaining({ query: 'BWET' }))
    await vi.waitFor(() => expect(wrapper.text()).toContain('No matching ticker listing was found.'))
    finishOldDiscovery({
      request_id: 'old-query', status: 'complete',
      candidates: [{ symbol: 'TCNEW', name: 'Stale candidate', exchange: 'TEST', type: 'Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).not.toContain('Use TCNEW')
    expect(wrapper.find('.search-source-candidate').exists()).toBe(false)
    wrapper.unmount()
  })

  it('automatically discovers an unknown local ticker and resolves a candidate before emitting its canonical ID', async () => {
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

    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/discover', {
      query: 'OIH', types: [], limit: 10, request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.text()).toContain('Use OIH')
    await wrapper.find('.search-source-candidate').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/acquire', {
      symbol: 'OIH', provider_candidate: { provider: 'free-source', symbol: 'OIH', exchange: 'NYSE Arca' },
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('OIH')
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ instrument_id: 43 })
    expect(preparationMock.ensure).toHaveBeenCalledWith(expect.objectContaining({
      target: { kind: 'instrument', instrument_id: 43 },
    }), expect.objectContaining({ onProgress: expect.any(Function) }))
  })

  it('discovers a prefix without resolving or preparing a non-exact listing', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post).mockResolvedValueOnce({
      status: 'complete', candidates: [
        { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', provider: 'fixture', instrument_id: null, identity_status: 'candidate' },
        { symbol: 'XLF', name: 'Financial Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', provider: 'fixture', instrument_id: null, identity_status: 'candidate' },
      ], source_outcomes: [],
    })
    const wrapper = mountSearchBar({ global: { stubs: { RouterLink: true } } })
    await wrapper.get('input').setValue('XL')
    const enter = wrapper.get('input').trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    await enter

    await vi.waitFor(() => expect(wrapper.text()).toContain('Use XLE'))
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(preparationMock.ensure).not.toHaveBeenCalled()
  })

  it('sends raw ETV in a dedicated fund search and allows a resolved provider ETV candidate to be selected', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'discover-etv', status: 'complete',
        candidates: [
          {
            symbol: 'EVOL', name: 'Example Exchange Traded Vehicle', exchange: 'XNYS',
            type: 'ETV', provider: 'free-source', instrument_id: null,
            identity_status: 'provider_candidate',
          },
          {
            symbol: 'NOTE', name: 'Example exchange traded note', exchange: 'XNYS',
            type: 'ETN', provider: 'free-source', instrument_id: null,
            identity_status: 'provider_candidate',
          },
        ],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'resolve-etv', status: 'resolved',
        instrument: {
          instrument_id: 991, symbol: 'EVOL', identity_status: 'resolved',
          instrument_type: 'Exchange Traded Vehicle',
        },
        source_outcomes: [],
      })

    const resultTypes = ['ETF', 'Fund', 'ETV', 'Exchange Traded Vehicle']
    const wrapper = mountSearchBar({
      props: { resultTypes, allowExpressions: false, allowSourceDiscovery: true },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await wrapper.find('input').setValue('EVOL')
    vi.advanceTimersByTime(260)
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/instruments/search', {
      q: 'EVOL', canonical_only: true, types: 'ETF,Fund,ETV,Exchange Traded Vehicle',
    })
    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))

    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/discover', expect.objectContaining({
      query: 'EVOL', types: ['ETF', 'Fund', 'ETV', 'Exchange Traded Vehicle'], limit: 10,
    }))
    expect(wrapper.text()).toContain('Use EVOL')
    expect(wrapper.text()).not.toContain('Use NOTE')
    await wrapper.find('.search-source-candidate').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/acquire', expect.objectContaining({
      symbol: 'EVOL', provider_candidate: { provider: 'free-source', symbol: 'EVOL', exchange: 'XNYS' },
    }))
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('EVOL')
    expect(wrapper.emitted('select')?.[0]).toHaveLength(3)
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({
      type: 'ETV', instrument_id: 991, identity_status: 'resolved', explicitlyResolved: true,
    })
    expect(wrapper.emitted('select')?.[0]?.[2]).toMatchObject({
      request_id: 'resolve-etv',
      status: 'resolved',
      instrument: { instrument_id: 991, symbol: 'EVOL', identity_status: 'resolved', instrument_type: 'Exchange Traded Vehicle' },
    })
  })

  it('automatically checks an explicitly opened discovery-only query without local search', async () => {
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
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()

    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    expect(api.post).toHaveBeenCalledWith('/instruments/discover', {
      query: 'UNXQ', types: ['Equity', 'Stock'], limit: 10, request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
    expect(wrapper.text()).toContain('Uncached Example Equity')
    expect(wrapper.text()).not.toContain('ETF-shaped collision')
  })

  it('keeps exact matches local and never discovers from picker-only selection', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([
      { symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF', instrument_id: 43 },
    ])
    const wrapper = mountSearchBar({
      props: { allowSourceDiscovery: true, mode: 'picker' },
      global: { stubs: { RouterLink: true } },
    })
    await wrapper.get('input').setValue('OIH')
    vi.advanceTimersByTime(260)
    await flushPromises()
    vi.advanceTimersByTime(600)
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    await wrapper.get('.result-item').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('OIH')
  })

  it('lets keyboard Enter resolve the first discovered candidate after automatic lookup', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post)
      .mockResolvedValueOnce({ status: 'complete', candidates: [{ symbol: 'C', name: 'Example C', exchange: 'XNYS', type: 'Equity', provider: 'fixture', instrument_id: null, identity_status: 'candidate' }], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'resolved', instrument: { instrument_id: 31, symbol: 'C', identity_status: 'verified' }, source_outcomes: [] })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    await wrapper.get('input').setValue('C')
    vi.advanceTimersByTime(260)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    expect(wrapper.text()).toContain('Use C')
    // The candidate is selected only after an intentional keyboard action;
    // default highlight alone must not turn Enter into a candidate resolve.
    await wrapper.get('input').trigger('keydown', { key: 'ArrowDown' })
    await wrapper.get('input').trigger('keydown.enter')
    await flushPromises()
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'C', instrument_id: 31, explicitlyResolved: true })
    expect(wrapper.emitted('select')?.[0]).toHaveLength(3)
    expect(wrapper.emitted('select')?.[0]?.[2]).toMatchObject({
      status: 'resolved', instrument: { instrument_id: 31, symbol: 'C', identity_status: 'verified' },
    })
  })

  it('resolves the exact remote ticker on ordinary Enter without arrow navigation', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        status: 'complete',
        candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        status: 'resolved', instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified', instrument_type: 'Common Stock' }, source_outcomes: [],
      })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')

    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    await enter
    await flushPromises()
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/acquire', expect.objectContaining({
      symbol: 'F', provider_candidate: { provider: 'fixture', symbol: 'F', exchange: 'XNYS' },
    }))
    expect(wrapper.emitted('select')?.[0]).toHaveLength(3)
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'F', instrument_id: 83, explicitlyResolved: true })
    expect(wrapper.emitted('select')?.[0]?.[2]).toMatchObject({ status: 'resolved', instrument: { instrument_id: 83, symbol: 'F' } })
  })

  it('waits for a known temporary discovery retry and completes the pending Enter intent', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    const retryAt = new Date(Date.now() + 5000).toISOString()
    vi.mocked(api.post)
      .mockResolvedValueOnce({ status: 'held', retry_at: retryAt, candidates: [], source_outcomes: [{ status: 'held', retry_at: retryAt, reason_code: 'provider_quota_admission_denied' }] })
      .mockResolvedValueOnce({ status: 'complete', candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'resolved', instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified' }, source_outcomes: [] })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(wrapper.text()).toContain('checking again after'), { interval: 1, timeout: 100 })
    expect(wrapper.text()).not.toContain('provider_quota_admission_denied')
    expect(wrapper.emitted('select')).toBeUndefined()

    vi.advanceTimersByTime(5000)
    await flushPromises()
    await enter
    await vi.waitFor(() => expect(wrapper.emitted('select')?.[0]?.[0]).toBe('F'))
    expect(api.post).toHaveBeenCalledTimes(3)
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'F', instrument_id: 83, explicitlyResolved: true })
  })

  it('continues a deliberate Enter through successive advancing temporary holds until discovery resolves', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    const firstRetryAt = new Date(Date.now() + 5000).toISOString()
    const secondRetryAt = new Date(Date.now() + 10000).toISOString()
    vi.mocked(api.post)
      .mockResolvedValueOnce({ status: 'held', retry_at: firstRetryAt, candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'held', retry_at: secondRetryAt, candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({
        status: 'complete',
        candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        status: 'resolved', instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified' }, source_outcomes: [],
      })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')

    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(wrapper.text()).toContain('checking again after'), { interval: 1, timeout: 100 })

    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(2)
    await vi.waitFor(() => expect(wrapper.text()).toContain('checking again after'), { interval: 1, timeout: 100 })

    vi.advanceTimersByTime(5000)
    await flushPromises()
    await enter
    await vi.waitFor(() => expect(wrapper.emitted('select')?.[0]?.[0]).toBe('F'))

    expect(api.post).toHaveBeenCalledTimes(4)
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'F', instrument_id: 83, explicitlyResolved: true })
    expect(wrapper.text()).not.toContain('provider_quota_admission_denied')
  })

  it('continues deliberate candidate identity verification through successive known holds', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    const firstRetryAt = new Date(Date.now() + 5000).toISOString()
    const secondRetryAt = new Date(Date.now() + 10000).toISOString()
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        status: 'complete',
        candidates: [{ symbol: 'UNXQ', name: 'Example equity', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({ status: 'held', retry_at: firstRetryAt, source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'held', retry_at: secondRetryAt, source_outcomes: [] })
      .mockResolvedValueOnce({
        status: 'resolved', instrument: { instrument_id: 77, symbol: 'UNXQ', identity_status: 'verified' }, source_outcomes: [],
      })
    const wrapper = mountSearchBar({
      props: {
        modelValue: 'UNXQ', allowSourceDiscovery: true, sourceDiscoveryOnly: true,
        readonly: true, openOnMount: true, requiredResolvedSymbol: 'UNXQ',
      },
      global: { stubs: { RouterLink: true } },
    })
    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.find('.search-source-candidate').exists()).toBe(true))
    const candidate = wrapper.get('.search-source-candidate')
    await candidate.trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(2)

    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(3)
    await vi.waitFor(() => expect(wrapper.text()).toContain('checking again after'), { interval: 1, timeout: 100 })

    vi.advanceTimersByTime(5000)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.emitted('select')?.[0]?.[0]).toBe('UNXQ'))
    expect(api.post).toHaveBeenCalledTimes(4)
    expect(wrapper.emitted('select')?.[0]?.[1]).toMatchObject({ symbol: 'UNXQ', instrument_id: 77, explicitlyResolved: true })
  })

  it('does not spin when a later temporary hold repeats an expired retry time', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    const retryAt = new Date(Date.now() + 5000).toISOString()
    vi.mocked(api.post)
      .mockResolvedValueOnce({ status: 'held', retry_at: retryAt, candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({ status: 'held', retry_at: retryAt, candidates: [], source_outcomes: [] })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.text()).toContain('checking again after'), { interval: 1, timeout: 100 })

    vi.advanceTimersByTime(5000)
    await flushPromises()
    await enter
    vi.advanceTimersByTime(60000)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.text()).toContain('temporarily held')
  })

  it('cancels a pending discovery retry when the query changes', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockResolvedValueOnce({
      status: 'held', retry_at: new Date(Date.now() + 500).toISOString(), candidates: [],
      source_outcomes: [{ status: 'held', retry_at: new Date(Date.now() + 500).toISOString(), reason_code: 'provider_quota_admission_denied' }],
    })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)

    await input.setValue('NVDA')
    await enter
    vi.advanceTimersByTime(1000)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.get('input').element).toHaveProperty('value', 'NVDA')
  })

  it('does not resolve ambiguous exact remote listings on ordinary Enter', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValueOnce([])
    vi.mocked(api.post).mockResolvedValueOnce({
      status: 'complete', candidates: [
        { symbol: 'F', name: 'Ford XNYS', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture-a', instrument_id: null, identity_status: 'provider_candidate' },
        { symbol: 'F', name: 'Ford BATS', exchange: 'BATS', type: 'Common Stock', provider: 'fixture-b', instrument_id: null, identity_status: 'provider_candidate' },
      ], source_outcomes: [],
    })
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    await enter
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.text()).toContain('More than one listing matches F')
    expect(preparationMock.ensure).not.toHaveBeenCalled()
  })

  it('does not submit a pending discovered ticker after the user changes the query', async () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
    vi.mocked(api.get).mockResolvedValue([])
    let finishDiscovery!: (value: unknown) => void
    vi.mocked(api.post).mockReturnValueOnce(new Promise(resolve => { finishDiscovery = resolve }) as ReturnType<typeof api.post>)
    const wrapper = mountSearchBar({ props: { allowSourceDiscovery: true }, global: { stubs: { RouterLink: true } } })
    const input = wrapper.get('input')
    await input.setValue('F')
    const enter = input.trigger('keydown.enter')
    vi.advanceTimersByTime(250)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)

    await input.setValue('NVDA')
    await enter
    finishDiscovery({
      status: 'complete',
      candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    await flushPromises()
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(api.post).toHaveBeenCalledTimes(1)
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
    vi.advanceTimersByTime(300)
    await flushPromises()
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
    vi.advanceTimersByTime(300)
    await flushPromises()
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
    vi.advanceTimersByTime(260)
    await flushPromises()
    vi.advanceTimersByTime(300)
    await flushPromises()
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
    expect(wrapper.emitted('select')?.[0]).toEqual([
      '=SPY-QQQ',
      { symbol: '=SPY-QQQ', name: '=SPY-QQQ', exchange: '', type: 'Synthetic' },
    ])
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
