import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import CoverageSummaryTool from '@/components/workstation/CoverageSummaryTool.vue'

describe('CoverageSummaryTool', () => {
  beforeEach(() => apiGet.mockReset())
  function mountTool(options: Record<string, any>) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    return mount(CoverageSummaryTool, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
  }

  it('checks a canonical OHLCV range and renders status plus missing slices', async () => {
    apiGet.mockImplementation(async (path?: string) => {
      if (path?.endsWith('/ohlcv')) {
        return {
          status: 'partial',
          covered_start: '2025-01-02T00:00:00Z',
          covered_end: '2025-12-31T00:00:00Z',
          bar_count: 248,
          missing_slices: [{ start: '2025-03-10T00:00:00Z', end: '2025-03-11T00:00:00Z' }],
          explanation: 'One internal gap was found in the requested range.',
          lineage: { provider_bar_count: 240, derived_bar_count: 8, unknown_bar_count: 0, source_lineage: 'provider_and_derived', source_timeframes: ['D1'] },
          adjustment_provenance: { mode: 'split_adjusted', factor_status: 'mixed_provider_native_opaque_and_inherited_from_canonical_d1', factor_version: null, factor_observation_count: 3, factor_rebuildable_observation_count: 2, factor_opaque_observation_count: 1, factor_kinds: ['provider_supplied', 'split_ratio'] },
          observed_cadence: { status: 'observed_cadence', sample_count: 2, median_interval_days: 4.5, min_interval_days: 1, max_interval_days: 8, semantics: 'diagnostic_of_returned_bar_timestamps_only' },
          storage_evidence: { status: 'reconciled', provider_bar_count: 240, observation_count: 240, matched_observation_count: 240, missing_observation_count: 0, mismatched_observation_count: 0, orphan_observation_count: 0 },
        }
      }
      return {
        local_coverage: { D1: { oldest: '2024-01-01T00:00:00Z', newest: '2025-12-31T00:00:00Z', bar_count: 500 } },
        dataset_states: [{ dataset_type: 'ohlcv', dataset_key: 'D1', status: 'fresh' }],
      }
    })
    const wrapper = mountTool({ props: { symbol: 'SPY' } })

    expect(wrapper.find('[role="region"][aria-label="SPY coverage"]').exists()).toBe(true)
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/coverage/instruments/SPY'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('Canonical instrument'))
    await wrapper.get('[aria-label="Coverage start date"]').setValue('2025-01-01')
    await wrapper.get('[aria-label="Coverage end date"]').setValue('2025-12-31')
    await wrapper.get('[aria-label="Coverage timeframe"]').setValue('D1')
    await wrapper.get('[aria-label="Coverage mode"]').setValue('historical')
    await wrapper.get('[aria-label="Check OHLCV range"]').trigger('click')

    await vi.waitFor(() => expect(wrapper.text()).toContain('One internal gap was found'))
    expect(apiGet).toHaveBeenCalledWith('/coverage/instruments/SPY/ohlcv', {
      timeframe: 'D1',
      start: '2025-01-01T00:00:00.000Z',
      end: '2025-12-31T23:59:59.999Z',
      mode: 'historical',
      adjusted: true,
    })
    expect(wrapper.text()).toContain('partial')
    expect(wrapper.text()).toContain('Missing slices (1)')
    expect(wrapper.text()).toContain('3/10/2025')
    expect(wrapper.find('.coverage-summary__assessment[role="status"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.find('.coverage-summary__assessment[role="status"]').text()).toContain('provider and derived')
    expect(wrapper.find('.coverage-summary__assessment[role="status"] .sr-only').text()).toContain('factor status mixed provider native opaque and inherited from canonical d1')
    expect(wrapper.find('.coverage-summary__assessment[role="status"] .sr-only').text()).toContain('Storage evidence reconciled: 240 matched, 0 missing, 0 mismatched, 0 orphan observations.')
    expect(wrapper.find('.coverage-summary__assessment[role="status"] .sr-only').text()).toContain('Observed cadence measured · 2 intervals · median 4.50d · min 1d · max 8d. This is diagnostic of returned bar timestamps only.')
    expect(wrapper.find('.coverage-summary__assessment[role="status"] .sr-only').text()).toContain('Adjustment inputs 3 observed; 2 rebuildable, 1 opaque (provider_supplied, split_ratio). This is input audit evidence, not proof that prices were recalculated locally.')
  })

  it('prevents reversed ranges and persists serializable controls', async () => {
    apiGet.mockResolvedValue({ local_coverage: {}, dataset_states: [] })
    const wrapper = mountTool({ props: { symbol: 'XLK', configuration: { coverage_timeframe: 'W1' } } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Canonical instrument'))
    await wrapper.get('[aria-label="Coverage start date"]').setValue('2026-02-01')
    await wrapper.get('[aria-label="Coverage end date"]').setValue('2026-01-01')
    expect(wrapper.text()).toContain('The end date must be on or after the start date.')
    expect(wrapper.get('[aria-label="Check OHLCV range"]').element).toHaveProperty('disabled', true)
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ coverage_timeframe: 'W1', coverage_start: '2026-02-01', coverage_end: '2026-01-01', coverage_mode: 'historical', coverage_adjusted: true }))
    expect(apiGet).not.toHaveBeenCalledWith('/coverage/instruments/XLK/ohlcv', expect.anything())
  })

  it('keeps stale and failed dataset states visible instead of hiding freshness limits', async () => {
    apiGet.mockResolvedValue({
      local_coverage: { D1: { oldest: '2024-01-01T00:00:00Z', newest: '2025-12-31T00:00:00Z', bar_count: 500 } },
      dataset_states: [
        { dataset_type: 'ohlcv', dataset_key: 'D1', status: 'stale' },
        { dataset_type: 'corporate_actions', dataset_key: '', status: 'failed' },
      ],
    })
    const wrapper = mountTool({ props: { symbol: 'SPY' } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('ohlcv · D1: stale'))
    expect(wrapper.text()).toContain('corporate_actions: failed')
    expect(wrapper.find('.coverage-summary__dataset--stale').exists()).toBe(true)
    expect(wrapper.find('.coverage-summary__dataset--failed').exists()).toBe(true)
    expect(wrapper.find('[role="region"][aria-label="SPY coverage"]').attributes('aria-busy')).toBe('false')
  })

  it('deduplicates canonical coverage hydration across linked windows', async () => {
    apiGet.mockResolvedValue({ local_coverage: {}, dataset_states: [] })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const first = mount(CoverageSummaryTool, { props: { symbol: 'SPY' }, global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
    const second = mount(CoverageSummaryTool, { props: { symbol: 'SPY' }, global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
    await vi.waitFor(() => expect(first.text()).toContain('Canonical instrument'))
    await vi.waitFor(() => expect(second.text()).toContain('Canonical instrument'))
    expect(apiGet).toHaveBeenCalledTimes(1)
  })
})
