import { beforeEach, describe, expect, it, vi } from 'vitest'

import { volumePlugin } from '@/lib/uplot/plugins/volume'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    fillRect: vi.fn(),
    fillStyle: '',
  }

  return {
    bbox: { top: 10, left: 20, width: 300, height: 180 },
    ctx,
    data: [
      [1, 2, 3],
      [100, 95, 90],
      [0, 0, 0],
      [0, 0, 0],
      [105, 90, 92],
      [200, 0, 100],
    ],
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('volumePlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws bars for non-zero volumes and colors by candle direction', () => {
    const plot = makePlot()
    const plugin = volumePlugin({ heightRatio: 0.2 })

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).toHaveBeenCalled()
    expect(plot.ctx.fillRect).toHaveBeenCalledTimes(2)
    expect(plot.ctx.fillStyle).toBe('rgba(38,166,154,0.4)')
  })

  it('returns early when all volume is zero', () => {
    const plot = makePlot()
    plot.data[5] = [0, 0, 0]

    volumePlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.fillRect).not.toHaveBeenCalled()
  })

  it('returns early when volume data is missing', () => {
    const plot = makePlot()
    plot.data[5] = []

    volumePlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.fillRect).not.toHaveBeenCalled()
  })
})
