import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import DashboardInstrumentSearch from '@/components/dashboard/DashboardInstrumentSearch.vue'

const { discover, resolveDiscovered } = vi.hoisted(() => ({
  discover: vi.fn(),
  resolveDiscovered: vi.fn(),
}))
const { resolveKnownSymbol } = vi.hoisted(() => ({ resolveKnownSymbol: vi.fn() }))

vi.mock('@/lib/onDemandAcquisition', () => ({
  discoverInstruments: discover,
  resolveDiscoveredInstrument: resolveDiscovered,
}))
vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: resolveKnownSymbol,
  formatInstrumentLookupError: (_symbol: string, error: Error) => error.message,
  getInstrumentInputHint: () => '',
  isExpressionInput: (value: string) => value.trim().startsWith('='),
  isResolvableExpressionInput: (value: string) => value.trim().startsWith('=') && value.trim().length > 1,
}))

function candidate(symbol: string, instrumentId: number | null = null, exchange = 'NASDAQ') {
  return {
    symbol,
    name: `${symbol} Corp`,
    exchange,
    type: 'Equity',
    provider: 'controlled-source',
    instrument_id: instrumentId,
    identity_status: instrumentId === null ? 'candidate' : 'verified',
  }
}

function discovery(candidates: ReturnType<typeof candidate>[], status = 'complete') {
  return { request_id: 'request-test', status, candidates, source_outcomes: [] }
}

function existingResolution(symbol: string, instrumentId = 17) {
  return {
    status: 'resolved',
    instrument: { instrument_id: instrumentId, symbol, identity_status: 'verified' },
    source_outcomes: [],
  }
}

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

const mountedDashboardSearches: Array<{ unmount: () => void }> = []

function mountDashboardSearch(options: any = {}) {
  const wrapper = mount(DashboardInstrumentSearch, { attachTo: document.body, ...options })
  mountedDashboardSearches.push(wrapper)
  return wrapper
}

describe('DashboardInstrumentSearch', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    resolveKnownSymbol.mockRejectedValue(new Error('Expression could not be resolved'))
  })

  afterEach(() => {
    for (const wrapper of mountedDashboardSearches.splice(0)) wrapper.unmount()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('keeps prefix discovery results as candidates until the user explicitly selects one', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('NVDA', null)]))
    resolveDiscovered.mockResolvedValueOnce({
      status: 'resolved',
      instrument: { instrument_id: 9, symbol: 'NVDA', identity_status: 'verified' },
      source_outcomes: [],
    })
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('NV')
    vi.advanceTimersByTime(230)
    await flushPromises()
    const button = document.body.querySelector('.dash-search-item') as HTMLButtonElement

    expect(discover).toHaveBeenCalledWith('NV', [], 10)
    expect(button.textContent).toContain('NVDA Corp')
    expect(resolveDiscovered).not.toHaveBeenCalled()
    expect(wrapper.emitted('select')).toBeUndefined()

    button.click()
    await flushPromises()
    expect(resolveDiscovered).toHaveBeenCalledWith(candidate('NVDA', null))
    expect(wrapper.emitted('select')?.[0]).toEqual(['NVDA'])
  })

  it('keeps a teleported candidate alive through ordinary mousedown and click', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('NVDA', null)]))
    resolveDiscovered.mockResolvedValueOnce({
      status: 'resolved',
      instrument: { instrument_id: 9, symbol: 'NVDA', identity_status: 'verified' },
      source_outcomes: [],
    })
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')
    await input.setValue('NV')
    vi.advanceTimersByTime(230)
    await flushPromises()
    const button = document.body.querySelector('.dash-search-item') as HTMLButtonElement
    expect(button).toBeTruthy()

    button.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await nextTick()
    expect(document.body.contains(button)).toBe(true)
    button.click()
    await flushPromises()

    expect(resolveDiscovered).toHaveBeenCalledWith(candidate('NVDA', null))
    expect(wrapper.emitted('select')?.[0]).toEqual(['NVDA'])
    expect(document.body.querySelector('.dash-search-results')).toBeNull()
  })

  it('selects a visible candidate by keyboard and ignores a late superseded resolution', async () => {
    let resolveOld!: (value: unknown) => void
    discover
      .mockResolvedValueOnce(discovery([candidate('NVDA', null)]))
      .mockResolvedValueOnce(discovery([candidate('NEWT', null)]))
    resolveDiscovered.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')

    await input.setValue('NV')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await input.trigger('keydown.enter')
    expect(resolveDiscovered).toHaveBeenCalledWith(candidate('NVDA', null))

    await input.setValue('NE')
    vi.advanceTimersByTime(230)
    await flushPromises()
    expect(document.body.textContent).toContain('NEWT Corp')
    resolveOld({
      status: 'resolved',
      instrument: { instrument_id: 9, symbol: 'NVDA', identity_status: 'verified' },
      source_outcomes: [],
    })
    await flushPromises()

    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.body.textContent).toContain('NEWT Corp')
    expect(document.body.textContent).not.toContain('NVDA Corp')
  })

  it('resolves one unique exact ticker without exposing provider choices', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('AAPL', 17)]))
    resolveDiscovered.mockResolvedValueOnce({
      ...existingResolution('AAPL'),
    })
    resolveKnownSymbol.mockRejectedValueOnce(new Error('Instrument is not available'))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('AAPL')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await flushPromises()

    expect(resolveDiscovered).toHaveBeenCalledWith(candidate('AAPL', 17))
    expect(resolveKnownSymbol).toHaveBeenCalledWith('AAPL', 'Instrument', { canonicalOnly: true })
    expect(wrapper.emitted('select')?.[0]).toEqual(['AAPL'])
    expect(document.body.textContent).not.toContain('controlled-source')
  })

  it('does not auto-resolve an exact-looking candidate from incomplete discovery', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('AAPL', null)], 'partial'))
    resolveKnownSymbol.mockRejectedValueOnce(new Error('Instrument is not available'))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('AAPL')
    vi.advanceTimersByTime(230)
    await flushPromises()

    expect(resolveDiscovered).not.toHaveBeenCalled()
    expect(resolveKnownSymbol).toHaveBeenCalledWith('AAPL', 'Instrument', { canonicalOnly: true })
    expect(document.body.querySelectorAll('.dash-search-item')).toHaveLength(1)
    expect(document.body.textContent).toContain('NASDAQ')
    expect(document.body.textContent).toContain('Some instrument candidates may be missing')
  })

  it('does not guess when an exact ticker has multiple listing candidates', async () => {
    discover.mockResolvedValueOnce(discovery([
      candidate('ABC', null, 'NYSE'),
      candidate('ABC', null, 'NASDAQ'),
    ]))
    resolveKnownSymbol.mockRejectedValueOnce(new Error('Instrument is not available'))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('ABC')
    vi.advanceTimersByTime(230)
    await flushPromises()

    expect(resolveKnownSymbol).toHaveBeenCalledWith('ABC', 'Instrument', { canonicalOnly: true })
    expect(resolveDiscovered).not.toHaveBeenCalled()
    expect(document.body.querySelectorAll('.dash-search-item')).toHaveLength(2)
  })

  it('ignores a superseded discovery response after the query changes', async () => {
    let resolveOld!: (value: unknown) => void
    discover
      .mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
      .mockResolvedValueOnce(discovery([candidate('MSFT', null)]))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    const input = wrapper.find('input')
    await input.setValue('A')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await input.setValue('M')
    expect(document.body.textContent).not.toContain('AAPL Corp')
    vi.advanceTimersByTime(230)
    await flushPromises()

    resolveOld(discovery([candidate('AAPL', null)]))
    await flushPromises()

    expect(discover).toHaveBeenNthCalledWith(1, 'A', [], 10)
    expect(discover).toHaveBeenNthCalledWith(2, 'M', [], 10)
    expect(document.body.textContent).toContain('MSFT Corp')
    expect(document.body.textContent).not.toContain('AAPL Corp')
    expect(resolveDiscovered).not.toHaveBeenCalled()
  })

  it('selects an exact cached listing while external discovery remains held', async () => {
    let resolveHeldDiscovery!: (value: unknown) => void
    discover.mockReturnValueOnce(new Promise(resolve => { resolveHeldDiscovery = resolve }))
    resolveKnownSymbol.mockResolvedValueOnce('XLB')
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')

    await input.setValue('XLB')
    vi.advanceTimersByTime(230)
    await flushPromises()

    expect(resolveKnownSymbol).toHaveBeenCalledWith('XLB', 'Instrument', { canonicalOnly: true })
    expect(resolveDiscovered).not.toHaveBeenCalled()
    expect(wrapper.emitted('select')?.[0]).toEqual(['XLB'])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['XLB'])
    expect(document.body.querySelectorAll('.dash-search-item')).toHaveLength(0)

    resolveHeldDiscovery(discovery([], 'held'))
    await flushPromises()
    expect(wrapper.emitted('select')).toHaveLength(1)
    expect(document.body.querySelector('.dash-search-error')).toBeNull()
  })

  it('ignores a late exact cached resolution after a newer search intent', async () => {
    let resolveOld!: (value: unknown) => void
    resolveKnownSymbol
      .mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
      .mockRejectedValueOnce(new Error('Instrument is not available'))
    discover
      .mockResolvedValueOnce(discovery([], 'held'))
      .mockResolvedValueOnce(discovery([candidate('NEWT', null)], 'partial'))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')

    await input.setValue('XLB')
    vi.advanceTimersByTime(230)
    await flushPromises()
    expect(resolveKnownSymbol).toHaveBeenNthCalledWith(1, 'XLB', 'Instrument', { canonicalOnly: true })

    await input.setValue('NEW')
    vi.advanceTimersByTime(230)
    await flushPromises()
    resolveOld('XLB')
    await flushPromises()

    expect(wrapper.emitted('select')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(input.element).toHaveProperty('value', 'NEW')
    expect(document.body.textContent).toContain('NEWT Corp')
    expect(resolveDiscovered).not.toHaveBeenCalled()
  })

  it('keeps expression resolution and surfaces identity failures without committing', async () => {
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')
    await input.setValue('=SPY-QQQ')
    expect(document.body.textContent).toContain('Expression')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(resolveKnownSymbol).toHaveBeenCalledWith('=SPY-QQQ', 'Instrument', { canonicalOnly: true })
    expect(document.body.textContent).toContain('Expression could not be resolved')
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(discover).not.toHaveBeenCalled()
  })
})
