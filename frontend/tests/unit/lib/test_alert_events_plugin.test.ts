import { beforeEach, describe, expect, it, vi } from 'vitest'

import { alertEventsPlugin } from '@/lib/uplot/plugins/alert-events'
import type { AlertEventMarker } from '@/lib/uplot/plugins/alert-events'

function makePlot() {
  const ctx = {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    closePath: vi.fn(),
    setLineDash: vi.fn(),
    strokeStyle: '',
    lineWidth: 0,
    globalAlpha: 1,
    fillStyle: '',
    font: '',
  }

  return {
    bbox: { top: 10, left: 20, width: 200, height: 120 },
    ctx,
    valToPos: vi.fn((value: number) => value),
  } as any
}

describe('alertEventsPlugin', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'devicePixelRatio', {
      value: 2,
      configurable: true,
    })
  })

  it('returns early without drawing when no markers are provided', () => {
    const plot = makePlot()
    const plugin = alertEventsPlugin(() => [])

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).not.toHaveBeenCalled()
    expect(plot.ctx.beginPath).not.toHaveBeenCalled()
  })

  it('draws tick line and triangle for a visible marker', () => {
    const plot = makePlot()
    const markers: AlertEventMarker[] = [
      { ts: 100, alertType: 'price' },
    ]
    const plugin = alertEventsPlugin(() => markers)

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).toHaveBeenCalledOnce()
    expect(plot.ctx.restore).toHaveBeenCalledOnce()
    expect(plot.ctx.setLineDash).toHaveBeenCalledWith([2, 3])
    expect(plot.ctx.stroke).toHaveBeenCalled()
    expect(plot.ctx.fill).toHaveBeenCalled()
    expect(plot.ctx.strokeStyle).toBe('#66bb6a')
    expect(plot.ctx.fillStyle).toBe('#66bb6a')
  })

  it('skips markers whose x position falls outside the plot bbox', () => {
    const plot = makePlot()
    // valToPos returns value as-is; bbox.left=20, bbox.left+width=220
    // ts=5 maps to x=5 which is < bbox.left (20) → out of range
    const markers: AlertEventMarker[] = [
      { ts: 5, alertType: 'indicator' },
    ]
    const plugin = alertEventsPlugin(() => markers)

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.save).toHaveBeenCalledOnce()
    expect(plot.ctx.fill).not.toHaveBeenCalled()
  })

  it('renders label text when marker has a label', () => {
    const plot = makePlot()
    const markers: AlertEventMarker[] = [
      { ts: 100, alertType: 'screener', label: 'HIT' },
    ]
    const plugin = alertEventsPlugin(() => markers)

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.fillText).toHaveBeenCalledWith(
      'HIT',
      expect.any(Number),
      expect.any(Number),
    )
  })

  it('uses fallback color for unknown alert types', () => {
    const plot = makePlot()
    const markers = [{ ts: 100, alertType: 'unknown' as any }]
    const plugin = alertEventsPlugin(() => markers)

    plugin.hooks?.draw?.[0](plot)

    expect(plot.ctx.strokeStyle).toBe('#f59e0b')
  })
})
