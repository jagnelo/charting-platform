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
            const y = u.valToPos(alert.price, 'y')
            if (y < 0 || y > u.height) continue

            const color = alert.triggered ? '#888' : (alert.color ?? '#f59e0b')
            ctx.strokeStyle = color
            ctx.lineWidth = 1
            ctx.setLineDash([6, 4])
            ctx.beginPath()
            ctx.moveTo(0, y)
            ctx.lineTo(u.width, y)
            ctx.stroke()

            if (alert.label) {
              ctx.fillStyle = color
              ctx.font = '11px monospace'
              ctx.setLineDash([])
              ctx.fillText(`▶ ${alert.label} ${alert.price}`, 4, y - 3)
            }
          }

          ctx.restore()
        },
      ],
    },
  }
}
