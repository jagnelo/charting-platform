<template>
  <div ref="root" class="study-range">
    <div v-if="!valid" class="study-range__state">Range has no aligned finite bounds.</div>
    <div v-else ref="host" class="study-range__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps<{ name: string; timestamps: string[]; lower: number[]; upper: number[]; center?: number[] | null }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null
function destroyChart() { chart?.destroy(); chart = null }

function xValues() { return props.timestamps.map((timestamp, index) => { const parsed = Date.parse(timestamp); return Number.isFinite(parsed) ? parsed / 1000 : index }) }
function data(): uPlot.AlignedData { return [xValues(), props.lower, props.upper, props.center?.length === props.lower.length ? props.center : props.lower.map(() => null)] }
function drawBand(instance: uPlot) {
  const context = instance.ctx
  context.save()
  context.fillStyle = 'rgba(119,195,238,.16)'
  context.beginPath()
  props.upper.forEach((value, index) => { const x = instance.valToPos(xValues()[index], 'x', true); const y = instance.valToPos(value, 'y', true); if (index === 0) context.moveTo(x, y); else context.lineTo(x, y) })
  for (let index = props.lower.length - 1; index >= 0; index -= 1) context.lineTo(instance.valToPos(xValues()[index], 'x', true), instance.valToPos(props.lower[index], 'y', true))
  context.closePath()
  context.fill()
  context.restore()
}
function hasValidData() { return props.timestamps.length > 0 && props.timestamps.length === props.lower.length && props.lower.length === props.upper.length && props.lower.every(value => Number.isFinite(value)) && props.upper.every(value => Number.isFinite(value)) && (!props.center || props.center.length === props.lower.length && props.center.every(value => Number.isFinite(value))) }
function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) { if (!valid.value) destroyChart(); return }
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(120, host.value.clientHeight)
  if (chart) { chart.setData(data()); chart.setSize({ width, height }); return }
  chart = new uPlot({
    width,
    height,
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: props.timestamps.every(timestamp => Number.isFinite(Date.parse(timestamp))) }, y: { auto: true } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, { label: 'Lower', stroke: '#5b9fc5', width: 1 }, { label: 'Upper', stroke: '#77c3ee', width: 1 }, { label: props.name, stroke: '#f0c674', width: 1.5 }],
    plugins: [{ hooks: { draw: [drawBand] } }],
  }, data(), host.value)
}
watch(() => [props.timestamps, props.lower, props.upper, props.center, props.name], async () => { valid.value = hasValidData(); await nextTick(); draw() }, { deep: true })
onMounted(async () => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); valid.value = hasValidData(); await nextTick(); draw() })
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.study-range { height:190px; min-height:120px; margin-top:4px; background:#101419; }.study-range__host { height:100%; }.study-range__state { display:grid; height:100%; place-items:center; color:#8497a4; font:10px "Segoe UI",Arial,sans-serif; }
</style>
