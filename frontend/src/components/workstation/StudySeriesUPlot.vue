<template>
  <div ref="root" class="study-series">
    <div v-if="!valid" class="study-series__state" role="status" aria-live="polite" aria-atomic="true">Series has no aligned timestamp/value data.</div>
    <div v-else ref="host" class="study-series__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; timestamps: string[]; values: Array<number | null> }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
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
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(100, host.value.clientHeight)
  if (chart) {
    chart.setData(data())
    chart.setSize({ width, height })
    return
  }
  chart = new uPlot({
    width, height,
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
.study-series { height:180px; min-height:100px; margin-top:4px; background:#101419; }.study-series__host { height:100%; }.study-series__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
