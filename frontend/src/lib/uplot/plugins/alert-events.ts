/**
 * Renders alert firing event markers as downward triangles at the bottom of the chart.
 * One marker per historical firing, positioned on the time axis at fired_at.
 */
import type uPlot from 'uplot'

export interface AlertEventMarker {
  ts: number           // unix timestamp in seconds
  alertType: 'price' | 'indicator' | 'screener'
  label?: string
}

const TYPE_COLORS: Record<string, string> = {
  price:     '#66bb6a',
  indicator: '#7986cb',
  screener:  '#ef9a9a',
}

export function alertEventsPlugin(
  getMarkers: () => AlertEventMarker[],
): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const markers = getMarkers()
          if (!markers.length) return

          const { ctx } = u
          const dpr     = devicePixelRatio || 1
          const bottom  = u.bbox.top + u.bbox.height
          const size    = 5 * dpr

          ctx.save()

          for (const marker of markers) {
            const x = u.valToPos(marker.ts, 'x', true)
            if (x < u.bbox.left || x > u.bbox.left + u.bbox.width) continue

            const color = TYPE_COLORS[marker.alertType] ?? '#f59e0b'

            // Vertical tick line from bottom of plot to triangle base
            ctx.strokeStyle = color
            ctx.lineWidth   = dpr
            ctx.globalAlpha = 0.35
            ctx.setLineDash([2, 3])
            ctx.beginPath()
            ctx.moveTo(x, u.bbox.top)
            ctx.lineTo(x, bottom)
            ctx.stroke()
            ctx.setLineDash([])
            ctx.globalAlpha = 1

            // Downward triangle anchored at bottom edge
            ctx.fillStyle = color
            ctx.beginPath()
            ctx.moveTo(x,        bottom - size * 1.8)
            ctx.lineTo(x - size, bottom)
            ctx.lineTo(x + size, bottom)
            ctx.closePath()
            ctx.fill()

            // Tiny label above triangle
            if (marker.label) {
              ctx.fillStyle  = color
              ctx.font       = `${dpr * 9}px monospace`
              ctx.globalAlpha = 0.8
              ctx.fillText(marker.label, x + size + dpr * 2, bottom - dpr * 2)
              ctx.globalAlpha = 1
            }
          }

          ctx.restore()
        },
      ],
    },
  }
}
