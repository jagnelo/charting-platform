import type { Watchlist } from '@/types'

export interface FlaggedWatchlistRow {
  itemId: number
  sourceWatchlistId: number
  instrumentId: number
  symbol: string
  name: string
  flagged: true
  values: {
    last: number | null
    change: number | null
  }
}

export function buildFlaggedWatchlistRows(
  watchlists: Watchlist[],
  prices: Record<string, { close?: number; pct?: number }>,
): FlaggedWatchlistRow[] {
  const seen = new Set<number>()
  const rows: FlaggedWatchlistRow[] = []
  for (const watchlist of watchlists) {
    for (const item of watchlist.items) {
      if (!item.flagged || seen.has(item.instrument_id)) continue
      seen.add(item.instrument_id)
      rows.push({
        itemId: item.id,
        sourceWatchlistId: watchlist.id,
        instrumentId: item.instrument_id,
        symbol: item.symbol ?? `#${item.instrument_id}`,
        name: item.name ?? item.symbol ?? `Instrument ${item.instrument_id}`,
        flagged: true,
        values: {
          last: prices[item.symbol ?? '']?.close ?? null,
          change: prices[item.symbol ?? '']?.pct ?? null,
        },
      })
    }
  }
  return rows
}
