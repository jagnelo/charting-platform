/**
 * Unit tests for frontend indicator implementations.
 * These mirror the backend indicator engine tests — both must agree.
 */
import { describe, it, expect } from 'vitest'
import { computeSMA } from '@/lib/uplot/indicators/sma'
import { computeEMA } from '@/lib/uplot/indicators/ema'
import { computeRSI } from '@/lib/uplot/indicators/rsi'
import { computeVWAP } from '@/lib/uplot/indicators/vwap'

const rising = (n: number, start = 100, step = 1): number[] =>
  Array.from({ length: n }, (_, i) => start + i * step)

const flat = (n: number, value = 100): number[] =>
  Array.from({ length: n }, () => value)

// ── SMA ───────────────────────────────────────────────────────────────────────

describe('computeSMA', () => {
  it('returns correct length', () => {
    expect(computeSMA(rising(30), 10)).toHaveLength(30)
  })

  it('first (period-1) values are null', () => {
    const result = computeSMA([1, 2, 3, 4, 5], 3)
    expect(result[0]).toBeNull()
    expect(result[1]).toBeNull()
    expect(result[2]).not.toBeNull()
  })

  it('basic average', () => {
    const result = computeSMA([1, 2, 3, 4, 5], 3)
    expect(result[2]).toBeCloseTo(2.0)
    expect(result[3]).toBeCloseTo(3.0)
    expect(result[4]).toBeCloseTo(4.0)
  })

  it('flat series equals the flat value', () => {
    const result = computeSMA(flat(30, 150), 10)
    const valid = result.filter(v => v !== null) as number[]
    expect(valid.every(v => Math.abs(v - 150) < 1e-9)).toBe(true)
  })

  it('period 1 equals input', () => {
    const closes = [10, 20, 30]
    expect(computeSMA(closes, 1)).toEqual(closes)
  })

  it('linear series SMA is linear', () => {
    const result = computeSMA(rising(20, 100, 1), 5)
    const valid = result.filter(v => v !== null) as number[]
    const diffs = valid.slice(1).map((v, i) => v - valid[i])
    expect(diffs.every(d => Math.abs(d - 1.0) < 1e-9)).toBe(true)
  })
})

// ── EMA ───────────────────────────────────────────────────────────────────────

describe('computeEMA', () => {
  it('returns correct length', () => {
    expect(computeEMA(rising(40), 12)).toHaveLength(40)
  })

  it('first (period-1) values are null', () => {
    const result = computeEMA([1, 2, 3, 4, 5], 3)
    expect(result[0]).toBeNull()
    expect(result[1]).toBeNull()
  })

  it('flat series converges to flat value', () => {
    const result = computeEMA(flat(50, 200), 10)
    const valid = result.filter(v => v !== null) as number[]
    expect(valid.every(v => Math.abs(v - 200) < 1e-6)).toBe(true)
  })

  it('EMA reacts faster than SMA on a spike', () => {
    const closes = [...flat(30, 100), ...flat(10, 200)]
    const ema = computeEMA(closes, 10)
    const sma = computeSMA(closes, 10)
    const lastEma = ema[ema.length - 1]!
    const lastSma = sma[sma.length - 1]!
    expect(lastEma).toBeGreaterThan(lastSma)
  })
})

// ── RSI ───────────────────────────────────────────────────────────────────────

describe('computeRSI', () => {
  it('returns correct length', () => {
    expect(computeRSI(rising(50), 14)).toHaveLength(50)
  })

  it('all-gains RSI approaches 100', () => {
    const result = computeRSI(rising(60, 100, 1), 14)
    const valid = result.filter(v => v !== null) as number[]
    expect(valid[valid.length - 1]).toBeGreaterThan(80)
  })

  it('all-losses RSI approaches 0', () => {
    const falling = Array.from({ length: 60 }, (_, i) => 100 - i)
    const result = computeRSI(falling, 14)
    const valid = result.filter(v => v !== null) as number[]
    expect(valid[valid.length - 1]).toBeLessThan(20)
  })

  it('values are in [0, 100]', () => {
    const rng = Array.from({ length: 100 }, (_, i) => 100 + Math.sin(i * 0.3) * 20)
    const result = computeRSI(rng, 14)
    const valid = result.filter(v => v !== null) as number[]
    expect(valid.every(v => v >= 0 && v <= 100)).toBe(true)
  })
})

// ── VWAP ──────────────────────────────────────────────────────────────────────

describe('computeVWAP', () => {
  const ts = Array.from({ length: 20 }, (_, i) =>
    new Date(2024, 0, 1).getTime() / 1000 + i * 86400
  )
  const n = 20
  const highs  = flat(n, 101)
  const lows   = flat(n, 99)
  const closes = flat(n, 100)
  const vols   = flat(n, 1_000_000)

  it('returns correct length', () => {
    expect(computeVWAP(ts, highs, lows, closes, vols)).toHaveLength(n)
  })

  it('flat price and equal volume equals price', () => {
    const result = computeVWAP(ts, highs, lows, closes, vols)
    const valid = result.filter(v => v !== null) as number[]
    // TP = (101 + 99 + 100) / 3 = 100
    expect(valid.every(v => Math.abs(v - 100) < 1e-6)).toBe(true)
  })
})
