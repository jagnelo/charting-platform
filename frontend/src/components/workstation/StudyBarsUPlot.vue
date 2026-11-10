<template>
  <div ref="root" class="study-bars">
    <div v-if="!valid" class="study-bars__state" role="status" aria-live="polite" aria-atomic="true">Bars have no finite observations.</div>
    <template v-else>
      <div ref="host" class="study-bars__host" />
      <div ref="legendHost" class="study-bars__legend" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; labels: string[]; values: number[] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const legendHost = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null
function destroyChart() { chart?.destroy(); chart = null }

function data(): uPlot.AlignedData { return [props.labels.map((_, index) => index), props.values] }
function categoryTickIndices(instance: uPlot, labels: string[]) {
  if (labels.length <= 1) return labels.map((_, index) => index)
  const widestLabel = Math.max(...labels.map(label => label.length))
  const minimumLabelSpace = Math.max(32, Math.min(132, widestLabel * 6 + 10))
  const visibleCount = Math.max(1, Math.min(labels.length, Math.floor(instance.bbox.width / minimumLabelSpace)))
  if (visibleCount === labels.length) return labels.map((_, index) => index)
  if (visibleCount === 1) return [Math.floor((labels.length - 1) / 2)]
  return Array.from({ length: visibleCount }, (_, index) => Math.round(index * (labels.length - 1) / (visibleCount - 1)))
}
function drawBars(instance: uPlot) {
  const context = instance.ctx
  const zero = instance.valToPos(0, 'y', true)
  context.save()
  props.values.forEach((value, index) => {
    const left = instance.valToPos(index - 0.42, 'x', true)
    const right = instance.valToPos(index + 0.42, 'x', true)
    const top = instance.valToPos(value, 'y', true)
    context.fillStyle = value >= 0 ? '#77c3ee' : '#e58b83'
    context.fillRect(Math.floor(left), Math.min(top, zero), Math.max(1, Math.floor(right - left)), Math.max(1, Math.abs(zero - top)))
  })
  context.restore()
}
function hasValidData() { return props.labels.length > 0 && props.labels.length === props.values.length && props.values.every(value => Number.isFinite(value)) }
function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) { if (!valid.value) destroyChart(); return }
  observer?.observe(host.value)
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
    legend: { mount: (_chart, element) => legendHost.value?.appendChild(element) },
    cursor: { drag: { x: false, y: false } },
    // Bars start at zero and stay inside the plot: the y range always includes 0, and the x range keeps half a category on each side.
    scales: {
      x: { time: false, range: (_u, min, max) => [Math.min(min, -0.5), Math.max(max, props.labels.length - 0.5)] },
      y: { auto: true, range: (_u, min, max) => { const low = Math.min(0, min); const high = Math.max(0, max); return [low, high === low ? low + 1 : high] } },
    },
    axes: [
      {
        stroke: '#70808b',
        grid: { stroke: '#26313a', width: 1 },
        ticks: { stroke: '#40505a', width: 1 },
        font: '10px Segoe UI',
        splits: instance => categoryTickIndices(instance, props.labels),
        values: (_u, values) => values.map(value => Number.isInteger(value) ? props.labels[value] ?? '' : ''),
      },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, { label: props.name, stroke: 'transparent', width: 0 }],
    plugins: [{ hooks: { draw: [drawBars] } }],
  }, data(), host.value)
}
watch(() => [props.labels, props.values, props.name], async () => { valid.value = hasValidData(); await nextTick(); draw() }, { deep: true })
onMounted(async () => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); valid.value = hasValidData(); await nextTick(); draw() })
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.study-bars { display:grid; grid-template-rows:minmax(0,1fr) auto; gap:2px; height:190px; min-height:120px; min-width:0; margin-top:4px; background:#101419; }.study-bars__host { min-height:0; min-width:0; }.study-bars__legend { min-width:0; max-width:100%; color:#b8c8d3; }.study-bars:not(:hover) .study-bars__legend { visibility:hidden; }.study-bars__legend :deep(.u-legend) { display:block; width:100%; max-width:100%; font:9px/1.2 "Segoe UI",Arial,sans-serif; }.study-bars__legend :deep(.u-inline tr) { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; width:100%; gap:2px 6px; margin:0; }.study-bars__legend :deep(.u-legend th),.study-bars__legend :deep(.u-legend td) { min-width:0; max-width:100%; padding:1px 2px; white-space:normal; overflow-wrap:anywhere; }.study-bars__legend :deep(.u-legend th) { flex:1 1 auto; text-align:left; }.study-bars__legend :deep(.u-legend td) { flex:0 1 auto; text-align:right; }.study-bars__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
