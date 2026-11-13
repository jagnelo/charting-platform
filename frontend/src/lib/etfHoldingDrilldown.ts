import type { ETFHolding, ETFHoldingsSnapshot } from '@/types'
import type { InstrumentAcquireResponse } from '@/lib/onDemandAcquisition'

export interface ETFHoldingDrilldownContext {
  etfSymbol?: string
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

/** Validates a real identity response against the exact reported holding context. */
export function isConfirmedETFHoldingIdentity(
  response: InstrumentAcquireResponse | null | undefined,
  context: ETFHoldingDrilldownContext,
): response is InstrumentAcquireResponse & { instrument: NonNullable<InstrumentAcquireResponse['instrument']> } {
  const instrument = response?.instrument
  return response?.status === 'resolved'
    && Boolean(instrument)
    && Number.isSafeInteger(instrument?.instrument_id)
    && instrument?.instrument_id === context.instrumentId
    && instrument?.symbol.trim().toUpperCase() === context.canonicalSymbol.trim().toUpperCase()
    && ['resolved', 'verified'].includes(instrument?.identity_status.trim().toLowerCase() ?? '')
}

const EQUITY_HOLDING_TYPES = new Set(['equity', 'stock', 'commonstock', 'commonshares', 'ordinaryshares', 'realestateinvestmenttrust'])

export function isEquitySecurityHolding(row: ETFHolding | null | undefined): boolean {
  if (!row || String(row.row_type || '').trim().toLowerCase() !== 'security') return false
  const holdingType = String(row.holding_type || '').trim().toLowerCase().replace(/[\s_-]+/g, '')
  if (!EQUITY_HOLDING_TYPES.has(holdingType)) return false
  const symbol = String(row.reported_symbol || row.constituent_symbol || '').trim()
  if (!symbol || /^holding-/i.test(symbol)) return false
  const metadata = row.extra_data ?? {}
  return metadata.is_synthetic !== true && metadata.synthetic !== true
    && metadata.is_reference !== true && metadata.reference !== true
}

export function isResolvedCanonicalEquityHolding(row: ETFHolding | null | undefined): row is ETFHolding & {
  constituent_instrument_id: number
  constituent_symbol: string
} {
  return Boolean(row && isEquitySecurityHolding(row) && row.is_resolved
    && Number.isSafeInteger(row.constituent_instrument_id) && Number(row.constituent_instrument_id) > 0
    && String(row.constituent_symbol || '').trim())
}

export function isEligibleUnresolvedEquityHolding(row: ETFHolding | null | undefined): boolean {
  if (!row || row.is_resolved || row.constituent_instrument_id != null) return false
  const reportedSymbol = String(row.reported_symbol || '').trim()
  if (!reportedSymbol || /^holding-/i.test(reportedSymbol)) return false
  return isEquitySecurityHolding(row)
}

export function createETFHoldingDrilldownContext(
  snapshot: ETFHoldingsSnapshot,
  row: ETFHolding,
  instrumentId: number,
  canonicalSymbol: string,
): ETFHoldingDrilldownContext {
  return {
    etfSymbol: snapshot.etf_symbol.trim().toUpperCase(),
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

export function isCurrentETFHoldingSelection(
  context: ETFHoldingDrilldownContext,
  etfSymbol: string,
  snapshot: ETFHoldingsSnapshot | null | undefined,
  holding: ETFHolding | null | undefined,
): boolean {
  if (!snapshot || !holding) return false
  const exactReportedTicker = context.canonicalSymbol.trim().toUpperCase()
    === holding.reported_symbol?.trim().toUpperCase()
  const exactResolvedTicker = holding.is_resolved
    && context.instrumentId === holding.constituent_instrument_id
    && context.canonicalSymbol.trim().toUpperCase() === holding.constituent_symbol?.trim().toUpperCase()
  return context.snapshotId === snapshot.id
    && context.holdingRowId === holding.id
    && context.instrumentId > 0
    && (exactReportedTicker || exactResolvedTicker)
    && etfSymbol.trim().toUpperCase() === snapshot.etf_symbol.trim().toUpperCase()
}

export function holdingDrilldownRouteQuery(context: ETFHoldingDrilldownContext): Record<string, string> {
  return {
    ...(context.etfSymbol ? { holding_etf_symbol: context.etfSymbol.trim().toUpperCase() } : {}),
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

export function holdingDrilldownRouteState(
  context: ETFHoldingDrilldownContext,
  confirmedIdentity?: InstrumentAcquireResponse,
): Record<string, string> {
  const state: Record<string, string> = {
    tcHoldingSelectionHandoff: JSON.stringify(context),
  }
  if (isConfirmedETFHoldingIdentity(confirmedIdentity, context)) {
    state.tcHoldingIdentityHandoff = JSON.stringify(confirmedIdentity)
  }
  return state
}

export function isSameETFHoldingDrilldownContext(
  left: ETFHoldingDrilldownContext | null | undefined,
  right: ETFHoldingDrilldownContext | null | undefined,
): boolean {
  if (!left || !right) return false
  return (left.etfSymbol?.trim().toUpperCase() ?? '') === (right.etfSymbol?.trim().toUpperCase() ?? '')
    && left.instrumentId === right.instrumentId
    && left.canonicalSymbol.trim().toUpperCase() === right.canonicalSymbol.trim().toUpperCase()
    && left.snapshotId === right.snapshotId
    && left.compositionDate === right.compositionDate
    && left.knownAt === right.knownAt
    && left.provenance === right.provenance
    && left.sourceProvider === right.sourceProvider
    && left.holdingRowId === right.holdingRowId
    && left.sourceRowId === right.sourceRowId
    && left.reportedSymbol === right.reportedSymbol
    && left.reportedName === right.reportedName
    && left.holdingType === right.holdingType
}

export function parseETFHoldingDrilldownRouteQuery(
  query: Record<string, unknown>,
  routeSymbol: string,
): ETFHoldingDrilldownContext | null {
  const value = (key: string) => typeof query[key] === 'string' ? String(query[key]).trim() : ''
  const snapshotId = Number(value('holding_snapshot_id'))
  const instrumentId = Number(value('holding_instrument_id'))
  const holdingRowId = Number(value('holding_row_id'))
  const canonicalSymbol = routeSymbol.trim().toUpperCase()
  if (!Number.isSafeInteger(snapshotId) || snapshotId <= 0
    || !Number.isSafeInteger(instrumentId) || instrumentId <= 0
    || !Number.isSafeInteger(holdingRowId) || holdingRowId <= 0
    || !canonicalSymbol || !value('holding_composition_date')
    || !value('holding_provenance') || !value('holding_source_provider')) return null

  return {
    ...(value('holding_etf_symbol') ? { etfSymbol: value('holding_etf_symbol').toUpperCase() } : {}),
    instrumentId,
    canonicalSymbol,
    snapshotId,
    compositionDate: value('holding_composition_date'),
    knownAt: value('holding_known_at'),
    provenance: value('holding_provenance'),
    sourceProvider: value('holding_source_provider'),
    holdingRowId,
    sourceRowId: value('holding_source_row_id'),
    reportedSymbol: value('holding_reported_symbol'),
    reportedName: value('holding_reported_name'),
    holdingType: value('holding_type'),
  }
}
