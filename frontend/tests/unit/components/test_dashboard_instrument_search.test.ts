import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import DashboardInstrumentSearch from '@/components/dashboard/DashboardInstrumentSearch.vue'

const { discover, resolveDiscovered, resolveExisting } = vi.hoisted(() => ({
  discover: vi.fn(),
  resolveDiscovered: vi.fn(),
  resolveExisting: vi.fn(),
}))
const { resolveExpression } = vi.hoisted(() => ({ resolveExpression: vi.fn() }))

vi.mock('@/lib/onDemandAcquisition', () => ({
  discoverInstruments: discover,
  resolveDiscoveredInstrument: resolveDiscovered,
  resolveExistingInstrument: resolveExisting,
}))
vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: resolveExpression,
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
    resolveExpression.mockRejectedValue(new Error('Expression could not be resolved'))
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

  it('resolves one unique exact ticker without exposing provider choices', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('AAPL', 17)]))
    resolveDiscovered.mockResolvedValueOnce({
      status: 'resolved',
      instrument: { instrument_id: 17, symbol: 'AAPL', identity_status: 'verified' },
      source_outcomes: [],
    })
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('AAPL')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await flushPromises()

    expect(resolveDiscovered).toHaveBeenCalledWith(candidate('AAPL', 17))
    expect(resolveExisting).not.toHaveBeenCalled()
    expect(wrapper.emitted('select')?.[0]).toEqual(['AAPL'])
    expect(document.body.textContent).not.toContain('controlled-source')
  })

  it('does not auto-resolve an exact-looking candidate from incomplete discovery', async () => {
    discover.mockResolvedValueOnce(discovery([candidate('AAPL', null)], 'partial'))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('AAPL')
    vi.advanceTimersByTime(230)
    await flushPromises()

    expect(resolveDiscovered).not.toHaveBeenCalled()
    expect(resolveExisting).not.toHaveBeenCalled()
    expect(document.body.querySelectorAll('.dash-search-item')).toHaveLength(1)
    expect(document.body.textContent).toContain('NASDAQ')
    expect(document.body.textContent).toContain('Some instrument candidates may be missing')
  })

  it('does not guess when an exact ticker has multiple listing candidates', async () => {
    discover.mockResolvedValueOnce(discovery([
      candidate('ABC', null, 'NYSE'),
      candidate('ABC', null, 'NASDAQ'),
    ]))
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })

    await wrapper.find('input').setValue('ABC')
    vi.advanceTimersByTime(230)
    await flushPromises()

    expect(resolveExisting).not.toHaveBeenCalled()
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

  it('keeps expression resolution and surfaces identity failures without committing', async () => {
    const wrapper = mountDashboardSearch({ props: { modelValue: '' } })
    const input = wrapper.find('input')
    await input.setValue('=SPY-QQQ')
    expect(document.body.textContent).toContain('Expression')
    await input.trigger('keydown.enter')
    await flushPromises()

    expect(resolveExpression).toHaveBeenCalledWith('=SPY-QQQ', 'Instrument', { canonicalOnly: true })
    expect(document.body.textContent).toContain('Expression could not be resolved')
    expect(wrapper.emitted('select')).toBeUndefined()
    expect(discover).not.toHaveBeenCalled()
  })
})
