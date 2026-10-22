import { describe, expect, it } from 'vitest'
import { normalizeNumericSeries, normalizeStructuredNumericSeries } from '@/lib/workstation/numericSeries'

describe('normalizeNumericSeries', () => {
  it('preserves aligned valid timestamps, finite values, and explicit gaps', () => {
    expect(normalizeNumericSeries(
      ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'],
      [1.5, null],
    )).toEqual({
      timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'],
      values: [1.5, null],
    })
  })

  it('turns malformed numeric values into explicit gaps without allowing non-finite data', () => {
    expect(normalizeNumericSeries(
      ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z'],
      [1, Number.NaN, 'not-a-number'],
    )).toEqual({
      timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z'],
      values: [1, null, null],
    })
  })

  it('rejects malformed timestamps, misalignment, and all-missing observations', () => {
    expect(normalizeNumericSeries(['not-a-date'], [1])).toBeNull()
    expect(normalizeNumericSeries(['2026-01-01T00:00:00Z'], [1, 2])).toBeNull()
    expect(normalizeNumericSeries(['2026-01-01T00:00:00Z'], [null])).toBeNull()
  })

  it('validates structured axes with the same rules used for rendering', () => {
    expect(normalizeStructuredNumericSeries({
      timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'],
      values: [1.5, null],
    })).toEqual({
      timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'],
      values: [1.5, null],
    })
    expect(normalizeStructuredNumericSeries({ timestamps: ['not-a-date'], values: [1] })).toBeNull()
    expect(normalizeStructuredNumericSeries({ timestamps: ['2026-01-01T00:00:00Z'], values: [null] })).toBeNull()
    expect(normalizeStructuredNumericSeries([1, 2])).toBeNull()
  })

  it.each([
    ['string observation', [1, 'not-a-number']],
    ['Boolean observation', [1, true]],
    ['non-finite observation', [1, Number.POSITIVE_INFINITY]],
  ])('rejects structured series with a malformed %s', (_case, values) => {
    expect(normalizeStructuredNumericSeries({
      timestamps: ['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z'],
      values,
    })).toBeNull()
  })
})
