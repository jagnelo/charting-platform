import { mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import OptionsChainPanel from '@/components/options/OptionsChainPanel.vue'

describe('OptionsChainPanel', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('handles empty option responses without available expirations', async () => {
    vi.mocked(api.get).mockResolvedValue({
      symbol: 'CSCOII',
      expiration: null,
      snapshot: null,
      rows: [],
    } as any)

    const wrapper = mount(OptionsChainPanel, {
      props: { symbol: 'CSCOII' },
    })

    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('No options available')
  })

  it('renders straddle rows and can switch to list mode', async () => {
    vi.mocked(api.get).mockResolvedValue({
      symbol: 'NVDA',
      expiration: '2026-06-19',
      available_expirations: ['2026-06-19'],
      snapshot: null,
      rows: [
        { instrument_id: 1, symbol: 'NVDA C', right: 'call', strike: 100, expiry_date: '2026-06-19', bid: 2, ask: 2.2, open_interest: 10, implied_vol: 0.3 },
        { instrument_id: 2, symbol: 'NVDA P', right: 'put', strike: 100, expiry_date: '2026-06-19', bid: 1.8, ask: 2.1, open_interest: 11, implied_vol: 0.31 },
      ],
    } as any)

    const wrapper = mount(OptionsChainPanel, {
      props: { symbol: 'NVDA' },
    })

    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Straddle')
    expect(wrapper.find('.options-table--straddle').exists()).toBe(true)

    await wrapper.findAll('.view-btn')[1].trigger('click')

    expect(wrapper.find('.options-table--straddle').exists()).toBe(false)
    expect(wrapper.find('.options-table').exists()).toBe(true)
  })
})
