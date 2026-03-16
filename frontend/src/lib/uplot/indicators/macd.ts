import { computeEMA } from './ema'

export interface MACDResult {
  macd: (number | null)[]
  signal: (number | null)[]
  histogram: (number | null)[]
}

export function computeMACD(
  closes: number[],
  fast = 12,
  slow = 26,
  signal = 9
): MACDResult {
  const fastEMA = computeEMA(closes, fast)
  const slowEMA = computeEMA(closes, slow)

  const macdLine: (number | null)[] = fastEMA.map((f, i) => {
    const s = slowEMA[i]
    return f != null && s != null ? f - s : null
  })

  const validMacd = macdLine.filter((v): v is number => v !== null)
  const signalRaw = computeEMA(validMacd, signal)

  // Re-align signal with original length
  const signalLine: (number | null)[] = []
  let signalIdx = 0
  for (const m of macdLine) {
    if (m === null) {
      signalLine.push(null)
    } else {
      signalLine.push(signalRaw[signalIdx] ?? null)
      signalIdx++
    }
  }

  const histogram: (number | null)[] = macdLine.map((m, i) => {
    const s = signalLine[i]
    return m != null && s != null ? m - s : null
  })

  return { macd: macdLine, signal: signalLine, histogram }
}
