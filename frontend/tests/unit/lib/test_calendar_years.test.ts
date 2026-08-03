import { describe, expect, it } from 'vitest'
import { calendarYearKeys } from '@/lib/workstation/calendarYears'

describe('calendarYearKeys', () => {
  it('returns sorted distinct years from canonical snapshot cells', () => {
    expect(calendarYearKeys([
      { calendar_year_performance: { '2026': {}, '2024': {}, '2025': {} } },
      { calendar_year_performance: { '2025': {}, invalid: {} } },
    ])).toEqual([2024, 2025, 2026])
  })
})
