<template>
  <div ref="root" class="ratio-chart">
    <div class="ratio-chart__legend"><strong>{{ ratioLabels }}</strong><span>{{ status }}</span></div>
    <div v-if="error" class="ratio-chart__state ratio-chart__state--error">{{ error }}</div>
    <div v-else-if="!hasPoints" class="ratio-chart__state">No aligned local bars.</div>
    <div v-else ref="host" class="ratio-chart__host" />
    <small v-if="warning" class="ratio-chart__warning">{{ warning }}</small>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'

const props = defineProps<{ symbol: string; benchmarks: string[] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const series = ref<Array<{ benchmark: string; points: Array<{ timestamp: string; value: number }>; coverage: number }>>([])
const error = ref<string | null>(null)
const warning = ref<string | null>(null)
const status = ref('Local adjusted')
let chart: uPlot | null = null
let resizeObserver: ResizeObserver | null = null
const ratioLabels = computed(() => props.benchmarks.map(benchmark => `${props.symbol}/${benchmark}`).join(' · '))
const hasPoints = computed(() => series.value.some(item => item.points.length > 0))
const colors = ['#6bc0ef', '#e7b35b', '#aa86e8', '#5fc8a2']

async function load() {
  const benchmarks = [...new Set(props.benchmarks.map(value => value.trim().toUpperCase()).filter(Boolean))]
  if (!props.symbol || !benchmarks.length) return
  error.value = null
  try {
    const payloads = await Promise.all(benchmarks.map(async benchmark => ({
      benchmark,
      payload: await api.get<{
        points: Array<{ timestamp: string; value: number }>
        coverage: number
        warnings: Array<{ message: string }>
      }>('/analysis/relative-strength', { symbol: props.symbol, benchmark, adjusted: true }),
    })))
    series.value = payloads.map(item => ({ benchmark: item.benchmark, points: item.payload.points, coverage: item.payload.coverage }))
    warning.value = payloads.flatMap(item => item.payload.warnings.map(warning => `${item.benchmark}: ${warning.message}`)).join(' ')
    status.value = `${payloads.map(item => `${item.benchmark} ${(item.payload.coverage * 100).toFixed(0)}%`).join(' · ')} overlap · local adjusted`
    await nextTick()
    draw()
  } catch (cause: any) {
    series.value = []
    error.value = cause?.message ?? 'Unable to calculate ratio'
  }
}

function seriesData(): uPlot.AlignedData {
  const timestamps = [...new Set(series.value.flatMap(item => item.points.map(point => point.timestamp)))].sort()
  return [timestamps.map(timestamp => Math.floor(new Date(timestamp).getTime() / 1000)), ...series.value.map(item => {
    const values = new Map(item.points.map(point => [point.timestamp, point.value]))
    return timestamps.map(timestamp => values.get(timestamp) ?? null)
  })]
}

function draw() {
  if (!host.value || !hasPoints.value) return
  const width = Math.max(180, host.value.clientWidth)
  const height = Math.max(90, host.value.clientHeight)
  const data = seriesData()
  if (chart && chart.series.length !== series.value.length + 1) {
    chart.destroy()
    chart = null
  }
  if (chart) {
    chart.setData(data)
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
    series: [{}, ...series.value.map((item, index) => ({ label: `${props.symbol}/${item.benchmark}`, stroke: colors[index % colors.length], width: 1.5 }))],
  }, data, host.value)
}

watch(() => `${props.symbol}/${props.benchmarks.join('/')}`, () => { void load() })
onMounted(() => {
  resizeObserver = new ResizeObserver(() => draw())
  if (root.value) resizeObserver.observe(root.value)
  void load()
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.destroy()
  chart = null
})
</script>

<style scoped>
.ratio-chart { position: relative; display: grid; height: 100%; min-height: 0; grid-template-rows: 21px minmax(0, 1fr) auto; background: #101419; }
.ratio-chart__legend { display: flex; gap: 8px; align-items: center; padding: 0 7px; color: #6bc0ef; border-bottom: 1px solid #26313a; font: 10px "Segoe UI", Arial, sans-serif; }
.ratio-chart__legend span { color: #8296a4; }
.ratio-chart__host { min-height: 0; }
.ratio-chart__state { display: grid; place-items: center; color: #8fa0aa; font: 11px "Segoe UI", Arial, sans-serif; }
.ratio-chart__state--error { color: #ec8f8f; }
.ratio-chart__warning { padding: 3px 7px; color: #d0ae6d; font: 9px "Segoe UI", Arial, sans-serif; }
</style>
