<template>
  <div v-if="plottedRows.length" class="symbol-map">
    <svg
      class="symbol-map__svg"
      width="100%"
      :height="svgHeight"
      :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="P&L by symbol outcome map"
    >
      <defs>
        <linearGradient id="symbol-map-axis" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#ef7f88" stop-opacity="0.56" />
          <stop offset="50%" stop-color="#657284" stop-opacity="0.78" />
          <stop offset="100%" stop-color="#6ddb95" stop-opacity="0.56" />
        </linearGradient>
        <linearGradient id="symbol-map-loss-zone" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#ef7f88" stop-opacity="0.13" />
          <stop offset="100%" stop-color="#ef7f88" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="symbol-map-gain-zone" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#6ddb95" stop-opacity="0" />
          <stop offset="100%" stop-color="#6ddb95" stop-opacity="0.13" />
        </linearGradient>
      </defs>

      <rect x="0.5" y="0.5" :width="svgWidth - 1" :height="svgHeight - 1" rx="18" fill="#090d12" stroke="#1f252c" />
      <rect :x="plotLeft" :y="plotTop" :width="zeroX - plotLeft" :height="plotHeight" fill="url(#symbol-map-loss-zone)" />
      <rect :x="zeroX" :y="plotTop" :width="plotRight - zeroX" :height="plotHeight" fill="url(#symbol-map-gain-zone)" />

      <text :x="plotLeft" y="34" fill="#ef9e9e" font-size="15" font-weight="800" letter-spacing="0.07em">LOSSES</text>
      <text :x="zeroX" y="34" fill="#8f98a8" font-size="15" font-weight="800" letter-spacing="0.07em" text-anchor="middle">BREAKEVEN</text>
      <text :x="plotRight" y="34" fill="#90d89e" font-size="15" font-weight="800" letter-spacing="0.07em" text-anchor="end">WINS</text>

      <line :x1="plotLeft" :x2="plotRight" :y1="axisY" :y2="axisY" stroke="url(#symbol-map-axis)" stroke-width="2" stroke-linecap="round" />
      <line :x1="zeroX" :x2="zeroX" :y1="plotTop" :y2="axisY + 10" stroke="#d5deeb" stroke-opacity="0.3" stroke-width="1" stroke-dasharray="4 5" />

      <g v-for="tick in axisTicks" :key="tick">
        <line
          :x1="valueToX(tick)"
          :x2="valueToX(tick)"
          :y1="plotTop + 4"
          :y2="axisY + 7"
          stroke="#657284"
          :stroke-opacity="tick === 0 ? 0 : 0.18"
        />
        <text
          :x="valueToX(tick)"
          :y="axisY + 30"
          fill="#7f8795"
          font-size="15"
          font-weight="800"
          text-anchor="middle"
        >
          {{ formatCompactPercent(tick) }}
        </text>
      </g>

      <rect
        v-for="bucket in densityBuckets"
        :key="bucket.key"
        :x="bucket.x"
        :y="bucket.y"
        :width="bucket.width"
        :height="bucket.height"
        :rx="Math.min(7, bucket.width / 2)"
        :fill="bucket.fill"
        :opacity="bucket.opacity"
      />

      <circle
        v-for="row in plottedRows"
        :key="row.symbol"
        class="symbol-map__point"
        :cx="row.x"
        :cy="row.y"
        :r="activeSymbol === row.symbol ? row.radius + 2 : row.radius"
        :fill="row.fill"
        :fill-opacity="row.pointOpacity"
        :stroke="activeSymbol === row.symbol ? '#eef3fb' : '#080b10'"
        :stroke-opacity="row.strokeOpacity"
        :stroke-width="activeSymbol === row.symbol ? 2.4 : 1.7"
        tabindex="0"
        role="button"
        :aria-label="`${row.symbol} ${formatSignedPercent(row.markedPct)} marked return, ${formatSignedMoney(row.markedPnl)} marked P&L`"
        data-testid="symbol-pnl-point"
        @mouseenter="showTooltip(row.symbol, $event)"
        @mousemove="showTooltip(row.symbol, $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(row.symbol, $event)"
        @blur="hideTooltip"
      />
    </svg>

    <Teleport to="body">
      <div
        v-if="activeRow"
        ref="tooltipRef"
        class="symbol-bars__tooltip"
        :style="tooltipStyle"
      >
        <div class="symbol-bars__tooltip-head">
          <strong>{{ activeRow.symbol }}</strong>
          <span :class="pnlClass(activeRow.markedPct)">
            {{ formatSignedPercent(activeRow.markedPct) }} marked
          </span>
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
          <div
            v-for="event in activeEvents"
            :key="`${event.position_id || event.ts}-${event.event_type}`"
            class="symbol-bars__tooltip-event"
          >
            <span>{{ formatShortDate(event.ts) }}</span>
            <span>{{ humanizeToken(event.event_type) }}</span>
            <span v-if="event.pnl_pct != null" :class="pnlClass(event.pnl_pct)">{{ formatSignedPercent(event.pnl_pct) }}</span>
            <span v-if="event.pnl != null" :class="pnlClass(event.pnl)">{{ formatSignedMoney(event.pnl) }}</span>
            <span>{{ humanizeToken(event.reason || event.event_type) }}</span>
          </div>
        </div>
        <div v-else class="symbol-bars__tooltip-empty">
          No closed or marked outcomes for this symbol yet.
        </div>
      </div>
    </Teleport>
  </div>
  <div v-else class="symbol-bars__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { CSSProperties } from 'vue'

const props = withDefaults(defineProps<{
  rows: Array<{
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
  }>
  events?: Array<{
    ts?: string
    position_id?: string | null
    event_type?: string | null
    symbol?: string | null
    pnl?: number | null
    pnl_pct?: number | null
    reason?: string | null
  }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No per-symbol attribution yet.',
  events: () => [],
})

type SymbolRow = NonNullable<typeof props.rows>[number]

const svgWidth = 640
const svgHeight = 242
const plotLeft = 36
const plotRight = 604
const plotTop = 56
const axisY = 184
const plotHeight = axisY - plotTop
const plotWidth = plotRight - plotLeft

const sortedRows = computed(() =>
  [...props.rows]
    .filter(row => row?.symbol)
    .sort((left, right) => {
      const markedDelta = Math.abs(markedPnlPercent(right)) - Math.abs(markedPnlPercent(left))
      if (markedDelta !== 0) return markedDelta
      return Math.abs(totalPnl(right)) - Math.abs(totalPnl(left))
    }),
)

const maxAbsPercent = computed(() =>
  Math.max(0.1, ...sortedRows.value.map(row => Math.abs(markedPnlPercent(row)))),
)

const axisTicks = computed(() => {
  const magnitude = niceMagnitude(maxAbsPercent.value)
  return [-magnitude, -magnitude / 2, 0, magnitude / 2, magnitude]
})

const densityBuckets = computed(() => {
  const bucketCount = 18
  const magnitude = niceMagnitude(maxAbsPercent.value)
  const bucketWidth = (magnitude * 2) / bucketCount
  const buckets = Array.from({ length: bucketCount }, (_, index) => ({
    lower: -magnitude + index * bucketWidth,
    upper: -magnitude + (index + 1) * bucketWidth,
    count: 0,
  }))
  for (const row of sortedRows.value) {
    const value = Math.max(-magnitude, Math.min(magnitude, markedPnlPercent(row)))
    const rawIndex = Math.floor((value + magnitude) / bucketWidth)
    const index = Math.max(0, Math.min(bucketCount - 1, rawIndex))
    buckets[index].count += 1
  }
  const maxCount = Math.max(1, ...buckets.map(bucket => bucket.count))
  return buckets
    .filter(bucket => bucket.count > 0)
    .map((bucket, index) => {
      const lower = valueToX(bucket.lower)
      const upper = valueToX(bucket.upper)
      const midpoint = (bucket.lower + bucket.upper) / 2
      const height = 18 + (bucket.count / maxCount) * 94
      const tone = toneForValue(midpoint)
      return {
        key: `${bucket.lower}-${bucket.upper}-${index}`,
        x: Math.min(lower, upper),
        y: axisY - height,
        width: Math.max(3, Math.abs(upper - lower)),
        height,
        fill: colorForTone(tone),
        opacity: tone === 'neutral' ? 0.24 : 0.32,
      }
    })
})

const plottedRows = computed(() =>
  sortedRows.value.map((row, index) => {
    const markedPnl = totalPnl(row)
    const realized = realizedPnl(row)
    const unrealized = unrealizedPnl(row)
    const realizedPct = realizedPnlPercent(row)
    const unrealizedPct = unrealizedPnlPercent(row)
    const markedPct = realizedPct + unrealizedPct
    const closedCount = Number(row.closed_trade_count ?? row.trade_count ?? 0)
    const openCount = Number(row.open_position_count ?? 0)
    const isUnrealizedOnly = closedCount <= 0 && openCount > 0
    const tone = toneForValue(markedPct)
    const baseRadius = 5.2 + Math.min(5.8, (Math.abs(markedPct) / maxAbsPercent.value) * 5.8)
    return {
      ...row,
      markedPnl,
      markedPct,
      realized,
      realizedPct,
      unrealized,
      unrealizedPct,
      x: valueToX(markedPct),
      y: jitterY(index, markedPct, sortedRows.value),
      radius: baseRadius,
      fill: colorForTone(tone),
      isUnrealizedOnly,
      pointOpacity: isUnrealizedOnly ? 0.46 : 0.96,
      strokeOpacity: isUnrealizedOnly ? 0.72 : 1,
    }
  }),
)

const hoveredSymbol = ref<string | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<CSSProperties>({})

const activeSymbol = computed(() => hoveredSymbol.value)
const activeRow = computed(() =>
  plottedRows.value.find(row => row.symbol === activeSymbol.value) ?? null,
)
const zeroX = computed(() => valueToX(0))
const activeEvents = computed(() =>
  props.events
    .filter(event => event?.symbol === activeSymbol.value && ['exit', 'open_at_end'].includes(String(event?.event_type ?? '')))
    .sort((left, right) => String(right.ts ?? '').localeCompare(String(left.ts ?? '')))
    .slice(0, 4),
)

function formatMoney(value: number) {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })
}

function formatSignedMoney(value: number) {
  if (!Number.isFinite(Number(value))) return '—'
  const formatted = formatMoney(Math.abs(Number(value)))
  if (Number(value) > 0) return `+${formatted}`
  if (Number(value) < 0) return `-${formatted}`
  return formatted
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`
}

function formatSignedPercent(value: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

function formatCompactPercent(value: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  const absValue = Math.abs(numeric)
  const decimals = absValue >= 10 ? 0 : absValue >= 1 ? 1 : 2
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(decimals)}%`
}

function formatR(value: number) {
  return `${value.toFixed(2)}R`
}

function formatShortDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function totalPnl(row: { total_pnl?: number | null; net_pnl?: number | null }) {
  const total = Number(row.total_pnl ?? row.net_pnl)
  return Number.isFinite(total) ? total : 0
}

function realizedPnl(row: { realized_pnl?: number | null; net_pnl?: number | null }) {
  const realized = Number(row.realized_pnl ?? row.net_pnl)
  return Number.isFinite(realized) ? realized : 0
}

function unrealizedPnl(row: { unrealized_pnl?: number | null }) {
  const unrealized = Number(row.unrealized_pnl ?? 0)
  return Number.isFinite(unrealized) ? unrealized : 0
}

function symbolOutcomeEvents(symbol?: string | null, eventTypes: string[] = ['exit', 'open_at_end']) {
  const normalizedSymbol = String(symbol ?? '')
  return props.events.filter(event => {
    if (event?.symbol !== normalizedSymbol) return false
    return eventTypes.includes(String(event.event_type ?? ''))
  })
}

function sumEventPercent(symbol?: string | null, eventTypes: string[] = ['exit', 'open_at_end']) {
  return symbolOutcomeEvents(symbol, eventTypes).reduce((total, event) => {
    const percent = Number(event.pnl_pct)
    return Number.isFinite(percent) ? total + percent : total
  }, 0)
}

function realizedPnlPercent(row: { symbol?: string | null }) {
  return sumEventPercent(row.symbol, ['exit'])
}

function unrealizedPnlPercent(row: { symbol?: string | null }) {
  return sumEventPercent(row.symbol, ['open_at_end'])
}

function markedPnlPercent(row: { symbol?: string | null }) {
  return realizedPnlPercent(row) + unrealizedPnlPercent(row)
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function positiveMetricClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function niceMagnitude(value: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return 1
  const exponent = Math.floor(Math.log10(numeric))
  const base = 10 ** exponent
  const scaled = numeric / base
  if (scaled <= 1) return base
  if (scaled <= 2) return 2 * base
  if (scaled <= 5) return 5 * base
  return 10 * base
}

function valueToPercent(value: number) {
  const magnitude = niceMagnitude(maxAbsPercent.value)
  const clamped = Math.max(-magnitude, Math.min(magnitude, Number(value)))
  return ((clamped + magnitude) / (magnitude * 2)) * 100
}

function valueToX(value: number) {
  return plotLeft + (valueToPercent(value) / 100) * plotWidth
}

function jitterY(index: number, value: number, rows: SymbolRow[]) {
  const magnitude = niceMagnitude(maxAbsPercent.value)
  const clusterTolerance = Math.max(0.08, magnitude * 0.045)
  const clusteredIndexes = rows
    .map((row, rowIndex) => ({
      index: rowIndex,
      distance: Math.abs(markedPnlPercent(row) - value),
    }))
    .filter(item => Number.isFinite(item.distance) && item.distance <= clusterTolerance)
    .sort((left, right) => left.index - right.index)
    .map(item => item.index)
  const clusterPosition = Math.max(0, clusteredIndexes.indexOf(index))
  const clusterSize = Math.max(1, clusteredIndexes.length)
  const spread = Math.min(plotHeight - 34, 24 + Math.max(0, clusterSize - 1) * 14)
  const offset = clusterSize === 1
    ? ((index % 3) - 1) * 14
    : -spread / 2 + (spread * clusterPosition) / (clusterSize - 1)
  const y = plotTop + plotHeight / 2 + offset
  return Math.max(plotTop + 22, Math.min(axisY - 26, y))
}

function toneForValue(value: number) {
  if (value > 0.005) return 'positive'
  if (value < -0.005) return 'negative'
  return 'neutral'
}

function colorForTone(tone: string) {
  if (tone === 'positive') return '#6ddb95'
  if (tone === 'negative') return '#ef7f88'
  return '#8fcaf2'
}

function summarizeTrades(row: {
  trade_count?: number | null
  closed_trade_count?: number | null
  open_position_count?: number | null
}) {
  const tradeCount = Number(row.closed_trade_count ?? row.trade_count ?? 0)
  const openCount = Number(row.open_position_count ?? 0)
  if (!tradeCount && !openCount) return 'No marked trades'
  const parts = [
    `${tradeCount} closed`,
    `${openCount} open`,
  ]
  return parts.join(' · ')
}

function humanizeToken(value?: string | null) {
  return String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function hideTooltip() {
  hoveredSymbol.value = null
}

async function showTooltip(symbol: string, event: FocusEvent | MouseEvent) {
  hoveredSymbol.value = symbol
  await nextTick()
  positionTooltip(event.currentTarget as Element | null)
}

function positionTooltip(anchor: Element | null) {
  if (!anchor || !tooltipRef.value) return
  const anchorRect = anchor.getBoundingClientRect()
  const tooltipRect = tooltipRef.value.getBoundingClientRect()
  const gap = 12
  const viewportPadding = 12
  const preferRight = anchorRect.right + gap + tooltipRect.width <= window.innerWidth - viewportPadding
  const fallbackLeft = anchorRect.left - tooltipRect.width - gap
  const left = preferRight
    ? anchorRect.right + gap
    : Math.max(viewportPadding, Math.min(fallbackLeft, window.innerWidth - tooltipRect.width - viewportPadding))
  const top = Math.max(
    viewportPadding,
    Math.min(
      anchorRect.top + anchorRect.height / 2 - tooltipRect.height / 2,
      window.innerHeight - tooltipRect.height - viewportPadding,
    ),
  )
  tooltipStyle.value = {
    left: `${left}px`,
    top: `${top}px`,
  }
}

onMounted(() => {
  window.addEventListener('scroll', hideTooltip, true)
  window.addEventListener('resize', hideTooltip)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', hideTooltip, true)
  window.removeEventListener('resize', hideTooltip)
})
</script>

<style scoped>
.symbol-map {
  display: grid;
  gap: 10px;
}

.symbol-map__svg {
  display: block;
  width: 100%;
  height: auto;
  min-height: 242px;
  max-height: 310px;
}

.symbol-map__point {
  cursor: pointer;
  transition: r 0.16s ease, stroke 0.16s ease, stroke-width 0.16s ease, fill-opacity 0.16s ease, stroke-opacity 0.16s ease;
}

.symbol-map__point:hover,
.symbol-map__point:focus-visible {
  outline: none;
}

.symbol-bars__empty {
  color: #7d8490;
  font-size: 12px;
}

.symbol-bars__tooltip {
  position: fixed;
  z-index: 1100;
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #1f252c;
  border-radius: 6px;
  background: #0f1319;
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.35);
  max-width: min(360px, calc(100vw - 24px));
  pointer-events: none;
}

.symbol-bars__tooltip-head,
.symbol-bars__tooltip-metrics,
.symbol-bars__tooltip-event {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
}

.symbol-bars__tooltip-head strong {
  color: #f3f3f3;
  font-size: 12px;
}

.symbol-bars__tooltip-metrics,
.symbol-bars__tooltip-events,
.symbol-bars__tooltip-empty,
.symbol-bars__tooltip-event {
  color: #97a1b2;
  font-size: 10px;
}

.symbol-bars__tooltip-secondary {
  opacity: 0.86;
}

.positive {
  color: #7ce5a1;
}

.negative {
  color: #ff8f9b;
}
</style>
