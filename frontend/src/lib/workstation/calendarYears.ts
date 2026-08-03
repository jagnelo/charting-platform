export interface CalendarYearPerformanceRow {
  calendar_year_performance?: Record<string, unknown>
}

export function calendarYearKeys(rows: CalendarYearPerformanceRow[]): number[] {
  const years = new Set<number>()
  for (const row of rows) {
    for (const key of Object.keys(row.calendar_year_performance ?? {})) {
      const year = Number(key)
      if (Number.isInteger(year)) years.add(year)
    }
  }
  return [...years].sort((left, right) => left - right)
}
