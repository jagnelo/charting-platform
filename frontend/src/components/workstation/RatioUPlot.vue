<template>
  <div ref="root" class="ratio-chart" :aria-busy="loading" :data-linked-timestamp="props.linkedTimestamp || undefined">
    <div class="ratio-chart__legend">
      <strong>{{ ratioLabels }}</strong>
      <template v-if="editableBenchmarks">
        <label class="ratio-chart__compare">Compare <input v-model="benchmarkDraft" aria-label="Ratio comparison symbol" placeholder="Symbol" @keydown.enter.prevent="addBenchmark" /></label>
        <button type="button" class="ratio-chart__add" aria-label="Add ratio comparison" @click="addBenchmark"><WorkstationGlyph kind="plus" /></button>
        <button v-for="benchmark in localBenchmarks" :key="benchmark" type="button" class="ratio-chart__chip" :aria-label="`Remove ratio comparison ${benchmark}`" :disabled="localBenchmarks.length <= 1" @click="removeBenchmark(benchmark)">{{ benchmark }} <WorkstationGlyph kind="close" /></button>
      </template>
      <label>As of <input v-model="asOfDraft" type="date" aria-label="Ratio as of" /></label><span>{{ status }}</span>
    </div>
    <div v-if="error" class="ratio-chart__state ratio-chart__state--error">{{ error }}</div>
    <div v-else-if="!hasPoints" class="ratio-chart__state">No aligned local bars.</div>
    <div v-else ref="host" class="ratio-chart__host" />
    <small v-if="warning" class="ratio-chart__warning">{{ warning }}</small>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'
import WorkstationGlyph from './WorkstationGlyph.vue'

const props = withDefaults(defineProps<{
  symbol: string
  benchmarks: string[]
  timeframe?: string
  asOf?: string | null
  linkedTimestamp?: string | null
  editableBenchmarks?: boolean
}>(), {
  timeframe: 'D1',
  asOf: null,
  linkedTimestamp: null,
  editableBenchmarks: false,
})
const queryClient = useQueryClient()
const emit = defineEmits<{ cursorTimestamp: [timestamp: string]; configuration: [configuration: Record<string, unknown>] }>()
const root = ref<HTMLElement | null>(null)
const host = ref<HTMLElement | null>(null)
const series = ref<Array<{ benchmark: string; points: Array<{ timestamp: string; value: number }>; coverage: number }>>([])
const error = ref<string | null>(null)
const warning = ref<string | null>(null)
const status = ref('Local adjusted')
const loading = ref(false)
const asOfDraft = ref(props.asOf ? props.asOf.slice(0, 10) : '')
let chart: uPlot | null = null
let resizeObserver: ResizeObserver | null = null
let applyingLinkedCursor = false
let lastPublishedCursor: string | null = null
let loadGeneration = 0
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
const benchmarkDraft = ref('')
function normalizeBenchmarks(values: unknown, symbol = props.symbol) {
  const numerator = symbol.trim().toUpperCase()
  return [...new Set((Array.isArray(values) ? values : [])
    .filter((value): value is string => typeof value === 'string')
    .map(value => value.trim().toUpperCase())
    .filter(Boolean))]
    .filter(value => value !== numerator)
}
// The Golden Layout parent persists tool configuration asynchronously. Keep an
// optimistic local copy so a user edit is visible and actionable immediately,
// even if the parent still holds its previous serialized snapshot for a tick.
const localBenchmarks = ref(normalizeBenchmarks(props.benchmarks))
let pendingBenchmarksKey: string | null = null
const ratioLabels = computed(() => localBenchmarks.value.map(benchmark => `${props.symbol}/${benchmark}`).join(' · '))
const alignedTimestamps = computed(() => {
  const [first, ...rest] = series.value
  if (!first?.points.length) return []
  const otherTimestamps = rest.map(item => new Set(item.points.map(point => point.timestamp)))
  return [...new Set(first.points.map(point => point.timestamp))]
    .filter(timestamp => otherTimestamps.every(timestamps => timestamps.has(timestamp)))
    .sort()
})
const hasPoints = computed(() => alignedTimestamps.value.length > 0)
const colors = ['#6bc0ef', '#e7b35b', '#aa86e8', '#5fc8a2']

function persistBenchmarks(next: string[]) {
  const normalized = normalizeBenchmarks(next)
  if (!normalized.length) return
  localBenchmarks.value = normalized
  pendingBenchmarksKey = normalized.join(',')
  emit('configuration', { ratio_benchmarks: normalized })
}

function addBenchmark() {
  const value = benchmarkDraft.value.trim().toUpperCase()
  if (!value) return
  persistBenchmarks([...localBenchmarks.value, value])
  benchmarkDraft.value = ''
}

function removeBenchmark(benchmark: string) {
  if (localBenchmarks.value.length <= 1) return
  persistBenchmarks(localBenchmarks.value.filter(value => value !== benchmark))
}

async function load() {
  if (!documentVisible.value) return
  const benchmarks = localBenchmarks.value
  if (!props.symbol || !benchmarks.length) return
  const generation = ++loadGeneration
  loading.value = true
  error.value = null
  try {
    const payloads = await Promise.all(benchmarks.map(async benchmark => ({
      benchmark,
      payload: await queryClient.fetchQuery<{
        points: Array<{ timestamp: string; value: number }>
        coverage: number
        warnings: Array<{ message: string }>
      }>({
        queryKey: ['workstation', 'relative-strength', props.symbol.toUpperCase(), benchmark, props.timeframe, asOfTimestamp() ?? null, true],
        queryFn: () => api.get('/analysis/relative-strength', {
          symbol: props.symbol,
          benchmark,
          timeframe: props.timeframe,
          adjusted: true,
          ...(asOfTimestamp() ? { as_of: asOfTimestamp() } : {}),
        }),
        staleTime: 30_000,
      }),
    })))
    if (generation !== loadGeneration) return
    series.value = payloads.map(item => ({ benchmark: item.benchmark, points: item.payload.points, coverage: item.payload.coverage }))
    warning.value = payloads.flatMap(item => item.payload.warnings.map(warning => `${item.benchmark}: ${warning.message}`)).join(' ')
    status.value = `${payloads.map(item => `${item.benchmark} ${(item.payload.coverage * 100).toFixed(0)}%`).join(' · ')} overlap · local adjusted${asOfDraft.value ? ` · as of ${asOfDraft.value}` : ''}`
    await nextTick()
    draw()
  } catch (cause: any) {
    if (generation !== loadGeneration) return
    series.value = []
    error.value = cause?.message ?? 'Unable to calculate ratio'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function handleVisibilityChange() {
  documentVisible.value = document.visibilityState !== 'hidden'
  if (!documentVisible.value) loadGeneration += 1
  else void load()
}

function asOfTimestamp() {
  return asOfDraft.value ? `${asOfDraft.value}T23:59:59Z` : undefined
}

watch(asOfDraft, value => {
  emit('configuration', { as_of: value || null })
  void load()
})
watch(() => props.asOf, value => {
  asOfDraft.value = value ? value.slice(0, 10) : ''
})

// The ratio tool stays mounted while linked symbols and timeframes change. Reload
// its aligned series when those inputs change; otherwise the legend can move to the
// new numerator while the plotted/table data remains from the previous ratio.
watch(() => props.symbol, () => {
  pendingBenchmarksKey = null
  localBenchmarks.value = normalizeBenchmarks(props.benchmarks)
  void load()
})
watch(() => props.benchmarks.join(','), key => {
  // Ignore the parent's old snapshot while an optimistic edit is pending.
  // Clear the fence once the serialized configuration catches up.
  if (pendingBenchmarksKey !== null) {
    if (key !== pendingBenchmarksKey) return
    pendingBenchmarksKey = null
  }
  localBenchmarks.value = normalizeBenchmarks(props.benchmarks)
  void load()
})
watch(() => props.timeframe, () => void load())

function seriesData(): uPlot.AlignedData {
  // Ratios are only meaningful where every requested leg has an observation.
  // Keep the aligned intersection here even if a provider accidentally returns
  // different calendars for separate benchmark requests; never bridge that gap
  // with null/forward-filled values in the numerical chart.
  const timestamps = alignedTimestamps.value
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
    // The workstation owns the dense ratio legend above the plot. uPlot's
    // default HTML legend would render below the canvas and collide with the
    // warning/footer row in compact docked windows.
    legend: { show: false },
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: true }, y: { auto: true } },
    axes: [
      { stroke: '#70808b', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
      { stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, ticks: { stroke: '#40505a', width: 1 }, font: '10px Segoe UI' },
    ],
    series: [{}, ...series.value.map((item, index) => ({ label: `${props.symbol}/${item.benchmark}`, stroke: colors[index % colors.length], width: 1.5 }))],
    hooks: {
      setCursor: [(u) => {
        if (applyingLinkedCursor || u.cursor.idx == null) return
        const xValues = u.data[0] as number[] | undefined
        const seconds = xValues?.[u.cursor.idx]
        if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return
        const timestamp = new Date(seconds * 1000).toISOString()
        if (timestamp === lastPublishedCursor) return
        lastPublishedCursor = timestamp
        emit('cursorTimestamp', timestamp)
      }],
    },
  }, data, host.value)
  applyLinkedTimestamp(props.linkedTimestamp)
}

function applyLinkedTimestamp(timestamp: string | null) {
  if (!chart || !timestamp) return
  const targetSeconds = new Date(timestamp).getTime() / 1000
  if (!Number.isFinite(targetSeconds)) return
  const xValues = chart.data[0] as number[] | undefined
  if (!xValues?.length) return
  let index = xValues.findIndex(value => value > targetSeconds)
  if (index === -1) index = xValues.length - 1
  else if (index > 0) index -= 1
  applyingLinkedCursor = true
  chart.setCursor({
    left: chart.valToPos(xValues[index], 'x'),
    top: chart.cursor.top ?? 0,
  })
  applyingLinkedCursor = false
}

watch(() => props.linkedTimestamp, applyLinkedTimestamp)
onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  resizeObserver = new ResizeObserver(() => draw())
  if (root.value) resizeObserver.observe(root.value)
  void load()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  resizeObserver?.disconnect()
  chart?.destroy()
  chart = null
})
</script>

<style scoped>
.ratio-chart { position: relative; display: grid; height: 100%; min-height: 0; grid-template-rows: 21px minmax(0, 1fr) auto; background: #101419; }
.ratio-chart__legend { display: flex; gap: 8px; align-items: center; padding: 0 7px; color: #6bc0ef; border-bottom: 1px solid #26313a; font: 10px "Segoe UI", Arial, sans-serif; }
.ratio-chart__legend label { display: inline-flex; gap: 3px; align-items: center; color: #9aabb6; }
.ratio-chart__legend input { width: 96px; border: 1px solid #42515c; background: #11161b; color: #dce9f2; font: inherit; }
.ratio-chart__compare input { width: 58px; }
.ratio-chart__add, .ratio-chart__chip { border: 1px solid #42515c; background: #182127; color: #b9c8d1; font: inherit; cursor: pointer; }
.ratio-chart__add { width: 18px; padding: 0; }
.ratio-chart__chip { padding: 1px 4px; color: #d8b36b; }
.ratio-chart__chip:disabled { cursor: default; opacity: .65; }
.ratio-chart__legend span { color: #8296a4; }
.ratio-chart__host { min-height: 0; }
.ratio-chart__state { display: grid; place-items: center; color: #8fa0aa; font: 11px "Segoe UI", Arial, sans-serif; }
.ratio-chart__state--error { color: #ec8f8f; }
.ratio-chart__warning { padding: 3px 7px; color: #d0ae6d; font: 9px "Segoe UI", Arial, sans-serif; }
</style>
