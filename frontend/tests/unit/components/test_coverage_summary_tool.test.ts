import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import CoverageSummaryTool from '@/components/workstation/CoverageSummaryTool.vue'

describe('CoverageSummaryTool', () => {
  it('checks a canonical OHLCV range and renders status plus missing slices', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path.endsWith('/ohlcv')) {
        return {
          status: 'partial',
          covered_start: '2025-01-02T00:00:00Z',
          covered_end: '2025-12-31T00:00:00Z',
          bar_count: 248,
          missing_slices: [{ start: '2025-03-10T00:00:00Z', end: '2025-03-11T00:00:00Z' }],
          explanation: 'One internal gap was found in the requested range.',
        }
      }
      return {
        local_coverage: { D1: { oldest: '2024-01-01T00:00:00Z', newest: '2025-12-31T00:00:00Z', bar_count: 500 } },
        dataset_states: [{ dataset_type: 'ohlcv', dataset_key: 'D1', status: 'fresh' }],
      }
    })
    const wrapper = mount(CoverageSummaryTool, { props: { symbol: 'SPY' } })

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
  })

  it('prevents reversed ranges and persists serializable controls', async () => {
    apiGet.mockResolvedValue({ local_coverage: {}, dataset_states: [] })
    const wrapper = mount(CoverageSummaryTool, { props: { symbol: 'XLK', configuration: { coverage_timeframe: 'W1' } } })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Canonical instrument'))
    await wrapper.get('[aria-label="Coverage start date"]').setValue('2026-02-01')
    await wrapper.get('[aria-label="Coverage end date"]').setValue('2026-01-01')
    expect(wrapper.text()).toContain('The end date must be on or after the start date.')
    expect(wrapper.get('[aria-label="Check OHLCV range"]').element).toHaveProperty('disabled', true)
    expect(wrapper.emitted('configuration')?.at(-1)?.[0]).toEqual(expect.objectContaining({ coverage_timeframe: 'W1', coverage_start: '2026-02-01', coverage_end: '2026-01-01', coverage_mode: 'historical', coverage_adjusted: true }))
    expect(apiGet).not.toHaveBeenCalledWith('/coverage/instruments/XLK/ohlcv', expect.anything())
  })
})
