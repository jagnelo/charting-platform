<template>
  <div class="iv-skew" ref="containerRef">
    <div class="chart-title">IV Skew</div>
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { ExposureLadderRow } from '@/types'

const props = defineProps<{
  ladder: ExposureLadderRow[]
  spot: number | null
}>()

const containerRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ro: ResizeObserver | null = null

function draw() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container) return

  const dpr = devicePixelRatio || 1
  const W = container.clientWidth
  const H = 160
  canvas.width = W * dpr
  canvas.height = H * dpr
  canvas.style.width = W + 'px'
  canvas.style.height = H + 'px'

  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, W, H)

  const rows = props.ladder.filter(r => r.call_iv != null || r.put_iv != null)
  if (rows.length < 2) {
    ctx.fillStyle = '#555'
    ctx.font = '12px monospace'
    ctx.textAlign = 'center'
    ctx.fillText('No IV data', W / 2, H / 2)
    return
  }

  const PAD_L = 40
  const PAD_R = 12
  const PAD_T = 16
  const PAD_B = 24

  const strikes = rows.map(r => r.strike)
  const minK = Math.min(...strikes)
  const maxK = Math.max(...strikes)
  const kRange = maxK - minK || 1

  const ivVals = rows.flatMap(r => [r.call_iv, r.put_iv].filter(v => v != null) as number[])
  const minIV = Math.min(...ivVals) * 0.95
  const maxIV = Math.max(...ivVals) * 1.05
  const ivRange = maxIV - minIV || 0.01

  const chartW = W - PAD_L - PAD_R
  const chartH = H - PAD_T - PAD_B

  function kx(k: number) { return PAD_L + ((k - minK) / kRange) * chartW }
  function vy(v: number) { return PAD_T + (1 - (v - minIV) / ivRange) * chartH }

  // Grid lines
  ctx.strokeStyle = '#1e1e1e'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = PAD_T + (chartH / 4) * i
    ctx.beginPath()
    ctx.moveTo(PAD_L, y)
    ctx.lineTo(W - PAD_R, y)
    ctx.stroke()
    const iv = maxIV - (ivRange / 4) * i
    ctx.fillStyle = '#555'
    ctx.font = '9px monospace'
    ctx.textAlign = 'right'
    ctx.fillText((iv * 100).toFixed(0) + '%', PAD_L - 3, y + 4)
  }

  // Spot line
  if (props.spot != null && props.spot >= minK && props.spot <= maxK) {
    ctx.strokeStyle = '#64b5f6'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 3])
    const sx = kx(props.spot)
    ctx.beginPath()
    ctx.moveTo(sx, PAD_T)
    ctx.lineTo(sx, H - PAD_B)
    ctx.stroke()
    ctx.setLineDash([])
  }

  // Call IV line
  const callRows = rows.filter(r => r.call_iv != null)
  if (callRows.length >= 2) {
    ctx.strokeStyle = '#26a69a'
    ctx.lineWidth = dpr
    ctx.beginPath()
    callRows.forEach((r, i) => {
      const x = kx(r.strike)
      const y = vy(r.call_iv!)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  // Put IV line
  const putRows = rows.filter(r => r.put_iv != null)
  if (putRows.length >= 2) {
    ctx.strokeStyle = '#ef5350'
    ctx.lineWidth = dpr
    ctx.beginPath()
    putRows.forEach((r, i) => {
      const x = kx(r.strike)
      const y = vy(r.put_iv!)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  // Strike axis labels (sampled)
  ctx.fillStyle = '#555'
  ctx.font = '9px monospace'
  ctx.textAlign = 'center'
  const step = Math.ceil(rows.length / 6)
  for (let i = 0; i < rows.length; i += step) {
    ctx.fillText(rows[i].strike.toFixed(0), kx(rows[i].strike), H - PAD_B + 12)
  }

  // Legend
  ctx.font = '9px monospace'
  ctx.fillStyle = '#26a69a'
  ctx.textAlign = 'left'
  ctx.fillText('Call IV', PAD_L, PAD_T - 4)
  ctx.fillStyle = '#ef5350'
  ctx.fillText('Put IV', PAD_L + 50, PAD_T - 4)
}

watch(() => [props.ladder, props.spot], draw, { deep: true, flush: 'post' })

onMounted(() => {
  ro = new ResizeObserver(draw)
  if (containerRef.value) ro.observe(containerRef.value)
  draw()
})

onUnmounted(() => ro?.disconnect())
</script>

<style scoped>
.iv-skew { width: 100%; overflow: hidden; }
.chart-title {
  font-size: 11px;
  color: #888;
  padding: 4px 8px 2px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
canvas { display: block; }
</style>
