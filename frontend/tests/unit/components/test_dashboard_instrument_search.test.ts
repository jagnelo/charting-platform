import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

describe('DashboardInstrumentSearch', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
  })

  it('searches instruments after debounce and emits selected result', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([
        { symbol: 'NVDA', name: 'NVIDIA Corp', exchange: 'NASDAQ', type: 'Equity' },
      ])
      .mockResolvedValueOnce({ symbol: 'NVDA' })

    const wrapper = mount(DashboardInstrumentSearch, {
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

    const wrapper = mount(DashboardInstrumentSearch, {
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

  it('does not resolve incomplete expressions or emit draft updates while typing', async () => {
    const wrapper = mount(DashboardInstrumentSearch, {
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

    const wrapper = mount(DashboardInstrumentSearch, {
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
