import type { Watchlist } from '@/types'

export interface ComboListDefinition {
  stable_key: string
  name: string
  payload: {
    union_watchlist_ids?: number[]
    intersection_watchlist_ids?: number[]
    exclude_watchlist_ids?: number[]
  }
}

export interface ComboWatchlistRow {
  itemId?: number
  sourceWatchlistId?: number
  instrumentId: number
  symbol: string
  name: string
  flagged?: boolean
  values: { last: number | null; change: number | null }
}

export function buildComboWatchlistRows(
  watchlists: Watchlist[],
  definition: ComboListDefinition,
  prices: Record<string, { close?: number; pct?: number }>,
): ComboWatchlistRow[] {
  const byId = new Map(watchlists.map(watchlist => [watchlist.id, watchlist]))
  const unionIds = uniqueValidIds(definition.payload.union_watchlist_ids)
  const intersectionIds = uniqueValidIds(definition.payload.intersection_watchlist_ids)
  const excludeIds = uniqueValidIds(definition.payload.exclude_watchlist_ids)
  const sourceIds = [...new Set([...unionIds, ...intersectionIds])]
  const union = unionIds.length
    ? new Set(unionIds.flatMap(id => byId.get(id)?.items.map(item => item.instrument_id) ?? []))
    : new Set(intersectionIds.length ? (byId.get(intersectionIds[0])?.items.map(item => item.instrument_id) ?? []) : [])
  const intersection = intersectionIds.length
    ? new Set(intersectionIds.reduce<number[] | null>((current, id) => {
      const ids = new Set(byId.get(id)?.items.map(item => item.instrument_id) ?? [])
      return current == null ? [...ids] : current.filter(instrumentId => ids.has(instrumentId))
    }, null) ?? [])
    : null
  const excluded = new Set(excludeIds.flatMap(id => byId.get(id)?.items.map(item => item.instrument_id) ?? []))
  const selected = [...union].filter(instrumentId => !excluded.has(instrumentId) && (intersection == null || intersection.has(instrumentId)))
  const sourceWatchlists = sourceIds.flatMap(id => byId.get(id) ? [byId.get(id)!] : [])
  const rows: ComboWatchlistRow[] = []
  for (const instrumentId of selected) {
    const source = sourceWatchlists.find(watchlist => watchlist.items.some(item => item.instrument_id === instrumentId))
    const item = source?.items.find(candidate => candidate.instrument_id === instrumentId)
    if (!item || !source) continue
    rows.push({
      itemId: item.id,
      sourceWatchlistId: source.id,
      instrumentId,
      symbol: item.symbol ?? `#${instrumentId}`,
      name: item.name ?? item.symbol ?? `Instrument ${instrumentId}`,
      flagged: item.flagged === true,
      values: {
        last: prices[item.symbol ?? '']?.close ?? null,
        change: prices[item.symbol ?? '']?.pct ?? null,
      },
    })
  }
  return rows
}

function uniqueValidIds(values: number[] | undefined): number[] {
  return [...new Set((values ?? []).filter(id => Number.isInteger(id) && id > 0))]
}
