<template>
  <div ref="root" class="benchmark-family-breadth-history">
    <div ref="host" class="benchmark-family-breadth-history__host" :class="{ 'benchmark-family-breadth-history__host--hidden': !valid }" aria-label="Benchmark family historical participation" />
    <div v-if="!valid" class="benchmark-family-breadth-history__state" role="status" aria-live="polite" aria-atomic="true">
      Family breadth history is unavailable.
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { BenchmarkFamilyBreadthHistoryState } from '@/stores/workspace'

const props = defineProps<{ history?: BenchmarkFamilyBreadthHistoryState }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null

const roleColors: Record<string, string> = {
  cap_weight: '#e7b764',
  equal_weight: '#62bd8c',
  value: '#74bde8',
  growth: '#d889bd',
}

function availableRoles() {
  return (props.history?.roles ?? []).filter(role => role.available && role.points.length > 0)
}

function hasValidData() {
  const roles = availableRoles()
  return roles.length > 0 && roles.every(role => role.points.every(point => (
    Number.isFinite(Date.parse(point.timestamp))
    && (point.above_ma.ma20 == null || Number.isFinite(point.above_ma.ma20))
  )))
}

function timestamps() {
  return [...new Set(availableRoles().flatMap(role => role.points.map(point => point.timestamp)))].sort()
}

function data(): uPlot.AlignedData {
  const points = timestamps()
  return [
    points.map(point => Math.floor(new Date(point).getTime() / 1000)),
    ...availableRoles().map(role => {
      const byTimestamp = new Map(role.points.map(point => [point.timestamp, point.above_ma.ma20]))
      return points.map(point => byTimestamp.get(point) ?? null)
    }),
  ]
}

function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) {
    if (!valid.value) chart?.destroy()
    if (!valid.value) chart = null
    return
  }
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
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: true }, y: { range: [0, 1] } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => `${Math.round(value * 100)}%`), font: '10px Segoe UI' },
    ],
    series: [
      {},
      ...availableRoles().map(role => ({
        label: role.label || role.role,
        stroke: roleColors[role.role] ?? '#9aabb6',
        width: 1.5,
      })),
    ],
  }, data(), host.value)
}

watch(() => props.history, async () => { await nextTick(); draw() }, { deep: true })
onMounted(async () => {
  observer = new ResizeObserver(draw)
  if (root.value) observer.observe(root.value)
  await nextTick()
  draw()
})
onBeforeUnmount(() => { observer?.disconnect(); chart?.destroy(); chart = null })
</script>

<style scoped>
.benchmark-family-breadth-history { flex: 1 1 100%; position: relative; z-index: 0; height: 150px; min-height: 120px; margin-top: 4px; background: #101419; }
.benchmark-family-breadth-history__host { height: 100%; }
.benchmark-family-breadth-history__host--hidden { display: none; }
.benchmark-family-breadth-history__state { display: grid; height: 100%; place-items: center; color: #8497a4; font: 10px "Segoe UI", Arial, sans-serif; pointer-events: none; }
</style>
