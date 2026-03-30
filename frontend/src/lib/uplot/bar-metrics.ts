import type uPlot from 'uplot'

export function getBarSpacingPx(u: uPlot): number {
  const dpr = devicePixelRatio || 1
  const p0 = u.valToPos(0, 'x', true)
  const p1 = u.valToPos(1, 'x', true)
  const spacing = Math.abs(p1 - p0)
  return Number.isFinite(spacing) && spacing > 0 ? spacing : 8 * dpr
}

export function getBodyWidthPx(u: uPlot, fillRatio = 0.78, minGapPx = 2): number {
  const dpr = devicePixelRatio || 1
  const spacing = getBarSpacingPx(u)
  const desired = Math.round(spacing * fillRatio)
  const maxWidth = Math.max(1, Math.floor(spacing - minGapPx * dpr))
  return Math.max(1, Math.min(desired, maxWidth))
}