import { describe, expect, it } from 'vitest'

import { computeMACD } from '@/lib/uplot/indicators/macd'
import { computeAVWAP, computeVWAP } from '@/lib/uplot/indicators/vwap'
import {
  computeADX,
  computeAroon,
  computeATR,
  computeBB,
  computeCCI,
  computeCMF,
  computeDEMA,
  computeDonchian,
  computeHMA,
  computeIchimoku,
  computeKeltner,
  computeMFI,
  computeMomentum,
  computeOBV,
  computePivotPoints,
  computePPO,
  computePSAR,
  computeROC,
  computeStdDev,
  computeStoch,
  computeTEMA,
  computeTRIX,
  computeVolumeRatio,
  computeWMA,
  computeWilliamsR,
} from '@/lib/uplot/indicators/all'

const closes = [10, 11, 12, 11, 13, 14, 13, 15, 16, 17, 18, 19]
const highs = [11, 12, 13, 12, 14, 15, 14, 16, 17, 18, 19, 20]
const lows = [9, 10, 11, 10, 12, 13, 12, 14, 15, 16, 17, 18]
const volumes = [100, 110, 90, 120, 130, 140, 115, 150, 160, 170, 180, 190]
const timestamps = [
  1_700_000_000, 1_700_003_600, 1_700_007_200, 1_700_010_800,
  1_700_014_400, 1_700_018_000, 1_700_086_400, 1_700_090_000,
  1_700_093_600, 1_700_097_200, 1_700_100_800, 1_700_104_400,
]

describe('extended indicator computation suite', () => {
  it('computes moving-average families and momentum oscillators', () => {
    expect(computeWMA(closes, 3)).toHaveLength(closes.length)
    expect(computeHMA(closes, 4)).toHaveLength(closes.length)
    expect(computeDEMA(closes, 3)).toHaveLength(closes.length)
    expect(computeTEMA(closes, 3)).toHaveLength(closes.length)
    expect(computeROC(closes, 3).at(-1)).not.toBeNull()
    expect(computeMomentum(closes, 3).at(-1)).toBe(3)
    expect(computeStdDev(closes, 3).at(-1)).not.toBeNull()
    expect(computeTRIX(closes, 3)).toHaveLength(closes.length)
    expect(computePPO(closes, 3, 5)).toHaveLength(closes.length)
  })

  it('computes channel and trend indicators', () => {
    const atr = computeATR(highs, lows, closes, 3)
    const bb = computeBB(closes, 3, 2)
    const keltner = computeKeltner(highs, lows, closes, 3, 3, 2)
    const donchian = computeDonchian(highs, lows, 3)
    const psar = computePSAR(highs, lows)
    const ichimoku = computeIchimoku(highs, lows, closes, 3, 4, 5, 2)
    const pivots = computePivotPoints(highs, lows, closes, 'fibonacci')

    expect(atr.at(-1)).not.toBeNull()
    expect(bb.upper.at(-1)).not.toBeNull()
    expect(keltner.upper.at(-1)).not.toBeNull()
    expect(donchian.mid.at(-1)).not.toBeNull()
    expect(psar.at(-1)).not.toBeNull()
    expect(ichimoku.tenkanLine).toHaveLength(closes.length)
    expect(pivots.pp[1]).not.toBeNull()
  })

  it('computes volume and breadth style indicators', () => {
    expect(computeOBV(closes, volumes).at(-1)).not.toBeNull()
    expect(computeVolumeRatio(volumes, 3).at(-1)).not.toBeNull()
    expect(computeCCI(highs, lows, closes, 3).at(-1)).not.toBeNull()
    expect(computeWilliamsR(highs, lows, closes, 3).at(-1)).not.toBeNull()
    expect(computeMFI(highs, lows, closes, volumes, 3).at(-1)).not.toBeNull()
    expect(computeCMF(highs, lows, closes, volumes, 3).at(-1)).not.toBeNull()
    expect(computeAroon(highs, lows, 3).up.at(-1)).not.toBeNull()
  })

  it('computes ADX, stochastic, MACD, VWAP, and AVWAP', () => {
    const adx = computeADX(highs, lows, closes, 3)
    const stoch = computeStoch(highs, lows, closes, 3, 2, 2)
    const macd = computeMACD(closes, 3, 5, 2)
    const vwap = computeVWAP(timestamps, highs, lows, closes, volumes)
    const avwap = computeAVWAP(timestamps, highs, lows, closes, volumes, timestamps[4])

    expect(adx.adx).toHaveLength(closes.length)
    expect(adx.plus_di.at(-1)).not.toBeNull()
    expect(stoch.k.at(-1)).not.toBeNull()
    expect(macd.histogram).toHaveLength(closes.length)
    expect(vwap.at(0)).toBeCloseTo(10)
    expect(avwap.slice(0, 4).every(v => v === null)).toBe(true)
    expect(avwap.at(-1)).not.toBeNull()
  })
})
