<template>
  <section class="rotation-tool" role="region" :aria-label="`Relative rotation vs ${rotationBenchmark}`" :aria-busy="loading">
    <header><strong>Relative Rotation · {{ rotationBenchmark }}</strong><div class="rotation-tool__controls"><label>Universe <select v-model="groupKey" aria-label="Rotation universe"><option value="sp500-sectors">S&amp;P 500 sectors</option><option value="us-benchmarks">US benchmarks</option><option v-for="family in familyKeys" :key="family.key" :value="family.key">{{ family.label }}</option></select></label><label>Benchmark <input v-model.trim="benchmark" aria-label="Rotation benchmark" :disabled="isFamily" /></label><label>Timeframe <select v-model="timeframe" aria-label="Rotation timeframe"><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option></select></label><label>Sampling <input v-model.number="sampling" aria-label="Rotation sampling" type="number" min="1" max="30" /></label><label>Lookback <input v-model.number="lookback" aria-label="Rotation lookback" type="number" min="2" max="252" /></label><label>Tail <input v-model.number="tailLength" aria-label="Rotation tail length" type="number" min="1" max="100" /></label><label>History <input v-model.number="historyLength" aria-label="Rotation history length" type="number" min="0" max="1000" /></label><label>As of <input v-model="asOf" aria-label="Rotation as of" type="date" /></label><label class="rotation-tool__adjusted"><input v-model="adjusted" aria-label="Rotation split adjusted" type="checkbox" /> Adjusted</label></div><small>Trend: ratio return over {{ lookback }} sampled observations · Momentum: change in that trend{{ historyLength ? ` · ${historyLength} history points` : '' }}{{ asOf ? ` · As of ${asOf}` : '' }}{{ freshness ? ` · ${formatWorkstationFreshness(freshness)}` : '' }}</small></header>
    <p v-if="loading" class="rotation-tool__state" role="status" aria-live="polite" aria-atomic="true">Calculating aligned local ratios…</p>
    <p v-else-if="error" class="rotation-tool__state rotation-tool__state--error" role="alert" aria-live="assertive" aria-atomic="true">{{ error }}</p>
    <p v-else-if="!rows.length" class="rotation-tool__state" role="status" aria-live="polite" aria-atomic="true">No {{ isFamily ? 'family-leg' : 'sector' }} rotation rows are available.</p>
    <template v-else>
      <div class="rotation-tool__plot-shell" @mousemove="onPlotMove" @mouseleave="hovered = null" @click="selectHovered">
        <div ref="plotHost" class="rotation-tool__plot" aria-label="Relative rotation trend and momentum plane" />
        <div v-if="hovered" class="rotation-tool__tooltip" :style="tooltipStyle" role="status" aria-live="polite" aria-atomic="true">
          <strong>{{ hovered.symbol }}</strong><span>{{ hovered.point.timestamp }}</span><span>Trend {{ percent(hovered.point.trend) }} · Momentum {{ percent(hovered.point.momentum) }}</span>
        </div>
      </div>
      <div class="rotation-tool__table"><div class="rotation-tool__head"><button type="button" @click="setSort('symbol')">{{ isFamily ? 'Leg' : 'Sector' }}{{ sortMark('symbol') }}</button><button type="button" @click="setSort('state')">State{{ sortMark('state') }}</button><button type="button" @click="setSort('trend')">Trend{{ sortMark('trend') }}</button><button type="button" @click="setSort('momentum')">Momentum{{ sortMark('momentum') }}</button><button type="button" @click="setSort('heading')">Heading{{ sortMark('heading') }}</button><button type="button" @click="setSort('distance')">Distance{{ sortMark('distance') }}</button><button type="button" @click="setSort('velocity')">Velocity{{ sortMark('velocity') }}</button><button type="button" @click="setSort('transition')">Transition{{ sortMark('transition') }}</button><button type="button" @click="setSort('time_in_state')">Time{{ sortMark('time_in_state') }}</button><button type="button" @click="setSort('coverage')">Coverage{{ sortMark('coverage') }}</button><button type="button" @click="setSort('tail')">Tail{{ sortMark('tail') }}</button></div><button v-for="row in sortedRows" :key="row.role ?? row.instrument_id ?? row.symbol" type="button" class="rotation-tool__row" @click="emit('select', row.symbol, row.instrument_id)"><strong>{{ row.symbol }}</strong><span :class="`rotation-tool__state-${row.state}`">{{ row.state ?? 'Unavailable' }}</span><span v-if="row.warnings?.length" class="rotation-tool__warning" :title="row.warnings.map(warning => warning.message).join('\n')"><WorkstationGlyph kind="warning" /> {{ row.warnings.length }}</span><span v-else class="rotation-tool__warning-placeholder" aria-hidden="true" /><span>{{ percent(row.trend) }}</span><span>{{ percent(row.momentum) }}</span><span>{{ row.heading == null ? '—' : `${row.heading.toFixed(0)}°` }}</span><span>{{ percent(row.distance) }}</span><span>{{ percent(row.velocity) }}</span><span>{{ row.transition ?? '—' }}</span><span>{{ row.time_in_state ?? '—' }}</span><span>{{ percent(row.coverage) }}</span><span>{{ row.tail.length }}</span></button></div>
    </template>
  </section>
</template>

<style scoped>
.rotation-tool__head,
.rotation-tool__row { grid-template-columns: 54px 78px 34px repeat(7, minmax(58px, 1fr)) 64px 38px; }
.rotation-tool__head::before { content: 'Warnings'; grid-column: 3; color: #9baab5; font-weight: 600; text-transform: uppercase; }
.rotation-tool__warning { color: #e7bc68; }
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'
import { formatWorkstationFreshness } from '@/lib/workstation/freshness'
import WorkstationGlyph from './WorkstationGlyph.vue'

interface Tail { timestamp: string; trend: number; momentum: number }
interface Row { role?: string; label?: string; instrument_id?: number | null; symbol: string; state: string | null; trend: number | null; momentum: number | null; heading?: number | null; distance?: number | null; velocity?: number | null; transition?: string | null; time_in_state?: number | null; coverage: number; tail: Tail[]; history: Tail[]; warnings?: Array<{ code: string; message: string }> }
interface PlotPoint extends Tail { symbol: string; color: string; last: boolean }
type SortKey = 'symbol' | 'state' | 'trend' | 'momentum' | 'heading' | 'distance' | 'velocity' | 'transition' | 'time_in_state' | 'coverage' | 'tail'
const props = defineProps<{ configuration?: Record<string, unknown> }>()
const queryClient = useQueryClient()
const emit = defineEmits<{ select: [symbol: string, instrumentId?: number | null]; configuration: [configuration: Record<string, unknown>] }>()
const rows = ref<Row[]>([]), loading = ref(true), error = ref(''), freshness = ref('')
const configString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const groupKey = ref(configString('group_key', 'sp500-sectors'))
const benchmark = ref(configString('benchmark', 'SPY').toUpperCase())
const rotationBenchmark = ref(benchmark.value)
const familyKeys = [
  { key: 'sp500', label: 'S&P 500 legs' }, { key: 'sp400', label: 'S&P 400 legs' },
  { key: 'sp600', label: 'S&P 600 legs' }, { key: 'sp1500', label: 'S&P 1500 legs' },
  { key: 'russell1000', label: 'Russell 1000 legs' }, { key: 'russell2000', label: 'Russell 2000 legs' },
  { key: 'russell3000', label: 'Russell 3000 legs' }, { key: 'nasdaq100', label: 'Nasdaq 100 legs' },
]
const isFamily = computed(() => familyKeys.some(family => family.key === groupKey.value))
const timeframe = ref(['D1', 'W1', 'MN'].includes(configString('timeframe', 'D1')) ? configString('timeframe', 'D1') : 'D1')
const lookback = ref(Math.min(252, Math.max(2, Number(props.configuration?.lookback ?? 20) || 20)))
const tailLength = ref(Math.min(100, Math.max(1, Number(props.configuration?.tail_length ?? 10) || 10)))
const historyLength = ref(Math.min(1000, Math.max(0, Number(props.configuration?.history_length ?? 0) || 0)))
const sampling = ref(Math.min(30, Math.max(1, Number(props.configuration?.sampling ?? 1) || 1)))
const asOf = ref(configString('as_of', ''))
const adjusted = ref(props.configuration?.adjusted !== false)
const plotHost = ref<HTMLElement | null>(null)
const hovered = ref<{ symbol: string; point: PlotPoint; left: number; top: number } | null>(null)
const sortKey = ref<SortKey>('distance')
const sortDirection = ref<-1 | 1>(-1)
const sortedRows = computed(() => [...rows.value].sort((left, right) => {
  const a = sortValue(left, sortKey.value), b = sortValue(right, sortKey.value)
  if (a == null && b == null) return left.symbol.localeCompare(right.symbol)
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'string' && typeof b === 'string') return sortDirection.value * a.localeCompare(b)
  return sortDirection.value * (Number(a) - Number(b)) || left.symbol.localeCompare(right.symbol)
}))
const tooltipStyle = computed(() => hovered.value ? { left: `${hovered.value.left}px`, top: `${hovered.value.top}px` } : {})
let plot: uPlot | null = null
let observer: ResizeObserver | null = null
let observedPlotHost: HTMLElement | null = null
let points: PlotPoint[] = []
let loadGeneration = 0
function percent(value: number | null | undefined) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
function sortValue(row: Row, key: SortKey): string | number | null {
  if (key === 'symbol' || key === 'state' || key === 'transition') return row[key] ?? null
  if (key === 'tail') return row.tail.length
  return row[key] ?? null
}
function setSort(key: SortKey) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 1 ? -1 : 1
  else { sortKey.value = key; sortDirection.value = key === 'symbol' || key === 'state' || key === 'transition' ? 1 : -1 }
}
function sortMark(key: SortKey) { return sortKey.value === key ? (sortDirection.value === 1 ? ' ▲' : ' ▼') : '' }
function onPlotMove(event: MouseEvent) {
  if (!plot || !plotHost.value || !points.length) return
  const bounds = plotHost.value.getBoundingClientRect()
  const x = event.clientX - bounds.left
  const y = event.clientY - bounds.top
  let nearest: { point: PlotPoint; distance: number } | null = null
  for (const point of points) {
    const pointX = plot.valToPos(point.trend, 'x')
    const pointY = plot.valToPos(point.momentum, 'y')
    const distance = Math.hypot(pointX - x, pointY - y)
    if (!nearest || distance < nearest.distance) nearest = { point, distance }
  }
  if (!nearest || nearest.distance > 28) {
    hovered.value = null
    return
  }
  hovered.value = {
    symbol: nearest.point.symbol,
    point: nearest.point,
    left: Math.min(Math.max(8, x + 10), Math.max(8, bounds.width - 210)),
    top: Math.min(Math.max(8, y + 10), Math.max(8, bounds.height - 58)),
  }
}
function selectHovered() {
  if (hovered.value) emit('select', hovered.value.symbol, rows.value.find(row => row.symbol === hovered.value?.symbol)?.instrument_id)
}
function syncPlotObserver() {
  const host = plotHost.value
  if (host === observedPlotHost) return
  observer?.disconnect()
  observedPlotHost = host
  if (host) observer?.observe(host)
}
const colors: Record<string, string> = { leading: '#61c58c', weakening: '#e7bc68', improving: '#6dbbe6', lagging: '#df8181' }
function drawPlot() {
  syncPlotObserver()
  if (!plotHost.value) return
  points = rows.value.flatMap(row => {
    const curve = row.history.length ? row.history : row.tail
    return curve.map((tail, index) => ({ ...tail, symbol: row.symbol, color: colors[row.state ?? ''] ?? '#8796a1', last: index === curve.length - 1 }))
  })
  hovered.value = null
  const width = Math.max(200, plotHost.value.clientWidth), height = Math.max(130, plotHost.value.clientHeight)
  const data: uPlot.AlignedData = [points.map(point => point.trend), points.map(point => point.momentum)]
  if (plot) {
    plot.setData(data)
    plot.setSize({ width, height })
    return
  }
  const markerPlugin: uPlot.Plugin = { hooks: { draw: [(chart) => {
    const ctx = chart.ctx
    const zeroX = chart.valToPos(0, 'x')
    const zeroY = chart.valToPos(0, 'y')
    ctx.save()
    ctx.strokeStyle = '#53636e'
    ctx.lineWidth = 1
    ctx.setLineDash([3, 3])
    if (Number.isFinite(zeroX)) { ctx.beginPath(); ctx.moveTo(zeroX, 0); ctx.lineTo(zeroX, chart.height); ctx.stroke() }
    if (Number.isFinite(zeroY)) { ctx.beginPath(); ctx.moveTo(0, zeroY); ctx.lineTo(chart.width, zeroY); ctx.stroke() }
    ctx.font = '10px Segoe UI'
    ctx.fillStyle = '#7fca9e'
    if (Number.isFinite(zeroX) && Number.isFinite(zeroY)) {
      ctx.fillText('Leading', Math.min(chart.width - 54, zeroX + 6), Math.max(12, zeroY - 8))
      ctx.fillStyle = '#d2b675'
      ctx.fillText('Weakening', Math.min(chart.width - 66, zeroX + 6), Math.min(chart.height - 6, zeroY + 18))
      ctx.fillStyle = '#83bce0'
      ctx.fillText('Improving', Math.max(4, zeroX - 64), Math.max(12, zeroY - 8))
      ctx.fillStyle = '#d88b8b'
      ctx.fillText('Lagging', Math.max(4, zeroX - 52), Math.min(chart.height - 6, zeroY + 18))
    }
    ctx.restore()
    for (const row of rows.value) {
      const curve = row.history.length ? row.history : row.tail
      if (curve.length < 2) continue
      ctx.save()
      ctx.strokeStyle = colors[row.state ?? ''] ?? '#8796a1'
      ctx.globalAlpha = 0.72
      ctx.lineWidth = 1
      ctx.beginPath()
      curve.forEach((tail, index) => {
        const x = chart.valToPos(tail.trend, 'x')
        const y = chart.valToPos(tail.momentum, 'y')
        if (!Number.isFinite(x) || !Number.isFinite(y)) return
        if (index === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.restore()
    }
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
  emit('configuration', { ...(props.configuration ?? {}), group_key: groupKey.value, benchmark: benchmark.value.toUpperCase(), timeframe: timeframe.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, history_length: historyLength.value, as_of: asOf.value || null, adjusted: adjusted.value })
}
function asOfTimestamp() { return asOf.value ? `${asOf.value}T23:59:59Z` : undefined }
async function load() {
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const params = { ...(isFamily.value ? {} : { benchmark: benchmark.value.toUpperCase() }), timeframe: timeframe.value, adjusted: adjusted.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, history_length: historyLength.value, as_of: asOfTimestamp() }
    const path = isFamily.value
      ? `/analysis/benchmark-families/${encodeURIComponent(groupKey.value)}/relative-rotation`
      : `/analysis/groups/${encodeURIComponent(groupKey.value)}/relative-rotation`
    const payload = await queryClient.fetchQuery<{ rows?: Row[]; roles?: Row[]; benchmark?: string; freshness?: string }>({
      queryKey: ['workstation', 'relative-rotation', groupKey.value, params],
      queryFn: () => api.get<{ rows?: Row[]; roles?: Row[]; benchmark?: string; freshness?: string }>(path, params),
      staleTime: 30_000,
    })
    if (generation !== loadGeneration) return
    rows.value = (payload.roles ?? payload.rows ?? []).map(row => ({ ...row, tail: row.tail ?? [], history: row.history ?? [], symbol: row.symbol ?? row.label ?? row.role ?? 'Unavailable' }))
    rotationBenchmark.value = payload.benchmark ?? benchmark.value.toUpperCase()
    freshness.value = payload.freshness ?? ''; await nextTick(); drawPlot()
  } catch (cause: any) {
    if (generation === loadGeneration) { rows.value = []; error.value = cause?.message ?? 'Relative rotation is unavailable.' }
  } finally { if (generation === loadGeneration) loading.value = false }
}
onMounted(async () => {
  observer = new ResizeObserver(drawPlot)
  syncPlotObserver()
  await load()
})
watch([groupKey, benchmark, timeframe, sampling, lookback, tailLength, historyLength, asOf, adjusted], () => { publishConfiguration(); if (sampling.value >= 1 && lookback.value >= 2 && tailLength.value >= 1 && historyLength.value >= 0) void load() })
watch(plotHost, syncPlotObserver, { flush: 'post' })
watch(() => props.configuration, configuration => {
  if (typeof configuration?.group_key === 'string') groupKey.value = configuration.group_key
  if (typeof configuration?.benchmark === 'string') benchmark.value = configuration.benchmark.toUpperCase()
  if (typeof configuration?.timeframe === 'string' && ['D1', 'W1', 'MN'].includes(configuration.timeframe)) timeframe.value = configuration.timeframe
  if (Number.isFinite(Number(configuration?.lookback))) lookback.value = Math.min(252, Math.max(2, Number(configuration?.lookback)))
  if (Number.isFinite(Number(configuration?.tail_length))) tailLength.value = Math.min(100, Math.max(1, Number(configuration?.tail_length)))
  if (Number.isFinite(Number(configuration?.history_length))) historyLength.value = Math.min(1000, Math.max(0, Number(configuration?.history_length)))
  if (Number.isFinite(Number(configuration?.sampling))) sampling.value = Math.min(30, Math.max(1, Number(configuration?.sampling)))
  if (typeof configuration?.as_of === 'string') asOf.value = configuration.as_of
  if (configuration?.as_of === null) asOf.value = ''
  if (typeof configuration?.adjusted === 'boolean') adjusted.value = configuration.adjusted
}, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); observedPlotHost = null; plot?.destroy(); plot = null })
</script>

<style scoped>.rotation-tool{display:grid;height:100%;min-height:0;grid-template-rows:auto 150px minmax(0,1fr);background:#11161b;color:#cad4db;font:10px "Segoe UI",Arial,sans-serif}.rotation-tool header{display:grid;gap:4px;padding:7px;border-bottom:1px solid #2d3841}.rotation-tool header small{color:#82929d}.rotation-tool__controls{display:flex;flex-wrap:wrap;gap:4px;align-items:center}.rotation-tool__controls label{display:flex;align-items:center;gap:2px;color:#9aabb6}.rotation-tool__controls input,.rotation-tool__controls select{min-width:0;width:58px;border:1px solid #3a4954;background:#172027;color:#dce6ed;font:inherit;padding:1px 3px}.rotation-tool__controls label:first-child select{width:112px}.rotation-tool__controls label:nth-child(7) input{width:100px}.rotation-tool__adjusted input{width:auto}.rotation-tool__state{display:grid;place-items:center;color:#8596a1}.rotation-tool__state--error{color:#e28c8c}.rotation-tool__plot-shell{position:relative;min-height:0;background:#101419;overflow:hidden}.rotation-tool__plot{width:100%;height:100%}.rotation-tool__tooltip{position:absolute;z-index:2;display:grid;gap:2px;min-width:190px;padding:5px 7px;border:1px solid #526674;background:#172027;color:#dce6ed;box-shadow:0 3px 12px #0008;pointer-events:none}.rotation-tool__tooltip span{color:#9aabb6}.rotation-tool__table{overflow:auto}.rotation-tool__head,.rotation-tool__row{display:grid;grid-template-columns:54px 78px repeat(7, minmax(58px, 1fr)) 64px 38px;align-items:center;gap:5px;padding:5px 7px;min-width:720px}.rotation-tool__head{position:sticky;top:0;background:#20282f;color:#9baab5;font-weight:600;text-transform:uppercase}.rotation-tool__head button{border:0;background:transparent;color:inherit;font:inherit;text-align:left;padding:0;cursor:pointer}.rotation-tool__head button:hover{color:#e4eef3}.rotation-tool__row{width:100%;border:0;border-bottom:1px solid #20282f;background:transparent;color:inherit;text-align:left;cursor:pointer}.rotation-tool__row:hover{background:#1d4057}.rotation-tool__state-leading{color:#61c58c}.rotation-tool__state-weakening{color:#e7bc68}.rotation-tool__state-improving{color:#6dbbe6}.rotation-tool__state-lagging{color:#df8181}</style>
