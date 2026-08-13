import type uPlot from 'uplot'
import { getBodyWidthPx } from '@/lib/uplot/bar-metrics'

export type AlternativeBarKind = 'renko' | 'kagi' | 'point_figure'

export interface AlternativeBarsOptions {
  kind: AlternativeBarKind
  upColor?: string
  downColor?: string
}

/**
 * Render non-time-based chart transforms with their own visual grammar.
 *
 * The server supplies transformed OHLC rows. Renko rows are bricks, Kagi rows
 * are directional segments, and Point & Figure rows are columns. Keeping the
 * drawing in a uPlot plugin preserves the single numerical renderer contract
 * and avoids platform-font/SVG fallbacks.
 */
export function alternativeBarsPlugin(options: AlternativeBarsOptions): uPlot.Plugin {
  const upColor = options.upColor ?? '#26a69a'
  const downColor = options.downColor ?? '#ef5350'

  return {
    hooks: {
      draw: [(u: uPlot) => {
        const [times, opens, highs, lows, closes] = u.data as number[][]
        if (!times?.length) return
        const dpr = devicePixelRatio || 1
        const bodyWidth = Math.max(3 * dpr, getBodyWidthPx(u, 0.82, 2))
        const half = bodyWidth / 2

        u.ctx.save()
        u.ctx.beginPath()
        u.ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height)
        u.ctx.clip()

        for (let i = 0; i < times.length; i += 1) {
          const o = opens[i], h = highs[i], l = lows[i], c = closes[i]
          if (![o, h, l, c].every(value => value != null && Number.isFinite(value))) continue
          const x = Math.round(u.valToPos(times[i], 'x', true))
          const yOpen = Math.round(u.valToPos(o, 'y', true))
          const yHigh = Math.round(u.valToPos(h, 'y', true))
          const yLow = Math.round(u.valToPos(l, 'y', true))
          const yClose = Math.round(u.valToPos(c, 'y', true))
          const color = c >= o ? upColor : downColor
          u.ctx.strokeStyle = color
          u.ctx.fillStyle = color
          u.ctx.lineWidth = Math.max(1, dpr)

          if (options.kind === 'renko') {
            const top = Math.min(yOpen, yClose)
            const height = Math.max(dpr, Math.abs(yClose - yOpen))
            u.ctx.fillRect(x - half, top, bodyWidth, height)
            continue
          }

          if (options.kind === 'kagi') {
            u.ctx.beginPath()
            u.ctx.moveTo(x, yHigh)
            u.ctx.lineTo(x, yLow)
            u.ctx.stroke()
            // Kagi change-of-direction connectors remain visible at dense zoom.
            if (i > 0 && Number.isFinite(times[i - 1])) {
              const previous = closes[i - 1]
              if (previous != null && Number.isFinite(previous)) {
                u.ctx.beginPath()
                u.ctx.moveTo(Math.round(u.valToPos(times[i - 1], 'x', true)), yOpen)
                u.ctx.lineTo(x, yOpen)
                u.ctx.stroke()
              }
            }
            continue
          }

          // Point & Figure: draw deterministic X/O marks for each transformed
          // column instead of pretending the column is a time-based candle.
          const direction = c >= o ? 1 : -1
          const range = Math.max(1, Math.abs(yClose - yOpen))
          const marks = Math.max(1, Math.min(24, Math.round(range / Math.max(4 * dpr, bodyWidth))))
          const step = range / marks
          for (let mark = 0; mark < marks; mark += 1) {
            const center = direction > 0
              ? yClose + (mark + 0.5) * step
              : yOpen - (mark + 0.5) * step
            const size = Math.max(2 * dpr, Math.min(bodyWidth * 0.42, step * 0.32))
            u.ctx.beginPath()
            if (direction > 0) {
              u.ctx.moveTo(x - size, center - size)
              u.ctx.lineTo(x + size, center + size)
              u.ctx.moveTo(x + size, center - size)
              u.ctx.lineTo(x - size, center + size)
            } else {
              u.ctx.arc(x, center, size, 0, Math.PI * 2)
            }
            u.ctx.stroke()
          }
        }
        u.ctx.restore()
      }],
    },
  }
}
