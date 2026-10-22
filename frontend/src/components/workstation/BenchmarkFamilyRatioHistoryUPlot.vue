<template>
  <div ref="root" class="benchmark-family-ratio-history">
    <div ref="host" class="benchmark-family-ratio-history__host" :class="{ 'benchmark-family-ratio-history__host--hidden': !valid }" aria-label="Benchmark family relative strength history" />
    <div v-if="!valid" class="benchmark-family-ratio-history__state" role="status" aria-live="polite" aria-atomic="true">
      Family relative strength history is unavailable.
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { BenchmarkFamilyRatiosState, BenchmarkFamilyRatioState } from '@/stores/workspace'

const props = defineProps<{ ratios?: BenchmarkFamilyRatiosState }>()
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

function availableRatios(): BenchmarkFamilyRatioState[] {
  return (props.ratios?.ratios ?? []).filter(ratio => ratio.points.length > 0)
}

function hasValidData() {
  const ratios = availableRatios()
  return ratios.length > 0 && ratios.every(ratio => ratio.points.every(point => (
    Number.isFinite(Date.parse(point.timestamp)) && Number.isFinite(point.value)
  )))
}

function timestamps() {
  return [...new Set(availableRatios().flatMap(ratio => ratio.points.map(point => point.timestamp)))].sort()
}

function data(): uPlot.AlignedData {
  const points = timestamps()
  return [
    points.map(point => Math.floor(new Date(point).getTime() / 1000)),
    ...availableRatios().map(ratio => {
      const byTimestamp = new Map(ratio.points.map(point => [point.timestamp, point.value]))
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
    scales: { x: { time: true }, y: { auto: true } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => value.toFixed(2)), font: '10px Segoe UI' },
    ],
    series: [
      {},
      ...availableRatios().map(ratio => ({
        label: `${ratio.symbol}/${ratio.benchmark}`,
        stroke: roleColors[ratio.role] ?? '#9aabb6',
        width: 1.5,
      })),
    ],
  }, data(), host.value)
}

watch(() => props.ratios, async () => { await nextTick(); draw() }, { deep: true })
onMounted(async () => {
  observer = new ResizeObserver(draw)
  if (root.value) observer.observe(root.value)
  await nextTick()
  draw()
})
onBeforeUnmount(() => { observer?.disconnect(); chart?.destroy(); chart = null })
</script>

<style scoped>
.benchmark-family-ratio-history { flex: 1 1 100%; position: relative; z-index: 0; height: 150px; min-height: 120px; margin-top: 4px; background: #101419; }
.benchmark-family-ratio-history__host { height: 100%; }
.benchmark-family-ratio-history__host--hidden { display: none; }
.benchmark-family-ratio-history__state { display: grid; height: 100%; place-items: center; color: #8497a4; font: 10px "Segoe UI", Arial, sans-serif; pointer-events: none; }
</style>
