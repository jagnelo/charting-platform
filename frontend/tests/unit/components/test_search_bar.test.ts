import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

describe('SearchBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.useFakeTimers()
  })

  it('shows recently viewed instruments on focus with empty query', async () => {
    const recentStore = useRecentInstrumentsStore()
    recentStore.add('NVDA', 'NVIDIA')

    const wrapper = mount(SearchBar, {
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
        },
      },
    })

    await wrapper.find('input').trigger('focus')
    expect(wrapper.text()).toContain('Recently viewed')
    expect(wrapper.text()).toContain('NVDA')
  })

  it('loads search results after debounce and emits selected symbol on click', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
    ])

    const wrapper = mount(SearchBar, {
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

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'AAPL' })
    expect(wrapper.text()).toContain('Apple Inc.')

    await wrapper.findAll('.result-item')[0].trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([
      'AAPL',
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
    ])
  })

  it('does not offer or emit a raw direct symbol when search returns no provider matches', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([])

    const wrapper = mount(SearchBar, {
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

    expect(api.get).toHaveBeenCalledWith('/instruments/search', { q: 'TSLA' })
    expect(wrapper.text()).not.toContain('Open chart for')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('can scope provider-backed results to specific instrument types', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', type: 'Equity' },
      { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', type: 'ETF' },
    ])

    const wrapper = mount(SearchBar, {
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
      types: 'ETF,Fund',
    })
    expect(wrapper.text()).toContain('SPDR S&P 500 ETF Trust')
    expect(wrapper.text()).not.toContain('Apple Inc.')
  })

  it('resolves expression queries and emits the resulting symbol on enter', async () => {
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ symbol: '=SPY-QQQ' })

    const wrapper = mount(SearchBar, {
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
    const wrapper = mount(SearchBar, {
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
    const wrapper = mount(SearchBar, {
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
