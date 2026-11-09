import type { QueryClient } from '@tanstack/vue-query'
import { setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'

export type InstrumentCalendarStatusValue =
  | 'not_requested' | 'queued' | 'running' | 'deferred' | 'ready' | 'partial' | 'held' | 'unavailable' | 'stale'

export interface InstrumentCalendarStatus {
  version: 1
  status: InstrumentCalendarStatusValue
  has_pending_work: boolean
  retry_at: string | null
  reason_code: string | null
  updated_at: string | null
}

const instrumentCalendarQueryKey = (symbol: string, start: string, end: string) => [
  'workstation', 'instrument-calendar', symbol.trim().toUpperCase(), start, end,
] as const

export const instrumentCalendarStatusQueryKey = (symbol: string, sessionEpoch: number, instrumentId?: number | null) => [
  'workstation', 'instrument-calendar-status', symbol.trim().toUpperCase(), instrumentId ?? null, sessionEpoch,
] as const

export function isCurrentInstrumentCalendarContext(
  capturedSymbol: string,
  currentSymbol: string,
  capturedSessionEpoch: number,
  currentSessionEpoch: number,
  capturedInstrumentId?: number | null,
  currentInstrumentId?: number | null,
): boolean {
  return capturedSymbol.trim().toUpperCase() === currentSymbol.trim().toUpperCase()
    && capturedSessionEpoch === currentSessionEpoch
    && (capturedInstrumentId === undefined || capturedInstrumentId === currentInstrumentId)
}

/** A ready/partial status is useful only when it carries real producer progress. */
export function shouldRefreshInstrumentCalendar(
  previous: InstrumentCalendarStatus | null,
  next: InstrumentCalendarStatus | null | undefined,
): boolean {
  if (!next || !['ready', 'partial'].includes(next.status) || !next.updated_at) return false
  const nextStamp = Date.parse(next.updated_at)
  if (!Number.isFinite(nextStamp)) return false
  if (!previous) return true
  if (previous.has_pending_work && !next.has_pending_work) return true
  const previousStamp = previous.updated_at ? Date.parse(previous.updated_at) : Number.NaN
  return !Number.isFinite(previousStamp) || nextStamp > previousStamp
}

/** Poll cadence is a read schedule; provider retry deadlines always come from the API. */
export function instrumentCalendarStatusRefetchInterval(
  status: InstrumentCalendarStatus | null | undefined,
  now = Date.now(),
): number | false {
  if (status?.retry_at) {
    const retryAt = Date.parse(status.retry_at)
    if (Number.isFinite(retryAt) && retryAt > now) return retryAt - now
  }
  return status?.has_pending_work ? 2_000 : 15_000
}

export interface InstrumentCalendarRequestPriority {
  priority: ApiRequestPriority
  queueKey: string
  refresh?: boolean
}

/** Share same-context calendar reads across docked chart remounts. */
export function fetchInstrumentCalendar<T>(
  queryClient: QueryClient,
  symbol: string,
  start: string,
  end: string,
  load: (signal: AbortSignal) => Promise<T>,
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
    queryFn: ({ signal }) => load(signal),
    staleTime: requestPriority?.refresh ? 0 : 60_000,
  })
}

export async function invalidateInstrumentCalendar(
  queryClient: QueryClient,
  symbol: string,
  start: string,
  end: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: instrumentCalendarQueryKey(symbol, start, end),
    exact: true,
    refetchType: 'none',
  })
}
