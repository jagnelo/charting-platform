import { describe, expect, it } from 'vitest'
import { describeMarketMap } from '@/lib/workstation/marketMapAccessibility'

describe('describeMarketMap', () => {
  it('summarizes canvas scope, coverage, metrics, and disclosures', () => {
    expect(describeMarketMap({
      sourceName: 'S&P 500', period: '1D', timeframe: 'D1', adjustment: 'split_adjusted',
      areaMetric: 'market_cap', colorMetric: 'relative_return', freshness: 'current',
      requestedCount: 500, evaluatedCount: 480, coverage: 0.96, colorCoverage: 0.94,
      areaCoverage: 0.99, visibleCount: 480, groupCount: 11, selectedCount: 2,
      warningCount: 3, exclusionCount: 4,
    })).toBe('S&P 500 market map for 1D D1, split adjusted; relative return colour by market cap area; 480 visible members in 11 groups; coverage 96% (480 of 500 evaluated); freshness current; colour coverage 94%, area coverage 99%, 3 warnings, 4 exclusions; 2 selected.')
  })

  it('keeps unavailable coverage explicit', () => {
    expect(describeMarketMap({
      sourceName: 'Pending universe', period: 'CUSTOM', timeframe: 'W1', adjustment: 'raw',
      areaMetric: 'equal', colorMetric: 'return', freshness: 'unavailable',
      requestedCount: 0, evaluatedCount: 0, coverage: Number.NaN, visibleCount: 0,
      groupCount: 0, selectedCount: 0, warningCount: 0, exclusionCount: 1,
    })).toContain('coverage unknown (0 of 0 evaluated)')
  })
})
