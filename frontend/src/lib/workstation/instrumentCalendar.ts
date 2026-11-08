import type { QueryClient } from '@tanstack/vue-query'
import { setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'

const instrumentCalendarQueryKey = (symbol: string, start: string, end: string) => [
  'workstation', 'instrument-calendar', symbol.trim().toUpperCase(), start, end,
] as const

export interface InstrumentCalendarRequestPriority {
  priority: ApiRequestPriority
  queueKey: string
}

/** Share same-context calendar reads across docked chart remounts. */
export function fetchInstrumentCalendar<T>(
  queryClient: QueryClient,
  symbol: string,
  start: string,
  end: string,
  load: () => Promise<T>,
  requestPriority?: InstrumentCalendarRequestPriority,
): Promise<T> {
  if (requestPriority?.priority === 'high') {
    // A hidden chart may have started the shared exact-range read first. Once
    // the chart becomes visible, promote that same queued request instead of
    // allocating a duplicate calendar GET behind foreground work.
    setQueuedApiRequestPriority(requestPriority.queueKey, 'high')
  }
  return queryClient.fetchQuery({
    queryKey: instrumentCalendarQueryKey(symbol, start, end),
    queryFn: load,
    staleTime: 60_000,
  })
}
