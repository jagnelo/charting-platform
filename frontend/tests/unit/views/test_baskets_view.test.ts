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

let pickerResults: Array<{ symbol: string; instrument_id: number; name: string }> = []

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
          props: ['modelValue', 'placeholder', 'readonly'],
          emits: ['select', 'update:modelValue'],
          template: `
            <button class="search-stub" type="button" :disabled="readonly" @click="selectNext()">
              Add instrument
            </button>
          `,
          methods: {
            selectNext() {
              const result = pickerResults.shift()
              if (result) this.$emit('select', result.symbol, result)
              else this.$emit('select', 'UNRESOLVED')
            },
          },
        },
      },
    },
  })
}

describe('BasketsView', () => {
  beforeEach(() => {
    pickerResults = [
      { symbol: 'AAPL', instrument_id: 101, name: 'Apple Inc.' },
      { symbol: 'MSFT', instrument_id: 202, name: 'Microsoft Corp.' },
      { symbol: 'NVDA', instrument_id: 303, name: 'NVIDIA Corp.' },
    ]
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.delete).mockReset()
    routerPush.mockReset()
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/baskets') return [] as never
      if (String(path).endsWith('/snapshots')) return [] as never
      return [] as never
    })
  })

  it('loads baskets and opens the first one', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])

    const wrapper = mountView()
    await flushPromises()

    expect(api.get).toHaveBeenCalledWith('/baskets')
    expect(wrapper.text()).toContain('Manual basket')
    expect(wrapper.text()).toContain('Apple Inc.')
  })

  it('freezes basket editing until initial and explicit reloads have settled', async () => {
    let releaseInitial: ((value: unknown) => void) | undefined
    let releaseRefresh: ((value: unknown) => void) | undefined
    let basketListCalls = 0
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path === '/baskets') {
        basketListCalls += 1
        return new Promise(resolve => {
          if (basketListCalls === 1) releaseInitial = resolve
          else releaseRefresh = resolve
        }) as never
      }
      return Promise.resolve([]) as never
    })

    const wrapper = mountView()
    await nextTick()
    expect(wrapper.get('input[placeholder="Basket name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.basket-new').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.search-stub').attributes('disabled')).toBeDefined()

    await vi.waitFor(() => expect(releaseInitial).toBeDefined())
    releaseInitial!([basket()])
    await vi.waitFor(() => expect(wrapper.text()).not.toContain('Loading baskets...'))
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Manual basket')
    expect(wrapper.get('input[placeholder="Basket name"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('button[title="Discard or save your edits before refreshing saved baskets."]').trigger('click')
    expect(wrapper.get('input[placeholder="Basket name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.basket-new').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.search-stub').attributes('disabled')).toBeDefined()

    await vi.waitFor(() => expect(releaseRefresh).toBeDefined())
    releaseRefresh!([basket({ name: 'Manual basket reloaded' })])
    await vi.waitFor(() => expect(wrapper.text()).not.toContain('Loading baskets...'))
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Manual basket reloaded')
    expect(wrapper.get('input[placeholder="Basket name"]').attributes('disabled')).toBeUndefined()
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
        { instrument_id: 101, weight: '0.5' },
        { instrument_id: 202, weight: '0.5' },
      ],
    })
  })

  it('creates a valid equal-weight basket from a canonical picker result', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockResolvedValue(basket({ id: 45, name: 'Equal basket' }))
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[placeholder="Basket name"]').setValue('Equal basket')
    await wrapper.get('.search-stub').trigger('click')
    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith('/baskets', {
      name: 'Equal basket', description: null, weighting_scheme: 'equal',
      members: [{ instrument_id: 101 }],
    })
  })

  it('preserves a new basket draft after create failure so the user can retry', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post)
      .mockRejectedValueOnce(new Error('Basket service unavailable'))
      .mockResolvedValueOnce(basket({ id: 46, name: 'Retry basket' }))
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[placeholder="Basket name"]').setValue('Retry basket')
    await wrapper.get('.search-stub').trigger('click')
    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Basket service unavailable')
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Retry basket')
    expect(wrapper.get('.member-symbol').text()).toBe('AAPL')
    expect(wrapper.get('h2').text()).toBe('New basket')

    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Basket saved.')
    expect(wrapper.get('.basket-card--active').text()).toContain('Retry basket')
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
    expect(wrapper.get('.basket-panel').classes()).toContain('basket-panel--readonly')
    expect(wrapper.get('.member-table').text()).toContain('AAPL')
    expect(wrapper.find('input[placeholder="Basket name"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.btn-danger').exists()).toBe(false)
  })

  it('opens the current basket immediately without a view-owned preparation barrier', async () => {
    vi.mocked(api.get).mockResolvedValue([basket({ id: 42 })])
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.member-symbol').trigger('click')
    expect(routerPush).toHaveBeenLastCalledWith('/chart/AAPL')
    routerPush.mockReset()

    await wrapper.get('[data-testid="basket-open-chart"]').trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/chart/BASKET%3A42')
    expect(wrapper.find('[data-testid="basket-chart-preparation-status"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="basket-open-available-chart"]').exists()).toBe(false)
  })

  it('keeps every basket row in the shared chart route when a source member is unresolved', async () => {
    vi.mocked(api.get).mockResolvedValue([basket({
      id: 44,
      is_system_managed: true,
      is_read_only: true,
      members: [{
        id: 88, instrument_id: null, symbol: 'UNRESOLVED', name: 'Reported constituent',
        source_holding_id: 501, position: 1, weight: '1.0', label: null, notes: null,
        metadata: { reason: 'identity_unverified' }, created_at: '2026-11-06', updated_at: '2026-11-06',
      }],
    })])
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-testid="basket-open-chart"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="basket-open-chart"]').trigger('click')

    expect(routerPush).toHaveBeenCalledWith('/chart/BASKET%3A44')
    expect(wrapper.text()).not.toContain('Preparing D1 history')
    expect(wrapper.text()).not.toContain('Open dashboard with available constituent history')
  })

  it('keeps the current selection when a user cancels a dirty basket switch, then discards explicitly', async () => {
    const first = basket({ id: 9 })
    const second = basket({ id: 10, name: 'Second basket', members: [{
      id: 2, instrument_id: 303, symbol: 'NVDA', name: 'NVIDIA Corp.', source_holding_id: null,
      position: 1, weight: null, label: null, notes: null, metadata: {}, created_at: '2026-01-01', updated_at: '2026-01-01',
    }] })
    vi.mocked(api.get).mockResolvedValue([first, second])

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('input[placeholder="Basket name"]').setValue('Unsaved first basket')
    await wrapper.findAll('button.basket-card')[1]!.trigger('click')
    ;(document.body.querySelector('[aria-labelledby="basket-discard-title"] .btn-secondary') as HTMLButtonElement).click()
    await flushPromises()
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Unsaved first basket')

    await wrapper.findAll('button.basket-card')[1]!.trigger('click')
    ;(document.body.querySelector('[data-testid="basket-confirm-discard"]') as HTMLButtonElement).click()
    await flushPromises()
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Second basket')
    expect(wrapper.text()).toContain('NVIDIA Corp.')
    expect(wrapper.text()).not.toContain('Apple Inc.')
  })

  it('keeps a dirty basket when New is cancelled and clears its members only after discard confirmation', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[placeholder="Basket name"]').setValue('Unsaved basket edit')
    await wrapper.get('.basket-new').trigger('click')
    expect(document.body.querySelector('[aria-labelledby="basket-discard-title"]')).not.toBeNull()
    ;(document.body.querySelector('[aria-labelledby="basket-discard-title"] .btn-secondary') as HTMLButtonElement).click()
    await flushPromises()

    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Unsaved basket edit')
    expect(wrapper.get('.member-symbol').text()).toBe('AAPL')

    await wrapper.get('.basket-new').trigger('click')
    ;(document.body.querySelector('[data-testid="basket-confirm-discard"]') as HTMLButtonElement).click()
    await flushPromises()

    expect(wrapper.get('h2').text()).toBe('New basket')
    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.findAll('.member-row')).toHaveLength(1)
    expect(wrapper.get('.member-row--head').exists()).toBe(true)
    expect(wrapper.find('.basket-card--active').exists()).toBe(false)
  })

  it('saves resolved picker IDs when adding and removing members from a saved basket', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])
    const saved = basket({
      name: 'Updated basket',
      members: [{
        id: 2, instrument_id: 202, symbol: 'MSFT', name: 'Microsoft Corp.', source_holding_id: null,
        position: 1, weight: null, label: null, notes: null, metadata: {}, created_at: '2026-01-01', updated_at: '2026-01-01',
      }],
    })
    vi.mocked(api.patch).mockResolvedValue(saved)

    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[aria-label="Remove AAPL"]').trigger('click')
    pickerResults = [{ symbol: 'MSFT', instrument_id: 202, name: 'Microsoft Corp.' }]
    await wrapper.get('.search-stub').trigger('click')
    await wrapper.get('input[placeholder="Basket name"]').setValue('Updated basket')
    await wrapper.get('.btn-primary').trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith('/baskets/9', {
      name: 'Updated basket', description: null, weighting_scheme: 'equal',
      members: [{ instrument_id: 202 }],
    })
  })

  it('does not add an unresolved recent symbol without a canonical instrument ID', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    pickerResults = []
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.search-stub').trigger('click')

    expect(wrapper.text()).toContain('Choose a resolved instrument from the search results')
    expect(wrapper.findAll('.member-row')).toHaveLength(1)
  })

  it('distinguishes canonical listings by ID even when their reported ticker text matches', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    pickerResults = [
      { symbol: 'ABC', instrument_id: 401, name: 'ABC common shares, XNYS' },
      { symbol: 'ABC', instrument_id: 402, name: 'ABC common shares, XNAS' },
    ]
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('input[placeholder="Basket name"]').setValue('Two listings')
    await wrapper.get('.search-stub').trigger('click')
    await wrapper.get('.search-stub').trigger('click')

    expect(wrapper.findAll('.member-row')).toHaveLength(3)
    expect(wrapper.text()).toContain('ABC common shares, XNYS')
    expect(wrapper.text()).toContain('ABC common shares, XNAS')
    expect(wrapper.text()).not.toContain('already in this basket')
  })

  it('preserves dated issuer provenance for read-only snapshot baskets', async () => {
    const sourceBasket = basket({
      id: 22,
      name: 'SPY holdings 2026-11-05',
      source_type: 'etf_holdings',
      source_snapshot_id: 801,
      composition_date: '2026-11-05',
      is_system_managed: true,
      is_read_only: true,
      latest_snapshot_date: '2026-11-05',
      metadata: {
        etf_symbol: 'SPY', source_provider: 'spdr', provenance: 'issuer_self_snapshotted_holdings',
        source_quality: 'verified', completeness_status: 'complete', source_identifier: 'SPDR:SPY:801',
        source_url: 'https://issuer.example/SPY.xlsx', source_artifact_hash: 'f'.repeat(64),
      },
    })
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === '/baskets') return [sourceBasket] as never
      if (path === '/baskets/22/snapshots') return [{
        id: 901, composition_date: '2026-11-05', known_at: '2026-11-06T10:00:00Z',
        source_type: 'etf_holdings', source_snapshot_id: 801, member_count: 1,
        metadata: { source_provider: 'spdr', provenance: 'issuer_self_snapshotted_holdings' },
      }] as never
      return [] as never
    })

    const wrapper = mountView()
    await flushPromises()
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledWith('/baskets/22/snapshots'))
    await vi.waitFor(() => expect(wrapper.get('[data-testid="basket-snapshot-history"]').text()).toContain('2026-11-06T10:00:00Z'))

    const summary = wrapper.get('[data-testid="basket-source-summary"]')
    expect(summary.text()).toContain('SPY')
    expect(summary.text()).toContain('spdr')
    expect(summary.text()).toContain('2026-11-05')
    expect(summary.text()).toContain('Latest stored snapshot')
    expect(summary.text()).toContain('Current eligibility is assessed separately in ETF Holdings')
    const sourceDetails = wrapper.get('[data-testid="basket-source-provenance"]')
    expect(sourceDetails.attributes('open')).toBeUndefined()
    expect(sourceDetails.find('summary').text()).toBe('Source details')
    expect(wrapper.findAll('.member-table, [data-testid="basket-source-provenance"]').map(item => item.element.tagName))
      .toEqual(['DIV', 'DETAILS'])
    expect(wrapper.get('[data-testid="basket-source-provenance"]').text()).toContain('2026-11-05')
    expect(wrapper.get('[data-testid="basket-source-provenance"]').text()).toContain('SPDR:SPY:801')
    expect(wrapper.get('[data-testid="basket-source-provenance"]').text()).toContain('issuer_self_snapshotted_holdings')
    expect(wrapper.get('[data-testid="basket-source-provenance"]').text()).toContain('f'.repeat(64))
    expect(wrapper.find('.btn-danger').exists()).toBe(false)
    expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('does not display late snapshot history after switching to another issuer basket', async () => {
    const first = basket({
      id: 11, name: 'First issuer basket', is_system_managed: true, is_read_only: true,
      source_snapshot_id: 101, composition_date: '2026-11-01',
    })
    const second = basket({
      id: 12, name: 'Second issuer basket', is_system_managed: true, is_read_only: true,
      source_snapshot_id: 102, composition_date: '2026-11-02',
    })
    let releaseFirst: ((value: unknown) => void) | undefined
    vi.mocked(api.get).mockImplementation((path: string) => {
      if (path === '/baskets') return Promise.resolve([first, second]) as never
      if (path === '/baskets/11/snapshots') {
        return new Promise(resolve => { releaseFirst = resolve }) as never
      }
      if (path === '/baskets/12/snapshots') {
        return Promise.resolve([{
          id: 202, composition_date: '2026-11-02', known_at: '2026-11-03T10:00:00Z',
          source_type: 'etf_holdings', source_snapshot_id: 102, member_count: 1,
          metadata: { source_provider: 'spdr', provenance: 'issuer_self_snapshotted_holdings' },
        }]) as never
      }
      return Promise.resolve([]) as never
    })
    const wrapper = mountView()
    await flushPromises()
    expect(releaseFirst).toBeTypeOf('function')

    await wrapper.findAll('button.basket-card')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="basket-snapshot-history"]').text()).toContain('2026-11-02')

    releaseFirst?.([{
      id: 101, composition_date: '2026-11-01', known_at: '2026-11-02T10:00:00Z',
      source_type: 'etf_holdings', source_snapshot_id: 101, member_count: 1,
      metadata: { source_provider: 'ishares', provenance: 'issuer_self_snapshotted_holdings' },
    }])
    await flushPromises()
    expect(wrapper.get('[data-testid="basket-snapshot-history"]').text()).toContain('2026-11-02')
    expect(wrapper.get('[data-testid="basket-snapshot-history"]').text()).not.toContain('2026-11-01')
  })

  it('routes using the latest selected basket and leaves member readiness to the shared chart loader', async () => {
    vi.mocked(api.get).mockResolvedValue([
      basket({ id: 42 }),
      basket({ id: 43, name: 'Next basket', members: [{
        id: 2, instrument_id: 303, symbol: 'NVDA', name: 'NVIDIA Corp.', source_holding_id: null,
        position: 1, weight: null, label: null, notes: null, metadata: {}, created_at: '2026-01-01', updated_at: '2026-01-01',
      }] }),
    ])
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('button.basket-card')[1]!.trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="basket-open-chart"]').trigger('click')

    expect((wrapper.get('input[placeholder="Basket name"]').element as HTMLInputElement).value)
      .toBe('Next basket')
    expect(routerPush).toHaveBeenCalledWith('/chart/BASKET%3A43')
  })

  it('cancels delete without mutation, then deletes only after confirmation', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])
    vi.mocked(api.delete).mockResolvedValue(undefined)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.btn-danger').trigger('click')
    ;(document.body.querySelector('[aria-labelledby="basket-delete-title"] .btn-secondary') as HTMLButtonElement).click()
    await flushPromises()
    expect(api.delete).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Manual basket')

    await wrapper.get('.btn-danger').trigger('click')
    ;(document.body.querySelector('[aria-labelledby="basket-delete-title"] .btn-danger') as HTMLButtonElement).click()
    await flushPromises()
    expect(api.delete).toHaveBeenCalledWith('/baskets/9')
    expect(wrapper.text()).toContain('Basket deleted.')
    expect(wrapper.text()).toContain('New basket')
  })

  it('keeps the selected basket available after delete failure and allows a retry', async () => {
    vi.mocked(api.get).mockResolvedValue([basket()])
    vi.mocked(api.delete)
      .mockRejectedValueOnce(new Error('Basket service unavailable'))
      .mockResolvedValueOnce(undefined)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('.btn-danger').trigger('click')
    ;(document.body.querySelector('[aria-labelledby="basket-delete-title"] .btn-danger') as HTMLButtonElement).click()
    await flushPromises()

    expect(api.delete).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Basket service unavailable')
    expect(wrapper.get('.basket-card--active').text()).toContain('Manual basket')
    expect(wrapper.get('.member-symbol').text()).toBe('AAPL')
    expect(document.body.querySelector('[aria-labelledby="basket-delete-title"]')).toBeNull()

    await wrapper.get('.btn-danger').trigger('click')
    ;(document.body.querySelector('[aria-labelledby="basket-delete-title"] .btn-danger') as HTMLButtonElement).click()
    await flushPromises()

    expect(api.delete).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Basket deleted.')
    expect(wrapper.get('h2').text()).toBe('New basket')
  })

  it('does not publish a late basket reload after the view unmounts', async () => {
    let resolveBaskets: ((loaded: ReturnType<typeof basket>[]) => void) | undefined
    vi.mocked(api.get).mockReturnValueOnce(new Promise(resolve => {
      resolveBaskets = resolve
    }) as never)

    const wrapper = mountView()
    wrapper.unmount()
    resolveBaskets?.([basket()])
    await flushPromises()

    expect(api.get).toHaveBeenCalledTimes(1)
  })
})
