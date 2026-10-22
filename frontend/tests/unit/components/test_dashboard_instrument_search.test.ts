import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import DashboardInstrumentSearch from '@/components/dashboard/DashboardInstrumentSearch.vue'

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

const mountedDashboardSearches: Array<{ unmount: () => void }> = []

function mountDashboardSearch(options: any = {}) {
  const wrapper = mount(DashboardInstrumentSearch, options)
  mountedDashboardSearches.push(wrapper)
  return wrapper
}

describe('DashboardInstrumentSearch', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    for (const wrapper of mountedDashboardSearches.splice(0)) wrapper.unmount()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('searches instruments after debounce and emits selected result', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([
        { symbol: 'NVDA', name: 'NVIDIA Corp', exchange: 'NASDAQ', type: 'Equity' },
      ])
      .mockResolvedValueOnce({ symbol: 'NVDA' })

    const wrapper = mountDashboardSearch({
      props: { modelValue: '' },
      attachTo: document.body,
    })

    await wrapper.find('input').setValue('NVDA')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await nextTick()

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'NVDA' })
    expect(document.body.textContent).toContain('NVIDIA Corp')

    const button = document.body.querySelector('.dash-search-item') as HTMLButtonElement
    button.click()
    await flushPromises()
    await nextTick()

    expect(wrapper.emitted('select')?.[0]).toEqual(['NVDA'])
  })

  it('does not emit a symbol when provider search returns no results', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const wrapper = mountDashboardSearch({
      props: { modelValue: '' },
      attachTo: document.body,
    })

    await wrapper.find('input').setValue('mcd')
    vi.advanceTimersByTime(230)
    await flushPromises()
    await nextTick()

    await wrapper.find('input').trigger('keydown.enter')
    await flushPromises()
    await nextTick()

    expect(document.body.querySelectorAll('.dash-search-item').length).toBe(0)
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('does not publish a late search response after the widget unmounts', async () => {
    let resolveResults!: (results: any[]) => void
    const resultsLoaded = new Promise<any[]>(resolve => { resolveResults = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(resultsLoaded)
    const wrapper = mountDashboardSearch({
      props: { modelValue: '' },
      attachTo: document.body,
    })

    await wrapper.find('input').setValue('NVDA')
    vi.advanceTimersByTime(230)
    await Promise.resolve()
    const vm = wrapper.vm as unknown as { results: any[]; loading: boolean }
    wrapper.unmount()
    mountedDashboardSearches.splice(mountedDashboardSearches.indexOf(wrapper), 1)
    resolveResults([{ symbol: 'NVDA', name: 'NVIDIA Corp', exchange: 'NASDAQ', type: 'Equity' }])
    await flushPromises()

    expect(vm.results).toEqual([])
    expect(vm.loading).toBe(true)
  })

  it('does not resolve incomplete expressions or emit draft updates while typing', async () => {
    const wrapper = mountDashboardSearch({
      props: { modelValue: '' },
      attachTo: document.body,
    })

    const input = wrapper.find('input')
    await input.setValue('=')
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(api.post).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Finish the expression to continue.')

    await input.trigger('keydown.enter')
    await flushPromises()

    expect(api.post).not.toHaveBeenCalled()
  })

  it('resolves expressions and surfaces lookup errors', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('API POST /instruments/resolve-expression → 404: {"detail":"Constituent instrument \'QQQX\' not found"}')
    )

    const wrapper = mountDashboardSearch({
      props: { modelValue: '' },
      attachTo: document.body,
    })

    const input = wrapper.find('input')
    await input.setValue('=SPY-QQQ')
    await input.trigger('keydown.enter')
    await flushPromises()
    await nextTick()

    expect(api.post).toHaveBeenCalledWith('/instruments/resolve-expression', {
      expression: '=SPY-QQQ',
    })
    expect(document.body.textContent).toContain('Could not resolve =SPY-QQQ')
  })
})
