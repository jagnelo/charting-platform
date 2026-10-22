const PROJECTION_STEP = 1.08
export const MAX_CHART_PROJECTION_STEPS = 20
const LATEST_RANGE_TOLERANCE = 0.08

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

/**
 * Whether a requested chart range still reaches the latest bar.
 *
 * uPlot batches scale commits, so interaction handlers must derive this state
 * from the clamped range they requested rather than immediately reading
 * `u.scales.x`, which can still describe the previous frame.
 */
export function isChartRangeAtLatest(max: number, latest: number, span: number): boolean {
  if (![max, latest, span].every(Number.isFinite) || span < 0) return false
  return max >= latest - span * LATEST_RANGE_TOLERANCE
}
