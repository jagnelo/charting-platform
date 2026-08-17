import { api } from '@/lib/api'
import type { MarketMap, MarketMapRequest } from '@/types'

export function fetchMarketMap(request: MarketMapRequest): Promise<MarketMap> {
  return api.post<MarketMap>('/analysis/market-map', request)
}
