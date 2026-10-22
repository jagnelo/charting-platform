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

export interface TagColumnWatchlist {
  id: number
  name: string
  is_managed?: boolean
  is_locked?: boolean
  items: readonly { id: number; instrument_id: number }[]
}

export interface TagColumnMembershipRow {
  symbol: string
  instrumentId: number | null
}

export interface TagColumnConfigurationUpdate {
  targetWatchlistIds: unknown
  visibleColumnKeys: unknown
}

const pendingMembershipMutations = new Set<string>()

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

export function resolveTagColumnTargets(
  configuredIds: unknown,
  watchlists: readonly TagColumnWatchlist[],
): TagColumnTarget[] {
  return parseTagColumnWatchlistIds(configuredIds).map(id => {
    const target = watchlists.find(watchlist => watchlist.id === id)
    return {
      id,
      name: target?.name ?? `WatchList ${id} (unavailable)`,
      locked: Boolean(target?.is_locked || target?.is_managed),
      instrumentIds: target ? target.items.map(item => item.instrument_id) : null,
    }
  })
}

export function mergeTagColumnConfiguration(
  configuration: Record<string, unknown>,
  update: TagColumnConfigurationUpdate,
  fallbackColumnKeys: readonly string[],
): Record<string, unknown> {
  const targetWatchlistIds = parseTagColumnWatchlistIds(update.targetWatchlistIds)
  const visibleColumnKeys = Array.isArray(update.visibleColumnKeys)
    ? [...new Set(update.visibleColumnKeys.filter((key): key is string => typeof key === 'string'))]
    : [...fallbackColumnKeys]

  return {
    ...configuration,
    tag_watchlist_ids: targetWatchlistIds,
    column_keys: visibleColumnKeys,
  }
}

export function createTagColumnMembershipToggler(dependencies: {
  getPersonalWatchlists: () => readonly TagColumnWatchlist[]
  isDisposed: () => boolean
  addItem: (watchlistId: number, instrumentId: number) => Promise<unknown>
  removeItem: (watchlistId: number, itemId: number) => Promise<unknown>
  setError: (message: string) => void
}): (row: TagColumnMembershipRow, targetWatchlistId?: number) => Promise<void> {
  return async (row, targetWatchlistId) => {
    const instrumentId = row.instrumentId
    if (
      dependencies.isDisposed()
      || targetWatchlistId == null
      || !Number.isInteger(targetWatchlistId)
      || instrumentId == null
      || !Number.isInteger(instrumentId)
      || instrumentId <= 0
    ) return

    const target = dependencies.getPersonalWatchlists().find(watchlist => watchlist.id === targetWatchlistId)
    if (!target || target.is_managed || target.is_locked) {
      dependencies.setError('Tag Columns can change membership only in an unlocked personal WatchList.')
      return
    }

    const mutationKey = `${target.id}:${instrumentId}`
    if (pendingMembershipMutations.has(mutationKey)) return
    pendingMembershipMutations.add(mutationKey)
    dependencies.setError('')
    try {
      const existing = target.items.find(item => item.instrument_id === instrumentId)
      if (existing) {
        await dependencies.removeItem(target.id, existing.id)
        if (dependencies.getPersonalWatchlists().find(list => list.id === target.id)?.items.some(item => item.instrument_id === instrumentId)) {
          dependencies.setError(`Unable to remove ${row.symbol} from ${target.name}.`)
        }
      } else {
        const added = await dependencies.addItem(target.id, instrumentId)
        if (!added || !dependencies.getPersonalWatchlists().find(list => list.id === target.id)?.items.some(item => item.instrument_id === instrumentId)) {
          dependencies.setError(`Unable to add ${row.symbol} to ${target.name}.`)
        }
      }
    } finally {
      pendingMembershipMutations.delete(mutationKey)
    }
  }
}
