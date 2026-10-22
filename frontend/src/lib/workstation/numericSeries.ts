export interface NumericSeriesPayload {
  timestamps: string[]
  values: Array<number | null>
}

export function isStructuredNumericSeriesValue(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
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

/** Validate a structured series payload while leaving legacy value arrays distinct. */
export function normalizeStructuredNumericSeries(value: unknown): NumericSeriesPayload | null {
  if (!isStructuredNumericSeriesValue(value)) return null
  if (!Array.isArray(value.values) || !value.values.every(item => item === null || (typeof item === 'number' && Number.isFinite(item)))) return null
  return normalizeNumericSeries(value.timestamps, value.values)
}
