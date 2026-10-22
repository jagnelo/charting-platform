import { describe, expect, it } from 'vitest'
import { breadthReferenceTargetEvidence } from '@/lib/workstation/breadthReferenceEvidence'

describe('breadth reference-target evidence', () => {
  it('describes the equal-weight group derivation and its alignment evidence', () => {
    expect(breadthReferenceTargetEvidence({
      reference_universe: { kind: 'group', key: 'sp500-sectors', point_in_time: true },
      reference_target: {
        target: 'equal_weight_member_return_index',
        method: 'derived_equal_weight_return_index',
        universe: { kind: 'market_group', stable_key: 'sp500-sectors' },
        membership_version: 42,
        member_count: 6,
        point_count: 4,
        covered_member_points: 20,
        mean_covered_members: 5,
        alignment: 'exact_timestamp_no_forward_fill',
      },
    })).toEqual({
      kind: 'aggregate',
      target: 'Equal-weight group aggregate · sp500-sectors',
      derivation: 'Derived equal weight return index',
      membership: 'version 42 · 6 members',
      coverage: '83.3% average · 5.0/6 members per point',
      alignedSeries: '4 aligned points · 20 covered member-points',
      alignment: 'Exact timestamp · no forward fill',
    })
  })

  it('keeps a direct benchmark symbol distinct from an aggregate target', () => {
    expect(breadthReferenceTargetEvidence({ reference_symbol: 'spy' })).toEqual({
      kind: 'symbol',
      target: 'Reference symbol · SPY',
      derivation: null,
      membership: null,
      coverage: null,
      alignedSeries: null,
      alignment: null,
    })
  })

  it('does not invent group lineage when the response omits it', () => {
    expect(breadthReferenceTargetEvidence({
      reference_universe: { kind: 'group', key: 'sp500-sectors' },
      reference_target: { universe: { stable_key: 'sp500-sectors' } },
    })).toEqual({
      kind: 'aggregate',
      target: 'Equal-weight group aggregate · sp500-sectors',
      derivation: null,
      membership: null,
      coverage: null,
      alignedSeries: null,
      alignment: null,
    })
    expect(breadthReferenceTargetEvidence({})).toBeNull()
  })
})
