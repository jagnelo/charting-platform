/**
 * Renders active price alert levels as horizontal dashed lines.
 */
import type uPlot from 'uplot'

export interface AlertLine {
  id?: number
  price: number
  color?: string
  label?: string
  triggered?: boolean
}

export function alertLinesPlugin(
  getAlerts: () => AlertLine[],
  getSelectedId?: () => number | null,
): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const alerts = getAlerts()
          if (!alerts.length) return

          const selectedId = getSelectedId?.() ?? null
          const dpr = devicePixelRatio || 1

          const { ctx } = u
          ctx.save()

          for (const alert of alerts) {
            const y = u.valToPos(alert.price, 'y', true)   // device pixels
            if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) continue

            const isSelected = alert.id != null && alert.id === selectedId
            const color = alert.triggered ? '#888' : (alert.color ?? '#f59e0b')
            ctx.strokeStyle = color
            ctx.lineWidth = isSelected ? dpr * 2.5 : dpr
            ctx.setLineDash([6, 4])
            ctx.shadowColor = isSelected ? color : 'transparent'
            ctx.shadowBlur  = isSelected ? 8 : 0
            ctx.beginPath()
            ctx.moveTo(u.bbox.left, y)
            ctx.lineTo(u.bbox.left + u.bbox.width, y)
            ctx.stroke()

            if (alert.label) {
              ctx.fillStyle = color
              ctx.font = `${dpr * 11}px monospace`
              ctx.setLineDash([])
              ctx.shadowBlur = 0
              ctx.fillText(`▶ ${alert.label} ${alert.price}`, u.bbox.left + dpr * 4, y - dpr * 3)
            }
          }

          ctx.restore()
        },
      ],
    },
  }
}
