/**
 * Hit testing for drawings — determines if a pixel coordinate (cx, cy)
 * is "on" a drawing, enabling click-to-select.
 */
import type uPlot from 'uplot'
import type { AnyDrawing } from './types'

const HIT_RADIUS = 8   // pixels tolerance

type TimeToX = (time: number) => number

export function hitTest(
  drawing: AnyDrawing,
  cx: number,
  cy: number,
  u: uPlot,
  timeToX: TimeToX = (time) => time,
): boolean {
  if (!drawing.points.length) return false

  switch (drawing.type) {
    case 'trendline':
    case 'ray':
    case 'arrow':
      return hitTestLine(drawing, cx, cy, u, timeToX)
    case 'horizontal_line':
      return hitTestHorizontal(drawing, cx, cy, u)
    case 'vertical_line':
      return hitTestVertical(drawing, cx, cy, u, timeToX)
    case 'fibonacci_retracement':
    case 'fibonacci_extension':
      return hitTestFibonacci(drawing, cx, cy, u, timeToX)
    case 'rectangle':
      return hitTestRectangle(drawing, cx, cy, u, timeToX)
    case 'circle':
      return hitTestCircle(drawing, cx, cy, u, timeToX)
    case 'text_box':
      return hitTestPoint(drawing, cx, cy, u, timeToX)
    default:
      return false
  }
}

function toPixel(time: number, price: number, u: uPlot, timeToX: TimeToX): [number, number] {
  return [timeToX(time), u.valToPos(price, 'y')]
}

function distToSegment(
  px: number, py: number,
  ax: number, ay: number,
  bx: number, by: number,
): number {
  const dx = bx - ax, dy = by - ay
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay)
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
}

function hitTestLine(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  if (d.points.length < 2) return false
  const [p0, p1] = [d.points[0]!, d.points[1]!]
  const [x1, y1] = toPixel(p0.time, p0.price, u, timeToX)
  const [x2, y2] = toPixel(p1.time, p1.price, u, timeToX)
  return distToSegment(cx, cy, x1, y1, x2, y2) < HIT_RADIUS
}

function hitTestHorizontal(d: AnyDrawing, cx: number, cy: number, u: uPlot): boolean {
  const y = u.valToPos(d.points[0].price, 'y')
  return Math.abs(cy - y) < HIT_RADIUS
}

function hitTestVertical(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  const x = timeToX(d.points[0].time)
  return Math.abs(cx - x) < HIT_RADIUS
}

function hitTestFibonacci(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  // Hit any of the fib level lines
  if (d.points.length < 2) return false
  const levels = (d as any).levels ?? [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
  const [p0, p1] = [d.points[0]!, d.points[1]!]

  const x1 = timeToX(p0.time)
  const x2 = timeToX(p1.time)
  const left = Math.min(x1, x2)
  const right = Math.max(x1, x2)
  if (cx < left - HIT_RADIUS || cx > right + HIT_RADIUS) return false

  const priceRange = p1.price - p0.price
  for (const level of levels) {
    const price = p0.price + priceRange * level
    const y = u.valToPos(price, 'y')
    if (Math.abs(cy - y) < HIT_RADIUS) return true
  }
  return false
}

function hitTestRectangle(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  if (d.points.length < 2) return false
  const [p0, p1] = [d.points[0]!, d.points[1]!]
  const [x1, y1] = toPixel(p0.time, p0.price, u, timeToX)
  const [x2, y2] = toPixel(p1.time, p1.price, u, timeToX)
  const minX = Math.min(x1, x2), maxX = Math.max(x1, x2)
  const minY = Math.min(y1, y2), maxY = Math.max(y1, y2)
  // Hit on edge
  const onLeft   = Math.abs(cx - minX) < HIT_RADIUS && cy >= minY && cy <= maxY
  const onRight  = Math.abs(cx - maxX) < HIT_RADIUS && cy >= minY && cy <= maxY
  const onTop    = Math.abs(cy - minY) < HIT_RADIUS && cx >= minX && cx <= maxX
  const onBottom = Math.abs(cy - maxY) < HIT_RADIUS && cx >= minX && cx <= maxX
  return onLeft || onRight || onTop || onBottom
}

function hitTestCircle(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  if (d.points.length < 2) return false
  const [p0, p1] = [d.points[0]!, d.points[1]!]
  const [x1, y1] = toPixel(p0.time, p0.price, u, timeToX)
  const [x2, y2] = toPixel(p1.time, p1.price, u, timeToX)
  const pcx = (x1 + x2) / 2, pcy = (y1 + y2) / 2
  const rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2
  const dx = (cx - pcx) / Math.max(rx, 1), dy = (cy - pcy) / Math.max(ry, 1)
  const dist = Math.sqrt(dx * dx + dy * dy)
  return Math.abs(dist - 1) < HIT_RADIUS / Math.max(rx, ry)
}

function hitTestPoint(d: AnyDrawing, cx: number, cy: number, u: uPlot, timeToX: TimeToX): boolean {
  const p = d.points[0]
  if (!p) return false
  const [x, y] = toPixel(p.time, p.price, u, timeToX)
  const pointRadius = HIT_RADIUS * 1.5
  return Math.abs(cx - x) <= pointRadius && Math.abs(cy - y) <= pointRadius
}
