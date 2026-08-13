import { beforeEach, describe, expect, it, vi } from 'vitest'
import { alternativeBarsPlugin } from '@/lib/uplot/plugins/alternative-bars'

function makePlot() {
  const ctx = {
    save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), rect: vi.fn(), clip: vi.fn(),
    moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fillRect: vi.fn(), arc: vi.fn(),
    strokeStyle: '', fillStyle: '', lineWidth: 0,
  }
  return {
    bbox: { top: 0, left: 0, width: 300, height: 200 },
    ctx,
    data: [[1, 2], [100, 110], [110, 120], [95, 105], [110, 105], [0, 0]],
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : value),
  } as any
}

describe('alternativeBarsPlugin', () => {
  beforeEach(() => Object.defineProperty(globalThis, 'devicePixelRatio', { value: 1, configurable: true }))

  it('renders Renko rows as filled bricks without candle wicks', () => {
    const plot = makePlot()
    alternativeBarsPlugin({ kind: 'renko' }).hooks?.draw?.[0](plot)
    expect(plot.ctx.fillRect).toHaveBeenCalledTimes(2)
    expect(plot.ctx.lineTo).not.toHaveBeenCalled()
  })

  it('renders Kagi rows as directional segments and connectors', () => {
    const plot = makePlot()
    alternativeBarsPlugin({ kind: 'kagi' }).hooks?.draw?.[0](plot)
    expect(plot.ctx.stroke).toHaveBeenCalledTimes(3)
    expect(plot.ctx.lineTo).toHaveBeenCalled()
  })

  it('renders Point & Figure columns with geometric X/O marks', () => {
    const plot = makePlot()
    alternativeBarsPlugin({ kind: 'point_figure' }).hooks?.draw?.[0](plot)
    expect(plot.ctx.arc).toHaveBeenCalled()
    expect(plot.ctx.stroke).toHaveBeenCalled()
  })

  it('does not draw for an empty transformed series', () => {
    const plot = makePlot()
    plot.data = [[], [], [], [], []]
    alternativeBarsPlugin({ kind: 'renko' }).hooks?.draw?.[0](plot)
    expect(plot.ctx.save).not.toHaveBeenCalled()
  })
})
