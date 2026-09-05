export type SourceCapabilityDescriptor = {
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
  return 'available'
}

export function sourceIsNotCurrent(source: SourceCapabilityDescriptor): boolean {
  const availability = String(source.provenance?.availability ?? '')
  return source.provenance?.usable_for_current_analysis === false
    || NON_CURRENT_AVAILABILITIES.has(availability)
}

export function formatSourceFailureClass(value: unknown): string {
  return String(value ?? '').replace(/_/g, ' ')
}

export function sourceAvailabilitySuffix(source: SourceCapabilityDescriptor): string {
  const rawAvailability = String(source.provenance?.availability ?? '')
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
