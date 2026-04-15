import type uPlot from 'uplot'
import { getBodyWidthPx } from '@/lib/uplot/bar-metrics'

export interface OhlcBarsOptions {
  upColor?: string
  downColor?: string
  lineWidth?: number
}

export function ohlcBarsPlugin(opts: OhlcBarsOptions = {}): uPlot.Plugin {
  const upColor = opts.upColor ?? '#26a69a'
  const downColor = opts.downColor ?? '#ef5350'
  const lineWidth = opts.lineWidth ?? 1

  return {
    hooks: {
      draw: [(u: uPlot) => {
        const { ctx } = u
        const [times, opens, highs, lows, closes] = u.data as number[][]
        if (!times?.length) return

        const dpr = devicePixelRatio || 1
        const tickWidth = Math.max(3 * dpr, getBodyWidthPx(u, 0.58, 2) / 2)

        ctx.save()
        ctx.beginPath()
        ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height)
        ctx.clip()
        ctx.lineWidth = lineWidth * dpr

        for (let i = 0; i < times.length; i++) {
          const t = times[i], o = opens[i], h = highs[i], l = lows[i], c = closes[i]
          if (o == null || h == null || l == null || c == null) continue

          const x = Math.round(u.valToPos(t, 'x', true))
          const yO = Math.round(u.valToPos(o, 'y', true))
          const yH = Math.round(u.valToPos(h, 'y', true))
          const yL = Math.round(u.valToPos(l, 'y', true))
          const yC = Math.round(u.valToPos(c, 'y', true))

          ctx.strokeStyle = c >= o ? upColor : downColor
          ctx.beginPath()
          ctx.moveTo(x, yH)
          ctx.lineTo(x, yL)
          ctx.moveTo(x - tickWidth, yO)
          ctx.lineTo(x, yO)
          ctx.moveTo(x, yC)
          ctx.lineTo(x + tickWidth, yC)
          ctx.stroke()
        }

        ctx.restore()
      }],
    },
  }
}
