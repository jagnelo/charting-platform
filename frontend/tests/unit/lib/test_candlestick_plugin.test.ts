import { beforeEach, describe, expect, it, vi } from 'vitest'

import { candlestickPlugin } from '@/lib/uplot/plugins/candlestick'

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
    fillRect: vi.fn(),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
  }

  return {
    bbox: { top: 0, left: 0, width: 300, height: 200 },
    ctx,
    data: [
      [1, 2],
      [100, 95],
      [110, 105],
      [90, 80],
      [105, 85],
      [1000, 1100],
    ],
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('candlestickPlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws wicks and bodies for each valid candle', () => {
    const plot = makePlot()
    const plugin = candlestickPlugin({ wickWidth: 2, bodyMinHeight: 2 })

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.clip).toHaveBeenCalled()
    expect(plot.ctx.stroke).toHaveBeenCalledTimes(2)
    expect(plot.ctx.fillRect).toHaveBeenCalledTimes(2)
    expect(plot.ctx.lineWidth).toBe(4)
    expect(plot.ctx.fillStyle).toBe('#ef5350')
  })

  it('skips drawing when there are no time values', () => {
    const plot = makePlot()
    plot.data = [[], [], [], [], []]
    const plugin = candlestickPlugin()

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
    expect(plot.ctx.fillRect).not.toHaveBeenCalled()
  })

  it('skips candles with incomplete OHLC data', () => {
    const plot = makePlot()
    plot.data[1][1] = null as any
    const plugin = candlestickPlugin()

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.fillRect).toHaveBeenCalledTimes(1)
  })
})
