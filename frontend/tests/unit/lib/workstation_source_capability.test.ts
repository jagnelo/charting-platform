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

  it('fails closed for missing or unrecognized ETF capability while retaining explicit historical availability', () => {
    const current = { source_kind: 'etf_holdings', provenance: { availability: 'current', usable_for_current_analysis: true } }
    const currentWithoutUsability = { source_kind: 'etf_holdings', provenance: { availability: 'current' } }
    const historical = { source_kind: 'etf_holdings', provenance: { availability: 'available' } }
    const notApplicable = { source_kind: 'etf_holdings', provenance: { availability: 'not_applicable' } }
    const unknown = { source_kind: 'etf_holdings', provenance: { availability: 'unknown' } }
    const unrecognized = { source_kind: 'etf_holdings', provenance: { availability: 'future_state' } }
    const missing = { source_kind: 'etf_holdings', provenance: {} }
    const pending = { source_kind: 'etf_holdings', provenance: { availability: 'holdings_snapshot_not_loaded' } }

    expect(sourceAvailability(current)).toBe('available')
    expect(sourceIsNotCurrent(current)).toBe(false)
    expect(sourceAvailability(currentWithoutUsability)).toBe('unavailable')
    expect(sourceIsNotCurrent(currentWithoutUsability)).toBe(true)
    expect(sourceAvailability(historical)).toBe('available')
    expect(sourceIsNotCurrent(historical)).toBe(false)
    expect(sourceAvailability(notApplicable)).toBe('unavailable')
    expect(sourceIsNotCurrent(notApplicable)).toBe(true)
    expect(sourceAvailability(unknown)).toBe('unavailable')
    expect(sourceIsNotCurrent(unknown)).toBe(true)
    expect(sourceAvailability(unrecognized)).toBe('unavailable')
    expect(sourceIsNotCurrent(unrecognized)).toBe(true)
    expect(sourceAvailability(missing)).toBe('unavailable')
    expect(sourceIsNotCurrent(missing)).toBe(true)
    expect(sourceAvailability(pending)).toBe('pending')
    expect(sourceIsNotCurrent(pending)).toBe(false)
    expect(sourceAvailabilitySuffix(missing)).toBe(' · Not current (unknown)')
  })

  it('preserves legacy selection behavior for non-ETF descriptors without capability metadata', () => {
    expect(sourceAvailability({})).toBe('available')
    expect(sourceIsNotCurrent({})).toBe(false)
  })

  it('includes state and failure class in the picker label', () => {
    const source = { provenance: { availability: 'stale', failure_class: 'provider_transport' } }
    expect(formatSourceFailureClass('provider_transport')).toBe('provider transport')
    expect(sourceIsNotCurrent(source)).toBe(true)
    expect(sourceAvailabilitySuffix(source)).toBe(' · Not current (stale) · provider transport')
  })

  it('uses explicit human labels for access and quota diagnostics', () => {
    expect(formatSourceFailureClass('authentication_required')).toBe('authentication required')
    expect(formatSourceFailureClass('access_denied')).toBe('access denied')
    expect(formatSourceFailureClass('quota_rate_limited')).toBe('quota/rate limited')
  })
})
