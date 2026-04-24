/**
 * Renders options key levels (call wall, put wall, gamma flip, max pain)
 * as horizontal lines on the price chart.
 */
import type uPlot from 'uplot'
import type { ExposureKeyLevels } from '@/types'

export interface OptionsLevelsConfig {
  callWall?: boolean
  putWall?: boolean
  gammaFlip?: boolean
  maxPain?: boolean
}

const LEVEL_STYLES: Record<keyof ExposureKeyLevels, { color: string; dash: number[]; label: string }> = {
  call_wall:  { color: '#26a69a', dash: [8, 4], label: 'Call Wall' },
  put_wall:   { color: '#ef5350', dash: [8, 4], label: 'Put Wall' },
  gamma_flip: { color: '#64b5f6', dash: [5, 3], label: 'GEX Flip' },
  max_pain:   { color: '#ffb74d', dash: [4, 6], label: 'Max Pain' },
}

export function optionsLevelsPlugin(
  getLevels: () => ExposureKeyLevels | null,
  config: OptionsLevelsConfig = {},
): uPlot.Plugin {
  const show = {
    call_wall:  config.callWall  !== false,
    put_wall:   config.putWall   !== false,
    gamma_flip: config.gammaFlip !== false,
    max_pain:   config.maxPain   !== false,
  }

  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const levels = getLevels()
          if (!levels) return

          const dpr = devicePixelRatio || 1
          const { ctx } = u
          ctx.save()
          ctx.font = `${dpr * 10}px monospace`

          for (const key of Object.keys(LEVEL_STYLES) as Array<keyof ExposureKeyLevels>) {
            if (!show[key]) continue
            const val = levels[key]
            if (val == null) continue

            const y = u.valToPos(val, 'y', true)
            if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) continue

            const { color, dash, label } = LEVEL_STYLES[key]
            ctx.strokeStyle = color
            ctx.lineWidth = dpr
            ctx.setLineDash(dash)
            ctx.globalAlpha = 0.75
            ctx.beginPath()
            ctx.moveTo(u.bbox.left, y)
            ctx.lineTo(u.bbox.left + u.bbox.width, y)
            ctx.stroke()

            ctx.setLineDash([])
            ctx.globalAlpha = 0.9
            ctx.fillStyle = color
            ctx.shadowColor = 'transparent'
            const priceLabel = val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            ctx.fillText(`${label} ${priceLabel}`, u.bbox.left + dpr * 4, y - dpr * 3)
          }

          ctx.globalAlpha = 1
          ctx.restore()
        },
      ],
    },
  }
}
