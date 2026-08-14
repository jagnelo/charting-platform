<template><div ref="root" class="breadth-history"><div v-if="!history?.points.length" class="breadth-history__state">Historical breadth is unavailable.</div><div v-else ref="host" class="breadth-history__host" /></div></template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { BreadthHistoryState } from '@/stores/workspace'

const props = defineProps<{ history?: BreadthHistoryState }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
let chart: uPlot | null = null
let observer: ResizeObserver | null = null
function destroyChart() { chart?.destroy(); chart = null }
function hasValidData() { return Boolean(props.history?.points.length) }
function data(): uPlot.AlignedData {
  const points = props.history?.points ?? []
  return [points.map(point => new Date(point.timestamp).getTime() / 1000), ...['ma20', 'ma50', 'ma200'].map(key => points.map(point => point.above_ma[key] ?? null))]
}
function draw() {
  if (!hasValidData() || !host.value) { if (!hasValidData()) destroyChart(); return }
  const width = Math.max(180, host.value.clientWidth), height = Math.max(120, host.value.clientHeight)
  if (chart) { chart.setData(data()); chart.setSize({ width, height }); return }
  chart = new uPlot({ width, height, cursor: { drag: { x: true, y: false } }, scales: { x: { time: true }, y: { range: [0, 1] } }, axes: [{ stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, font: '10px Segoe UI' }, { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, vals) => vals.map(value => `${Math.round(value * 100)}%`), font: '10px Segoe UI' }], series: [{}, { label: '>20 MA', stroke: '#62bd8c', width: 1.5 }, { label: '>50 MA', stroke: '#74bde8', width: 1.5 }, { label: '>200 MA', stroke: '#e7b764', width: 1.5 }] }, data(), host.value)
}
watch(() => props.history, async () => { await nextTick(); draw() }, { deep: true })
onMounted(async () => { observer = new ResizeObserver(draw); if (root.value) observer.observe(root.value); await nextTick(); draw() })
onBeforeUnmount(() => { observer?.disconnect(); destroyChart() })
</script>
<style scoped>.breadth-history{height:100%;min-height:0;background:#101419}.breadth-history__host{height:100%}.breadth-history__state{display:grid;height:100%;place-items:center;color:#8497a4;font:10px "Segoe UI",Arial,sans-serif}</style>
