import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ETFHoldingsPanel from '@/components/etf/ETFHoldingsPanel.vue'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))

const storedSnapshot = {
  id: 41,
  etf_profile_id: 4,
  etf_instrument_id: 14,
  etf_symbol: 'SPY',
  etf_name: 'SPDR S&P 500 ETF Trust',
  composition_date: '2026-05-31',
  known_at: '2026-06-01T04:00:00Z',
  provenance: 'issuer_current_holdings',
  source_provider: 'issuer-test',
  source_quality: 'issuer_current',
  completeness_status: 'complete',
  row_count: 1,
  resolved_count: 1,
  unresolved_count: 0,
  total_weight: '0.07000000',
  parser_version: 'test-v1',
  holdings: [{
    id: 1,
    snapshot_id: 41,
    constituent_instrument_id: 100,
    constituent_symbol: 'AAPL',
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
    resolution_confidence: '0.97',
    holding_type: 'equity',
    row_type: 'security',
    is_resolved: true,
  }],
}

describe('ETF stored snapshot and current-analysis labels', () => {
  beforeEach(() => vi.mocked(api.get).mockReset())

  it('keeps a controlled stored fixture visible without implying current eligibility', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ ...storedSnapshot, provenance: 'controlled_fixture', source_quality: 'controlled fixture' })
      .mockResolvedValueOnce({
        availability: 'unknown', usable_for_current_analysis: false, displayable_last_known: true,
        reason: 'No holdings snapshot has been stored for this ETF.',
        symbol_audit: { next_action: 'internal source review only' },
      })

    const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('AAPL'))

    expect(wrapper.get('[data-testid="etf-stored-snapshot-label"]').text()).toBe('Stored snapshot: Controlled test fixture')
    expect(wrapper.get('[data-testid="etf-current-analysis-eligibility"]').text()).toContain('unknown')
    expect(wrapper.text()).toContain('Capability reason (current-analysis scope): No holdings snapshot has been stored for this ETF.')
    expect(wrapper.text()).not.toContain('internal source review only')
    expect(wrapper.find('.open-holding-button').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('availability')?.at(-1)).toEqual([false])
  })

  it('preserves actual dated SEC evidence when current eligibility is stale', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({
        ...storedSnapshot, provenance: 'sec_filing', source_provider: 'SEC EDGAR',
        source_quality: 'historical_filing', composition_date: '2025-12-31',
        known_at: '2026-02-17T14:05:00Z',
      })
      .mockResolvedValueOnce({
        availability: 'stale', source_tier: 'sec_filing', usable_for_current_analysis: false,
        displayable_last_known: true,
        reason: 'The dated filing does not establish issuer-current support.',
      })

    const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'SPY' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('AAPL'))

    expect(wrapper.get('[data-testid="etf-stored-snapshot-label"]').text()).toBe('Stored snapshot: sec filing')
    expect(wrapper.text()).toContain('SEC EDGAR')
    expect(wrapper.get('time[data-testid="etf-stored-composition-date"]').attributes('datetime')).toBe('2025-12-31')
    expect(wrapper.get('time[datetime="2026-02-17T14:05:00Z"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Capability reason (current-analysis scope): The dated filing does not establish issuer-current support.')
    expect(wrapper.emitted('availability')?.at(-1)).toEqual([false])
  })

  it('distinguishes an empty stored-snapshot read from unknown eligibility', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        availability: 'unknown', usable_for_current_analysis: false, displayable_last_known: false,
        reason: 'No holdings snapshot has been stored for this ETF.',
      })

    const wrapper = mount(ETFHoldingsPanel, { props: { symbol: 'DXJ' } })
    await vi.waitFor(() => expect(wrapper.text()).toContain('No stored holdings snapshot is available for inspection.'))

    expect(wrapper.get('[data-testid="etf-stored-snapshot-label"]').text()).toBe('No stored holdings snapshot')
    expect(wrapper.get('[data-testid="etf-current-analysis-eligibility"]').text()).toContain('unknown')
    expect(wrapper.text()).toContain('No current holdings snapshot is available for analysis.')
    expect(wrapper.text()).toContain('Capability reason (current-analysis scope): No holdings snapshot has been stored for this ETF.')
  })
})
