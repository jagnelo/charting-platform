import type { QueryClient } from '@tanstack/vue-query'
import { api, setQueuedApiRequestPriority, type ApiRequestOptions } from '@/lib/api'
import type { Instrument } from '@/types'
import { instrumentLookupQueueKey } from '@/lib/instruments'

export type CanonicalInstrument = Instrument

export const INSTRUMENT_QUERY_ROOT = ['workstation', 'instrument'] as const

export function fetchCanonicalInstrument(
  queryClient: QueryClient,
  symbol: string,
  options: Pick<ApiRequestOptions, 'priority' | 'signal' | 'foreground'> = {},
) {
  const normalized = symbol.trim().toUpperCase()
  const queueKey = instrumentLookupQueueKey(normalized, true)
  if (options.foreground && options.priority === 'high') setQueuedApiRequestPriority(queueKey, 'high', true)
  return queryClient.fetchQuery<CanonicalInstrument>({
    queryKey: [...INSTRUMENT_QUERY_ROOT, normalized],
    queryFn: () => api.get<CanonicalInstrument>(
      `/instruments/${encodeURIComponent(normalized)}`,
      { canonical_only: true },
      { ...options, priority: options.priority ?? 'high', queueKey },
    ),
    staleTime: 30_000,
  })
}
