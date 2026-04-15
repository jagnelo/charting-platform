import type uPlot from 'uplot'

export interface BaselinePluginOptions {
  baseline?: () => number | null
  aboveColor?: string
  belowColor?: string
  lineColor?: string
}

export function baselinePlugin(opts: BaselinePluginOptions = {}): uPlot.Plugin {
  const aboveColor = opts.aboveColor ?? 'rgba(38,166,154,0.14)'
  const belowColor = opts.belowColor ?? 'rgba(239,83,80,0.12)'
  const lineColor = opts.lineColor ?? '#777'

  return {
    hooks: {
      draw: [(u: uPlot) => {
        const [x, , , , close] = u.data as number[][]
        if (!x?.length || !close?.length) return

        const base = opts.baseline?.() ?? close.find(v => v != null && Number.isFinite(v)) ?? null
        if (base == null || !Number.isFinite(base)) return

        const { ctx, bbox } = u
        const baseY = u.valToPos(base, 'y', true)
        const bottom = bbox.top + bbox.height

        ctx.save()
        ctx.beginPath()
        ctx.rect(bbox.left, bbox.top, bbox.width, bbox.height)
        ctx.clip()

        const drawArea = (above: boolean) => {
          ctx.beginPath()
          let started = false
          for (let i = 0; i < x.length; i++) {
            const val = close[i]
            if (val == null || !Number.isFinite(val)) {
              started = false
              continue
            }
            const px = u.valToPos(x[i], 'x', true)
            const py = u.valToPos(val, 'y', true)
            if (!started) {
              ctx.moveTo(px, baseY)
              ctx.lineTo(px, py)
              started = true
            } else {
              ctx.lineTo(px, py)
            }
          }
          const lastX = u.valToPos(x[x.length - 1], 'x', true)
          const firstX = u.valToPos(x[0], 'x', true)
          ctx.lineTo(lastX, baseY)
          ctx.lineTo(firstX, baseY)
          ctx.closePath()
          ctx.fillStyle = above ? aboveColor : belowColor
          ctx.fill()
        }

        ctx.save()
        ctx.beginPath()
        ctx.rect(bbox.left, bbox.top, bbox.width, Math.max(0, baseY - bbox.top))
        ctx.clip()
        drawArea(true)
        ctx.restore()

        ctx.save()
        ctx.beginPath()
        ctx.rect(bbox.left, baseY, bbox.width, Math.max(0, bottom - baseY))
        ctx.clip()
        drawArea(false)
        ctx.restore()

        ctx.strokeStyle = lineColor
        ctx.lineWidth = devicePixelRatio || 1
        ctx.setLineDash([4 * (devicePixelRatio || 1), 3 * (devicePixelRatio || 1)])
        ctx.beginPath()
        ctx.moveTo(bbox.left, baseY)
        ctx.lineTo(bbox.left + bbox.width, baseY)
        ctx.stroke()
        ctx.restore()
      }],
    },
  }
}
