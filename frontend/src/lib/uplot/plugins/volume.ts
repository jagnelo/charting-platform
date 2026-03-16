import uPlot from 'uplot'

export function volumePlugin(opts: {
  upColor?: string
  downColor?: string
  heightRatio?: number // fraction of chart height
} = {}): uPlot.Plugin {
  const {
    upColor = 'rgba(38,166,154,0.4)',
    downColor = 'rgba(239,83,80,0.4)',
    heightRatio = 0.15,
  } = opts

  function drawVolume(u: uPlot) {
    const { ctx, data, bbox } = u
    const timeData = data[0] as number[]
    const openData = data[1] as number[]
    const closeData = data[4] as number[]
    const volumeData = data[5] as number[]

    if (!volumeData?.length) return

    const dpr = devicePixelRatio || 1
    const maxVol = Math.max(...volumeData.filter(Boolean))
    if (maxVol === 0) return

    const volAreaH = bbox.height * heightRatio
    const volAreaTop = bbox.top + bbox.height - volAreaH

    ctx.save()

    for (let i = 0; i < timeData.length; i++) {
      const vol = volumeData[i]
      if (!vol) continue

      const isUp = (closeData[i] ?? 0) >= (openData[i] ?? 0)
      ctx.fillStyle = isUp ? upColor : downColor

      const xPx = Math.round(u.valToPos(timeData[i], 'x', true))
      const barW = Math.max(1, Math.round(bbox.width / timeData.length * 0.7 * dpr))
      const halfW = Math.floor(barW / 2)
      const barH = (vol / maxVol) * volAreaH

      ctx.fillRect(xPx - halfW, volAreaTop + volAreaH - barH, barW, barH)
    }

    ctx.restore()
  }

  return { hooks: { draw: [drawVolume] } }
}
