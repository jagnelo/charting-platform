import { beforeEach, describe, expect, it, vi } from 'vitest'

import { approxVolumeProfilePlugin } from '@/lib/uplot/plugins/approx-volume-profile'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    rect: vi.fn(),
    clip: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    fillStyle: '',
    font: '',
  }

  return {
    bbox: { top: 0, left: 0, width: 300, height: 200 },
    ctx,
    data: [
      [0, 1, 2],
      [],
      [110, 115, 120],
      [100, 105, 108],
      [],
      [1000, 500, 250],
    ],
    scales: { x: { min: 0, max: 2 } },
    valToPos: vi.fn((value: number, scale: string) => scale === 'x' ? value * 10 : 200 - value),
  } as any
}

describe('approxVolumeProfilePlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('draws approximate profile buckets and a label', () => {
    const plot = makePlot()

    approxVolumeProfilePlugin({ bins: 4 }).hooks?.draw?.[0](plot)

    expect(plot.ctx.fillRect).toHaveBeenCalled()
    expect(plot.ctx.fillText).toHaveBeenCalledWith('Approx VP', expect.any(Number), expect.any(Number))
  })

  it('returns early when no positive profile can be derived', () => {
    const plot = makePlot()
    plot.data[5] = [0, 0, 0]

    approxVolumeProfilePlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
  })

  it('returns early for invalid price ranges', () => {
    const plot = makePlot()
    plot.data[2] = [100, 100, 100]
    plot.data[3] = [100, 100, 100]

    approxVolumeProfilePlugin().hooks?.draw?.[0](plot)

    expect(plot.ctx.fillRect).not.toHaveBeenCalled()
  })
})
