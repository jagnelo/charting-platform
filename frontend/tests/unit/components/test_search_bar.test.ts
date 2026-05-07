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

    await wrapper.find('.result-item').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['AAPL'])
  })

  it('shows a direct-open row immediately for ticker input', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    )

    const wrapper = mount(SearchBar, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await wrapper.find('input').setValue('TSLA')
    await nextTick()

    expect(wrapper.text()).toContain('Open chart for')
    expect(wrapper.text()).toContain('TSLA')

    await wrapper.find('.result-item--direct').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['TSLA'])
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
    expect(wrapper.emitted('select')?.[0]).toEqual(['=SPY-QQQ'])
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
})
