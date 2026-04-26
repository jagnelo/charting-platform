import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ohlcBarsPlugin } from '@/lib/uplot/plugins/ohlc-bars'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    rect: vi.fn(),
    clip: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    strokeStyle: '',
    lineWidth: 0,
  }

  return {
    bbox: { top: 0, left: 0, width: 300, height: 200 },
    ctx,
    data: [
      [1, 2],
      [100, 90],
      [110, 100],
      [95, 80],
      [105, 85],
    ],
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('ohlcBarsPlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws OHLC bars using up and down colors', () => {
    const plot = makePlot()
    const plugin = ohlcBarsPlugin({ lineWidth: 1.5 })

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.clip).toHaveBeenCalled()
    expect(plot.ctx.stroke).toHaveBeenCalledTimes(2)
    expect(plot.ctx.lineWidth).toBe(3)
    expect(plot.ctx.strokeStyle).toBe('#ef5350')
  })

  it('returns early when no timestamps exist', () => {
    const plot = makePlot()
    plot.data = [[], [], [], [], []]

    ohlcBarsPlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
  })

  it('skips incomplete bars', () => {
    const plot = makePlot()
    plot.data[4][0] = null as any

    ohlcBarsPlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.stroke).toHaveBeenCalledTimes(1)
  })
})
