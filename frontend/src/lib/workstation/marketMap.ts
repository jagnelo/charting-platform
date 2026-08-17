import { api } from '@/lib/api'
import type { MarketMap, MarketMapCell, MarketMapRequest, MarketMapSnapshot, MarketMapSnapshotSummary } from '@/types'

export function fetchMarketMap(request: MarketMapRequest): Promise<MarketMap> {
  return api.post<MarketMap>('/analysis/market-map', request)
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
