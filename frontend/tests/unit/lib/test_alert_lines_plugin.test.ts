import { beforeEach, describe, expect, it, vi } from 'vitest'

import { alertLinesPlugin } from '@/lib/uplot/plugins/alert-lines'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillText: vi.fn(),
    setLineDash: vi.fn(),
    strokeStyle: '',
    lineWidth: 0,
    shadowColor: '',
    shadowBlur: 0,
    fillStyle: '',
    font: '',
  }

  return {
    bbox: { top: 10, left: 20, width: 200, height: 120 },
    ctx,
    valToPos: vi.fn((value: number) => value),
  } as any
}

describe('alertLinesPlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws visible alert lines and labels', () => {
    const plot = makePlot()
    const plugin = alertLinesPlugin(
      () => [
        { id: 7, price: 50, color: '#abc', label: 'Resistance' },
        { id: 8, price: 500, color: '#def', label: 'Hidden' },
      ],
      () => 7,
    )

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.beginPath).toHaveBeenCalledTimes(1)
    expect(plot.ctx.setLineDash).toHaveBeenCalledWith([6, 4])
    expect(plot.ctx.fillText).toHaveBeenCalledWith(
      '▶ Resistance 50',
      expect.any(Number),
      expect.any(Number),
    )
    expect(plot.ctx.lineWidth).toBe(5)
  })

  it('returns early when no alerts are provided', () => {
    const plot = makePlot()
    const plugin = alertLinesPlugin(() => [])

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
    expect(plot.ctx.beginPath).not.toHaveBeenCalled()
  })

  it('uses triggered styling when an alert has already fired', () => {
    const plot = makePlot()
    const plugin = alertLinesPlugin(() => [{ price: 70, triggered: true }])

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.strokeStyle).toBe('#888')
    expect(plot.ctx.lineWidth).toBe(2)
  })
})
