import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DrawingRenderer } from '@/lib/drawings/renderer'

function makeContext() {
  return {
    clearRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    setLineDash: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    fillText: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    ellipse: vi.fn(),
    arc: vi.fn(),
    measureText: vi.fn((text: string) => ({ width: text.length * 7 })),
    strokeStyle: '#fff',
    fillStyle: '#fff',
    lineWidth: 1,
    globalAlpha: 1,
    shadowColor: '',
    shadowBlur: 0,
    font: '',
  }
}

function makeCanvas(ctx: ReturnType<typeof makeContext>) {
  return {
    width: 400,
    height: 240,
    getContext: vi.fn(() => ctx),
  } as any
}

describe('DrawingRenderer', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders multiple drawing types plus a measurement overlay', () => {
    const ctx = makeContext()
    const canvas = makeCanvas(ctx)
    const renderer = new DrawingRenderer(canvas)

    renderer.attach({
      valToPos: (value: number) => 240 - value,
    } as any)
    renderer.setTimeToXMapper((time) => time * 10)

    renderer.renderAll([
      {
        type: 'trendline',
        points: [{ time: 1, price: 100 }, { time: 10, price: 120 }],
        style: { color: '#0af', lineWidth: 2, opacity: 0.9 },
        isSelected: true,
      },
      {
        type: 'ray',
        points: [{ time: 2, price: 90 }, { time: 2, price: 120 }],
        style: { color: '#fa0' },
        extendRight: true,
      },
      {
        type: 'horizontal_line',
        points: [{ time: 0, price: 110 }],
        style: { color: '#fff', fontSize: 12 },
        label: 'Resistance',
      },
      {
        type: 'vertical_line',
        points: [{ time: 8, price: 0 }],
        style: { color: '#fff' },
      },
      {
        type: 'fibonacci_retracement',
        points: [{ time: 3, price: 90 }, { time: 7, price: 130 }],
        style: { color: '#4caf50' },
        isSelected: true,
      },
      {
        type: 'rectangle',
        points: [{ time: 4, price: 105 }, { time: 6, price: 95 }],
        style: { color: '#ff0' },
        filled: true,
        isSelected: true,
      },
      {
        type: 'circle',
        points: [{ time: 4, price: 80 }, { time: 6, price: 60 }],
        style: { color: '#0ff' },
        filled: true,
        isSelected: true,
      },
      {
        type: 'half_circle',
        points: [{ time: 8, price: 70 }, { time: 10, price: 50 }],
        style: { color: '#f0f' },
        isSelected: true,
      },
      {
        type: 'text_box',
        points: [{ time: 5, price: 140 }],
        style: { color: '#fff', fontSize: 14, fontFamily: 'monospace' },
        text: 'note',
      },
      {
        type: 'arrow',
        points: [{ time: 9, price: 100 }, { time: 11, price: 130 }],
        style: { color: '#f55' },
        isSelected: true,
      },
      {
        type: 'freehand',
        points: [{ time: 1, price: 50 }, { time: 2, price: 52 }, { time: 3, price: 54 }],
        style: { color: '#5f5' },
      },
      {
        type: 'trendline',
        points: [{ time: 0, price: 0 }, { time: 1, price: 1 }],
        style: { color: '#000' },
        isVisible: false,
      },
    ] as any, {
      x1: 20,
      y1: 20,
      x2: 120,
      y2: 80,
      label: ['Move', '+12%'],
    })

    expect(ctx.clearRect).toHaveBeenCalled()
    expect(ctx.stroke).toHaveBeenCalled()
    expect(ctx.fillRect).toHaveBeenCalled()
    expect(ctx.strokeRect).toHaveBeenCalled()
    expect(ctx.ellipse).toHaveBeenCalled()
    expect(ctx.arc).toHaveBeenCalled()
    expect(ctx.fillText).toHaveBeenCalled()
  })

  it('returns safely when no plot is attached, and clear works independently', () => {
    const ctx = makeContext()
    const renderer = new DrawingRenderer(makeCanvas(ctx))

    renderer.clear()
    renderer.renderAll([{ type: 'trendline', points: [], style: {} }] as any)

    expect(ctx.clearRect).toHaveBeenCalled()
    expect(ctx.stroke).not.toHaveBeenCalled()
  })
})
