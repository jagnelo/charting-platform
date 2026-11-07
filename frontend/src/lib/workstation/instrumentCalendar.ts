import type { QueryClient } from '@tanstack/vue-query'

const instrumentCalendarQueryKey = (symbol: string, start: string, end: string) => [
  'workstation', 'instrument-calendar', symbol.trim().toUpperCase(), start, end,
] as const

/** Share same-context calendar reads across docked chart remounts. */
export function fetchInstrumentCalendar<T>(
  queryClient: QueryClient,
  symbol: string,
  start: string,
  end: string,
  load: () => Promise<T>,
): Promise<T> {
  return queryClient.fetchQuery({
    queryKey: instrumentCalendarQueryKey(symbol, start, end),
    queryFn: load,
    staleTime: 60_000,
  })
}
