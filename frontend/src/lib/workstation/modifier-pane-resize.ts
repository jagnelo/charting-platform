export type PaneResizeSide = 'above' | 'below'

/**
 * Resize the panes on one side of a Golden Layout divider evenly while using
 * only the nearest pane on the opposite side as the counterweight.
 * `dividerIndex` identifies the pane immediately above the divider.
 */
export function resizePanesEvenly(
  sizes: number[],
  minimumSizes: number[],
  dividerIndex: number,
  requestedDelta: number,
  side: PaneResizeSide,
): number[] | null {
  if (sizes.length !== minimumSizes.length || sizes.length < 2) return null
  if (!Number.isInteger(dividerIndex) || dividerIndex < 0 || dividerIndex >= sizes.length - 1) return null
  if (!Number.isFinite(requestedDelta)
    || sizes.some(size => !Number.isFinite(size) || size <= 0)
    || minimumSizes.some(size => !Number.isFinite(size) || size < 0)) return null

  const selectedIndexes = side === 'above'
    ? Array.from({ length: dividerIndex + 1 }, (_, index) => index)
    : Array.from({ length: sizes.length - dividerIndex - 1 }, (_, index) => dividerIndex + index + 1)
  const counterweightIndex = side === 'above' ? dividerIndex + 1 : dividerIndex
  const pairIndexes = [...selectedIndexes, counterweightIndex]
  const pairTotal = pairIndexes.reduce((total, index) => total + sizes[index], 0)
  const selectedMinimum = selectedIndexes.reduce((total, index) => total + minimumSizes[index], 0)
  const counterweightMinimum = minimumSizes[counterweightIndex]
  const initialSelectedSize = selectedIndexes.reduce((total, index) => total + sizes[index], 0)
  const targetSelectedSize = side === 'above'
    ? initialSelectedSize + requestedDelta
    : initialSelectedSize - requestedDelta
  const boundedSelectedSize = Math.max(
    selectedMinimum,
    Math.min(pairTotal - counterweightMinimum, targetSelectedSize),
  )
  const evenSizes = distributeEvenly(boundedSelectedSize, selectedIndexes.map(index => minimumSizes[index]))
  if (!evenSizes) return null

  const next = [...sizes]
  selectedIndexes.forEach((index, selectedIndex) => { next[index] = evenSizes[selectedIndex] })
  next[counterweightIndex] = pairTotal - boundedSelectedSize
  return next
}

function distributeEvenly(total: number, minimumSizes: number[]): number[] | null {
  if (minimumSizes.length === 0) return null
  if (!Number.isFinite(total) || total < minimumSizes.reduce((sum, size) => sum + size, 0)) return null

  const result = Array<number>(minimumSizes.length).fill(0)
  let unresolved = minimumSizes.map((_, index) => index)
  let remaining = total
  while (unresolved.length > 0) {
    const share = remaining / unresolved.length
    const fixed = unresolved.filter(index => minimumSizes[index] > share)
    if (fixed.length === 0) {
      for (const index of unresolved) result[index] = share
      break
    }
    const fixedIndexes = new Set(fixed)
    for (const index of fixed) {
      result[index] = minimumSizes[index]
      remaining -= minimumSizes[index]
    }
    unresolved = unresolved.filter(index => !fixedIndexes.has(index))
  }
  return result
}
