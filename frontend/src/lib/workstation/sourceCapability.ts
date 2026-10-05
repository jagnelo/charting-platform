export type SourceCapabilityDescriptor = {
  source_kind?: string
  provenance?: Record<string, unknown> | null
}

export type SourceAvailability = 'available' | 'pending' | 'unavailable'

const PENDING_AVAILABILITIES = new Set([
  'profile_not_loaded',
  'holdings_snapshot_not_loaded',
  'holdings_snapshot_unresolved',
  'membership_not_loaded',
])

const NON_CURRENT_AVAILABILITIES = new Set(['unavailable', 'stale', 'degraded', 'unknown'])

export function sourceAvailability(source: SourceCapabilityDescriptor): SourceAvailability {
  const availability = String(source.provenance?.availability ?? '')
  if (PENDING_AVAILABILITIES.has(availability)) return 'pending'
  if (NON_CURRENT_AVAILABILITIES.has(availability)) return 'unavailable'
  if (source.source_kind === 'etf_holdings') {
    const usable = source.provenance?.usable_for_current_analysis
    if (availability === 'current') return usable === true ? 'available' : 'unavailable'
    if (availability === 'available' && usable !== false) return 'available'
    return 'unavailable'
  }
  return 'available'
}

export function sourceIsNotCurrent(source: SourceCapabilityDescriptor): boolean {
  const availability = String(source.provenance?.availability ?? '')
  if (source.source_kind === 'etf_holdings') {
    return sourceAvailability(source) === 'unavailable'
  }
  return source.provenance?.usable_for_current_analysis === false
    || NON_CURRENT_AVAILABILITIES.has(availability)
}

export function formatSourceFailureClass(value: unknown): string {
  const normalized = String(value ?? '')
  const labels: Record<string, string> = {
    access_denied: 'access denied',
    authentication_required: 'authentication required',
    quota_rate_limited: 'quota/rate limited',
  }
  return labels[normalized] ?? normalized.replace(/_/g, ' ')
}

export function sourceAvailabilitySuffix(source: SourceCapabilityDescriptor): string {
  const rawAvailability = String(source.provenance?.availability ?? '')
    || (source.source_kind === 'etf_holdings' ? 'unknown' : '')
  const availability = sourceAvailability(source)
  const failureClass = source.provenance?.failure_class
  const failureSuffix = failureClass ? ` · ${formatSourceFailureClass(failureClass)}` : ''
  if (availability === 'unavailable') {
    if (rawAvailability === 'unavailable') return ` · Unavailable${failureSuffix}`
    return ` · Not current (${formatSourceFailureClass(rawAvailability)})${failureSuffix}`
  }
  if (availability === 'pending') return ' · Pending membership'
  return ''
}
