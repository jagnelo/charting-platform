import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import BasketsView from '@/views/BasketsView.vue'

const routerPush = vi.fn()

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

import { api } from '@/lib/api'

let pickerSymbols: string[] = []

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

function basket(overrides: Record<string, unknown> = {}) {
  return {
    id: 9,
    user_id: 1,
    name: 'Manual basket',
    description: null,
    source_type: 'manual',
    weighting_scheme: 'equal',
    rebalance_frequency: null,
    classification_mode: 'custom',
    sector: null,
    industry: null,
    source_etf_profile_id: null,
    source_snapshot_id: null,
    composition_date: null,
    is_system_managed: false,
    is_read_only: false,
    metadata: {},
    members: [
      {
        id: 1,
        instrument_id: 101,
        symbol: 'AAPL',
        name: 'Apple Inc.',
        source_holding_id: null,
        position: 1,
        weight: null,
        label: null,
        notes: null,
        metadata: {},
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function mountView() {
  return mount(BasketsView, {
    global: {
      stubs: {
        SearchBar: {
          props: ['modelValue', 'placeholder'],
          emits: ['select', 'update:modelValue'],
          template: `
            <button class="search-stub" type="button" @click="$emit('select', nextSymbol())">
              Add instrument
            </button>
          `,
          methods: {
            nextSymbol() {
              return pickerSymbols.shift() ?? 'AAPL'
            },
          },
        },
      },
    },
  })
}

describe('BasketsView', () => {
  beforeEach(() => {
    pickerSymbols = ['AAPL', 'MSFT', 'NVDA']
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.delete).mockReset()
    routerPush.mockReset()
  })

  it('loads baskets and opens the first one', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])

    const wrapper = mountView()
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/baskets')
    expect(wrapper.text()).toContain('Manual basket')
    expect(wrapper.text()).toContain('Apple Inc.')
  })

  it('creates a custom weighted basket from picker-selected symbols', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockResolvedValue(basket({
      id: 44,
      name: 'Mega cap pair',
      weighting_scheme: 'custom',
      members: [],
    }))

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('input[placeholder="Basket name"]').setValue('Mega cap pair')
    await wrapper.find('select').setValue('custom')
    await wrapper.find('.search-stub').trigger('click')
    await wrapper.find('.search-stub').trigger('click')

    const weights = wrapper.findAll('input.weight-input')
    await weights[0].setValue('50')
    await weights[1].setValue('50')

    await wrapper.find('.btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/baskets', {
      name: 'Mega cap pair',
      description: null,
      weighting_scheme: 'custom',
      members: [
        { symbol: 'AAPL', weight: '0.5' },
        { symbol: 'MSFT', weight: '0.5' },
      ],
    })
  })

  it('keeps custom weighted baskets disabled until fully allocated', async () => {
    vi.mocked(api.get).mockResolvedValue([])

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('input[placeholder="Basket name"]').setValue('Under allocated')
    await wrapper.find('select').setValue('custom')
    await wrapper.find('.search-stub').trigger('click')
    await wrapper.find('input.weight-input').setValue('50')

    expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('locks ETF-derived baskets as read-only', async () => {
    vi.mocked(api.get).mockResolvedValue([
      basket({
        id: 22,
        name: 'SPY holdings',
        source_type: 'etf_holdings',
        is_system_managed: true,
        is_read_only: true,
      }),
    ])

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Read-only basket materialized from an ETF holdings snapshot.')
    expect(wrapper.find('input[placeholder="Basket name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.btn-danger').exists()).toBe(false)
  })

  it('opens a selected basket as a synthetic chart token', async () => {
    vi.mocked(api.get).mockResolvedValue([basket({ id: 42 })])

    const wrapper = mountView()
    await flushPromises()

    await wrapper.find('.btn-secondary').trigger('click')

    expect(routerPush).toHaveBeenCalledWith('/chart/BASKET%3A42')
  })
})
