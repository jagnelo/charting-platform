import { describe, expect, it, vi } from 'vitest'

import { optionsLevelsPlugin } from '@/lib/uplot/plugins/options-levels'

function makePlot() {
  return {
    bbox: { top: 0, left: 0, width: 400, height: 300 },
    ctx: {
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
      globalAlpha: 1,
      fillStyle: '',
      shadowColor: '',
      font: '',
    },
    valToPos: vi.fn().mockReturnValue(100),
  } as any
}

describe('optionsLevelsPlugin', () => {
  it('draws level labels when key levels are present', () => {
    const plugin = optionsLevelsPlugin(() => ({
      call_wall: 920,
      put_wall: 880,
      gamma_flip: 905,
      max_pain: 900,
    }))
    const plot = makePlot()

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.beginPath).toHaveBeenCalled()
    expect(plot.ctx.fillText).toHaveBeenCalled()
    expect(plot.valToPos).toHaveBeenCalled()
  })

  it('respects disabled level config', () => {
    const plugin = optionsLevelsPlugin(
      () => ({ call_wall: 920, put_wall: null, gamma_flip: null, max_pain: null }),
      { callWall: false },
    )
    const plot = makePlot()
    plugin.hooks?.draw?.[0](plot)
    expect(plot.ctx.beginPath).not.toHaveBeenCalled()
  })
})
