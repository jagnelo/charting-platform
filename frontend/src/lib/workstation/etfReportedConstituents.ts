import type { ETFHolding } from '@/types'
import { isEquitySecurityHolding, isResolvedCanonicalEquityHolding } from '@/lib/etfHoldingDrilldown'

export interface ETFReportedConstituentRow {
  rowKey: string
  instrumentId: number | null
  symbol: string
  name: string
  values: {
    weight: number | null
    holding_type: string
    resolution: string
  }
}

export function etfHoldingWatchlistRowKey(etfSymbol: string, snapshotId: number, holdingId: number): string {
  return `etf-holding:${etfSymbol.trim().toUpperCase()}:${snapshotId}:${holdingId}`
}

export function projectReportedETFHoldings(
  etfSymbol: string,
  snapshotId: number,
  holdings: ETFHolding[],
): ETFReportedConstituentRow[] {
  return holdings.map(row => {
    const canonicalEquity = isResolvedCanonicalEquityHolding(row)
    const parsedWeight = row.weight == null || row.weight === '' ? null : Number(row.weight)
    return {
      rowKey: etfHoldingWatchlistRowKey(etfSymbol, snapshotId, row.id),
      instrumentId: canonicalEquity ? row.constituent_instrument_id : null,
      symbol: String(row.reported_symbol || row.constituent_symbol || '').trim() || '—',
      name: String(row.reported_name || row.constituent_name || '').trim() || 'Reported holding',
      values: {
        weight: parsedWeight != null && Number.isFinite(parsedWeight) ? parsedWeight : null,
        holding_type: `${row.row_type || 'holding'} · ${row.holding_type || 'type not reported'}`,
        resolution: canonicalEquity
          ? 'Canonical equity resolved'
          : row.is_resolved
            ? 'Reported; canonical equity link unavailable'
            : isEquitySecurityHolding(row)
              ? 'Equity identity not resolved'
              : 'Not eligible for equity charting',
      },
    }
  })
}
