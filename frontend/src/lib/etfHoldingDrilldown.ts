import type { ETFHolding, ETFHoldingsSnapshot } from '@/types'

export interface ETFHoldingDrilldownContext {
  instrumentId: number
  canonicalSymbol: string
  snapshotId: number
  compositionDate: string
  knownAt: string
  provenance: string
  sourceProvider: string
  holdingRowId: number
  sourceRowId: string
  reportedSymbol: string
  reportedName: string
  holdingType: string
}

export function isEligibleUnresolvedEquityHolding(row: ETFHolding | null | undefined): boolean {
  if (!row || row.is_resolved || row.constituent_instrument_id != null) return false
  if (String(row.row_type || '').trim().toLowerCase() !== 'security') return false

  const holdingType = String(row.holding_type || '').trim().toLowerCase().replace(/[\s_-]+/g, '')
  if (!['equity', 'stock', 'commonstock', 'commonshares', 'ordinaryshares'].includes(holdingType)) return false

  const symbol = String(row.reported_symbol || '').trim()
  if (!symbol || /^holding-/i.test(symbol)) return false
  const metadata = row.extra_data ?? {}
  if (metadata.is_synthetic === true || metadata.synthetic === true
    || metadata.is_reference === true || metadata.reference === true) return false
  return true
}

export function createETFHoldingDrilldownContext(
  snapshot: ETFHoldingsSnapshot,
  row: ETFHolding,
  instrumentId: number,
  canonicalSymbol: string,
): ETFHoldingDrilldownContext {
  return {
    instrumentId,
    canonicalSymbol,
    snapshotId: snapshot.id,
    compositionDate: snapshot.composition_date,
    knownAt: snapshot.known_at ?? '',
    provenance: snapshot.provenance,
    sourceProvider: snapshot.source_provider,
    holdingRowId: row.id,
    sourceRowId: row.source_row_id ?? '',
    reportedSymbol: String(row.reported_symbol || '').trim(),
    reportedName: String(row.reported_name || row.constituent_name || '').trim(),
    holdingType: row.holding_type,
  }
}

export function holdingDrilldownRouteQuery(context: ETFHoldingDrilldownContext): Record<string, string> {
  return {
    holding_snapshot_id: String(context.snapshotId),
    holding_composition_date: context.compositionDate,
    holding_known_at: context.knownAt,
    holding_provenance: context.provenance,
    holding_source_provider: context.sourceProvider,
    holding_instrument_id: String(context.instrumentId),
    holding_row_id: String(context.holdingRowId),
    holding_source_row_id: context.sourceRowId,
    holding_reported_symbol: context.reportedSymbol,
    holding_reported_name: context.reportedName,
    holding_type: context.holdingType,
  }
}
