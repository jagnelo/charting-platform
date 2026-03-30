/**
 * uPlot candlestick plugin.
 *
 * IMPORTANT: uPlot's draw hook canvas operates in DEVICE pixels (DPR-scaled).
 * All coordinates must use u.valToPos(val, scale, true) — the third `true`
 * argument returns device-pixel coordinates. Using CSS-pixel coordinates
 * (without true) causes candles to appear in only the top-left fraction of the
 * canvas on HiDPI/Retina displays.
 *
 * Data series: [timestamps, opens, highs, lows, closes, volumes]
 */
import type uPlot from 'uplot'
import { getBodyWidthPx } from '@/lib/uplot/bar-metrics'

export interface CandlestickOptions {
  upColor?: string
  downColor?: string
  wickWidth?: number
  bodyMinHeight?: number
}

const DEFAULT_OPTS: Required<CandlestickOptions> = {
  upColor: '#26a69a',
  downColor: '#ef5350',
  wickWidth: 1,
  bodyMinHeight: 1,
}

export function candlestickPlugin(opts: CandlestickOptions = {}): uPlot.Plugin {
  const cfg = { ...DEFAULT_OPTS, ...opts }

  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const { ctx } = u
          const [times, opens, highs, lows, closes] = u.data as number[][]
          if (!times?.length) return

          ctx.save()

          // Width is based on current visible bar spacing, not the timeframe.
          const bodyWidth = getBodyWidthPx(u, 0.78, 2)
          const halfBody  = bodyWidth / 2
          const wickWidth = cfg.wickWidth * (devicePixelRatio || 1)

          for (let i = 0; i < times.length; i++) {
            const t = times[i], o = opens[i], h = highs[i], l = lows[i], c = closes[i]
            if (o == null || h == null || l == null || c == null) continue

            // All positions in device pixels (true = device pixels)
            const x  = Math.round(u.valToPos(t, 'x', true))
            const yO = Math.round(u.valToPos(o, 'y', true))
            const yH = Math.round(u.valToPos(h, 'y', true))
            const yL = Math.round(u.valToPos(l, 'y', true))
            const yC = Math.round(u.valToPos(c, 'y', true))

            const isUp  = c >= o
            const color = isUp ? cfg.upColor : cfg.downColor
            ctx.fillStyle   = color
            ctx.strokeStyle = color

            // Wick
            ctx.lineWidth = wickWidth
            ctx.beginPath()
            ctx.moveTo(x, yH)
            ctx.lineTo(x, yL)
            ctx.stroke()

            // Body
            const bodyTop = Math.min(yO, yC)
            const bodyBot = Math.max(yO, yC)
            const bodyH   = Math.max(cfg.bodyMinHeight * (devicePixelRatio || 1), bodyBot - bodyTop)
            ctx.fillRect(x - halfBody, bodyTop, bodyWidth, bodyH)
          }

          ctx.restore()
        },
      ],
    },
  }
}