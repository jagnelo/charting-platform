import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
import HistoryAcquisitionControl from '@/components/chart/HistoryAcquisitionControl.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(accept => { resolve = accept })
  return { promise, resolve }
}

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

const missingCoverage = {
  status: 'partial', bar_count: 4,
  missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-01-31T23:59:59Z' }],
}
const resolvedIdentity = {
  request_id: 'resolve-id', status: 'resolved',
  instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [],
}
const partialHistory = {
  request_id: 'history-id', status: 'partial', instrument_id: 43, symbol: 'OIH', timeframe: 'D1', adjusted: true,
  requested_start: '2026-01-01T00:00:00.000Z', requested_end: '2026-01-31T23:59:59.999Z',
  coverage: { status: 'partial', bar_count: 7, missing_slices: [] }, bars: [], source_outcomes: [],
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
})

afterEach(() => vi.unstubAllGlobals())

describe('HistoryAcquisitionControl', () => {
  it('uses one accessible click for bounded coverage, identity, then history stages', async () => {
    const coverage = deferred<typeof missingCoverage>()
    const identity = deferred<typeof resolvedIdentity>()
    const history = deferred<typeof partialHistory>()
    vi.mocked(api.get).mockReturnValueOnce(coverage.promise as never)
    vi.mocked(api.post).mockReturnValueOnce(identity.promise as never).mockReturnValueOnce(history.promise as never)
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })
    const button = wrapper.get('[data-testid="history-load-missing"]')
    expect(button.element.tagName).toBe('BUTTON')
    expect(button.attributes('type')).toBe('button')
    expect((button.element as HTMLButtonElement).tabIndex).toBe(0)
    expect(button.text()).toBe('Load missing history')
    expect(wrapper.text()).toContain('Custom date range')
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()

    await button.trigger('click')
    expect(button.text()).toBe('Checking local history…')
    expect(api.get).toHaveBeenCalledTimes(1)
    const requestedRange = vi.mocked(api.get).mock.calls[0][1] as { start: string; end: string; timeframe: string }
    expect(requestedRange.timeframe).toBe('D1')
    expect(Date.parse(requestedRange.end) - Date.parse(requestedRange.start)).toBeLessThanOrEqual(180 * 24 * 60 * 60 * 1000)

    coverage.resolve(missingCoverage)
    await flushPromises()
    expect(button.text()).toBe('Checking instrument…')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenNthCalledWith(1, '/instruments/acquire', {
      symbol: 'OIH', request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })

    identity.resolve(resolvedIdentity)
    await flushPromises()
    expect(button.text()).toBe('Loading missing history…')
    expect(api.post).toHaveBeenCalledTimes(2)
    const historyRequest = vi.mocked(api.post).mock.calls[1][1] as { start: string; end: string }
    expect(vi.mocked(api.post).mock.calls[1][0]).toBe('/instruments/43/history-acquisitions')
    expect(Date.parse(historyRequest.end) - Date.parse(historyRequest.start)).toBeLessThanOrEqual(180 * 24 * 60 * 60 * 1000)

    history.resolve(partialHistory)
    await flushPromises()
    expect(button.text()).toBe('Load missing history')
    expect(wrapper.text()).toContain('Some history loaded; 0 range(s) remain unavailable.')
    expect(wrapper.emitted('loaded')?.[0]?.[0]).toMatchObject({ status: 'partial', instrument_id: 43 })
  })

  it('does not resolve identity or call a source when local coverage is sufficient', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'ready', bar_count: 180, missing_slices: [] })
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('already available locally')
    expect(wrapper.text()).toContain('No source request was sent')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('does not resolve identity or acquire history when local coverage fails', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('coverage unavailable'))
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Local history could not be checked')
    expect(wrapper.text()).toContain('No source request was sent')
  })

  it('stops after a denied identity and retains the existing chart path', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(missingCoverage)
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'r', status: 'identity_conflict', instrument: null, source_outcomes: [] })
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(vi.mocked(api.post).mock.calls[0][0]).toBe('/instruments/acquire')
    expect(wrapper.text()).toContain('identity of OIH is conflicting')
    expect(wrapper.text()).toContain('No history was requested')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('rejects a resolved identity whose symbol does not match the selected chart', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(missingCoverage)
    vi.mocked(api.post).mockResolvedValueOnce({
      ...resolvedIdentity,
      instrument: { ...resolvedIdentity.instrument, symbol: 'SPY' },
    })
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('could not be verified')
    expect(wrapper.text()).toContain('No history was requested')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('rejects an unsafe canonical ID before history acquisition', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(missingCoverage)
    vi.mocked(api.post).mockResolvedValueOnce({
      ...resolvedIdentity,
      instrument: { ...resolvedIdentity.instrument, instrument_id: Number.MAX_SAFE_INTEGER + 1 },
    })
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('could not be verified')
    expect(vi.mocked(api.post).mock.calls.map(([path]) => path)).not.toContain('/instruments/9007199254740992/history-acquisitions')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('keeps current chart bars untouched for a held history result', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(missingCoverage)
    vi.mocked(api.post)
      .mockResolvedValueOnce(resolvedIdentity)
      .mockResolvedValueOnce({ ...partialHistory, status: 'held' })
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })

    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.get('[data-testid="history-load-missing"]').text()).toBe('Load missing history'))

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Your existing chart remains available')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('does not apply a late coverage result after the selected symbol changes', async () => {
    const coverage = deferred<typeof missingCoverage>()
    vi.mocked(api.get).mockReturnValueOnce(coverage.promise as never)
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })
    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await wrapper.setProps({ symbol: 'SPY' })
    coverage.resolve(missingCoverage)
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('OIH')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })

  it('does not apply a late identity result after the timeframe changes', async () => {
    const identity = deferred<typeof resolvedIdentity>()
    vi.mocked(api.get).mockResolvedValueOnce(missingCoverage)
    vi.mocked(api.post).mockReturnValueOnce(identity.promise as never)
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })
    await wrapper.get('[data-testid="history-load-missing"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="history-load-missing"]').text()).toBe('Checking instrument…')
    await wrapper.setProps({ timeframe: 'M5' })
    identity.resolve(resolvedIdentity)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('loaded')).toBeUndefined()
    expect(wrapper.get('[data-testid="history-load-missing"]').text()).toBe('Load missing history')
  })

  it('keeps custom ranges bounded and exposes a native keyboard-operable disclosure', async () => {
    const wrapper = mount(HistoryAcquisitionControl, {
      props: { symbol: 'OIH', timeframe: 'D1', adjusted: true },
    })
    const summary = wrapper.get('summary')
    expect(summary.attributes('tabindex')).toBeUndefined()
    expect(summary.element.tagName).toBe('SUMMARY')

    await wrapper.get('[aria-label="History start date"]').setValue('2025-01-01')
    await wrapper.get('[aria-label="History end date"]').setValue('2026-01-01')
    expect(wrapper.get('[data-testid="history-load-missing"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('at most 180 days')
    expect(api.get).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
  })
})
