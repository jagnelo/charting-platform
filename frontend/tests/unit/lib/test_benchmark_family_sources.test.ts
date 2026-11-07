import { describe, expect, it } from 'vitest'
import { benchmarkFamilyConstituentSourceId, benchmarkFamilyHistoryTargets, breadthSnapshotBenchmark } from '@/lib/workstation/benchmarkFamilySources'

describe('benchmark family constituent source identities', () => {
  it('opens the selected family through its locked cap-weight constituent source by default', () => {
    expect(benchmarkFamilyConstituentSourceId('SP400')).toBe('benchmark-family:sp400:cap_weight')
  })

  it('supports explicit equal/style role sources without ticker reconstruction', () => {
    expect(benchmarkFamilyConstituentSourceId('nasdaq100', 'equal_weight')).toBe('benchmark-family:nasdaq100:equal_weight')
    expect(benchmarkFamilyConstituentSourceId('sp500', 'value')).toBe('benchmark-family:sp500:value')
    expect(benchmarkFamilyConstituentSourceId('sp500', 'growth')).toBe('benchmark-family:sp500:growth')
  })

  it('rejects an empty family rather than creating a malformed source', () => {
    expect(benchmarkFamilyConstituentSourceId('   ')).toBeNull()
  })

  it('uses SPY only for generic groups and never substitutes it for an unmapped family', () => {
    expect(breadthSnapshotBenchmark(null, undefined)).toBe('SPY')
    expect(breadthSnapshotBenchmark({ logical_key: 'small-cap-family' }, undefined)).toBeUndefined()
    expect(breadthSnapshotBenchmark({ logical_key: 'large-cap-family' }, ' spy ')).toBe('SPY')
  })

  it('prepares the family itself and adds only its explicitly mapped cap proxy', () => {
    expect(benchmarkFamilyHistoryTargets('small-cap-family', undefined)).toEqual([
      { kind: 'family', family_key: 'small-cap-family' },
    ])
    expect(benchmarkFamilyHistoryTargets('large-cap-family', ' ivv ')).toEqual([
      { kind: 'family', family_key: 'large-cap-family' },
      { kind: 'instrument', symbol: 'IVV' },
    ])
  })
})
