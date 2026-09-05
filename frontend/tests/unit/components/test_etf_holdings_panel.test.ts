import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ETFHoldingsPanel from '@/components/etf/ETFHoldingsPanel.vue'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
  },
}))

const snapshot = {
  id: 1,
  etf_profile_id: 1,
  etf_instrument_id: 10,
  etf_symbol: 'SPY',
  etf_name: 'SPDR S&P 500 ETF Trust',
  composition_date: '2026-05-31',
  known_at: '2026-06-01T04:00:00Z',
  provenance: 'issuer_current_holdings',
  source_provider: 'issuer-test',
  source_quality: 'issuer_current',
  completeness_status: 'complete',
  row_count: 2,
  resolved_count: 1,
  unresolved_count: 1,
  total_weight: '0.10000000',
  parser_version: 'test-v1',
  holdings: [
    {
      id: 1,
      snapshot_id: 1,
      constituent_instrument_id: 100,
      constituent_symbol: 'HOLDING-LEGACY123',
      constituent_name: 'Apple Inc.',
      position: 1,
      reported_symbol: 'AAPL',
      reported_name: 'Apple Inc.',
      weight: '0.07000000',
      shares: '100',
      market_value: '19000',
      currency: 'USD',
      country: 'US',
      exchange: 'NASDAQ',
      cusip: '037833100',
      isin: 'US0378331005',
      resolution_confidence: '0.97000000',
      holding_type: 'equity',
      row_type: 'security',
      is_resolved: true,
    },
    {
      id: 2,
      snapshot_id: 1,
      constituent_instrument_id: null,
      constituent_symbol: null,
      constituent_name: null,
      position: 2,
      reported_symbol: null,
      reported_name: 'US Dollar',
      weight: '0.03000000',
      holding_type: 'cash',
      row_type: 'cash',
      is_resolved: false,
      resolution_note: 'Non-security row was preserved without instrument materialization.',
    },
  ],
}

describe('ETFHoldingsPanel', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('renders latest holdings and emits selected constituent symbols', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce({
        availability: 'current',
        source_tier: 'issuer_native',
        usable_for_current_analysis: true,
        displayable_last_known: true,
        consecutive_failures: 0,
        reason: 'A complete holdings snapshot passed the latest adapter check.',
      })
    const wrapper = mount(ETFHoldingsPanel, {
      props: { symbol: 'SPY' },
    })

  await vi.waitFor(() => {
    expect(wrapper.text()).toContain('Holdings')
    expect(wrapper.text()).toContain('AAPL')
  })

  expect(wrapper.text()).not.toContain('HOLDING-LEGACY123')

  expect(wrapper.text()).toContain('issuer-test')
  expect(wrapper.text()).toContain('1/2 ready')
  expect(wrapper.text()).toContain('10.00%')
  expect(wrapper.text()).toContain('Selected holding')
  expect(wrapper.text()).toContain('USD 19,000')
  expect(wrapper.text()).toContain('NASDAQ · US')
  expect(wrapper.text()).toContain('ready')

  await wrapper.find('.open-holding-button').trigger('click')
  expect(wrapper.emitted('openSymbol')?.[0]).toEqual(['AAPL'])

  await wrapper.find('.nav-button:nth-child(2)').trigger('click')
  expect(wrapper.text()).toContain('US Dollar')
  expect(wrapper.text()).toContain('reference')
  expect(wrapper.find('.open-holding-button').attributes('disabled')).toBeDefined()
  expect(wrapper.emitted('availability')?.at(-1)).toEqual([true])
})

  it('stays hidden when holdings are unavailable', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('404'))
    const wrapper = mount(ETFHoldingsPanel, {
      props: { symbol: 'ABC' },
    })

    await vi.waitFor(() => {
      expect(wrapper.emitted('availability')?.at(-1)).toEqual([false])
    })

    expect(wrapper.html()).toBe('<!--v-if-->')
  })

  it('shows last-known holdings without advertising current usability when capability is degraded', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce({
        availability: 'degraded',
        source_tier: 'sec_filing',
        usable_for_current_analysis: false,
        displayable_last_known: true,
        composition_date: snapshot.composition_date,
        consecutive_failures: 1,
        reason: 'Holdings are reconstructed from SEC filings and are not issuer-current support.',
      })

    const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'SPY' } })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('degraded')
      expect(wrapper.text()).toContain('not issuer-current support')
    })

    expect(wrapper.emitted('availability')?.at(-1)).toEqual([false])
    expect(wrapper.text()).toContain('A last-known snapshot may be displayed')
  })

  it.each(['stale', 'unavailable', 'not_applicable', 'unknown'])(
    'keeps a %s no-snapshot capability visible and provider-attributed',
    async availability => {
      vi.mocked(api.get)
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce({
          availability,
          source_provider: 'wisdomtree',
          source_tier: 'none',
          usable_for_current_analysis: false,
          displayable_last_known: false,
          consecutive_failures: 1,
          reason: `${availability} route evidence`,
        })

      const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'DXJ' } })

      await vi.waitFor(() => {
        expect(wrapper.text()).toContain(availability.replace('_', ' '))
      })

      expect(wrapper.text()).toContain('wisdomtree')
      expect(wrapper.text()).toContain(`${availability} route evidence`)
      expect(wrapper.text()).toContain('No current holdings snapshot is available')
      expect(wrapper.emitted('availability')?.at(-1)).toEqual([false])
    },
  )

  it('shows the machine-readable issuer access classification in the degradation notice', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        availability: 'unavailable',
        source_provider: 'wisdomtree',
        source_tier: 'none',
        usable_for_current_analysis: false,
        displayable_last_known: false,
        consecutive_failures: 1,
        failure_class: 'issuer_access_blocked',
        reason: 'WisdomTree issuer access challenge blocked the product route.',
      })

    const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'DXJ' } })

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Last check classification: issuer access blocked')
    })
  })
})
