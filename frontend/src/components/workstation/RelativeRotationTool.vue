<template>
  <section class="rotation-tool">
    <header><strong>Relative Rotation · {{ benchmark }}</strong><div class="rotation-tool__controls"><label>Universe <select v-model="groupKey" aria-label="Rotation universe"><option value="sp500-sectors">S&amp;P 500 sectors</option><option value="us-benchmarks">US benchmarks</option></select></label><label>Benchmark <input v-model.trim="benchmark" aria-label="Rotation benchmark" /></label><label>Timeframe <select v-model="timeframe" aria-label="Rotation timeframe"><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option></select></label><label>Sampling <input v-model.number="sampling" aria-label="Rotation sampling" type="number" min="1" max="30" /></label><label>Lookback <input v-model.number="lookback" aria-label="Rotation lookback" type="number" min="2" max="252" /></label><label>Tail <input v-model.number="tailLength" aria-label="Rotation tail length" type="number" min="1" max="100" /></label><label>As of <input v-model="asOf" aria-label="Rotation as of" type="date" /></label><label class="rotation-tool__adjusted"><input v-model="adjusted" aria-label="Rotation split adjusted" type="checkbox" /> Adjusted</label></div><small>Trend: ratio return over {{ lookback }} sampled observations · Momentum: change in that trend{{ asOf ? ` · As of ${asOf}` : '' }}{{ freshness ? ` · ${freshness}` : '' }}</small></header>
    <p v-if="loading" class="rotation-tool__state">Calculating aligned local ratios…</p>
    <p v-else-if="error" class="rotation-tool__state rotation-tool__state--error">{{ error }}</p>
    <p v-else-if="!rows.length" class="rotation-tool__state">No sector rotation rows are available.</p>
    <template v-else>
      <div ref="plotHost" class="rotation-tool__plot" aria-label="Relative rotation trend and momentum plane" />
      <div class="rotation-tool__table"><div class="rotation-tool__head"><span>Sector</span><span>State</span><span>Trend</span><span>Momentum</span><span>Heading</span><span>Distance</span><span>Velocity</span><span>Transition</span><span>Time</span><span>Coverage</span><span>Tail</span></div><button v-for="row in rows" :key="row.instrument_id" type="button" class="rotation-tool__row" @click="emit('select', row.symbol)"><strong>{{ row.symbol }}</strong><span :class="`rotation-tool__state-${row.state}`">{{ row.state ?? 'Unavailable' }}</span><span>{{ percent(row.trend) }}</span><span>{{ percent(row.momentum) }}</span><span>{{ row.heading == null ? '—' : `${row.heading.toFixed(0)}°` }}</span><span>{{ percent(row.distance) }}</span><span>{{ percent(row.velocity) }}</span><span>{{ row.transition ?? '—' }}</span><span>{{ row.time_in_state ?? '—' }}</span><span>{{ percent(row.coverage) }}</span><span>{{ row.tail.length }}</span></button></div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'

interface Tail { timestamp: string; trend: number; momentum: number }
interface Row { instrument_id: number; symbol: string; state: string | null; trend: number | null; momentum: number | null; heading?: number | null; distance?: number | null; velocity?: number | null; transition?: string | null; time_in_state?: number | null; coverage: number; tail: Tail[] }
interface PlotPoint extends Tail { color: string; last: boolean }
const props = defineProps<{ configuration?: Record<string, unknown> }>()
const emit = defineEmits<{ select: [symbol: string]; configuration: [configuration: Record<string, unknown>] }>()
const rows = ref<Row[]>([]), loading = ref(true), error = ref(''), freshness = ref('')
const configString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const groupKey = ref(configString('group_key', 'sp500-sectors'))
const benchmark = ref(configString('benchmark', 'SPY').toUpperCase())
const timeframe = ref(['D1', 'W1', 'MN'].includes(configString('timeframe', 'D1')) ? configString('timeframe', 'D1') : 'D1')
const lookback = ref(Math.min(252, Math.max(2, Number(props.configuration?.lookback ?? 20) || 20)))
const tailLength = ref(Math.min(100, Math.max(1, Number(props.configuration?.tail_length ?? 10) || 10)))
const sampling = ref(Math.min(30, Math.max(1, Number(props.configuration?.sampling ?? 1) || 1)))
const asOf = ref(configString('as_of', ''))
const adjusted = ref(props.configuration?.adjusted !== false)
const plotHost = ref<HTMLElement | null>(null)
let plot: uPlot | null = null
let observer: ResizeObserver | null = null
let points: PlotPoint[] = []
let loadGeneration = 0
function percent(value: number | null | undefined) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
const colors: Record<string, string> = { leading: '#61c58c', weakening: '#e7bc68', improving: '#6dbbe6', lagging: '#df8181' }
function drawPlot() {
  if (!plotHost.value) return
  points = rows.value.flatMap(row => row.tail.map((tail, index) => ({ ...tail, color: colors[row.state ?? ''] ?? '#8796a1', last: index === row.tail.length - 1 })))
  const width = Math.max(200, plotHost.value.clientWidth), height = Math.max(130, plotHost.value.clientHeight)
  const data: uPlot.AlignedData = [points.map(point => point.trend), points.map(point => point.momentum)]
  if (plot) {
    plot.setData(data)
    plot.setSize({ width, height })
    return
  }
  const markerPlugin: uPlot.Plugin = { hooks: { draw: [(chart) => {
    const ctx = chart.ctx
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index]
      const x = chart.valToPos(point.trend, 'x'), y = chart.valToPos(point.momentum, 'y')
      ctx.fillStyle = point.color; ctx.beginPath(); ctx.arc(x, y, point.last ? 3.5 : 2, 0, Math.PI * 2); ctx.fill()
    }
  }] } }
  plot = new uPlot({ width, height, cursor: { drag: { x: true, y: true } }, scales: { x: { auto: true }, y: { auto: true } }, axes: [
    { label: 'Relative trend', stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => `${(value * 100).toFixed(1)}%`), font: '10px Segoe UI' },
    { label: 'Relative momentum', stroke: '#9aabb6', grid: { stroke: '#26313a', width: 1 }, values: (_u, values) => values.map(value => `${(value * 100).toFixed(1)}%`), font: '10px Segoe UI' },
  ], series: [{}, { show: false }], plugins: [markerPlugin] }, data, plotHost.value)
}
function publishConfiguration() {
  emit('configuration', { ...(props.configuration ?? {}), group_key: groupKey.value, benchmark: benchmark.value.toUpperCase(), timeframe: timeframe.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, as_of: asOf.value || null, adjusted: adjusted.value })
}
function asOfTimestamp() { return asOf.value ? `${asOf.value}T23:59:59Z` : undefined }
async function load() {
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const payload = await api.get<{ rows: Row[]; freshness?: string }>(`/analysis/groups/${encodeURIComponent(groupKey.value)}/relative-rotation`, { benchmark: benchmark.value.toUpperCase(), timeframe: timeframe.value, adjusted: adjusted.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, as_of: asOfTimestamp() })
    if (generation !== loadGeneration) return
    rows.value = payload.rows; freshness.value = payload.freshness ?? ''; await nextTick(); drawPlot()
  } catch (cause: any) {
    if (generation === loadGeneration) { rows.value = []; error.value = cause?.message ?? 'Relative rotation is unavailable.' }
  } finally { if (generation === loadGeneration) loading.value = false }
}
onMounted(async () => {
  observer = new ResizeObserver(drawPlot)
  if (plotHost.value) observer.observe(plotHost.value)
  await load()
})
watch([groupKey, benchmark, timeframe, sampling, lookback, tailLength, asOf, adjusted], () => { publishConfiguration(); if (sampling.value >= 1 && lookback.value >= 2 && tailLength.value >= 1) void load() })
watch(() => props.configuration, configuration => {
  if (typeof configuration?.group_key === 'string') groupKey.value = configuration.group_key
  if (typeof configuration?.benchmark === 'string') benchmark.value = configuration.benchmark.toUpperCase()
  if (typeof configuration?.timeframe === 'string' && ['D1', 'W1', 'MN'].includes(configuration.timeframe)) timeframe.value = configuration.timeframe
  if (Number.isFinite(Number(configuration?.lookback))) lookback.value = Math.min(252, Math.max(2, Number(configuration?.lookback)))
  if (Number.isFinite(Number(configuration?.tail_length))) tailLength.value = Math.min(100, Math.max(1, Number(configuration?.tail_length)))
  if (Number.isFinite(Number(configuration?.sampling))) sampling.value = Math.min(30, Math.max(1, Number(configuration?.sampling)))
  if (typeof configuration?.as_of === 'string') asOf.value = configuration.as_of
  if (configuration?.as_of === null) asOf.value = ''
  if (typeof configuration?.adjusted === 'boolean') adjusted.value = configuration.adjusted
}, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); plot?.destroy(); plot = null })
</script>

<style scoped>.rotation-tool{display:grid;height:100%;min-height:0;grid-template-rows:auto 150px minmax(0,1fr);background:#11161b;color:#cad4db;font:10px "Segoe UI",Arial,sans-serif}.rotation-tool header{display:grid;gap:4px;padding:7px;border-bottom:1px solid #2d3841}.rotation-tool header small{color:#82929d}.rotation-tool__controls{display:flex;flex-wrap:wrap;gap:4px;align-items:center}.rotation-tool__controls label{display:flex;align-items:center;gap:2px;color:#9aabb6}.rotation-tool__controls input,.rotation-tool__controls select{min-width:0;width:58px;border:1px solid #3a4954;background:#172027;color:#dce6ed;font:inherit;padding:1px 3px}.rotation-tool__controls label:first-child select{width:112px}.rotation-tool__controls label:nth-child(7) input{width:100px}.rotation-tool__adjusted input{width:auto}.rotation-tool__state{display:grid;place-items:center;color:#8596a1}.rotation-tool__state--error{color:#e28c8c}.rotation-tool__plot{min-height:0;background:#101419}.rotation-tool__table{overflow:auto}.rotation-tool__head,.rotation-tool__row{display:grid;grid-template-columns:54px 78px repeat(7, minmax(58px, 1fr)) 64px 38px;align-items:center;gap:5px;padding:5px 7px;min-width:720px}.rotation-tool__head{position:sticky;top:0;background:#20282f;color:#9baab5;font-weight:600;text-transform:uppercase}.rotation-tool__row{width:100%;border:0;border-bottom:1px solid #20282f;background:transparent;color:inherit;text-align:left;cursor:pointer}.rotation-tool__row:hover{background:#1d4057}.rotation-tool__state-leading{color:#61c58c}.rotation-tool__state-weakening{color:#e7bc68}.rotation-tool__state-improving{color:#6dbbe6}.rotation-tool__state-lagging{color:#df8181}</style>
