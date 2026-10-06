const PROJECTION_STEP = 1.08
export const MAX_CHART_PROJECTION_STEPS = 20

export function normalizeChartProjectionSteps(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  return Math.max(0, Math.min(MAX_CHART_PROJECTION_STEPS, Math.trunc(value)))
}

/** Expand/contracts a price range around its midpoint, in the active scale space. */
export function adjustChartProjectionRange(
  min: number,
  max: number,
  steps: number,
  logarithmic = false,
): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max) return [min, max]
  const factor = PROJECTION_STEP ** steps
  if (logarithmic && min > 0) {
    const low = Math.log(min)
    const high = Math.log(max)
    const mid = (low + high) / 2
    const half = ((high - low) / 2) * factor
    return [Math.exp(mid - half), Math.exp(mid + half)]
  }
  const mid = (min + max) / 2
  const half = ((max - min) / 2) * factor
  return [mid - half, mid + half]
}
