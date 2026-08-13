import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

import SettingsView from '@/views/SettingsView.vue'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
  await nextTick()
}

const providerPolicies = [
  {
    provider: 'yfinance',
    capability: 'fetch_option_chain',
    supported_capabilities: ['fetch_option_chain', 'search_instruments'],
    is_enabled: true,
    is_pinned: false,
    auto_weight_enabled: true,
    base_priority: 10,
    effective_score: 0.95,
    learned_weight: 1,
    max_concurrency: 4,
    tokens_per_minute: 120,
    burst_capacity: 20,
    cooldown_seconds: 30,
    freshness_seconds: 300,
    failure_streak: 0,
    last_success_at: '2026-04-30T10:00:00Z',
    last_failure_at: null,
    circuit_open_until: null,
    ewma_latency_ms: 1050,
    ewma_success_rate: 0.98,
    ewma_completeness: 0.99,
    ewma_freshness: 0.97,
    ewma_consistency: 0.96,
    last_error_type: null,
    last_error_message: null,
  },
  {
    provider: 'yfinance',
    capability: 'search_instruments',
    supported_capabilities: ['fetch_option_chain', 'search_instruments'],
    is_enabled: true,
    is_pinned: true,
    auto_weight_enabled: false,
    base_priority: 20,
    effective_score: 0.81,
    learned_weight: 1,
    max_concurrency: 4,
    tokens_per_minute: 120,
    burst_capacity: 20,
    cooldown_seconds: 30,
    freshness_seconds: 120,
    failure_streak: 1,
    last_success_at: '2026-04-29T10:00:00Z',
    last_failure_at: '2026-04-30T08:00:00Z',
    circuit_open_until: null,
    ewma_latency_ms: 875,
    ewma_success_rate: 0.9,
    ewma_completeness: 0.93,
    ewma_freshness: 0.91,
    ewma_consistency: 0.92,
    last_error_type: 'TimeoutError',
    last_error_message: 'Provider timed out',
  },
]

const providerUsage = [
  {
    provider: 'yfinance',
    base_url: 'https://finance.yahoo.com',
    description: 'Yahoo market data',
    usage_mode: 'call_count',
    usage_unit_label: 'requests',
    limit_kind: 'unknown',
    quota_limit: null,
    estimated_quota_limit: null,
    quota_window_seconds: null,
    current_window_started_at: null,
    current_window_ends_at: null,
    current_window_requests: null,
    current_window_units: null,
    current_window_utilization_pct: null,
    retained_requests: 233,
    retained_units: 233,
    requests_24h: 26,
    units_24h: 26,
    requests_7d: 233,
    units_7d: 233,
    success_rate_24h: 100,
    failure_rate_24h: 0,
    timeout_rate_24h: 0,
    avg_latency_ms_24h: 1050,
    p95_latency_ms_24h: 3389,
    last_request_at: '2026-04-30T10:15:00Z',
    last_success_at: '2026-04-30T10:15:00Z',
    last_failure_at: null,
    top_operations: [
      { operation_family: 'fetch_option_chain', requests: 62, units: 62, failures: 0, successes: 62 },
      { operation_family: 'search_instruments', requests: 26, units: 26, failures: 0, successes: 26 },
    ],
    capability_breakdown: [
      { capability: 'option_chain', requests: 62, units: 62, failures: 0 },
    ],
    error_breakdown: [],
    hourly_buckets: Array.from({ length: 24 }, (_, index) => ({
      bucket_start: `2026-04-30T${String(index).padStart(2, '0')}:00:00Z`,
      requests: index === 23 ? 26 : 1,
      units: index === 23 ? 26 : 1,
      failures: 0,
    })),
    daily_buckets: Array.from({ length: 7 }, (_, index) => ({
      bucket_start: `2026-04-${String(index + 24).padStart(2, '0')}T00:00:00Z`,
      requests: index === 4 ? 160 : 18,
      units: index === 4 ? 160 : 18,
      failures: 0,
    })),
  },
]

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/presets') return Promise.resolve([])
      if (path === '/providers/policies') return Promise.resolve(providerPolicies)
      if (path === '/providers/usage') return Promise.resolve(providerUsage)
      if (path.startsWith('/providers/reconciliation/issues')) return Promise.resolve([])
      return Promise.resolve([])
    })
  })

  it('keeps usage details collapsed by default and removes duplicate request units', async () => {
    const wrapper = mount(SettingsView, {
      global: {
        plugins: [createPinia()],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Show usage')
    expect(wrapper.text()).not.toContain('Top operations')
    expect(wrapper.text()).not.toContain('26 requests')

    await wrapper.findAll('.provider-toggle')[0].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Top operations')
    expect(wrapper.text()).toContain('Fetch Option Chain')
    expect(wrapper.text()).toContain('62 calls')
    expect(wrapper.text()).not.toContain('62 requests')
  })

  it('keeps capability controls inside a collapsed configuration pane', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'admin', email: 'admin@example.com', is_admin: true }
    const wrapper = mount(SettingsView, {
      global: {
        plugins: [pinia],
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Show config')
    expect(wrapper.text()).not.toContain('Tokens / min')

    await wrapper.findAll('.provider-toggle')[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Capability configuration')
    expect(wrapper.text()).toContain('Tokens / min')
    expect(wrapper.text()).toContain('Fetch Option Chain')
    expect(wrapper.text()).toContain('Search Instruments')
  })

  it('does not expose provider configuration controls to regular users', async () => {
    const wrapper = mount(SettingsView, {
      global: { plugins: [createPinia()] },
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('Show config')
    expect(wrapper.text()).not.toContain('Capability configuration')
  })

  it('shows the reconciliation queue only to admins and attributes review actions', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { id: 7, username: 'admin', email: 'admin@example.com', is_admin: true }
    const issue = {
      id: 19,
      provider: 'edgar',
      provider_symbol: 'ABC',
      issue_type: 'ambiguous_ticker_issuer',
      status: 'open' as const,
      candidates: [{ name: 'ABC Holdings', cik: '1', exchange: 'NASDAQ' }],
      payload: { symbol: 'ABC' },
      observed_at: '2026-08-11T12:00:00Z',
      resolved_at: null,
      resolution: null,
    }
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/presets') return Promise.resolve([])
      if (path === '/providers/policies') return Promise.resolve(providerPolicies)
      if (path === '/providers/usage') return Promise.resolve(providerUsage)
      if (path.startsWith('/providers/reconciliation/issues')) return Promise.resolve([issue])
      return Promise.resolve([])
    })
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ ok: true })

    const wrapper = mount(SettingsView, {
      global: { plugins: [pinia] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Identity reconciliation review')
    expect(wrapper.text()).toContain('ABC Holdings')
    const resolveButton = wrapper.findAll('button').find((button) => button.text() === 'Mark resolved')
    expect(resolveButton).toBeDefined()
    await resolveButton!.trigger('click')
    expect(api.patch).toHaveBeenCalledWith(
      '/providers/reconciliation/issues/19',
      expect.objectContaining({ status: 'resolved' }),
    )
  })
})
