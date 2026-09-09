import { describe, expect, it } from 'vitest'
import { describeOhlcvBarProvenance, summarizeOhlcvProvenance } from '@/lib/workstation/ohlcvProvenance'
import type { OHLCVBar } from '@/types'

const baseBar: OHLCVBar = {
  ts: '2025-01-02T00:00:00Z',
  open: 10,
  high: 12,
  low: 9,
  close: 11,
  is_adjusted: true,
}

describe('OHLCV provenance summaries', () => {
  it('describes a provider-observed adjusted bar without naming an unknown provider', () => {
    expect(describeOhlcvBarProvenance({ ...baseBar, is_derived: false })).toBe(
      'Provider-observed adjusted data.',
    )
  })

  it('describes derived bars with their source timeframe, method, and source count', () => {
    expect(describeOhlcvBarProvenance({
      ...baseBar,
      is_derived: true,
      source_timeframe: 'D1',
      derivation_method: 'd1_ohlcv_xnys_calendar_aggregation',
      source_bar_count: 5,
    })).toBe(
      'Derived adjusted data from D1 via d1_ohlcv_xnys_calendar_aggregation using 5 source bars.',
    )
  })

  it('summarizes mixed provider and derived ranges while preserving unknown lineage', () => {
    expect(summarizeOhlcvProvenance([
      { ...baseBar, is_derived: false },
      { ...baseBar, ts: '2025-01-03T00:00:00Z', is_derived: true },
      { ...baseBar, ts: '2025-01-04T00:00:00Z' },
    ], 'W1', 'heikin_ashi')).toBe(
      'W1 heikin ashi chart; 3 bars; adjusted; mixed provider-observed and derived lineage, 1 with unknown lineage.',
    )
  })

  it('reports an empty chart explicitly', () => {
    expect(summarizeOhlcvProvenance([], 'D1')).toBe('D1 chart; no OHLCV bars loaded.')
  })
})
