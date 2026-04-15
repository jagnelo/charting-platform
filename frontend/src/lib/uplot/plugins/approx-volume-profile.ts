import type uPlot from 'uplot'

export interface ApproxVolumeProfileOptions {
  bins?: number
  widthRatio?: number
  color?: string
}

export function approxVolumeProfilePlugin(opts: ApproxVolumeProfileOptions = {}): uPlot.Plugin {
  const bins = opts.bins ?? 40
  const widthRatio = opts.widthRatio ?? 0.18
  const color = opts.color ?? 'rgba(100,181,246,0.18)'

  return {
    hooks: {
      draw: [(u: uPlot) => {
        const [x, , highs, lows, , volumes] = u.data as number[][]
        if (!x?.length || !volumes?.length) return

        const xMin = u.scales.x.min ?? 0
        const xMax = u.scales.x.max ?? x.length - 1
        let low = Infinity
        let high = -Infinity
        for (let i = 0; i < x.length; i++) {
          if (i < xMin || i > xMax) continue
          if (lows[i] < low) low = lows[i]
          if (highs[i] > high) high = highs[i]
        }
        if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) return

        const buckets = new Array(bins).fill(0)
        const step = (high - low) / bins
        for (let i = 0; i < x.length; i++) {
          if (i < xMin || i > xMax) continue
          const vol = volumes[i] ?? 0
          if (vol <= 0) continue
          const lo = Math.max(low, lows[i])
          const hi = Math.min(high, highs[i])
          const start = Math.max(0, Math.floor((lo - low) / step))
          const end = Math.min(bins - 1, Math.floor((hi - low) / step))
          const count = Math.max(1, end - start + 1)
          for (let b = start; b <= end; b++) buckets[b] += vol / count
        }

        const max = Math.max(...buckets)
        if (max <= 0) return

        const { ctx, bbox } = u
        const profileW = bbox.width * widthRatio
        const right = bbox.left + bbox.width

        ctx.save()
        ctx.beginPath()
        ctx.rect(bbox.left, bbox.top, bbox.width, bbox.height)
        ctx.clip()
        ctx.fillStyle = color

        for (let b = 0; b < bins; b++) {
          const priceLo = low + b * step
          const priceHi = priceLo + step
          const y1 = u.valToPos(priceLo, 'y', true)
          const y2 = u.valToPos(priceHi, 'y', true)
          const top = Math.min(y1, y2)
          const height = Math.max(1, Math.abs(y2 - y1))
          const width = (buckets[b] / max) * profileW
          ctx.fillRect(right - width, top, width, height)
        }

        ctx.fillStyle = 'rgba(160,160,160,0.48)'
        ctx.font = `${10 * (devicePixelRatio || 1)}px monospace`
        ctx.fillText('Approx VP', right - profileW + 4, bbox.top + 14)
        ctx.restore()
      }],
    },
  }
}
