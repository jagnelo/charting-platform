import { describe, expect, it } from 'vitest'
import {
  formatSourceFailureClass,
  sourceAvailability,
  sourceAvailabilitySuffix,
  sourceIsNotCurrent,
} from '@/lib/workstation/sourceCapability'

describe('watchlist source capability state', () => {
  it.each([
    ['stale', 'unavailable'],
    ['degraded', 'unavailable'],
    ['unknown', 'unavailable'],
    ['unavailable', 'unavailable'],
    ['holdings_snapshot_not_loaded', 'pending'],
    ['holdings_snapshot_unresolved', 'pending'],
    ['available', 'available'],
  ] as const)('classifies %s as %s', (availability, expected) => {
    expect(sourceAvailability({ provenance: { availability } })).toBe(expected)
  })

  it('blocks explicitly non-current capabilities even when availability is omitted', () => {
    expect(sourceIsNotCurrent({ provenance: { usable_for_current_analysis: false } })).toBe(true)
    expect(sourceIsNotCurrent({ provenance: { availability: 'available', usable_for_current_analysis: true } })).toBe(false)
  })

  it('includes state and failure class in the picker label', () => {
    const source = { provenance: { availability: 'stale', failure_class: 'provider_transport' } }
    expect(formatSourceFailureClass('provider_transport')).toBe('provider transport')
    expect(sourceIsNotCurrent(source)).toBe(true)
    expect(sourceAvailabilitySuffix(source)).toBe(' · Not current (stale) · provider transport')
  })
})
