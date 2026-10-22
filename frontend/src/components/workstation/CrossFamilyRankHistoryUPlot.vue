<template>
  <div ref="root" class="cross-family-rank-history">
    <div ref="host" class="cross-family-rank-history__host" :class="{ 'cross-family-rank-history__host--hidden': !valid }" aria-label="Cross-family historical rank" />
    <div v-if="!valid" class="cross-family-rank-history__state" role="status" aria-live="polite" aria-atomic="true">
      Cross-family rank history is unavailable.
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { CrossFamilyRankingHistoryState } from '@/stores/workspace'

const props = defineProps<{ history?: CrossFamilyRankingHistoryState }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const valid = ref(false)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null

const palette = ['#e7b764', '#62bd8c', '#74bde8', '#d889bd', '#d98b6a', '#a897e8']

function availableRows() {
  return (props.history?.rows ?? []).filter(row => row.available && row.points.length > 0)
}

function timestamps() {
  return [...new Set(availableRows().flatMap(row => row.points.map(point => point.timestamp)))].sort()
}

function hasValidData() {
  const rows = availableRows()
  return rows.length > 0
    && rows.some(row => row.points.some(point => Number.isFinite(point.rank)))
    && rows.every(row => row.points.every(point => Number.isFinite(Date.parse(point.timestamp)) && (point.rank == null || Number.isFinite(point.rank))))
}

function data(): uPlot.AlignedData {
  const points = timestamps()
  return [
    points.map(point => Math.floor(new Date(point).getTime() / 1000)),
    ...availableRows().map(row => {
      const byTimestamp = new Map(row.points.map(point => [point.timestamp, point.rank ?? null]))
      return points.map(point => byTimestamp.get(point) ?? null)
    }),
  ]
}

function destroyChart() {
  chart?.destroy()
  chart = null
}

function draw() {
  valid.value = hasValidData()
  if (!valid.value || !host.value) {
    if (!valid.value) destroyChart()
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
    scales: { x: { time: true }, y: { auto: true, dir: -1 } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => `#${Math.round(value)}`), font: '10px Segoe UI' },
    ],
    series: [
      {},
      ...availableRows().map((row, index) => ({
        label: `${row.family_name || row.label || row.family_key} rank`,
        stroke: palette[index % palette.length],
        width: 1.5,
        points: { show: true, size: 3 },
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
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>

<style scoped>
.cross-family-rank-history { flex: 1 1 100%; position: relative; z-index: 0; height: 150px; min-height: 120px; margin-top: 4px; background: #101419; }
.cross-family-rank-history__host { height: 100%; }
.cross-family-rank-history__host--hidden { display: none; }
.cross-family-rank-history__state { display: grid; height: 100%; place-items: center; color: #8497a4; font: 10px "Segoe UI", Arial, sans-serif; pointer-events: none; }
</style>
