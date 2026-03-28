/**
 * Renders active price alert levels as horizontal dashed lines.
 */
import type uPlot from 'uplot'

export interface AlertLine {
  price: number
  color?: string
  label?: string
  triggered?: boolean
}

export function alertLinesPlugin(getAlerts: () => AlertLine[]): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const alerts = getAlerts()
          if (!alerts.length) return

          const { ctx } = u
          ctx.save()

          for (const alert of alerts) {
            const y = u.valToPos(alert.price, 'y', true)   // device pixels
            if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) continue

            const color = alert.triggered ? '#888' : (alert.color ?? '#f59e0b')
            ctx.strokeStyle = color
            ctx.lineWidth = devicePixelRatio || 1
            ctx.setLineDash([6, 4])
            ctx.beginPath()
            ctx.moveTo(u.bbox.left, y)
            ctx.lineTo(u.bbox.left + u.bbox.width, y)
            ctx.stroke()

            if (alert.label) {
              ctx.fillStyle = color
              ctx.font = `${(devicePixelRatio || 1) * 11}px monospace`
              ctx.setLineDash([])
              ctx.fillText(`▶ ${alert.label} ${alert.price}`, u.bbox.left + (devicePixelRatio || 1) * 4, y - (devicePixelRatio || 1) * 3)
            }
          }

          ctx.restore()
        },
      ],
    },
  }
}
