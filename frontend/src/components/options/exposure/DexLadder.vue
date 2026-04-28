<template>
  <div class="dex-ladder" ref="containerRef">
    <div class="chart-title">DEX Ladder</div>
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { buildExpirationPalette } from '@/lib/expirationPalette'
import type { ExposureLadderRow } from '@/types'

const props = defineProps<{
  ladder: ExposureLadderRow[]
  spot: number | null
  enabledExpirations: Set<string>
  allExpirations: string[]
}>()

const containerRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ro: ResizeObserver | null = null

const palette = computed(() => buildExpirationPalette(props.allExpirations))

function draw() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const dpr = devicePixelRatio || 1
  const W = container.clientWidth
  const H = Math.max(200, props.ladder.length * 18 + 40)
  canvas.width = W * dpr
  canvas.height = H * dpr
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`

  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, W, H)

  const PAD_L = 64
  const PAD_R = 12
  const PAD_T = 20
  const PAD_B = 10
  const barH = 14
  const rowH = 18

  const rows = props.ladder
  if (!rows.length) {
    ctx.fillStyle = '#555'
    ctx.font = '12px monospace'
    ctx.textAlign = 'center'
    ctx.fillText('No data', W / 2, H / 2)
    return
  }

  const enabled = props.enabledExpirations
  const pal = palette.value

  let maxAbs = 0
  for (const row of rows) {
    let cd = 0
    let pd = 0
    for (const [exp, bd] of Object.entries(row.by_expiry)) {
      if (!enabled.size || enabled.has(exp)) {
        cd += bd.call_dex
        pd += Math.abs(bd.put_dex)
      }
    }
    maxAbs = Math.max(maxAbs, cd, pd)
  }
  if (maxAbs === 0) maxAbs = 1

  const chartW = W - PAD_L - PAD_R
  const midX = PAD_L + chartW / 2

  ctx.strokeStyle = '#333'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(midX, PAD_T)
  ctx.lineTo(midX, H - PAD_B)
  ctx.stroke()

  if (props.spot != null) {
    const spotIdx = rows.reduce((best, row, i) => (
      Math.abs(row.strike - props.spot!) < Math.abs(rows[best].strike - props.spot!) ? i : best
    ), 0)
    const sy = PAD_T + spotIdx * rowH + rowH / 2
    ctx.strokeStyle = '#64b5f6'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 3])
    ctx.beginPath()
    ctx.moveTo(PAD_L, sy)
    ctx.lineTo(W - PAD_R, sy)
    ctx.stroke()
    ctx.setLineDash([])
  }

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i]
    const y = PAD_T + i * rowH

    ctx.fillStyle = '#888'
    ctx.font = '10px monospace'
    ctx.textAlign = 'right'
    ctx.fillText(row.strike.toFixed(0), PAD_L - 4, y + rowH / 2 + 4)

    const exps = Object.keys(row.by_expiry).filter(exp => !enabled.size || enabled.has(exp))
    exps.sort()

    let callOffset = 0
    let putOffset = 0
    for (const exp of exps) {
      const bd = row.by_expiry[exp]
      const color = pal.get(exp) ?? '#666'

      const callW = (bd.call_dex / maxAbs) * (chartW / 2)
      if (callW > 0) {
        ctx.fillStyle = color
        ctx.fillRect(midX + callOffset, y + (rowH - barH) / 2, callW, barH)
        callOffset += callW
      }

      const putW = (Math.abs(bd.put_dex) / maxAbs) * (chartW / 2)
      if (putW > 0) {
        ctx.fillStyle = color
        ctx.fillRect(midX - putOffset - putW, y + (rowH - barH) / 2, putW, barH)
        putOffset += putW
      }
    }
  }

  ctx.fillStyle = '#555'
  ctx.font = '9px monospace'
  ctx.textAlign = 'center'
  const labelVal = maxAbs >= 1e9
    ? `${(maxAbs / 1e9).toFixed(1)}B`
    : maxAbs >= 1e6
      ? `${(maxAbs / 1e6).toFixed(1)}M`
      : maxAbs.toFixed(0)
  ctx.fillText(`-${labelVal}`, PAD_L + 4, PAD_T - 4)
  ctx.fillText(`+${labelVal}`, W - PAD_R - 4, PAD_T - 4)
}

watch(() => [props.ladder, props.enabledExpirations, props.allExpirations, props.spot], draw, {
  deep: true,
  flush: 'post',
})

onMounted(() => {
  ro = new ResizeObserver(draw)
  if (containerRef.value) ro.observe(containerRef.value)
  draw()
})

onUnmounted(() => ro?.disconnect())
</script>

<style scoped>
.dex-ladder {
  width: 100%;
  overflow: hidden;
}

.chart-title {
  font-size: 11px;
  color: #888;
  padding: 4px 8px 2px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

canvas {
  display: block;
}
</style>
