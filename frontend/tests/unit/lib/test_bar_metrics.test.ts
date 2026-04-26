import { describe, expect, it, vi } from 'vitest'

import { getBarSpacingPx, getBodyWidthPx } from '@/lib/uplot/bar-metrics'

describe('bar-metrics', () => {
  it('computes bar spacing from x positions', () => {
    const plot = {
      valToPos: vi.fn()
        .mockReturnValueOnce(10)
        .mockReturnValueOnce(22),
    } as any

    expect(getBarSpacingPx(plot)).toBe(12)
  })

  it('falls back to a reasonable spacing when valToPos is invalid', () => {
    const plot = {
      valToPos: vi.fn()
        .mockReturnValueOnce(NaN)
        .mockReturnValueOnce(Infinity),
    } as any

    expect(getBarSpacingPx(plot)).toBe(8)
  })

  it('derives body width using ratio and min gap', () => {
    const plot = {
      valToPos: vi.fn()
        .mockReturnValueOnce(0)
        .mockReturnValueOnce(20),
    } as any

    expect(getBodyWidthPx(plot, 0.5, 2)).toBe(10)
  })
})

