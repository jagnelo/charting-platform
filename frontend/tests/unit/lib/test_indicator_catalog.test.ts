/**
 * Unit tests for the indicator catalog utilities.
 *
 * Covers: indicatorDefaultPane, cloneDefaultIndicator, indicatorDisplayName,
 * and the INDICATOR_CATALOG data integrity invariants.
 */
import { describe, it, expect } from 'vitest'
import {
  INDICATOR_CATALOG,
  indicatorDefaultPane,
  cloneDefaultIndicator,
  indicatorDisplayName,
} from '@/lib/indicators/catalog'
import type { IndicatorType } from '@/types'

// ── indicatorDefaultPane ──────────────────────────────────────────────────────

describe('indicatorDefaultPane — main-pane indicators', () => {
  const mainPaneTypes: IndicatorType[] = [
    'sma', 'ema', 'wma', 'hma', 'dema', 'tema',
    'bb', 'keltner', 'donchian',
    'vwap', 'avwap',
    'volume',          // volume renders on main pane as a sub-series
    'psar', 'ichimoku',
    'pivot_points',
  ]

  for (const type of mainPaneTypes) {
    it(`${type} → 'main'`, () => {
      expect(indicatorDefaultPane(type)).toBe('main')
    })
  }
})

describe('indicatorDefaultPane — sub-pane indicators', () => {
  const subPaneTypes: IndicatorType[] = [
    'rsi', 'macd', 'stoch', 'adx', 'aroon',
    'cci', 'williams_r', 'mfi', 'roc', 'momentum',
    'stddev', 'cmf', 'obv', 'atr',
    'trix', 'ppo',
    'volume_ratio',
  ]

  for (const type of subPaneTypes) {
    it(`${type} → 'separate'`, () => {
      expect(indicatorDefaultPane(type)).toBe('separate')
    })
  }
})

// ── cloneDefaultIndicator ─────────────────────────────────────────────────────

describe('cloneDefaultIndicator', () => {
  it('returns an object with the correct type', () => {
    const cfg = cloneDefaultIndicator('sma')
    expect(cfg.type).toBe('sma')
  })

  it('clones params — mutations do not affect subsequent calls', () => {
    const a = cloneDefaultIndicator('ema')
    const b = cloneDefaultIndicator('ema')
    a.params.period = 999
    expect(b.params.period).not.toBe(999)
  })

  it('clones style — mutations do not affect subsequent calls', () => {
    const a = cloneDefaultIndicator('sma')
    const b = cloneDefaultIndicator('sma')
    a.style.color = '#deadff'
    expect(b.style.color).not.toBe('#deadff')
  })

  it('returns pane = main for sma', () => {
    expect(cloneDefaultIndicator('sma').pane).toBe('main')
  })

  it('returns pane = separate for rsi', () => {
    expect(cloneDefaultIndicator('rsi').pane).toBe('separate')
  })

  it('avwap anchor_timestamp is a recent unix timestamp (>0 and in the past)', () => {
    const cfg = cloneDefaultIndicator('avwap')
    const now = Math.floor(Date.now() / 1000)
    expect(typeof cfg.params.anchor_timestamp).toBe('number')
    expect(cfg.params.anchor_timestamp as number).toBeGreaterThan(0)
    expect(cfg.params.anchor_timestamp as number).toBeLessThanOrEqual(now)
  })
})

// ── indicatorDisplayName ──────────────────────────────────────────────────────

describe('indicatorDisplayName', () => {
  it('sma(20) → "SMA(20)"', () => {
    expect(indicatorDisplayName({ type: 'sma', params: { period: 20 } })).toBe('SMA(20)')
  })

  it('ema(50) → "EMA(50)"', () => {
    expect(indicatorDisplayName({ type: 'ema', params: { period: 50 } })).toBe('EMA(50)')
  })

  it('macd(12,26,9) → "MACD(12,26,9)"', () => {
    expect(indicatorDisplayName({ type: 'macd', params: { fast: 12, slow: 26, signal: 9 } }))
      .toBe('MACD(12,26,9)')
  })

  it('vwap → "VWAP" (no params)', () => {
    expect(indicatorDisplayName({ type: 'vwap', params: {} })).toBe('VWAP')
  })

  it('avwap includes formatted date', () => {
    // Fixed anchor: 2024-01-15T00:00:00Z
    const anchor = new Date('2024-01-15T00:00:00Z').getTime() / 1000
    const name = indicatorDisplayName({ type: 'avwap', params: { anchor_timestamp: anchor } })
    expect(name).toMatch(/^AVWAP\(2024-01-/)
  })
})

// ── INDICATOR_CATALOG integrity ───────────────────────────────────────────────

describe('INDICATOR_CATALOG data integrity', () => {
  it('every entry has a non-empty type', () => {
    for (const item of INDICATOR_CATALOG) {
      expect(item.type).toBeTruthy()
    }
  })

  it('every entry has a defaultConfig with matching type', () => {
    for (const item of INDICATOR_CATALOG) {
      expect(item.defaultConfig.type).toBe(item.type)
    }
  })

  it('every defaultConfig has a pane field', () => {
    for (const item of INDICATOR_CATALOG) {
      expect(['main', 'separate']).toContain(item.defaultConfig.pane)
    }
  })

  it('every defaultConfig has a style with color and lineWidth', () => {
    for (const item of INDICATOR_CATALOG) {
      expect(typeof item.defaultConfig.style.color).toBe('string')
      expect(typeof item.defaultConfig.style.lineWidth).toBe('number')
    }
  })

  it('no duplicate types', () => {
    const types = INDICATOR_CATALOG.map(i => i.type)
    const unique = new Set(types)
    expect(unique.size).toBe(types.length)
  })
})
