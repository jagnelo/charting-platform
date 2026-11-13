<template>
  <div ref="root" class="study-scatter">
    <div v-if="!valid" class="study-scatter__state" role="status" aria-live="polite" aria-atomic="true">Scatter output has no aligned numeric points.</div>
    <template v-else>
      <div ref="host" class="study-scatter__host" />
      <div ref="legendHost" class="study-scatter__legend" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; x: number[]; y: number[] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const legendHost = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null

function destroyChart() {
  chart?.destroy()
  chart = null
}

function drawPoints(instance: uPlot) {
  const context = instance.ctx
  context.save()
  context.fillStyle = '#77c3ee'
  for (let index = 0; index < props.x.length; index += 1) {
    const x = instance.valToPos(props.x[index], 'x', true)
    const y = instance.valToPos(props.y[index], 'y', true)
    context.beginPath()
    context.arc(x, y, 2.5, 0, Math.PI * 2)
    context.fill()
  }
  context.restore()
}

function hasValidPoints() {
  return props.x.length > 0 && props.x.length === props.y.length && props.x.every(Number.isFinite) && props.y.every(Number.isFinite)
}

function draw() {
  valid.value = hasValidPoints()
  if (!valid.value || !host.value) {
    if (!valid.value) destroyChart()
    return
  }
  observer?.observe(host.value)
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(120, host.value.clientHeight)
  const data: uPlot.AlignedData = [props.x, props.y]
  if (chart) { chart.setData(data); chart.setSize({ width, height }); return }
  chart = new uPlot({ width, height, legend: { mount: (_chart, element) => legendHost.value?.appendChild(element) }, cursor: { drag: { x: true, y: true } }, scales: { x: { auto: true }, y: { auto: true } }, axes: [
    { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
  ], series: [{}, { label: props.name, stroke: 'transparent', width: 0 }], plugins: [{ hooks: { draw: [drawPoints] } }] }, data, host.value)
}

watch(() => [props.x, props.y, props.name], async () => { valid.value = hasValidPoints(); await nextTick(); draw() }, { deep: true })
onMounted(async () => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); valid.value = hasValidPoints(); await nextTick(); draw() })
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.study-scatter { display:grid; grid-template-rows:minmax(0,1fr) auto; gap:2px; height:190px; min-height:120px; min-width:0; margin-top:4px; background:#101419; }
.study-scatter__host { min-height:0; min-width:0; }
.study-scatter__legend { min-width:0; max-width:100%; color:#b8c8d3; }
.study-scatter__legend :deep(.u-legend) { display:block; width:100%; max-width:100%; font:9px/1.2 "Segoe UI",Arial,sans-serif; }
.study-scatter__legend :deep(.u-inline tr) { display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; width:100%; gap:2px 6px; margin:0; }
.study-scatter__legend :deep(.u-legend th), .study-scatter__legend :deep(.u-legend td) { min-width:0; max-width:100%; padding:1px 2px; white-space:normal; overflow-wrap:anywhere; }
.study-scatter__legend :deep(.u-legend th) { flex:1 1 auto; text-align:left; }
.study-scatter__legend :deep(.u-legend td) { flex:0 1 auto; text-align:right; }
.study-scatter__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
