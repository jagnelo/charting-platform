import { describe, expect, it } from 'vitest'
import { workstationFreshness } from '@/lib/workstation/freshness'

describe('workstation freshness mapping', () => {
  it.each([
    [{ isLoading: true }, 'fetching', 'Fetching'],
    [{ isFetchingHistory: true }, 'fetching', 'Backfilling history'],
    [{ freshness: 'current' }, 'current', 'Current · canonical'],
    [{ freshness: 'delayed' }, 'delayed', 'Delayed'],
    [{ freshness: 'stale' }, 'stale', 'Stale · cached'],
    [{ freshness: 'partial' }, 'partial', 'Partial coverage'],
    [{ freshness: 'coverage-limited' }, 'coverage-limited', 'Coverage limited'],
    [{ freshness_detail: { other: 1 } }, 'coverage-limited', 'Coverage limited'],
    [{ hasBars: true }, 'stale', 'Stale · local observations'],
    [{}, 'unavailable', 'Unavailable'],
  ] as const)('maps %j to %s', (input, kind, label) => {
    expect(workstationFreshness(input)).toEqual({ kind, label })
  })
})
