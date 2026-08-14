<template>
  <div ref="root" class="generic-breadth-history">
    <div v-if="!valid" class="generic-breadth-history__state" role="status" aria-live="polite" aria-atomic="true">Historical condition breadth is unavailable.</div>
    <div v-else ref="host" class="generic-breadth-history__host" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { GenericBreadthHistoryState } from '@/stores/workspace'

const props = defineProps<{ history?: GenericBreadthHistoryState }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null

function destroyChart() { chart?.destroy(); chart = null }
function hasValidData() {
  const points = props.history?.points ?? []
  return points.length > 0 && points.every(point => (
    Number.isFinite(Date.parse(point.timestamp))
    && (point.percentage == null || Number.isFinite(point.percentage))
  ))
}
function data(): uPlot.AlignedData {
  const points = props.history?.points ?? []
  return [
    points.map(point => Math.floor(new Date(point.timestamp).getTime() / 1000)),
    points.map(point => point.percentage),
  ]
}
function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) { if (!valid.value) destroyChart(); return }
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(110, host.value.clientHeight)
  if (chart) {
    chart.setData(data())
    chart.setSize({ width, height })
    return
  }
  chart = new uPlot({
    width,
    height,
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: true }, y: { range: [0, 1] } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => `${Math.round(value * 100)}%`), font: '10px Segoe UI' },
    ],
    series: [{}, { label: 'Condition breadth', stroke: '#77c3ee', width: 1.5 }],
  }, data(), host.value)
}

watch(() => props.history, async () => { valid.value = hasValidData(); await nextTick(); draw() }, { deep: true })
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
.generic-breadth-history { position: relative; z-index: 0; height: 150px; min-height: 110px; margin-top: 4px; background: #101419; }
.generic-breadth-history__host { height: 100%; }
.generic-breadth-history__state { display: grid; height: 100%; place-items: center; color: #8497a4; font: 10px "Segoe UI", Arial, sans-serif; pointer-events: none; }
</style>
