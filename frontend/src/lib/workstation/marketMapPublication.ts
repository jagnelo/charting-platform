export type MarketMapAnalysisScope = 'full' | 'selection'

export interface MarketMapAnalysisSourceInput {
  sourceId: string
  scope: MarketMapAnalysisScope
  selectedIds: number[]
}

export interface MarketMapAnalysisSource {
  sourceId: string
  scope: MarketMapAnalysisScope
  selectedIds: number[]
  error?: string
}

/** Resolve a Market Map handoff without mutating its parent watchlist. */
export function resolveMarketMapAnalysisSource(input: MarketMapAnalysisSourceInput): MarketMapAnalysisSource {
  const selectedIds = input.scope === 'selection'
    ? [...new Set(input.selectedIds.filter(id => Number.isInteger(id) && id > 0))]
    : []
  if (!selectedIds.length) return { sourceId: input.sourceId, scope: 'full', selectedIds: [] }
  const sourceId = `explicit:${selectedIds.join(',')}`
  if (sourceId.length > 4096) {
    return {
      sourceId: input.sourceId,
      scope: input.scope,
      selectedIds,
      error: 'The selected member set is too large for an explicit analysis source; save it as a personal watchlist first.',
    }
  }
  return { sourceId, scope: input.scope, selectedIds }
}
