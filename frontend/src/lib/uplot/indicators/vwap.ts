/**
 * Volume Weighted Average Price (VWAP)
 * Resets at start of each trading day for intraday timeframes.
 */
export function computeVWAP(
  timestamps: number[],
  highs: number[],
  lows: number[],
  closes: number[],
  volumes: number[],
  resetDaily: boolean = true,
): (number | null)[] {
  const result: (number | null)[] = new Array(timestamps.length).fill(null)
  let cumPV = 0
  let cumVol = 0
  let lastDay = -1

  for (let i = 0; i < timestamps.length; i++) {
    const day = new Date(timestamps[i] * 1000).getUTCDate()
    if (resetDaily && day !== lastDay) {
      cumPV = 0
      cumVol = 0
      lastDay = day
    }
    const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3
    const vol = volumes[i] ?? 0
    cumPV += typicalPrice * vol
    cumVol += vol
    result[i] = cumVol > 0 ? cumPV / cumVol : closes[i]
  }
  return result
}

/**
 * Anchored VWAP — starts accumulating from a user-defined anchor timestamp.
 */
export function computeAVWAP(
  timestamps: number[],
  highs: number[],
  lows: number[],
  closes: number[],
  volumes: number[],
  anchorTimestamp: number,
): (number | null)[] {
  const result: (number | null)[] = new Array(timestamps.length).fill(null)
  let cumPV = 0
  let cumVol = 0
  let anchored = false

  for (let i = 0; i < timestamps.length; i++) {
    if (!anchored && timestamps[i] >= anchorTimestamp) anchored = true
    if (!anchored) continue
    const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3
    const vol = volumes[i] ?? 0
    cumPV += typicalPrice * vol
    cumVol += vol
    result[i] = cumVol > 0 ? cumPV / cumVol : closes[i]
  }
  return result
}
