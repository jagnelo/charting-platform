<template>
  <div ref="root" class="study-series">
    <div v-if="!valid" class="study-series__state" role="status" aria-live="polite" aria-atomic="true">Series has no aligned timestamp/value data.</div>
    <template v-else>
      <div ref="host" class="study-series__host" />
      <div ref="legendHost" class="study-series__legend" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; timestamps: string[]; values: Array<number | null> }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const legendHost = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null
function destroyChart() { chart?.destroy(); chart = null }

function data(): uPlot.AlignedData {
  return [
    props.timestamps.map(timestamp => Math.floor(new Date(timestamp).getTime() / 1000)),
    props.values,
  ]
}
function hasValidData() {
  return props.timestamps.length > 0
    && props.timestamps.length === props.values.length
    && props.timestamps.every(timestamp => Number.isFinite(Date.parse(timestamp)))
    && props.values.every(value => value == null || Number.isFinite(value))
}
function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) { if (!valid.value) destroyChart(); return }
  observer?.observe(host.value)
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(100, host.value.clientHeight)
  if (chart) {
    chart.setData(data())
    chart.setSize({ width, height })
    return
  }
  chart = new uPlot({
    width, height,
    legend: { mount: (_chart, element) => legendHost.value?.appendChild(element) },
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: true }, y: { auto: true } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, { label: props.name, stroke: '#77c3ee', width: 1.5 }],
  }, data(), host.value)
}

watch(() => [props.timestamps, props.values, props.name], async () => { valid.value = hasValidData(); await nextTick(); draw() }, { deep: true })
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
.study-series { display:grid; grid-template-rows:minmax(0,1fr) auto; gap:2px; height:180px; min-height:100px; min-width:0; margin-top:4px; background:#101419; }.study-series__host { min-height:0; min-width:0; }.study-series__legend { min-width:0; max-width:100%; color:#b8c8d3; }.study-series__legend :deep(.u-legend) { display:block; width:100%; max-width:100%; font:9px/1.2 "Segoe UI",Arial,sans-serif; }.study-series__legend :deep(.u-inline tr) { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; width:100%; gap:2px 6px; margin:0; }.study-series__legend :deep(.u-legend th),.study-series__legend :deep(.u-legend td) { min-width:0; max-width:100%; padding:1px 2px; white-space:normal; overflow-wrap:anywhere; }.study-series__legend :deep(.u-legend th) { flex:1 1 auto; text-align:left; }.study-series__legend :deep(.u-legend td) { flex:0 1 auto; text-align:right; }.study-series__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
