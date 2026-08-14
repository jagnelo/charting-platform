<template>
  <div ref="root" class="study-histogram">
    <div v-if="!valid" class="study-histogram__state" role="status" aria-live="polite" aria-atomic="true">Distribution has no numeric observations.</div>
    <div v-else ref="host" class="study-histogram__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

interface HistogramBin { start: number; end: number; count: number }

const props = defineProps<{ name: string; bins: HistogramBin[]; current?: number | null }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null
function destroyChart() { chart?.destroy(); chart = null }

function data(): uPlot.AlignedData {
  const indices = props.bins.flatMap((_, index) => [index]).concat(props.bins.length)
  return [indices, [...props.bins.map(bin => bin.count), 0]]
}

function drawBars(instance: uPlot) {
  const context = instance.ctx
  const baseline = instance.valToPos(0, 'y', true)
  context.save()
  context.fillStyle = '#77c3ee'
  props.bins.forEach((bin, index) => {
    const left = instance.valToPos(index, 'x', true)
    const right = instance.valToPos(index + 1, 'x', true)
    const top = instance.valToPos(bin.count, 'y', true)
    context.fillRect(Math.floor(left) + 1, Math.min(top, baseline), Math.max(1, Math.floor(right - left) - 2), Math.max(1, Math.abs(baseline - top)))
  })
  if (typeof props.current === 'number' && Number.isFinite(props.current) && props.bins.length) {
    const index = props.current <= props.bins[0].start
      ? 0
      : props.current >= props.bins[props.bins.length - 1].end
        ? props.bins.length - 1
        : Math.max(0, props.bins.findIndex(bin => props.current! >= bin.start && props.current! <= bin.end))
    const marker = instance.valToPos(index + 0.5, 'x', true)
    context.strokeStyle = '#f0c674'
    context.lineWidth = 2
    context.beginPath()
    context.moveTo(marker, instance.bbox.top)
    context.lineTo(marker, instance.bbox.top + instance.bbox.height)
    context.stroke()
  }
  context.restore()
}
function hasValidData() { return props.bins.length > 0 && props.bins.every(bin => Number.isFinite(bin.start) && Number.isFinite(bin.end) && Number.isFinite(bin.count) && bin.count >= 0) }

function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) { if (!valid.value) destroyChart(); return }
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(120, host.value.clientHeight)
  if (chart) {
    chart.setData(data())
    chart.setSize({ width, height })
    return
  }
  chart = new uPlot({
    width,
    height,
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: false }, y: { auto: true, min: 0 } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI', values: (_u, values) => values.map(value => {
        const bin = props.bins[Math.round(value)]
        return bin ? `${format(bin.start)}–${format(bin.end)}` : ''
      }) },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, { label: props.name, stroke: 'transparent', width: 0 }],
    plugins: [{ hooks: { draw: [drawBars] } }],
  }, data(), host.value)
}

function format(value: number) { return Number.isInteger(value) ? String(value) : value.toFixed(2) }

// The current observation controls the highlighted marker independently of
// the histogram bins. Keep the existing uPlot instance and redraw in place
// when only that observation changes.
watch(() => [props.bins, props.name, props.current], async () => { valid.value = hasValidData(); await nextTick(); draw() }, { deep: true })
onMounted(async () => {
  observer = new ResizeObserver(draw)
  if (root.value) observer.observe(root.value)
  valid.value = hasValidData()
  await nextTick()
  draw()
})
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.study-histogram { height:190px; min-height:120px; margin-top:4px; background:#101419; }.study-histogram__host { height:100%; }.study-histogram__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
