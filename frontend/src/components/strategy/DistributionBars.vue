<template>
  <div v-if="hasData" class="r-outcome-map">
    <div class="r-outcome-map__headings" aria-hidden="true">
      <strong class="negative">LOSSES</strong>
      <strong>BREAKEVEN</strong>
      <strong class="positive">WINS</strong>
    </div>
    <div
      ref="hostRef"
      class="r-outcome-map__plot"
      role="img"
      aria-label="Closed trade outcomes by R multiple"
    >
      <div class="r-outcome-map__zero" aria-hidden="true" />
      <button
        v-for="trade in plottedTrades"
        :key="trade.key"
        class="r-outcome-map__point"
        :data-testid="'r-outcome-point'"
        :aria-label="`${trade.label} ${formatR(trade.rMultiple)}`"
        :style="pointStyle(trade)"
        type="button"
        @mouseenter="showTooltip(trade.key, $event)"
        @mousemove="showTooltip(trade.key, $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(trade.key, $event)"
        @blur="hideTooltip"
      />
      <div v-if="!plottedTrades.length" class="r-outcome-map__no-trades">
        Histogram available, but no closed trade detail rows were provided.
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="activeTrade"
        ref="tooltipRef"
        class="r-outcome-map__tooltip"
        :style="{ ...tooltipBaseStyle, ...tooltipStyle }"
      >
        <div class="r-outcome-map__tooltip-head">
          <strong>{{ activeTrade.label }}</strong>
          <span :class="pnlClass(activeTrade.rMultiple)">{{ formatR(activeTrade.rMultiple) }}</span>
        </div>
        <div class="r-outcome-map__tooltip-grid">
          <span>Exit</span>
          <strong>{{ formatShortDate(activeTrade.exit_at) }}</strong>
          <span>Reason</span>
          <strong>{{ humanizeToken(activeTrade.exit_reason || activeTrade.reason || 'exit') }}</strong>
          <span>P&amp;L</span>
          <strong :class="pnlClass(activeTrade.pnl_pct ?? activeTrade.pnl)">
            {{ activeTrade.pnl_pct == null ? '—' : formatSignedPercent(Number(activeTrade.pnl_pct)) }}
            <small v-if="activeTrade.pnl != null">{{ formatSignedMoney(Number(activeTrade.pnl)) }}</small>
          </strong>
        </div>
      </div>
    </Teleport>
  </div>
  <div v-else class="r-outcome-map__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

type HistogramRow = { lower: number; upper: number; count: number }
type TradeRow = {
  instrument_symbol?: string | null
  symbol?: string | null
  pnl?: number | null
  pnl_pct?: number | null
  r_multiple?: number | null
  exit_reason?: string | null
  reason?: string | null
  exit_at?: string | null
}

const props = withDefaults(defineProps<{
  rows: HistogramRow[]
  trades?: TradeRow[]
  emptyLabel?: string
}>(), {
  emptyLabel: 'No closed trade R multiples yet.',
  trades: () => [],
})

const hostRef = ref<HTMLDivElement | null>(null)
const chart = ref<uPlot | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<CSSProperties>({})
const activeTradeKey = ref<string | null>(null)
const pointPositions = ref<Record<string, { left: number; top: number }>>({})
let resizeObserver: ResizeObserver | null = null
let observedHost: HTMLDivElement | null = null

const normalizedRows = computed(() => props.rows.filter(row => (
  Number.isFinite(row.lower)
  && Number.isFinite(row.upper)
  && Number.isFinite(row.count)
  && Number(row.count) >= 0
)))
const normalizedTrades = computed(() => props.trades.filter(trade => (
  typeof trade?.r_multiple === 'number' && Number.isFinite(trade.r_multiple)
)))
const hasData = computed(() => normalizedRows.value.length > 0 || normalizedTrades.value.length > 0)
const maxCount = computed(() => Math.max(1, ...normalizedRows.value.map(row => Number(row.count) || 0)))
const maxAbsPnl = computed(() => Math.max(1, ...normalizedTrades.value.map(trade => Math.abs(Number(trade.pnl ?? 0)))))
const domainMagnitude = computed(() => Math.max(
  2,
  Math.ceil(Math.max(
    1,
    ...normalizedRows.value.flatMap(row => [Math.abs(Number(row.lower)), Math.abs(Number(row.upper))]),
    ...normalizedTrades.value.map(trade => Math.abs(Number(trade.r_multiple ?? 0))),
  )),
))
const xPoints = computed(() => {
  const values = [
    ...normalizedRows.value.map(row => (Number(row.lower) + Number(row.upper)) / 2),
    ...normalizedTrades.value.map(trade => Number(trade.r_multiple)),
  ]
  return [...new Set(values.filter(Number.isFinite))].sort((left, right) => left - right)
})
const chartData = computed<uPlot.AlignedData>(() => {
  const x = xPoints.value
  const counts = x.map(value => {
    const row = normalizedRows.value.find(item => value >= Number(item.lower) && value <= Number(item.upper))
    return row ? Number(row.count) : 0
  })
  return [x, counts] as uPlot.AlignedData
})
const plottedTrades = computed(() => normalizedTrades.value.map((trade, index) => {
  const rMultiple = Number(trade.r_multiple ?? 0)
  const tone = toneForValue(rMultiple)
  return {
    ...trade,
    key: tradeKey(trade, index),
    label: trade.instrument_symbol || trade.symbol || 'Trade',
    rMultiple,
    tone,
    yValue: pointY(index, rMultiple),
    radius: 5.4 + Math.min(5.8, (Math.abs(Number(trade.pnl ?? 0)) / maxAbsPnl.value) * 5.8),
    fill: colorForTone(tone),
  }
}))
const activeTrade = computed(() => plottedTrades.value.find(trade => trade.key === activeTradeKey.value) ?? null)

const tooltipBaseStyle = {
  position: 'fixed', zIndex: '1100', display: 'grid', gap: '8px', width: 'max-content',
  maxWidth: 'min(340px, calc(100vw - 24px))', padding: '10px', border: '1px solid #263142',
  borderRadius: '8px', background: '#0c1119', boxShadow: '0 18px 36px rgba(0, 0, 0, 0.42)',
  pointerEvents: 'none',
} satisfies CSSProperties

function pointY(index: number, value: number) {
  const clusterTolerance = Math.max(0.12, domainMagnitude.value * 0.035)
  const clustered = normalizedTrades.value
    .map((trade, tradeIndex) => ({ index: tradeIndex, distance: Math.abs(Number(trade.r_multiple ?? 0) - value) }))
    .filter(item => Number.isFinite(item.distance) && item.distance <= clusterTolerance)
  const clusterPosition = Math.max(0, clustered.findIndex(item => item.index === index))
  const clusterSize = Math.max(1, clustered.length)
  const spread = Math.min(0.72, 0.28 + Math.max(0, clusterSize - 1) * 0.12)
  const offset = clusterSize === 1 ? ((index % 3) - 1) * 0.11 : -spread / 2 + (spread * clusterPosition) / (clusterSize - 1)
  return Math.max(0.05, Math.min(maxCount.value * 0.9, maxCount.value * (0.48 + offset)))
}

function toneForValue(value: number) {
  if (value > 0.05) return 'positive'
  if (value < -0.05) return 'negative'
  return 'neutral'
}

function colorForTone(tone: string) {
  if (tone === 'positive') return '#6ddb95'
  if (tone === 'negative') return '#ef7f88'
  return '#8fcaf2'
}

function formatR(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(value % 1 === 0 ? 0 : 2)}R`
}

function formatSignedPercent(value: number) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%` : '—'
}

function formatMoney(value: number) {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2, minimumFractionDigits: 2 })
}

function formatSignedMoney(value: number) {
  if (!Number.isFinite(Number(value))) return '—'
  const numeric = Number(value)
  const formatted = formatMoney(Math.abs(numeric))
  return numeric > 0 ? `+${formatted}` : numeric < 0 ? `-${formatted}` : formatted
}

function formatShortDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return { positive: Number.isFinite(numeric) && numeric > 0, negative: Number.isFinite(numeric) && numeric < 0 }
}

function humanizeToken(value?: string | null) {
  return String(value ?? '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function tradeKey(trade: TradeRow, index: number) {
  return `${trade.instrument_symbol || trade.symbol || 'trade'}-${trade.exit_at || index}-${trade.r_multiple ?? 0}-${index}`
}

function pointStyle(trade: (typeof plottedTrades.value)[number]) {
  const position = pointPositions.value[trade.key]
  return {
    left: `${position?.left ?? 50}px`,
    top: `${position?.top ?? 50}px`,
    width: `${trade.radius * 2}px`,
    height: `${trade.radius * 2}px`,
    background: trade.fill,
  }
}

function updatePointPositions() {
  const instance = chart.value
  const valueToPosition = typeof instance?.valToPos === 'function'
    ? (value: number, scale: 'x' | 'y') => instance.valToPos(value, scale)
    : () => 50
  const next: Record<string, { left: number; top: number }> = {}
  for (const trade of plottedTrades.value) {
    next[trade.key] = {
      left: valueToPosition(trade.rMultiple, 'x'),
      top: valueToPosition(trade.yValue, 'y'),
    }
  }
  pointPositions.value = next
}

function outcomePlugin(): uPlot.Plugin {
  return {
    hooks: {
      draw: [instance => {
        const ctx = instance.ctx
        const valueToPosition = typeof instance.valToPos === 'function'
          ? (value: number, scale: 'x' | 'y') => instance.valToPos(value, scale)
          : () => 50
        const baseline = valueToPosition(0, 'y')
        for (const row of normalizedRows.value) {
          const x1 = valueToPosition(Number(row.lower), 'x')
          const x2 = valueToPosition(Number(row.upper), 'x')
          const y = valueToPosition(Number(row.count), 'y')
          const midpoint = (Number(row.lower) + Number(row.upper)) / 2
          ctx.fillStyle = colorForTone(toneForValue(midpoint))
          ctx.globalAlpha = toneForValue(midpoint) === 'neutral' ? 0.3 : 0.36
          ctx.fillRect(Math.min(x1, x2), y, Math.max(3, Math.abs(x2 - x1)), Math.max(1, baseline - y))
        }
        ctx.globalAlpha = 1
        updatePointPositions()
      }],
    },
  }
}

function buildChart() {
  const host = hostRef.value
  if (!host || !hasData.value) return
  if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy()
  host.querySelector('.uplot')?.remove()
  chart.value = new uPlot({
    width: Math.max(280, host.clientWidth || 640),
    height: 220,
    legend: { show: false },
    cursor: { show: false },
    scales: { x: { time: false, min: -domainMagnitude.value, max: domainMagnitude.value }, y: { min: 0, max: maxCount.value } },
    axes: [
      { stroke: '#7f8795', font: '11px monospace', grid: { stroke: '#65728433', width: 1 }, values: (_u, values) => values.map(value => formatR(Number(value))) },
      { stroke: '#7f8795', font: '10px monospace', size: 34, grid: { stroke: '#65728422', width: 1 }, values: (_u, values) => values.map(value => String(Math.round(Number(value)))) },
    ],
    series: [{}, { show: false }],
    plugins: [outcomePlugin()],
  }, chartData.value, host)
  nextTick(updatePointPositions)
}

function destroyChart() {
  if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy()
  chart.value = null
  pointPositions.value = {}
}

function refreshChart() {
  destroyChart()
  if (hasData.value) nextTick(buildChart)
}

function hideTooltip() { activeTradeKey.value = null }

async function showTooltip(key: string, event: FocusEvent | MouseEvent) {
  activeTradeKey.value = key
  await nextTick()
  positionTooltip(event.currentTarget as Element | null)
}

function positionTooltip(anchor: Element | null) {
  if (!anchor || !tooltipRef.value) return
  const anchorRect = anchor.getBoundingClientRect()
  const tooltipRect = tooltipRef.value.getBoundingClientRect()
  const gap = 12
  const padding = 12
  const preferRight = anchorRect.right + gap + tooltipRect.width <= window.innerWidth - padding
  const fallbackLeft = anchorRect.left - tooltipRect.width - gap
  const left = preferRight ? anchorRect.right + gap : Math.max(padding, Math.min(fallbackLeft, window.innerWidth - tooltipRect.width - padding))
  const top = Math.max(padding, Math.min(anchorRect.top + anchorRect.height / 2 - tooltipRect.height / 2, window.innerHeight - tooltipRect.height - padding))
  tooltipStyle.value = { left: `${left}px`, top: `${top}px` }
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
  refreshChart()
  window.addEventListener('scroll', hideTooltip, true)
  window.addEventListener('resize', hideTooltip)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resizeChart)
    syncResizeObserver()
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  observedHost = null
  window.removeEventListener('scroll', hideTooltip, true)
  window.removeEventListener('resize', hideTooltip)
  destroyChart()
})

watch([normalizedRows, normalizedTrades], refreshChart, { deep: true })
watch(hostRef, syncResizeObserver, { flush: 'post' })
</script>

<style scoped>
.r-outcome-map { display: grid; gap: 6px; }
.r-outcome-map__headings { display: grid; grid-template-columns: 1fr 1fr 1fr; padding: 0 8px; color: #8f98a8; font-size: 11px; font-weight: 800; letter-spacing: .07em; }
.r-outcome-map__headings :nth-child(2) { text-align: center; }
.r-outcome-map__headings :nth-child(3) { text-align: right; }
.r-outcome-map__plot { position: relative; min-height: 220px; overflow: hidden; border: 1px solid #1f252c; border-radius: 12px; background: #090d12; }
.r-outcome-map__zero { position: absolute; inset: 8px 50% 26px auto; border-left: 1px dashed #d5deeb55; pointer-events: none; }
.r-outcome-map__plot :deep(.uplot) { width: 100%; height: 220px; }
.r-outcome-map__point { position: absolute; z-index: 2; transform: translate(-50%, -50%); padding: 0; border: 2px solid #080b10; border-radius: 50%; cursor: pointer; box-shadow: 0 0 0 0 #eef3fb; transition: box-shadow .16s ease, transform .16s ease; }
.r-outcome-map__point:hover, .r-outcome-map__point:focus-visible { outline: none; box-shadow: 0 0 0 2px #eef3fb; transform: translate(-50%, -50%) scale(1.15); }
.r-outcome-map__no-trades { position: absolute; inset: 50% 0 auto; transform: translateY(-50%); color: #8f98a8; font-size: 12px; text-align: center; pointer-events: none; }
.r-outcome-map__empty { color: #7d8490; font-size: 12px; }
.r-outcome-map__tooltip { position: fixed; z-index: 1100; display: grid; gap: 8px; width: max-content; max-width: min(340px, calc(100vw - 24px)); padding: 10px; border: 1px solid #263142; border-radius: 8px; background: #0c1119; box-shadow: 0 18px 36px #0000006b; pointer-events: none; }
.r-outcome-map__tooltip-head { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.r-outcome-map__tooltip-head strong { color: #f3f3f3; font-size: 12px; }
.r-outcome-map__tooltip-grid { display: grid; grid-template-columns: max-content max-content; gap: 5px 14px; color: #97a1b2; font-size: 10px; }
.r-outcome-map__tooltip-grid strong { display: inline-flex; gap: 8px; justify-content: flex-end; color: #dce3ee; font-weight: 700; }
.r-outcome-map__tooltip-grid small { color: #8e98a8; font: inherit; }
.positive { color: #74e39a; }.negative { color: #ff9aa7; }
</style>
