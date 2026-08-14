<template>
  <div v-if="plottedRows.length" class="symbol-map">
    <div class="symbol-map__headings" aria-hidden="true">
      <strong class="negative">LOSSES</strong>
      <strong>BREAKEVEN</strong>
      <strong class="positive">WINS</strong>
    </div>
    <div ref="hostRef" class="symbol-map__plot" role="img" aria-label="P&amp;L by symbol outcome map">
      <div class="symbol-map__zero" aria-hidden="true" />
      <button
        v-for="row in plottedRows"
        :key="row.symbol"
        class="symbol-map__point"
        data-testid="symbol-pnl-point"
        :aria-label="`${row.symbol} ${formatSignedPercent(row.markedPct)} marked return, ${formatSignedMoney(row.markedPnl)} marked P&L`"
        :fill-opacity="row.pointOpacity"
        :style="pointStyle(row)"
        type="button"
        @mouseenter="showTooltip(row.symbol, $event)"
        @mousemove="showTooltip(row.symbol, $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(row.symbol, $event)"
        @blur="hideTooltip"
      />
    </div>

    <Teleport to="body">
      <div v-if="activeRow" ref="tooltipRef" class="symbol-bars__tooltip" :style="tooltipStyle">
        <div class="symbol-bars__tooltip-head">
          <strong>{{ activeRow.symbol }}</strong>
          <span :class="pnlClass(activeRow.markedPct)">{{ formatSignedPercent(activeRow.markedPct) }} marked</span>
        </div>
        <div class="symbol-bars__tooltip-metrics">
          <span>{{ summarizeTrades(activeRow) }}</span>
          <span class="symbol-bars__tooltip-secondary" :class="pnlClass(activeRow.realizedPct)">{{ formatSignedPercent(activeRow.realizedPct) }} · {{ formatSignedMoney(activeRow.realized) }} realized</span>
          <span class="symbol-bars__tooltip-secondary" :class="pnlClass(activeRow.unrealizedPct)">{{ formatSignedPercent(activeRow.unrealizedPct) }} · {{ formatSignedMoney(activeRow.unrealized) }} unrealized</span>
          <span class="symbol-bars__tooltip-secondary" :class="pnlClass(activeRow.markedPct)">{{ formatSignedMoney(activeRow.markedPnl) }} marked value</span>
          <span v-if="activeRow.win_rate != null" :class="positiveMetricClass(activeRow.win_rate)">{{ formatPercent(activeRow.win_rate) }} win</span>
          <span v-if="activeRow.avg_r != null" :class="pnlClass(activeRow.avg_r)">{{ formatR(activeRow.avg_r) }} avg</span>
        </div>
        <div v-if="activeEvents.length" class="symbol-bars__tooltip-events">
          <div v-for="event in activeEvents" :key="`${event.position_id || event.ts}-${event.event_type}`" class="symbol-bars__tooltip-event">
            <span>{{ formatShortDate(event.ts) }}</span>
            <span>{{ humanizeToken(event.event_type) }}</span>
            <span v-if="event.pnl_pct != null" :class="pnlClass(event.pnl_pct)">{{ formatSignedPercent(event.pnl_pct) }}</span>
            <span v-if="event.pnl != null" :class="pnlClass(event.pnl)">{{ formatSignedMoney(event.pnl) }}</span>
            <span>{{ humanizeToken(event.reason || event.event_type) }}</span>
          </div>
        </div>
        <div v-else class="symbol-bars__tooltip-empty">No closed or marked outcomes for this symbol yet.</div>
      </div>
    </Teleport>
  </div>
  <div v-else class="symbol-bars__empty">{{ emptyLabel }}</div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

type SymbolRow = {
  symbol: string
  net_pnl: number
  total_pnl?: number | null
  realized_pnl?: number | null
  unrealized_pnl?: number | null
  closed_trade_count?: number | null
  open_position_count?: number | null
  trade_count?: number | null
  win_rate?: number | null
  avg_r?: number | null
}
type SymbolEvent = {
  ts?: string
  position_id?: string | null
  event_type?: string | null
  symbol?: string | null
  pnl?: number | null
  pnl_pct?: number | null
  reason?: string | null
}

const props = withDefaults(defineProps<{
  rows: SymbolRow[]
  events?: SymbolEvent[]
  emptyLabel?: string
}>(), {
  emptyLabel: 'No per-symbol attribution yet.',
  events: () => [],
})

const hostRef = ref<HTMLDivElement | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<CSSProperties>({})
const hoveredSymbol = ref<string | null>(null)
const chart = ref<uPlot | null>(null)
const pointPositions = ref<Record<string, { left: number; top: number }>>({})
let resizeObserver: ResizeObserver | null = null
let observedHost: HTMLDivElement | null = null

const sortedRows = computed(() => [...props.rows]
  .filter(row => row?.symbol)
  .sort((left, right) => Math.abs(markedPnlPercent(right)) - Math.abs(markedPnlPercent(left)) || Math.abs(totalPnl(right)) - Math.abs(totalPnl(left))))
const maxAbsPercent = computed(() => Math.max(0.1, ...sortedRows.value.map(row => Math.abs(markedPnlPercent(row)))))
const magnitude = computed(() => niceMagnitude(maxAbsPercent.value))
const buckets = computed(() => {
  const bucketCount = 18
  const bucketWidth = (magnitude.value * 2) / bucketCount
  const values = Array.from({ length: bucketCount }, (_, index) => ({
    lower: -magnitude.value + index * bucketWidth,
    upper: -magnitude.value + (index + 1) * bucketWidth,
    count: 0,
  }))
  for (const row of sortedRows.value) {
    const value = Math.max(-magnitude.value, Math.min(magnitude.value, markedPnlPercent(row)))
    const index = Math.max(0, Math.min(bucketCount - 1, Math.floor((value + magnitude.value) / bucketWidth)))
    values[index].count += 1
  }
  return values
})
const maxCount = computed(() => Math.max(1, ...buckets.value.map(bucket => bucket.count)))
const xPoints = computed(() => [...new Set([
  ...buckets.value.map(bucket => (bucket.lower + bucket.upper) / 2),
  ...sortedRows.value.map(row => markedPnlPercent(row)),
])].sort((left, right) => left - right))
const chartData = computed<uPlot.AlignedData>(() => {
  const x = xPoints.value
  const counts = x.map(value => buckets.value.find(bucket => value >= bucket.lower && value <= bucket.upper)?.count ?? 0)
  return [x, counts] as uPlot.AlignedData
})
const plottedRows = computed(() => sortedRows.value.map((row, index) => {
  const markedPnl = totalPnl(row)
  const realized = realizedPnl(row)
  const unrealized = unrealizedPnl(row)
  const realizedPct = realizedPnlPercent(row)
  const unrealizedPct = unrealizedPnlPercent(row)
  const markedPct = realizedPct + unrealizedPct
  const closedCount = Number(row.closed_trade_count ?? row.trade_count ?? 0)
  const openCount = Number(row.open_position_count ?? 0)
  const isUnrealizedOnly = closedCount <= 0 && openCount > 0
  return {
    ...row,
    markedPnl,
    markedPct,
    realized,
    realizedPct,
    unrealized,
    unrealizedPct,
    yValue: pointY(index, markedPct),
    radius: 5.2 + Math.min(5.8, (Math.abs(markedPct) / maxAbsPercent.value) * 5.8),
    fill: colorForTone(toneForValue(markedPct)),
    isUnrealizedOnly,
    pointOpacity: isUnrealizedOnly ? 0.46 : 0.96,
  }
}))
const activeRow = computed(() => plottedRows.value.find(row => row.symbol === hoveredSymbol.value) ?? null)
const activeEvents = computed(() => props.events
  .filter(event => event?.symbol === hoveredSymbol.value && ['exit', 'open_at_end'].includes(String(event?.event_type ?? '')))
  .sort((left, right) => String(right.ts ?? '').localeCompare(String(left.ts ?? '')))
  .slice(0, 4))

function totalPnl(row: { total_pnl?: number | null; net_pnl?: number | null }) {
  const value = Number(row.total_pnl ?? row.net_pnl)
  return Number.isFinite(value) ? value : 0
}
function realizedPnl(row: { realized_pnl?: number | null; net_pnl?: number | null }) {
  const value = Number(row.realized_pnl ?? row.net_pnl)
  return Number.isFinite(value) ? value : 0
}
function unrealizedPnl(row: { unrealized_pnl?: number | null }) {
  const value = Number(row.unrealized_pnl ?? 0)
  return Number.isFinite(value) ? value : 0
}
function symbolEvents(symbol?: string | null, types = ['exit', 'open_at_end']) {
  return props.events.filter(event => event?.symbol === String(symbol ?? '') && types.includes(String(event.event_type ?? '')))
}
function sumEventPercent(symbol?: string | null, types = ['exit', 'open_at_end']) {
  return symbolEvents(symbol, types).reduce((total, event) => {
    const value = Number(event.pnl_pct)
    return Number.isFinite(value) ? total + value : total
  }, 0)
}
function realizedPnlPercent(row: { symbol?: string | null }) { return sumEventPercent(row.symbol, ['exit']) }
function unrealizedPnlPercent(row: { symbol?: string | null }) { return sumEventPercent(row.symbol, ['open_at_end']) }
function markedPnlPercent(row: { symbol?: string | null }) { return realizedPnlPercent(row) + unrealizedPnlPercent(row) }
function niceMagnitude(value: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return 1
  const base = 10 ** Math.floor(Math.log10(numeric))
  const scaled = numeric / base
  return scaled <= 1 ? base : scaled <= 2 ? 2 * base : scaled <= 5 ? 5 * base : 10 * base
}
function pointY(index: number, value: number) {
  const tolerance = Math.max(0.08, magnitude.value * 0.045)
  const clustered = sortedRows.value.map((row, rowIndex) => ({ index: rowIndex, distance: Math.abs(markedPnlPercent(row) - value) })).filter(item => item.distance <= tolerance)
  const position = Math.max(0, clustered.findIndex(item => item.index === index))
  const size = Math.max(1, clustered.length)
  const spread = Math.min(0.72, 0.28 + Math.max(0, size - 1) * 0.1)
  const offset = size === 1 ? ((index % 3) - 1) * 0.11 : -spread / 2 + (spread * position) / (size - 1)
  return Math.max(0.05, Math.min(maxCount.value * 0.9, maxCount.value * (0.48 + offset)))
}
function toneForValue(value: number) { return value > 0.005 ? 'positive' : value < -0.005 ? 'negative' : 'neutral' }
function colorForTone(tone: string) { return tone === 'positive' ? '#6ddb95' : tone === 'negative' ? '#ef7f88' : '#8fcaf2' }
function formatMoney(value: number) { return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2, minimumFractionDigits: 2 }) }
function formatSignedMoney(value: number) { if (!Number.isFinite(Number(value))) return '—'; const numeric = Number(value); const formatted = formatMoney(Math.abs(numeric)); return numeric > 0 ? `+${formatted}` : numeric < 0 ? `-${formatted}` : formatted }
function formatPercent(value: number) { return `${value.toFixed(2)}%` }
function formatSignedPercent(value: number) { const numeric = Number(value); return Number.isFinite(numeric) ? `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%` : '—' }
function formatR(value: number) { return `${value.toFixed(2)}R` }
function formatShortDate(value?: string) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' }) }
function pnlClass(value: unknown) { const numeric = Number(value); return { positive: Number.isFinite(numeric) && numeric > 0, negative: Number.isFinite(numeric) && numeric < 0 } }
function positiveMetricClass(value: unknown) { return pnlClass(value) }
function humanizeToken(value?: string | null) { return String(value ?? '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase()) }
function summarizeTrades(row: { trade_count?: number | null; closed_trade_count?: number | null; open_position_count?: number | null }) { const closed = Number(row.closed_trade_count ?? row.trade_count ?? 0); const open = Number(row.open_position_count ?? 0); return !closed && !open ? 'No marked trades' : `${closed} closed · ${open} open` }

function pointStyle(row: (typeof plottedRows.value)[number]) {
  const position = pointPositions.value[row.symbol]
  return { left: `${position?.left ?? 50}px`, top: `${position?.top ?? 50}px`, width: `${row.radius * 2}px`, height: `${row.radius * 2}px`, background: row.fill }
}
function updatePointPositions() {
  const instance = chart.value
  const valueToPosition = typeof instance?.valToPos === 'function'
    ? (value: number, scale: 'x' | 'y') => instance.valToPos(value, scale)
    : () => 50
  const next: Record<string, { left: number; top: number }> = {}
  for (const row of plottedRows.value) next[row.symbol] = { left: valueToPosition(row.markedPct, 'x'), top: valueToPosition(row.yValue, 'y') }
  pointPositions.value = next
}
function outcomePlugin(): uPlot.Plugin {
  return { hooks: { draw: [instance => {
    const valueToPosition = typeof instance.valToPos === 'function'
      ? (value: number, scale: 'x' | 'y') => instance.valToPos(value, scale)
      : () => 50
    const baseline = valueToPosition(0, 'y')
    for (const bucket of buckets.value) {
      const x1 = valueToPosition(bucket.lower, 'x')
      const x2 = valueToPosition(bucket.upper, 'x')
      const y = valueToPosition(bucket.count, 'y')
      const tone = toneForValue((bucket.lower + bucket.upper) / 2)
      instance.ctx.fillStyle = colorForTone(tone)
      instance.ctx.globalAlpha = tone === 'neutral' ? 0.24 : 0.32
      instance.ctx.fillRect(Math.min(x1, x2), y, Math.max(3, Math.abs(x2 - x1)), Math.max(1, baseline - y))
    }
    instance.ctx.globalAlpha = 1
    updatePointPositions()
  }] } }
}
function buildChart() {
  const host = hostRef.value
  if (!host || !plottedRows.value.length) return
  if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy()
  host.querySelector('.uplot')?.remove()
  chart.value = new uPlot({
    width: Math.max(280, host.clientWidth || 640), height: 220, legend: { show: false }, cursor: { show: false },
    scales: { x: { time: false, min: -magnitude.value, max: magnitude.value }, y: { min: 0, max: maxCount.value } },
    axes: [
      { stroke: '#7f8795', font: '11px monospace', grid: { stroke: '#65728433', width: 1 }, values: (_u, values) => values.map(value => formatSignedPercent(Number(value))) },
      { stroke: '#7f8795', font: '10px monospace', size: 34, grid: { stroke: '#65728422', width: 1 }, values: (_u, values) => values.map(value => String(Math.round(Number(value)))) },
    ], series: [{}, { show: false }], plugins: [outcomePlugin()],
  }, chartData.value, host)
  nextTick(updatePointPositions)
}
function destroyChart() { if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy(); chart.value = null; pointPositions.value = {} }
function refreshChart() { destroyChart(); if (plottedRows.value.length) nextTick(buildChart) }
function hideTooltip() { hoveredSymbol.value = null }
async function showTooltip(symbol: string, event: FocusEvent | MouseEvent) { hoveredSymbol.value = symbol; await nextTick(); positionTooltip(event.currentTarget as Element | null) }
function positionTooltip(anchor: Element | null) {
  if (!anchor || !tooltipRef.value) return
  const anchorRect = anchor.getBoundingClientRect(); const tooltipRect = tooltipRef.value.getBoundingClientRect(); const gap = 12; const padding = 12
  const preferRight = anchorRect.right + gap + tooltipRect.width <= window.innerWidth - padding; const fallbackLeft = anchorRect.left - tooltipRect.width - gap
  tooltipStyle.value = { left: `${preferRight ? anchorRect.right + gap : Math.max(padding, Math.min(fallbackLeft, window.innerWidth - tooltipRect.width - padding))}px`, top: `${Math.max(padding, Math.min(anchorRect.top + anchorRect.height / 2 - tooltipRect.height / 2, window.innerHeight - tooltipRect.height - padding))}px` }
}

function resizeChart() {
  if (chart.value && typeof chart.value.setSize === 'function') {
    chart.value.setSize({ width: Math.max(280, hostRef.value?.clientWidth || 640), height: 220 })
  }
  updatePointPositions()
}

function syncResizeObserver() {
  if (!resizeObserver) return
  const host = hostRef.value
  if (host === observedHost) return
  resizeObserver.disconnect()
  observedHost = host
  if (host) resizeObserver.observe(host)
}

onMounted(() => {
  refreshChart(); window.addEventListener('scroll', hideTooltip, true); window.addEventListener('resize', hideTooltip)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resizeChart)
    syncResizeObserver()
  }
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  observedHost = null
  window.removeEventListener('scroll', hideTooltip, true); window.removeEventListener('resize', hideTooltip); destroyChart()
})
watch([sortedRows, () => props.events], refreshChart, { deep: true })
watch(hostRef, syncResizeObserver, { flush: 'post' })
</script>

<style scoped>
.symbol-map { display: grid; gap: 6px; }
.symbol-map__headings { display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 0 8px; color: #8f98a8; font-size: 11px; font-weight: 800; letter-spacing: .07em; }.symbol-map__headings :nth-child(2) { text-align: center; }.symbol-map__headings :nth-child(3) { text-align: right; }
.symbol-map__plot { position: relative; min-height: 220px; overflow: hidden; border: 1px solid #1f252c; border-radius: 12px; background: #090d12; }.symbol-map__plot :deep(.uplot) { width: 100%; height: 220px; }
.symbol-map__zero { position: absolute; inset: 8px 50% 26px auto; border-left: 1px dashed #d5deeb55; pointer-events: none; }
.symbol-map__point { position: absolute; z-index: 2; transform: translate(-50%, -50%); padding: 0; border: 2px solid #080b10; border-radius: 50%; cursor: pointer; transition: box-shadow .16s ease, transform .16s ease; }.symbol-map__point:hover,.symbol-map__point:focus-visible { outline: none; box-shadow: 0 0 0 2px #eef3fb; transform: translate(-50%, -50%) scale(1.15); }
.symbol-bars__empty { color: #7d8490; font-size: 12px; }.symbol-bars__tooltip { position: fixed; z-index: 1100; display: grid; gap: 8px; padding: 10px; border: 1px solid #1f252c; border-radius: 6px; background: #0f1319; box-shadow: 0 18px 36px #00000059; max-width: min(360px, calc(100vw - 24px)); pointer-events: none; }.symbol-bars__tooltip-head,.symbol-bars__tooltip-metrics,.symbol-bars__tooltip-event { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }.symbol-bars__tooltip-head strong { color: #f3f3f3; font-size: 12px; }.symbol-bars__tooltip-metrics,.symbol-bars__tooltip-events,.symbol-bars__tooltip-empty,.symbol-bars__tooltip-event { color: #97a1b2; font-size: 10px; }.symbol-bars__tooltip-secondary { opacity: .86; }.positive { color: #7ce5a1; }.negative { color: #ff8f9b; }
</style>
