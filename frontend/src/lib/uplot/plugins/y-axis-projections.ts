/**
 * Y-axis projection plugin — TradingView-style.
 *
 * For each enabled element, draws:
 *   • A thin dashed horizontal line from the element's rightmost X position
 *     to the right edge of the plot area.
 *   • A colored label chip on the Y axis at the element's price level.
 *
 * Chip behaviour:
 *   - Aligned flush with the left edge of the Y axis.
 *   - Width constrained to the Y axis width (no overflow).
 *   - chipLabel may contain "\n" to produce additional lines below the price.
 *   - Anti-overlap: chips are nudged apart (while dashed lines stay at true Y).
 */
import type uPlot from 'uplot'

export interface ProjectionItem {
  price: number
  color: string
  /**
   * Label shown below the price in the chip.
   * May contain "\n" to add further lines (e.g. "AVWAP\nJan 5").
   */
  chipLabel?: string
  /**
   * X position (bar index) where the dashed line originates.
   * undefined = full-width line from bbox.left to bbox.right (e.g. current price, high/low).
   */
  originX?: number
}

export function yAxisProjectionsPlugin(
  getItems: () => ProjectionItem[],
): uPlot.Plugin {
  function wrapLine(
    ctx: CanvasRenderingContext2D,
    text: string,
    maxW: number,
  ): string[] {
    if (!text) return []
    if (ctx.measureText(text).width <= maxW) return [text]
    const parts = text
      .replace(/([(),/])/g, '$1 ')
      .split(/\s+/)
      .filter(Boolean)
    const lines: string[] = []
    let cur = ''
    for (const part of parts) {
      const next = cur ? `${cur} ${part}` : part
      if (ctx.measureText(next).width <= maxW) {
        cur = next
        continue
      }
      if (cur) lines.push(cur)
      cur = part
    }
    if (cur) lines.push(cur)
    return lines.flatMap(line => {
      if (ctx.measureText(line).width <= maxW) return [line]
      const chunks: string[] = []
      let chunk = ''
      for (const ch of line) {
        const next = chunk + ch
        if (ctx.measureText(next).width <= maxW) chunk = next
        else {
          if (chunk) chunks.push(chunk)
          chunk = ch
        }
      }
      if (chunk) chunks.push(chunk)
      return chunks
    })
  }

  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const items = getItems()
          if (!items.length) return

          const dpr    = devicePixelRatio || 1
          const { ctx } = u
          const bbox   = u.bbox

          // Y axis sits to the right of the plot bbox. Keep chips over the same
          // fixed text lane as tick values instead of sizing each chip to text.
          const yAxisW   = u.width * dpr - (bbox.left + bbox.width)
          const tickLaneOffset = dpr * 5
          const chipX    = bbox.left + bbox.width + tickLaneOffset
          const chipW    = Math.max(20 * dpr, yAxisW - tickLaneOffset)
          const maxChipW = chipW

          const fontSize    = Math.round(10 * dpr)
          const smallFontSz = Math.round(9 * dpr)
          const lineH       = fontSize + dpr * 2
          const padX        = dpr * 3
          const padV        = dpr * 3   // vertical padding inside chip

          ctx.save()

          // ── Pass 1: compute per-item geometry ────────────────────────────────
          interface ChipData {
            item:    ProjectionItem
            trueY:   number
            lines:   string[]       // [priceText, ...labelLines]
            chipH:   number
            chipW:   number
            displayY: number        // nudged center — set in pass 2
          }

          const chips: ChipData[] = []

          for (const item of items) {
            const trueY = u.valToPos(item.price, 'y', true)
            if (trueY < bbox.top || trueY > bbox.top + bbox.height) continue

            const valueText  = item.price >= 1000
              ? item.price.toFixed(0)
              : item.price.toFixed(2)
            ctx.font = `${smallFontSz}px monospace`
            const labelLines = item.chipLabel
              ? item.chipLabel.split('\n').flatMap(line => wrapLine(ctx, line, maxChipW - padX * 2))
              : []
            const lines      = [valueText, ...labelLines]

            const chipH = lineH * lines.length + padV * 2

            chips.push({ item, trueY, lines, chipH, chipW, displayY: trueY })
          }

          if (!chips.length) { ctx.restore(); return }

          // ── Pass 2: anti-overlap nudging (sort top→bottom, greedy push) ──────
          chips.sort((a, b) => a.trueY - b.trueY)

          const gap = dpr
          let lastBottom = -Infinity
          for (const c of chips) {
            const idealTop  = c.trueY - c.chipH / 2
            const nudgedTop = Math.max(idealTop, lastBottom + gap)
            c.displayY = nudgedTop + c.chipH / 2
            lastBottom = nudgedTop + c.chipH
          }

          const firstTop = chips[0].displayY - chips[0].chipH / 2
          const finalBottom = chips[chips.length - 1].displayY + chips[chips.length - 1].chipH / 2
          const totalChipH = chips.reduce((sum, c) => sum + c.chipH, 0) + gap * (chips.length - 1)
          let shift = 0
          if (firstTop < bbox.top) shift = bbox.top - firstTop
          if (totalChipH <= bbox.height && finalBottom + shift > bbox.top + bbox.height) {
            shift -= finalBottom + shift - (bbox.top + bbox.height)
          }
          if (shift !== 0) {
            for (const c of chips) c.displayY += shift
          }

          // ── Pass 3: draw everything ──────────────────────────────────────────
          for (const { item, trueY, lines, chipH, chipW, displayY } of chips) {
            // Dashed projection line at the TRUE price level
            const xStart = item.originX != null
              ? Math.max(u.valToPos(item.originX, 'x', true), bbox.left)
              : bbox.left
            const lineEnd = chipX

            ctx.beginPath()
            ctx.strokeStyle  = item.color
            ctx.lineWidth    = dpr
            ctx.setLineDash([4 * dpr, 3 * dpr])
            ctx.globalAlpha  = 0.65
            ctx.moveTo(xStart, trueY)
            ctx.lineTo(lineEnd, trueY)
            ctx.stroke()
            ctx.setLineDash([])
            ctx.globalAlpha = 1

            // Optional connector: thin line on Y-axis edge if chip was nudged
            const chipTop = displayY - chipH / 2
            if (Math.abs(displayY - trueY) > chipH / 2 + dpr) {
              ctx.beginPath()
              ctx.strokeStyle = item.color
              ctx.lineWidth   = dpr * 0.75
              ctx.globalAlpha = 0.4
              ctx.moveTo(chipX, trueY)
              ctx.lineTo(chipX, displayY)
              ctx.stroke()
              ctx.globalAlpha = 1
            }

            // Chip background
            ctx.fillStyle   = item.color
            ctx.globalAlpha = 1
            ctx.beginPath()
            const r = dpr * 2
            ctx.roundRect(chipX, Math.round(chipTop) + 0.5, chipW, chipH, r)
            ctx.fill()
            ctx.globalAlpha = 1

            // Text lines (clipped to chip bounds)
            ctx.save()
            ctx.beginPath()
            ctx.rect(chipX, chipTop, chipW, chipH)
            ctx.clip()

            ctx.textBaseline = 'middle'
            ctx.textAlign    = 'left'

            for (let li = 0; li < lines.length; li++) {
              const isFirst = li === 0
              ctx.font      = isFirst
                ? `bold ${fontSize}px monospace`
                : `${smallFontSz}px monospace`
              ctx.fillStyle = isFirst
                ? '#ffffff'
                : 'rgba(255,255,255,0.82)'

              const textY = chipTop + padV + lineH * li + lineH / 2
              ctx.fillText(lines[li], chipX + padX, textY)
            }

            ctx.restore()
          }

          ctx.restore()
        },
      ],
    },
  }
}
