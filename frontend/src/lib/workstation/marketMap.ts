import { api } from '@/lib/api'
import type { MarketMap, MarketMapCell, MarketMapRequest, MarketMapSnapshot, MarketMapSnapshotSummary } from '@/types'

export type WatchlistHistoryStatusKind = 'pending' | 'partial' | 'fetching' | 'failed' | 'ready' | 'unavailable'

export interface WatchlistHistoryTimeframeStatus {
  timeframe: string
  member_count: number
  covered_member_count: number
  coverage_percent: number
  bar_count: number
  oldest?: string | null
  newest?: string | null
  in_progress_count: number
  complete_count: number
  failed_count: number
  pending_count: number
}

export interface WatchlistSourceHistoryStatus {
  source_id: string
  source_kind?: string | null
  name: string
  locked: boolean
  membership_version?: string | null
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  limited: boolean
  excluded_count: number
  overall_status: WatchlistHistoryStatusKind
  timeframes: WatchlistHistoryTimeframeStatus[]
  message?: string | null
}

export interface WatchlistSourceHistoryRefreshResult {
  run_id?: number | null
  source_ids: string[]
  timeframes: string[]
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  limited: boolean
  queued: number
  already_queued: number
  queue_unavailable: boolean
  message?: string | null
}

export interface WatchlistHistoryRefreshRun {
  id: number
  source_ids: string[]
  timeframes: string[]
  membership_versions?: Record<string, string | null>
  as_of?: string | null
  max_instruments: number
  available_instrument_count: number
  selected_instrument_count: number
  queued_count: number
  already_queued_count: number
  status: string
  cancel_requested: boolean
  progress: Record<string, number | string | boolean>
  error?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export function fetchMarketMap(request: MarketMapRequest): Promise<MarketMap> {
  return api.post<MarketMap>('/analysis/market-map', request)
}

export function fetchWatchlistSourceHistoryStatus(
  sourceId: string,
  timeframes: string[] = ['D1'],
  maxInstruments = 5000,
): Promise<WatchlistSourceHistoryStatus> {
  return api.get<WatchlistSourceHistoryStatus>(
    `/watchlists/sources/history-status/${encodeURIComponent(sourceId)}`,
    { timeframes, max_instruments: maxInstruments },
  )
}

export function refreshWatchlistSourceHistory(
  sourceId: string,
  timeframes: string[] = ['D1'],
  maxInstruments = 5000,
): Promise<WatchlistSourceHistoryRefreshResult> {
  return api.post<WatchlistSourceHistoryRefreshResult>('/watchlists/sources/history-refresh', {
    source_ids: [sourceId],
    timeframes,
    max_instruments: maxInstruments,
  })
}

export function fetchWatchlistHistoryRefreshRun(runId: number): Promise<WatchlistHistoryRefreshRun> {
  return api.get<WatchlistHistoryRefreshRun>(`/watchlists/history-refresh-runs/${runId}`)
}

export function cancelWatchlistHistoryRefreshRun(runId: number): Promise<WatchlistHistoryRefreshRun> {
  return api.post<WatchlistHistoryRefreshRun>(`/watchlists/history-refresh-runs/${runId}/cancel`, {})
}

export function fetchMarketMapCache(cacheKey: string): Promise<MarketMap> {
  return api.get<MarketMap>(`/analysis/market-map/cache/${encodeURIComponent(cacheKey)}`)
}

export function fetchMarketMapSnapshots(): Promise<MarketMapSnapshotSummary[]> {
  return api.get<MarketMapSnapshotSummary[]>('/analysis/market-map/snapshots')
}

export function saveMarketMapSnapshot(name: string, cacheKey: string): Promise<MarketMapSnapshot> {
  return api.post<MarketMapSnapshot>('/analysis/market-map/snapshots', { name, cache_key: cacheKey })
}

export function fetchMarketMapSnapshot(snapshotId: number): Promise<MarketMapSnapshot> {
  return api.get<MarketMapSnapshot>(`/analysis/market-map/snapshots/${snapshotId}`)
}

export function deleteMarketMapSnapshot(snapshotId: number): Promise<void> {
  return api.delete<void>(`/analysis/market-map/snapshots/${snapshotId}`)
}

export interface MarketMapLayoutCell extends MarketMapCell {
  x: number
  y: number
  width: number
  height: number
}

/** Deterministic slice-and-dice geometry with no DOM/provider-dependent inputs. */
export function layoutMarketMapCells(cells: MarketMapCell[], width = 100, height = 100): MarketMapLayoutCell[] {
  // A cell without a finite positive area has no drawable treemap geometry. Keep it
  // in the source response for warning/coverage detail, but do not invent a unit tile.
  const weighted = cells
    .filter(cell => cell.area_value != null && Number.isFinite(cell.area_value) && cell.area_value > 0)
    .map(cell => ({ cell, area: cell.area_value as number }))
  const total = weighted.reduce((sum, item) => sum + item.area, 0) || 1
  let x = 0
  let y = 0
  let remainingWidth = width
  let remainingHeight = height
  let remainingArea = total
  return weighted.map(({ cell, area }, index) => {
    const fraction = area / Math.max(remainingArea, 0.0001)
    const horizontal = remainingWidth >= remainingHeight
    const tileWidth = horizontal ? remainingWidth * fraction : remainingWidth
    const tileHeight = horizontal ? remainingHeight : remainingHeight * fraction
    const result: MarketMapLayoutCell = { ...cell, x, y, width: tileWidth, height: tileHeight }
    if (horizontal) { x += tileWidth; remainingWidth -= tileWidth } else { y += tileHeight; remainingHeight -= tileHeight }
    remainingArea -= area
    if (index === weighted.length - 1) {
      result.width = Math.max(result.width, width - result.x)
      result.height = Math.max(result.height, height - result.y)
    }
    return result
  })
}
