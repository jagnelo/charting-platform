export interface NumericSeriesPayload {
  timestamps: string[]
  values: Array<number | null>
}

/** Validate an axes-based numeric series before it reaches uPlot. */
export function normalizeNumericSeries(timestamps: unknown, values: unknown): NumericSeriesPayload | null {
  if (!Array.isArray(timestamps) || !Array.isArray(values) || timestamps.length === 0 || timestamps.length !== values.length) return null
  if (!timestamps.every(timestamp => typeof timestamp === 'string' && Number.isFinite(Date.parse(timestamp)))) return null
  const normalized = values.map(value => {
    if (value == null) return null
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  })
  if (!normalized.some(value => value != null)) return null
  return { timestamps: timestamps as string[], values: normalized }
}
