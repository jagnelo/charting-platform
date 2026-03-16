/**
 * Exponential Moving Average computation
 */
export function computeEMA(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null)
  const k = 2 / (period + 1)
  let ema: number | null = null

  for (let i = 0; i < closes.length; i++) {
    if (ema === null) {
      if (i >= period - 1) {
        let sum = 0
        for (let j = i - period + 1; j <= i; j++) sum += closes[j]
        ema = sum / period
        result[i] = ema
      }
    } else {
      ema = closes[i] * k + ema * (1 - k)
      result[i] = ema
    }
  }
  return result
}
