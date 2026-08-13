import { describe, expect, it } from 'vitest'
import { autoRatioBenchmarks, autoRatioExpression } from '@/lib/workstation/ratioExpression'

describe('autoRatioExpression', () => {
  const sectors = ['XLK', 'XLE']

  it('uses benchmark and equal-weight defaults before sector drill-down', () => {
    expect(autoRatioExpression('SPY', sectors)).toBe('=SPY/RSP')
    expect(autoRatioExpression('RSP', sectors)).toBe('=RSP/SPY')
    expect(autoRatioExpression('XLK', sectors)).toBe('=XLK/SPY')
  })

  it('compares a selected constituent to the active ETF', () => {
    expect(autoRatioExpression('NVDA', sectors, 'XLK')).toBe('=NVDA/XLK')
    expect(autoRatioExpression('NVDA', sectors)).toBe('=NVDA/SPY')
  })

  it('derives non-self-referential benchmark legs for the ratio chart', () => {
    expect(autoRatioBenchmarks('SPY', sectors)).toEqual(['RSP'])
    expect(autoRatioBenchmarks('RSP', sectors)).toEqual(['SPY'])
    expect(autoRatioBenchmarks('XLK', sectors)).toEqual(['SPY'])
    expect(autoRatioBenchmarks('NVDA', sectors, 'XLK')).toEqual(['XLK', 'SPY'])
  })
})
