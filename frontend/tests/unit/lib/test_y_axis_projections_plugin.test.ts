import { beforeEach, describe, expect, it, vi } from 'vitest'

import { yAxisProjectionsPlugin } from '@/lib/uplot/plugins/y-axis-projections'

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
    fill: vi.fn(),
    fillText: vi.fn(),
    setLineDash: vi.fn(),
    roundRect: vi.fn(),
    measureText: vi.fn((text: string) => ({ width: text.length * 6 })),
    strokeStyle: '',
    fillStyle: '',
    lineWidth: 0,
    globalAlpha: 1,
    font: '',
    textBaseline: '',
    textAlign: '',
  }

  return {
    bbox: { top: 10, left: 20, width: 300, height: 180 },
    ctx,
    width: 400,
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('yAxisProjectionsPlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws projection lines and label chips', () => {
    const plot = makePlot()
    const plugin = yAxisProjectionsPlugin(() => [
      { price: 80, color: '#0af', chipLabel: 'High\nResistance', originX: 5 },
      { price: 120, color: '#fa0' },
    ])

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.roundRect).toHaveBeenCalledTimes(2)
    expect(plot.ctx.fillText).toHaveBeenCalled()
    expect(plot.ctx.setLineDash).toHaveBeenCalledWith([8, 6])
  })

  it('returns early when there are no projection items', () => {
    const plot = makePlot()

    yAxisProjectionsPlugin(() => []).hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
  })

  it('skips items outside the visible y-range', () => {
    const plot = makePlot()
    const plugin = yAxisProjectionsPlugin(() => [{ price: 500, color: '#fff' }])

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.roundRect).not.toHaveBeenCalled()
  })
})
