/**
 * Unit tests for drawing hit detection.
 * All geometry is tested without a real uPlot instance.
 */
import { describe, it, expect, vi } from 'vitest'
import { hitTest } from '@/lib/drawings/hit_test'
import type uPlot from 'uplot'

// Mock uPlot with identity transforms for easy mental math
function makeUPlot(scale = 1): Partial<uPlot> {
  return {
    valToPos: vi.fn((val: number) => val * scale),  // price/time → pixel
    posToVal: vi.fn((pos: number) => pos / scale),
    width: 900,
    height: 500,
  } as any
}

const u = makeUPlot(1) as uPlot

function makeDrawing(type: string, points: Array<{ time: number; price: number }>) {
  return { type, points, style: {}, isVisible: true, isLocked: false } as any
}

describe('hitTest — horizontal_line', () => {
  const d = makeDrawing('horizontal_line', [{ time: 0, price: 200 }])

  it('hits when cy is within tolerance', () => {
    expect(hitTest(d, 500, 200, u)).toBe(true)
    expect(hitTest(d, 500, 205, u)).toBe(true)   // within 8px
  })

  it('misses when cy is beyond tolerance', () => {
    expect(hitTest(d, 500, 215, u)).toBe(false)   // >8px away
  })
})

describe('hitTest — vertical_line', () => {
  const d = makeDrawing('vertical_line', [{ time: 300, price: 0 }])

  it('hits when cx is within tolerance', () => {
    expect(hitTest(d, 300, 250, u)).toBe(true)
    expect(hitTest(d, 306, 250, u)).toBe(true)
  })

  it('misses when cx is beyond tolerance', () => {
    expect(hitTest(d, 320, 250, u)).toBe(false)
  })
})

describe('hitTest — trendline', () => {
  // Horizontal line from (100,100) to (400,100)
  const d = makeDrawing('trendline', [
    { time: 100, price: 100 },
    { time: 400, price: 100 },
  ])

  it('hits on the line segment', () => {
    expect(hitTest(d, 250, 100, u)).toBe(true)
    expect(hitTest(d, 250, 104, u)).toBe(true)   // within tolerance
  })

  it('misses far from the segment', () => {
    expect(hitTest(d, 250, 130, u)).toBe(false)
  })

  it('returns false for single point (incomplete drawing)', () => {
    const incomplete = makeDrawing('trendline', [{ time: 100, price: 100 }])
    expect(hitTest(incomplete, 100, 100, u)).toBe(false)
  })
})

describe('hitTest — rectangle', () => {
  // Rectangle from (50,50) to (200,200)
  const d = makeDrawing('rectangle', [
    { time: 50, price: 50 },
    { time: 200, price: 200 },
  ])

  it('hits on left edge', () => {
    expect(hitTest(d, 50, 125, u)).toBe(true)
  })

  it('hits on top edge', () => {
    expect(hitTest(d, 125, 50, u)).toBe(true)
  })

  it('hits on right edge', () => {
    expect(hitTest(d, 200, 125, u)).toBe(true)
  })

  it('hits on bottom edge', () => {
    expect(hitTest(d, 125, 200, u)).toBe(true)
  })

  it('misses inside the rectangle (hollow)', () => {
    expect(hitTest(d, 125, 125, u)).toBe(false)
  })

  it('misses well outside', () => {
    expect(hitTest(d, 400, 400, u)).toBe(false)
  })
})

describe('hitTest — text_box', () => {
  const d = makeDrawing('text_box', [{ time: 200, price: 150 }])

  it('hits near the anchor point', () => {
    expect(hitTest(d, 200, 150, u)).toBe(true)
    expect(hitTest(d, 210, 155, u)).toBe(true)
  })

  it('misses far from anchor', () => {
    expect(hitTest(d, 300, 300, u)).toBe(false)
  })
})

describe('hitTest — unknown type', () => {
  it('returns false for unknown drawing types', () => {
    const d = makeDrawing('unknown_future_type', [{ time: 100, price: 100 }])
    expect(hitTest(d, 100, 100, u)).toBe(false)
  })
})
