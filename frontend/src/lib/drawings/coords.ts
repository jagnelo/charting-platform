/**
 * Pure coordinate utilities for the bar-index ↔ timestamp conversion used by
 * the drawing system.  Extracted to a standalone module so they can be unit-
 * tested independently of the Vue component that owns the bar data.
 *
 * The key invariant: the mapping is continuous and has no derivative
 * discontinuity at the data/future boundary, so drawing drag is smooth when
 * a point crosses the last bar into the extrapolated future zone.
 */

/**
 * Returns the median successive gap between consecutive timestamps using up to
 * the last 40 samples.  Falls back to 86 400 s (one day) when fewer than two
 * bars are available or no finite positive differences are found.
 */
export function estimatedBarStep(timestamps: readonly number[]): number {
  if (timestamps.length < 2) return 86_400
  const samples: number[] = []
  for (let i = Math.max(1, timestamps.length - 40); i < timestamps.length; i++) {
    const diff = timestamps[i]! - timestamps[i - 1]!
    if (Number.isFinite(diff) && diff > 0) samples.push(diff)
  }
  if (!samples.length) return 86_400
  samples.sort((a, b) => a - b)
  return samples[Math.floor(samples.length / 2)]!
}

/**
 * Maps a unix timestamp to a fractional bar index.
 * - Before the first bar: linear extrapolation (result may be negative).
 * - Within the data range: linear interpolation between the surrounding pair.
 * - After the last bar: linear extrapolation (result > last index).
 */
export function drawingTimeToBarIndex(ts: number, timestamps: readonly number[]): number {
  if (!timestamps.length) return 0
  const first = timestamps[0]!
  const last  = timestamps[timestamps.length - 1]!
  const step  = estimatedBarStep(timestamps)
  if (ts <= first) return (ts - first) / step
  if (ts >= last)  return (timestamps.length - 1) + (ts - last) / step
  let lo = 0, hi = timestamps.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    if (timestamps[mid]! <= ts) lo = mid
    else hi = mid
  }
  return lo + (ts - timestamps[lo]!) / (timestamps[hi]! - timestamps[lo]!)
}

/**
 * Inverse of drawingTimeToBarIndex — maps a fractional bar index back to a
 * unix timestamp.  Provides a continuous, consistent coordinate space across
 * both the data region and the extrapolated future zone.
 */
export function barIndexToDrawingTime(idx: number, timestamps: readonly number[]): number {
  if (!timestamps.length) return 0
  const step = estimatedBarStep(timestamps)
  const last = timestamps.length - 1
  if (idx <= 0) return timestamps[0]! + idx * step
  if (idx >= last) return timestamps[last]! + (idx - last) * step
  const lo   = Math.floor(idx)
  const hi   = lo + 1
  const frac = idx - lo
  return timestamps[lo]! + frac * (timestamps[hi]! - timestamps[lo]!)
}
