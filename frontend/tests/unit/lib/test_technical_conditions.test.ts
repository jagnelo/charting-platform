import { describe, expect, it } from 'vitest'

import {
  createDefaultTechnicalCondition,
  createDefaultTechnicalIndicatorRef,
  describeTechnicalCondition,
  getTechnicalIndicatorOutputOptions,
  getTechnicalIndicatorParamDefs,
  normalizeTechnicalCondition,
  resetTechnicalConditionForType,
} from '@/lib/technicalConditions'

describe('technicalConditions', () => {
  it('creates indicator refs from the platform catalog defaults', () => {
    const ref = createDefaultTechnicalIndicatorRef('macd')
    expect(ref.type).toBe('macd')
    expect(ref.params.fast).toBe(12)
    expect(ref.params.slow).toBe(26)
    expect(ref.params.signal).toBe(9)
    expect(ref.output).toBe('macd')
  })

  it('exposes parameter and output definitions for broader indicators', () => {
    expect(getTechnicalIndicatorParamDefs('ichimoku').map(item => item.key)).toEqual([
      'tenkan',
      'kijun',
      'senkou_b',
      'displacement',
    ])
    expect(getTechnicalIndicatorOutputOptions('bb').map(item => item.value)).toEqual([
      'bb_upper',
      'bb_mid',
      'bb_lower',
    ])
  })

  it('normalizes indicator conditions with generic params and explicit output', () => {
    const condition = normalizeTechnicalCondition({
      type: 'indicator_threshold',
      indicator: 'bb',
      params: { period: 20, stdDev: 2 },
      output: 'bb_lower',
      op: 'gt',
      value: 81,
    })

    expect(condition.indicator).toBe('bb')
    expect(condition.params?.period).toBe(20)
    expect(condition.params?.std_dev).toBe(2)
    expect(condition.output).toBe('bb_lower')
  })

  it('normalizes cross conditions with per-indicator outputs', () => {
    const condition = normalizeTechnicalCondition({
      type: 'indicator_cross',
      indicator_a: {
        type: 'macd',
        params: { fast: 12, slow: 26, signal: 9 },
        output: 'macd',
      },
      indicator_b: {
        type: 'macd',
        params: { fast: 12, slow: 26, signal: 9 },
        output: 'signal',
      },
      op: 'crosses_above',
    })

    expect(condition.indicator_a?.params.fast).toBe(12)
    expect(condition.indicator_a?.output).toBe('macd')
    expect(condition.indicator_b?.output).toBe('signal')
  })

  it('normalizes legacy indicator payloads into broader shared refs', () => {
    const condition = normalizeTechnicalCondition({
      left_source: 'indicator',
      left_indicator: 'wma',
      left_period: 10,
      operator: 'gt',
      right_source: 'value',
      right_value: 0,
    })

    expect(condition.type).toBe('indicator_threshold')
    expect(condition.indicator).toBe('wma')
    expect(condition.params?.period).toBe(10)
  })

  it('describes indicator conditions with labels, params, and output line', () => {
    const description = describeTechnicalCondition(
      normalizeTechnicalCondition({
        type: 'price_indicator',
        field: 'close',
        indicator: 'bb',
        params: { period: 20, std_dev: 2 },
        output: 'bb_upper',
        op: 'gt',
      }),
    )

    expect(description).toContain('BB(20,2)')
    expect(description).toContain('Upper band')
  })

  it('resets stale indicator output when switching to non-indicator conditions', () => {
    const condition = createDefaultTechnicalCondition('indicator_threshold')
    condition.indicator = 'bb'
    condition.params = { period: 20, std_dev: 2 }
    condition.output = 'bb_lower'

    resetTechnicalConditionForType(condition, 'price_threshold')

    expect(condition.output).toBeUndefined()
    expect(condition.indicator).toBeUndefined()
    expect(condition.params).toBeUndefined()
  })

  it('uses real catalog defaults for price-indicator conditions', () => {
    const condition = createDefaultTechnicalCondition('price_indicator')
    expect(condition.indicator).toBe('sma')
    expect(condition.params?.period).toBe(20)
    expect(condition.output).toBeUndefined()
  })
})
