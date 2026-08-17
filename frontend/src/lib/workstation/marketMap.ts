import { api } from '@/lib/api'
import type { MarketMap, MarketMapCell, MarketMapRequest } from '@/types'

export function fetchMarketMap(request: MarketMapRequest): Promise<MarketMap> {
  return api.post<MarketMap>('/analysis/market-map', request)
}

export function fetchMarketMapCache(cacheKey: string): Promise<MarketMap> {
  return api.get<MarketMap>(`/analysis/market-map/cache/${encodeURIComponent(cacheKey)}`)
}

export interface MarketMapLayoutCell extends MarketMapCell {
  x: number
  y: number
  width: number
  height: number
}

/** Deterministic slice-and-dice geometry with no DOM/provider-dependent inputs. */
export function layoutMarketMapCells(cells: MarketMapCell[], width = 100, height = 100): MarketMapLayoutCell[] {
  const weighted = cells.map(cell => ({ cell, area: Math.max(cell.area_value ?? 1, 0.0001) }))
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
