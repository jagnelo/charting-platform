import type { QueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import type { Instrument } from '@/types'

export type CanonicalInstrument = Instrument

export const INSTRUMENT_QUERY_ROOT = ['workstation', 'instrument'] as const

export function fetchCanonicalInstrument(queryClient: QueryClient, symbol: string) {
  const normalized = symbol.trim().toUpperCase()
  return queryClient.fetchQuery<CanonicalInstrument>({
    queryKey: [...INSTRUMENT_QUERY_ROOT, normalized],
    queryFn: () => api.get<CanonicalInstrument>(`/instruments/${encodeURIComponent(normalized)}`, { canonical_only: true }),
    staleTime: 30_000,
  })
}
