<template>
  <div ref="root" class="study-scatter">
    <div v-if="!valid" class="study-scatter__state" role="status" aria-live="polite" aria-atomic="true">Scatter output has no aligned numeric points.</div>
    <div v-else ref="host" class="study-scatter__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; x: number[]; y: number[] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
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
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(120, host.value.clientHeight)
  const data: uPlot.AlignedData = [props.x, props.y]
  if (chart) { chart.setData(data); chart.setSize({ width, height }); return }
  chart = new uPlot({ width, height, cursor: { drag: { x: true, y: true } }, scales: { x: { auto: true }, y: { auto: true } }, axes: [
    { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
  ], series: [{}, { label: props.name, stroke: 'transparent', width: 0 }], plugins: [{ hooks: { draw: [drawPoints] } }] }, data, host.value)
}

watch(() => [props.x, props.y, props.name], async () => { valid.value = hasValidPoints(); await nextTick(); draw() }, { deep: true })
onMounted(async () => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); valid.value = hasValidPoints(); await nextTick(); draw() })
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.study-scatter { height:190px; min-height:120px; margin-top:4px; background:#101419; }
.study-scatter__host { height:100%; }
.study-scatter__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
