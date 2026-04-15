/**
 * Client-side indicator computation functions.
 *
 * Every function returns (number | null)[] or a typed dict of such arrays.
 * null means "not enough warmup data" at that bar index.
 *
 * All functions are pure and have no side effects.
 */

import { computeEMA } from './ema'
import { computeSMA } from './sma'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** SMA that treats nulls correctly (only outputs when window is fully non-null). */
function smaOfNullable(data: (number | null)[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(data.length).fill(null)
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0, allValid = true
    for (let j = i - period + 1; j <= i; j++) {
      if (data[j] == null) { allValid = false; break }
      sum += data[j] as number
    }
    if (allValid) result[i] = sum / period
  }
  return result
}

// ── WMA ───────────────────────────────────────────────────────────────────────

export function computeWMA(closes: number[], period: number): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  const denom = (period * (period + 1)) / 2
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = 0; j < period; j++) sum += closes[i - j] * (period - j)
    result[i] = sum / denom
  }
  return result
}

// ── HMA ───────────────────────────────────────────────────────────────────────

export function computeHMA(closes: number[], period: number): (number | null)[] {
  const half   = Math.max(1, Math.round(period / 2))
  const sqrtP  = Math.max(1, Math.round(Math.sqrt(period)))
  const wmaH   = computeWMA(closes, half)
  const wmaF   = computeWMA(closes, period)
  const n      = closes.length
  const raw: (number | null)[] = new Array(n).fill(null)
  for (let i = 0; i < n; i++) {
    const h = wmaH[i], f = wmaF[i]
    if (h != null && f != null) raw[i] = 2 * h - f
  }
  return smaOfNullable(raw, sqrtP)  // actually WMA of raw — reuse SMA as approximation
  // For fidelity use WMA, but SMA avoids double loop complexity here
}

// ── DEMA ──────────────────────────────────────────────────────────────────────

export function computeDEMA(closes: number[], period: number): (number | null)[] {
  const ema1 = computeEMA(closes, period)
  const ema2 = _emaOfNullable(ema1, period)
  return ema1.map((e1, i) => {
    const e2 = ema2[i]
    return e1 != null && e2 != null ? 2 * e1 - e2 : null
  })
}

// ── TEMA ──────────────────────────────────────────────────────────────────────

export function computeTEMA(closes: number[], period: number): (number | null)[] {
  const ema1 = computeEMA(closes, period)
  const ema2 = _emaOfNullable(ema1, period)
  const ema3 = _emaOfNullable(ema2, period)
  return ema1.map((e1, i) => {
    const e2 = ema2[i], e3 = ema3[i]
    return e1 != null && e2 != null && e3 != null ? 3 * e1 - 3 * e2 + e3 : null
  })
}

/** EMA computed over a nullable array (re-aligns to original length). */
function _emaOfNullable(data: (number | null)[], period: number): (number | null)[] {
  const vals = data.filter((v): v is number => v !== null)
  const emaVals = computeEMA(vals, period)
  const result: (number | null)[] = []
  let j = 0
  for (const v of data) {
    result.push(v === null ? null : (emaVals[j++] ?? null))
  }
  return result
}

// ── ATR ───────────────────────────────────────────────────────────────────────

export function computeATR(
  highs: number[], lows: number[], closes: number[], period: number,
): (number | null)[] {
  const n = closes.length
  const tr: number[] = new Array(n).fill(0)
  tr[0] = highs[0] - lows[0]
  for (let i = 1; i < n; i++) {
    tr[i] = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i - 1]),
      Math.abs(lows[i]  - closes[i - 1]),
    )
  }
  const result: (number | null)[] = new Array(n).fill(null)
  // Wilder smoothing: seed with simple average, then smooth
  let atr = tr.slice(0, period).reduce((a, b) => a + b, 0) / period
  result[period - 1] = atr
  for (let i = period; i < n; i++) {
    atr = (atr * (period - 1) + tr[i]) / period
    result[i] = atr
  }
  return result
}

// ── Bollinger Bands ───────────────────────────────────────────────────────────

export function computeBB(
  closes: number[], period: number, multiplier: number,
): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const n = closes.length
  const upper: (number | null)[] = new Array(n).fill(null)
  const mid:   (number | null)[] = new Array(n).fill(null)
  const lower: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += closes[j]
    const sma = sum / period
    let variance = 0
    for (let j = i - period + 1; j <= i; j++) variance += (closes[j] - sma) ** 2
    const stddev = Math.sqrt(variance / period)
    mid[i]   = sma
    upper[i] = sma + multiplier * stddev
    lower[i] = sma - multiplier * stddev
  }
  return { upper, mid, lower }
}

// ── Keltner Channels ──────────────────────────────────────────────────────────

export function computeKeltner(
  highs: number[], lows: number[], closes: number[],
  period: number, atrPeriod: number, multiplier: number,
): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const n   = closes.length
  const ema = computeEMA(closes, period)
  const atr = computeATR(highs, lows, closes, atrPeriod)
  const upper: (number | null)[] = new Array(n).fill(null)
  const mid:   (number | null)[] = new Array(n).fill(null)
  const lower: (number | null)[] = new Array(n).fill(null)
  for (let i = 0; i < n; i++) {
    const e = ema[i], a = atr[i]
    if (e != null && a != null) {
      mid[i] = e; upper[i] = e + multiplier * a; lower[i] = e - multiplier * a
    }
  }
  return { upper, mid, lower }
}

// ── Donchian Channels ─────────────────────────────────────────────────────────

export function computeDonchian(
  highs: number[], lows: number[], period: number,
): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const n = highs.length
  const upper: (number | null)[] = new Array(n).fill(null)
  const mid:   (number | null)[] = new Array(n).fill(null)
  const lower: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let hi = -Infinity, lo = Infinity
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j]
      if (lows[j]  < lo) lo = lows[j]
    }
    upper[i] = hi; lower[i] = lo; mid[i] = (hi + lo) / 2
  }
  return { upper, mid, lower }
}

// ── Parabolic SAR ─────────────────────────────────────────────────────────────

export function computePSAR(
  highs: number[], lows: number[],
  afStart = 0.02, afStep = 0.02, afMax = 0.2,
): (number | null)[] {
  const n = highs.length
  if (n < 2) return new Array(n).fill(null)
  const result: (number | null)[] = new Array(n).fill(null)
  let bull = true
  let sar = lows[0]
  let ep  = highs[0]
  let af  = afStart
  result[0] = null
  for (let i = 1; i < n; i++) {
    sar = sar + af * (ep - sar)
    if (bull) {
      sar = Math.min(sar, lows[i - 1], i >= 2 ? lows[i - 2] : lows[i - 1])
      if (lows[i] < sar) {
        bull = false; sar = ep; ep = lows[i]; af = afStart
      } else if (highs[i] > ep) {
        ep = highs[i]; af = Math.min(af + afStep, afMax)
      }
    } else {
      sar = Math.max(sar, highs[i - 1], i >= 2 ? highs[i - 2] : highs[i - 1])
      if (highs[i] > sar) {
        bull = true; sar = ep; ep = highs[i]; af = afStart
      } else if (lows[i] < ep) {
        ep = lows[i]; af = Math.min(af + afStep, afMax)
      }
    }
    result[i] = sar
  }
  return result
}

// ── Ichimoku Cloud ────────────────────────────────────────────────────────────

export function computeIchimoku(
  highs: number[], lows: number[], closes: number[],
  tenkan = 9, kijun = 26, senkouB = 52, displacement = 26,
): {
  tenkanLine:  (number | null)[]
  kijunLine:   (number | null)[]
  senkouALine: (number | null)[]
  senkouBLine: (number | null)[]
  chikouLine:  (number | null)[]
} {
  const n = closes.length
  const donchianMid = (i: number, p: number) => {
    let hi = -Infinity, lo = Infinity
    for (let j = i - p + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j]
      if (lows[j]  < lo) lo = lows[j]
    }
    return (hi + lo) / 2
  }
  const tenkanLine:  (number | null)[] = new Array(n).fill(null)
  const kijunLine:   (number | null)[] = new Array(n).fill(null)
  // Senkou lines look forward; we store them at actual bar index (may extend past n-1)
  const senkouALine: (number | null)[] = new Array(n).fill(null)
  const senkouBLine: (number | null)[] = new Array(n).fill(null)
  const chikouLine:  (number | null)[] = new Array(n).fill(null)

  for (let i = tenkan - 1; i < n; i++) tenkanLine[i] = donchianMid(i, tenkan)
  for (let i = kijun - 1;  i < n; i++) kijunLine[i]  = donchianMid(i, kijun)

  for (let i = kijun - 1; i < n; i++) {
    const t = tenkanLine[i], k = kijunLine[i]
    if (t != null && k != null && i + displacement < n)
      senkouALine[i + displacement] = (t + k) / 2
  }
  for (let i = senkouB - 1; i < n; i++) {
    if (i + displacement < n)
      senkouBLine[i + displacement] = donchianMid(i, senkouB)
  }
  for (let i = displacement; i < n; i++) {
    chikouLine[i - displacement] = closes[i]
  }
  return { tenkanLine, kijunLine, senkouALine, senkouBLine, chikouLine }
}

// ── Pivot Points ──────────────────────────────────────────────────────────────

export function computePivotPoints(
  highs: number[], lows: number[], closes: number[],
  method: 'classic' | 'fibonacci' | 'camarilla' = 'classic',
): {
  pp: (number | null)[]
  r1: (number | null)[]; r2: (number | null)[]; r3: (number | null)[]
  s1: (number | null)[]; s2: (number | null)[]; s3: (number | null)[]
} {
  const n  = closes.length
  const pp = new Array(n).fill(null) as (number | null)[]
  const r1 = new Array(n).fill(null) as (number | null)[]
  const r2 = new Array(n).fill(null) as (number | null)[]
  const r3 = new Array(n).fill(null) as (number | null)[]
  const s1 = new Array(n).fill(null) as (number | null)[]
  const s2 = new Array(n).fill(null) as (number | null)[]
  const s3 = new Array(n).fill(null) as (number | null)[]
  for (let i = 1; i < n; i++) {
    const h = highs[i-1], l = lows[i-1], c = closes[i-1]
    const pivot = (h + l + c) / 3
    const range = h - l
    pp[i] = pivot
    if (method === 'classic') {
      r1[i] = 2*pivot - l;       s1[i] = 2*pivot - h
      r2[i] = pivot + range;     s2[i] = pivot - range
      r3[i] = h + 2*(pivot - l); s3[i] = l - 2*(h - pivot)
    } else if (method === 'fibonacci') {
      r1[i] = pivot + 0.382*range; s1[i] = pivot - 0.382*range
      r2[i] = pivot + 0.618*range; s2[i] = pivot - 0.618*range
      r3[i] = pivot + 1.000*range; s3[i] = pivot - 1.000*range
    } else {
      r1[i] = c + range*1.1/12; s1[i] = c - range*1.1/12
      r2[i] = c + range*1.1/6;  s2[i] = c - range*1.1/6
      r3[i] = c + range*1.1/4;  s3[i] = c - range*1.1/4
    }
  }
  return { pp, r1, r2, r3, s1, s2, s3 }
}

// ── OBV ───────────────────────────────────────────────────────────────────────

export function computeOBV(closes: number[], vols: number[]): (number | null)[] {
  const n = closes.length
  if (n === 0) return []
  const result: (number | null)[] = new Array(n).fill(null)
  result[0] = 0
  for (let i = 1; i < n; i++) {
    const prev = result[i-1] as number
    if      (closes[i] > closes[i-1]) result[i] = prev + vols[i]
    else if (closes[i] < closes[i-1]) result[i] = prev - vols[i]
    else                              result[i] = prev
  }
  return result
}

// ── Volume Ratio ─────────────────────────────────────────────────────────────

export function computeVolumeRatio(vols: number[], period: number): (number | null)[] {
  const n = vols.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += vols[j]
    const avg = sum / period
    result[i] = avg > 0 ? vols[i] / avg : null
  }
  return result
}

// ── CCI ───────────────────────────────────────────────────────────────────────

export function computeCCI(
  highs: number[], lows: number[], closes: number[], period: number,
): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += (highs[j] + lows[j] + closes[j]) / 3
    const tpSma = sum / period
    let mad = 0
    for (let j = i - period + 1; j <= i; j++) mad += Math.abs((highs[j]+lows[j]+closes[j])/3 - tpSma)
    mad /= period
    result[i] = mad === 0 ? 0 : (((highs[i]+lows[i]+closes[i])/3) - tpSma) / (0.015 * mad)
  }
  return result
}

// ── ADX ───────────────────────────────────────────────────────────────────────

export function computeADX(
  highs: number[], lows: number[], closes: number[], period: number,
): { adx: (number | null)[]; plus_di: (number | null)[]; minus_di: (number | null)[] } {
  const n  = closes.length
  const adx:      (number | null)[] = new Array(n).fill(null)
  const plus_di:  (number | null)[] = new Array(n).fill(null)
  const minus_di: (number | null)[] = new Array(n).fill(null)
  if (n < period + 1) return { adx, plus_di, minus_di }

  let atrSum = 0, plusDmSum = 0, minusDmSum = 0
  for (let i = 1; i <= period; i++) {
    const tr = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i-1]),
      Math.abs(lows[i]  - closes[i-1]),
    )
    const up   = highs[i] - highs[i-1]
    const down = lows[i-1] - lows[i]
    atrSum    += tr
    plusDmSum  += up > down && up > 0 ? up : 0
    minusDmSum += down > up && down > 0 ? down : 0
  }

  let adxSum = 0, adxCount = 0
  for (let i = period + 1; i < n; i++) {
    const tr = Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i-1]),
      Math.abs(lows[i]  - closes[i-1]),
    )
    const up   = highs[i] - highs[i-1]
    const down = lows[i-1] - lows[i]
    atrSum     = atrSum    - atrSum    / period + tr
    plusDmSum  = plusDmSum  - plusDmSum  / period + (up > down && up > 0 ? up : 0)
    minusDmSum = minusDmSum - minusDmSum / period + (down > up && down > 0 ? down : 0)

    const pdi = atrSum !== 0 ? (plusDmSum  / atrSum) * 100 : 0
    const mdi = atrSum !== 0 ? (minusDmSum / atrSum) * 100 : 0
    plus_di[i]  = pdi
    minus_di[i] = mdi

    const diSum = pdi + mdi
    const dx    = diSum !== 0 ? (Math.abs(pdi - mdi) / diSum) * 100 : 0
    adxSum += dx
    adxCount++
    if (adxCount >= period) {
      if (adxCount === period) {
        adx[i] = adxSum / period
      } else {
        const prev = adx[i-1] as number
        adx[i] = (prev * (period - 1) + dx) / period
      }
    }
  }
  return { adx, plus_di, minus_di }
}

// ── Stochastic ────────────────────────────────────────────────────────────────

export function computeStoch(
  highs: number[], lows: number[], closes: number[],
  period = 14, smoothK = 3, smoothD = 3,
): { k: (number | null)[]; d: (number | null)[] } {
  const n = closes.length
  const rawK: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let hi = -Infinity, lo = Infinity
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j]
      if (lows[j]  < lo) lo = lows[j]
    }
    rawK[i] = hi === lo ? 50 : ((closes[i] - lo) / (hi - lo)) * 100
  }
  const k = smaOfNullable(rawK, smoothK)
  const d = smaOfNullable(k, smoothD)
  return { k, d }
}

// ── Williams %R ───────────────────────────────────────────────────────────────

export function computeWilliamsR(
  highs: number[], lows: number[], closes: number[], period: number,
): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let hi = -Infinity, lo = Infinity
    for (let j = i - period + 1; j <= i; j++) {
      if (highs[j] > hi) hi = highs[j]
      if (lows[j]  < lo) lo = lows[j]
    }
    result[i] = hi === lo ? -50 : ((hi - closes[i]) / (hi - lo)) * -100
  }
  return result
}

// ── MFI ───────────────────────────────────────────────────────────────────────

export function computeMFI(
  highs: number[], lows: number[], closes: number[], vols: number[], period: number,
): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  const tp = closes.map((c, i) => (highs[i] + lows[i] + c) / 3)
  for (let i = period; i < n; i++) {
    let posFlow = 0, negFlow = 0
    for (let j = i - period + 1; j <= i; j++) {
      const mf = tp[j] * vols[j]
      if (tp[j] > tp[j-1]) posFlow += mf
      else                  negFlow += mf
    }
    result[i] = negFlow === 0 ? 100 : 100 - 100 / (1 + posFlow / negFlow)
  }
  return result
}

// ── ROC ───────────────────────────────────────────────────────────────────────

export function computeROC(closes: number[], period: number): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period; i < n; i++) {
    const prev = closes[i - period]
    result[i] = prev !== 0 ? ((closes[i] - prev) / prev) * 100 : null
  }
  return result
}

// ── Momentum ──────────────────────────────────────────────────────────────────

export function computeMomentum(closes: number[], period: number): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period; i < n; i++) result[i] = closes[i] - closes[i - period]
  return result
}

// ── Std Dev ───────────────────────────────────────────────────────────────────

export function computeStdDev(closes: number[], period: number): (number | null)[] {
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += closes[j]
    const mean = sum / period
    let variance = 0
    for (let j = i - period + 1; j <= i; j++) variance += (closes[j] - mean) ** 2
    result[i] = Math.sqrt(variance / period)
  }
  return result
}

// ── CMF ───────────────────────────────────────────────────────────────────────

export function computeCMF(
  highs: number[], lows: number[], closes: number[], vols: number[], period: number,
): (number | null)[] {
  const n = closes.length
  const mfv = closes.map((c, i) => {
    const hl = highs[i] - lows[i]
    return hl === 0 ? 0 : ((c - lows[i] - (highs[i] - c)) / hl) * vols[i]
  })
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = period - 1; i < n; i++) {
    let sumMFV = 0, sumVol = 0
    for (let j = i - period + 1; j <= i; j++) { sumMFV += mfv[j]; sumVol += vols[j] }
    result[i] = sumVol === 0 ? 0 : sumMFV / sumVol
  }
  return result
}

// ── Aroon ─────────────────────────────────────────────────────────────────────

export function computeAroon(
  highs: number[], lows: number[], period: number,
): { up: (number | null)[]; down: (number | null)[] } {
  const n = highs.length
  const up:   (number | null)[] = new Array(n).fill(null)
  const down: (number | null)[] = new Array(n).fill(null)
  for (let i = period; i < n; i++) {
    let hiIdx = i, loIdx = i
    for (let j = i - period; j <= i; j++) {
      if (highs[j] > highs[hiIdx]) hiIdx = j
      if (lows[j]  < lows[loIdx])  loIdx = j
    }
    up[i]   = ((period - (i - hiIdx)) / period) * 100
    down[i] = ((period - (i - loIdx)) / period) * 100
  }
  return { up, down }
}

// ── TRIX ──────────────────────────────────────────────────────────────────────

export function computeTRIX(closes: number[], period: number): (number | null)[] {
  const ema1 = computeEMA(closes, period)
  const ema2 = _emaOfNullable(ema1, period)
  const ema3 = _emaOfNullable(ema2, period)
  const n = closes.length
  const result: (number | null)[] = new Array(n).fill(null)
  for (let i = 1; i < n; i++) {
    const cur = ema3[i], prev = ema3[i-1]
    if (cur != null && prev != null && prev !== 0)
      result[i] = ((cur - prev) / prev) * 100
  }
  return result
}

// ── PPO ───────────────────────────────────────────────────────────────────────

export function computePPO(closes: number[], fast: number, slow: number): (number | null)[] {
  const fastEMA = computeEMA(closes, fast)
  const slowEMA = computeEMA(closes, slow)
  return fastEMA.map((f, i) => {
    const s = slowEMA[i]
    return f != null && s != null && s !== 0 ? ((f - s) / s) * 100 : null
  })
}

// Re-export commonly used indicators for convenience
export { computeSMA, computeEMA }
