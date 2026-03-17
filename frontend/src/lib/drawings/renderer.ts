/**
 * Drawing renderer — renders all active drawings onto a canvas overlay
 * positioned absolutely over the uPlot chart.
 */
import type uPlot from 'uplot'
import type { AnyDrawing, FibonacciDrawing, RectangleDrawing, TextBoxDrawing, TrendlineDrawing, HorizontalLineDrawing } from './types'
import { FIBO_DEFAULT_LEVELS, FIBO_LEVEL_COLORS } from './types'

export class DrawingRenderer {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D
  private uplot: uPlot | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')!
  }

  attach(u: uPlot) {
    this.uplot = u
    this.resize()
  }

  resize() {
    // canvas sizing is managed by alignDrawingCanvas in UPlotChart
    // which uses u.over dimensions — nothing to do here
  }

  clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
  }

  renderAll(drawings: AnyDrawing[]) {
    this.clear()
    if (!this.uplot) return
    for (const drawing of drawings) {
      if (drawing.isVisible === false) continue
      this.render(drawing)
    }
  }

  private toPixel(time: number, price: number): [number, number] {
    const u = this.uplot!
    return [u.valToPos(time, 'x'), u.valToPos(price, 'y')]
  }

  private applyStyle(drawing: AnyDrawing) {
    const s = drawing.style
    this.ctx.strokeStyle = s.color ?? '#ffffff'
    this.ctx.fillStyle = (s.color ?? '#ffffff') + '33'  // 20% alpha fill
    this.ctx.lineWidth = s.lineWidth ?? 1.5
    this.ctx.globalAlpha = s.opacity ?? 1
    if (s.dashPattern?.length) {
      this.ctx.setLineDash(s.dashPattern)
    } else {
      this.ctx.setLineDash([])
    }
  }

  render(drawing: AnyDrawing) {
    const ctx = this.ctx
    ctx.save()
    this.applyStyle(drawing)

    // Selection highlight
    if (drawing.isSelected) {
      ctx.shadowColor = drawing.style.color ?? '#fff'
      ctx.shadowBlur = 6
    }

    switch (drawing.type) {
      case 'trendline':
      case 'ray':
        this.renderTrendline(drawing as TrendlineDrawing)
        break
      case 'horizontal_line':
        this.renderHorizontalLine(drawing as HorizontalLineDrawing)
        break
      case 'vertical_line':
        this.renderVerticalLine(drawing)
        break
      case 'fibonacci_retracement':
      case 'fibonacci_extension':
        this.renderFibonacci(drawing as FibonacciDrawing)
        break
      case 'rectangle':
        this.renderRectangle(drawing as RectangleDrawing)
        break
      case 'circle':
        this.renderCircle(drawing as RectangleDrawing)
        break
      case 'text_box':
        this.renderTextBox(drawing as TextBoxDrawing)
        break
      case 'arrow':
        this.renderArrow(drawing as TrendlineDrawing)
        break
    }

    ctx.restore()
  }

  private renderTrendline(d: TrendlineDrawing) {
    if (d.points.length < 2) return
    const [x1, y1] = this.toPixel(d.points[0].time, d.points[0].price)
    const [x2, y2] = this.toPixel(d.points[1].time, d.points[1].price)

    if (d.extendRight) {
      // Extend to right edge of canvas
      const slope = (y2 - y1) / (x2 - x1)
      const xEnd = this.canvas.width
      const yEnd = y1 + slope * (xEnd - x1)
      this.ctx.beginPath()
      this.ctx.moveTo(x1, y1)
      this.ctx.lineTo(xEnd, yEnd)
      this.ctx.stroke()
    } else {
      this.ctx.beginPath()
      this.ctx.moveTo(x1, y1)
      this.ctx.lineTo(x2, y2)
      this.ctx.stroke()
    }

    // Draw endpoint handles if selected
    if (d.isSelected) {
      this.drawHandle(x1, y1)
      this.drawHandle(x2, y2)
    }
  }

  private renderHorizontalLine(d: HorizontalLineDrawing) {
    const y = this.uplot!.valToPos(d.points[0].price, 'y')
    this.ctx.beginPath()
    this.ctx.moveTo(0, y)
    this.ctx.lineTo(this.canvas.width, y)
    this.ctx.stroke()

    if (d.label) {
      this.ctx.font = `${d.style.fontSize ?? 11}px monospace`
      this.ctx.fillStyle = d.style.color ?? '#fff'
      this.ctx.globalAlpha = 1
      this.ctx.fillText(d.label, 4, y - 3)
    }
  }

  private renderVerticalLine(d: AnyDrawing) {
    if (!d.points[0]) return
    const x = this.uplot!.valToPos(d.points[0].time, 'x')
    this.ctx.beginPath()
    this.ctx.moveTo(x, 0)
    this.ctx.lineTo(x, this.canvas.height)
    this.ctx.stroke()
  }

  private renderFibonacci(d: FibonacciDrawing) {
    if (d.points.length < 2) return
    const p0 = d.points[0]
    const p1 = d.points[1]
    const priceRange = p1.price - p0.price
    const levels = d.levels ?? FIBO_DEFAULT_LEVELS
    const ctx = this.ctx

    for (const level of levels) {
      const price = p0.price + priceRange * level
      const y = this.uplot!.valToPos(price, 'y')
      const color = FIBO_LEVEL_COLORS[level] ?? '#888'

      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = 1
      ctx.setLineDash([4, 3])
      ctx.globalAlpha = 0.8
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(this.canvas.width, y)
      ctx.stroke()

      ctx.font = '10px monospace'
      ctx.fillStyle = color
      ctx.globalAlpha = 1
      ctx.setLineDash([])
      ctx.fillText(`${(level * 100).toFixed(1)}%  ${price.toFixed(2)}`, this.canvas.width - 100, y - 3)
      ctx.restore()
    }
  }

  private renderRectangle(d: RectangleDrawing) {
    if (d.points.length < 2) return
    const [x1, y1] = this.toPixel(d.points[0].time, d.points[0].price)
    const [x2, y2] = this.toPixel(d.points[1].time, d.points[1].price)

    const rx = Math.min(x1, x2)
    const ry = Math.min(y1, y2)
    const rw = Math.abs(x2 - x1)
    const rh = Math.abs(y2 - y1)

    if (d.filled ?? false) {
      this.ctx.fillRect(rx, ry, rw, rh)
    }
    this.ctx.strokeRect(rx, ry, rw, rh)
  }

  private renderCircle(d: RectangleDrawing) {
    if (d.points.length < 2) return
    const [x1, y1] = this.toPixel(d.points[0].time, d.points[0].price)
    const [x2, y2] = this.toPixel(d.points[1].time, d.points[1].price)

    const cx = (x1 + x2) / 2
    const cy = (y1 + y2) / 2
    const rx = Math.abs(x2 - x1) / 2
    const ry = Math.abs(y2 - y1) / 2

    this.ctx.beginPath()
    this.ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
    if (d.filled ?? false) this.ctx.fill()
    this.ctx.stroke()
  }

  private renderTextBox(d: TextBoxDrawing) {
    const [x, y] = this.toPixel(d.points[0].time, d.points[0].price)
    const fontSize = d.style.fontSize ?? 13
    const font = d.style.fontFamily ?? 'monospace'
    this.ctx.font = `${fontSize}px ${font}`
    this.ctx.fillStyle = d.style.color ?? '#fff'
    this.ctx.globalAlpha = 1
    this.ctx.fillText(d.text, x, y)
  }

  private renderArrow(d: TrendlineDrawing) {
    if (d.points.length < 2) return
    const [x1, y1] = this.toPixel(d.points[0].time, d.points[0].price)
    const [x2, y2] = this.toPixel(d.points[1].time, d.points[1].price)

    this.ctx.beginPath()
    this.ctx.moveTo(x1, y1)
    this.ctx.lineTo(x2, y2)
    this.ctx.stroke()

    // Arrowhead
    const angle = Math.atan2(y2 - y1, x2 - x1)
    const size = 10
    this.ctx.beginPath()
    this.ctx.moveTo(x2, y2)
    this.ctx.lineTo(x2 - size * Math.cos(angle - Math.PI / 6), y2 - size * Math.sin(angle - Math.PI / 6))
    this.ctx.moveTo(x2, y2)
    this.ctx.lineTo(x2 - size * Math.cos(angle + Math.PI / 6), y2 - size * Math.sin(angle + Math.PI / 6))
    this.ctx.stroke()
  }

  private drawHandle(x: number, y: number) {
    this.ctx.save()
    this.ctx.fillStyle = '#fff'
    this.ctx.strokeStyle = this.ctx.strokeStyle
    this.ctx.lineWidth = 1.5
    this.ctx.globalAlpha = 1
    this.ctx.setLineDash([])
    this.ctx.beginPath()
    this.ctx.arc(x, y, 4, 0, Math.PI * 2)
    this.ctx.fill()
    this.ctx.stroke()
    this.ctx.restore()
  }
}