import { beforeEach, describe, expect, it, vi } from 'vitest'

import { baselinePlugin } from '@/lib/uplot/plugins/baseline'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    rect: vi.fn(),
    clip: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    setLineDash: vi.fn(),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 0,
  }

  return {
    bbox: { top: 0, left: 0, width: 320, height: 200 },
    ctx,
    data: [
      [1, 2, 3],
      [],
      [],
      [],
      [105, 95, 110],
    ],
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('baselinePlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws above and below fills around the baseline', () => {
    const plot = makePlot()
    const plugin = baselinePlugin({ baseline: () => 100 })

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.fill).toHaveBeenCalledTimes(2)
    expect(plot.ctx.stroke).toHaveBeenCalledTimes(1)
    expect(plot.ctx.setLineDash).toHaveBeenCalledWith([8, 6])
  })

  it('falls back to the first valid close when no explicit baseline is provided', () => {
    const plot = makePlot()

    baselinePlugin().hooks?.draw?.[0](plot)

    expect(plot.valToPos).toHaveBeenCalledWith(105, 'y', true)
  })

  it('returns early when no finite baseline can be resolved', () => {
    const plot = makePlot()
    plot.data[4] = [null as any, NaN, Infinity]

    baselinePlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
  })
})
