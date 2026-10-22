export const TAG_COLUMN_PREFIX = 'tag-watchlist:'

export interface TagColumnTarget {
  id: number
  name: string
  locked?: boolean
  instrumentIds: readonly number[] | null
}

export interface TagColumnDefinition {
  key: string
  targetWatchlistId: number
}

/** Accept only stable positive WatchList IDs and preserve their configured order. */
export function parseTagColumnWatchlistIds(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  const ids: number[] = []
  const seen = new Set<number>()
  for (const candidate of value) {
    if (typeof candidate !== 'number' || !Number.isInteger(candidate) || candidate <= 0 || seen.has(candidate)) continue
    seen.add(candidate)
    ids.push(candidate)
  }
  return ids
}

export function tagColumnKey(watchlistId: number): string {
  return `${TAG_COLUMN_PREFIX}${watchlistId}`
}

export function tagColumnMembership(
  target: TagColumnTarget | null | undefined,
  instrumentId: number | null,
): 'member' | 'not_member' | 'unavailable' {
  if (
    !target || !Number.isInteger(target.id) || target.id <= 0
    || !Array.isArray(target.instrumentIds)
    || instrumentId == null || !Number.isInteger(instrumentId) || instrumentId <= 0
  ) return 'unavailable'
  return target.instrumentIds.includes(instrumentId) ? 'member' : 'not_member'
}
