import { ApiError } from '@/lib/api'

export type TerminalResearchRunStatus = 'completed' | 'failed' | 'canceled'

const TERMINAL_STATUSES = new Set<TerminalResearchRunStatus>(['completed', 'failed', 'canceled'])

/**
 * A cancel request can lose a race to the worker finishing the run. Recognize
 * only the API's typed terminal conflict for this exact run-cancel endpoint;
 * ordinary 409s and all other API failures remain errors for the caller.
 */
export function terminalStatusFromCancelConflict(error: unknown, runId: number): TerminalResearchRunStatus | null {
  if (!(error instanceof ApiError)) return null
  const apiError = error
  const expectedPath = `/research/runs/${runId}/cancel`
  if (apiError.status !== 409 || apiError.method !== 'POST' || apiError.path !== expectedPath) return null

  const bodyMarker = ': '
  const markerIndex = error.message.indexOf(bodyMarker)
  if (markerIndex < 0) return null
  try {
    const body = JSON.parse(error.message.slice(markerIndex + bodyMarker.length)) as {
      detail?: { code?: unknown; status?: unknown }
    }
    const detail = body?.detail
    if (detail?.code !== 'research_run_terminal' || !TERMINAL_STATUSES.has(detail.status as TerminalResearchRunStatus)) return null
    return detail.status as TerminalResearchRunStatus
  } catch {
    return null
  }
}

/**
 * Confirm the server's terminal-conflict payload against the canonical run
 * endpoint. Never convert a conflict into a locally invented canceled state.
 */
export async function readTerminalRunAfterCancelConflict<T extends { id: number; status: string }>(
  error: unknown,
  runId: number,
  readRun: () => Promise<T | null | undefined>,
): Promise<T | null> {
  const reportedStatus = terminalStatusFromCancelConflict(error, runId)
  if (!reportedStatus) return null

  const current = await readRun()
  if (!current || current.id !== runId || current.status !== reportedStatus) {
    throw new Error(`The cancel request reported ${reportedStatus}, but the current run status could not be confirmed.`)
  }
  return current
}
