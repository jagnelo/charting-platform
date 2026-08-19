import { describe, expect, it } from 'vitest'
import { resolveMarketMapAnalysisSource } from '@/lib/workstation/marketMapPublication'

describe('Market Map analysis publication', () => {
  it('publishes a selected canonical subset as an explicit source', () => {
    expect(resolveMarketMapAnalysisSource({
      sourceId: 'benchmark-family:sp500:cap_weight',
      scope: 'selection',
      selectedIds: [4, 2, 4, 0, -1, 2.5],
    })).toEqual({ sourceId: 'explicit:4,2', scope: 'selection', selectedIds: [4, 2] })
  })

  it('preserves the full source when no subset is selected', () => {
    expect(resolveMarketMapAnalysisSource({ sourceId: 'watchlist:7', scope: 'selection', selectedIds: [] }))
      .toEqual({ sourceId: 'watchlist:7', scope: 'full', selectedIds: [] })
  })

  it('rejects an explicit source that exceeds the canonical source bound', () => {
    const result = resolveMarketMapAnalysisSource({
      sourceId: 'watchlist:7', scope: 'selection', selectedIds: Array.from({ length: 2000 }, (_, index) => index + 1),
    })
    expect(result.error).toContain('too large')
    expect(result.sourceId).toBe('watchlist:7')
    expect(result.selectedIds).toHaveLength(2000)
  })
})
