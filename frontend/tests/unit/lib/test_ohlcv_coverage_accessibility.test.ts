import { describe, expect, it } from 'vitest'
import { describeOhlcvCoverage } from '@/lib/workstation/ohlcvCoverageAccessibility'

describe('describeOhlcvCoverage', () => {
  it('keeps mixed source and opaque adjustment factors explicit', () => {
    expect(describeOhlcvCoverage({
      timeframe: 'W1', status: 'partial', barCount: 248,
      sourceLineage: 'provider_and_derived', providerBarCount: 240,
      derivedBarCount: 8, unknownBarCount: 0, sourceTimeframes: ['D1'],
      adjustmentMode: 'split_adjusted',
      factorStatus: 'mixed_provider_native_opaque_and_inherited_from_canonical_d1',
    })).toBe('W1 partial local coverage: 248 bars; provider and derived (240 provider, 8 derived, 0 unknown); adjustment split adjusted; factor status mixed provider native opaque and inherited from canonical d1; source timeframes D1.')
  })

  it('does not invent a factor version when it is unreported', () => {
    expect(describeOhlcvCoverage({
      timeframe: 'D1', status: 'ready', barCount: 2,
      sourceLineage: 'provider_only', providerBarCount: 2,
      derivedBarCount: 0, unknownBarCount: 0,
      adjustmentMode: 'raw', factorStatus: 'not_applied', factorVersion: null,
    })).not.toContain('factor version')
  })
})
