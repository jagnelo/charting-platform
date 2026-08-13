export type WorkstationFreshnessKind =
  | 'current'
  | 'delayed'
  | 'stale'
  | 'partial'
  | 'coverage-limited'
  | 'fetching'
  | 'unavailable'

export interface WorkstationFreshnessInput {
  freshness?: string | null
  freshness_detail?: Record<string, number> | null
  isLoading?: boolean
  isFetchingHistory?: boolean
  hasBars?: boolean
}

export interface WorkstationFreshnessState {
  kind: WorkstationFreshnessKind
  label: string
}

/** Normalize backend freshness values to the workstation's hyphenated vocabulary. */
export function normalizeWorkstationFreshness(value?: string | null): string {
  return String(value ?? '').toLowerCase().replace(/_/g, '-')
}

/** Render backend freshness values consistently in dense tool metadata. */
export function formatWorkstationFreshness(value?: string | null): string {
  const normalized = normalizeWorkstationFreshness(value)
  const labels: Record<string, string> = {
    current: 'Current',
    delayed: 'Delayed',
    stale: 'Stale',
    partial: 'Partial coverage',
    'coverage-limited': 'Coverage limited',
    fetching: 'Fetching',
    unavailable: 'Unavailable',
  }
  return labels[normalized] ?? (normalized ? normalized.replace(/-/g, ' ').replace(/\b\w/g, character => character.toUpperCase()) : 'Unavailable')
}

/**
 * Convert canonical backend freshness into the small, honest status vocabulary
 * used by the dense workstation shell. `current` means current according to
 * the canonical dataset's entitlement/freshness policy; it never implies a
 * consolidated real-time quote. A delayed state is accepted for future
 * provider capabilities without guessing it from a timestamp.
 */
export function workstationFreshness(input: WorkstationFreshnessInput): WorkstationFreshnessState {
  if (input.isLoading || input.isFetchingHistory) return { kind: 'fetching', label: input.isFetchingHistory ? 'Backfilling history' : 'Fetching' }
  // Backend analysis contracts historically use snake_case while the shell's
  // CSS/state vocabulary uses the documented hyphenated form. Normalize both
  // spellings at this boundary so coverage limits cannot be misreported as
  // stale or unavailable data.
  const freshness = normalizeWorkstationFreshness(input.freshness)
  if (freshness === 'delayed') return { kind: 'delayed', label: 'Delayed' }
  if (freshness === 'current') return { kind: 'current', label: 'Current · canonical' }
  if (freshness === 'stale') return { kind: 'stale', label: 'Stale · cached' }
  if (freshness === 'partial') return { kind: 'partial', label: 'Partial coverage' }
  if (freshness === 'coverage-limited') return { kind: 'coverage-limited', label: 'Coverage limited' }
  const detail = input.freshness_detail ?? {}
  if (Number(detail.other ?? 0) > 0 && Number(detail.current ?? 0) === 0) {
    return { kind: 'coverage-limited', label: 'Coverage limited' }
  }
  if (input.hasBars) return { kind: 'stale', label: 'Stale · local observations' }
  return { kind: 'unavailable', label: 'Unavailable' }
}
