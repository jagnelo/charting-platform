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

/**
 * Build the declared universe contract for an isolated Python Market Map run.
 *
 * Durable explicit-list sources are canonical user-library snapshots rather
 * than the ephemeral ``explicit:<ids>`` transport form. Both enter the
 * sandbox through the same provider-neutral watchlist resolver, while only
 * the durable version carries a point-in-time known-at boundary.
 */
export function marketMapPythonUniverse(sourceId: string): { kind: 'watchlist'; key: string; point_in_time: boolean } {
  const prefixes = [
    'benchmark-family:',
    'watchlist:',
    'market-group:',
    'etf-holdings:',
    'combo:',
    'explicit:',
    'explicit-list:',
  ]
  if (prefixes.some(prefix => sourceId.startsWith(prefix) && sourceId.length > prefix.length)) {
    return { kind: 'watchlist', key: sourceId, point_in_time: !sourceId.startsWith('explicit:') }
  }
  throw new Error('Python Market Map colours require a canonical watchlist source.')
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
