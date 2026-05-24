<template>
  <div v-if="hasData" class="r-outcome-map">
    <svg
      class="r-outcome-map__svg"
      width="100%"
      :height="svgHeight"
      :viewBox="`0 0 ${svgWidth} ${svgHeight}`"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Closed trade outcomes by R multiple"
    >
      <defs>
        <linearGradient id="r-outcome-axis" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#ef7f88" stop-opacity="0.56" />
          <stop offset="50%" stop-color="#657284" stop-opacity="0.8" />
          <stop offset="100%" stop-color="#6ddb95" stop-opacity="0.56" />
        </linearGradient>
        <linearGradient id="r-outcome-loss-zone" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#ef7f88" stop-opacity="0.13" />
          <stop offset="100%" stop-color="#ef7f88" stop-opacity="0" />
        </linearGradient>
        <linearGradient id="r-outcome-win-zone" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#6ddb95" stop-opacity="0" />
          <stop offset="100%" stop-color="#6ddb95" stop-opacity="0.13" />
        </linearGradient>
      </defs>

      <rect x="0.5" y="0.5" :width="svgWidth - 1" :height="svgHeight - 1" rx="18" fill="#090d12" stroke="#1f252c" />
      <rect :x="plotLeft" :y="plotTop" :width="zeroX - plotLeft" :height="plotHeight" fill="url(#r-outcome-loss-zone)" />
      <rect :x="zeroX" :y="plotTop" :width="plotRight - zeroX" :height="plotHeight" fill="url(#r-outcome-win-zone)" />

      <text :x="plotLeft" y="34" fill="#ef9e9e" font-size="15" font-weight="800" letter-spacing="0.07em">LOSSES</text>
      <text :x="zeroX" y="34" fill="#8f98a8" font-size="15" font-weight="800" letter-spacing="0.07em" text-anchor="middle">BREAKEVEN</text>
      <text :x="plotRight" y="34" fill="#90d89e" font-size="15" font-weight="800" letter-spacing="0.07em" text-anchor="end">WINS</text>

      <line :x1="plotLeft" :x2="plotRight" :y1="axisY" :y2="axisY" stroke="url(#r-outcome-axis)" stroke-width="2" stroke-linecap="round" />
      <line :x1="zeroX" :x2="zeroX" :y1="plotTop" :y2="axisY + 12" stroke="#d5deeb" stroke-opacity="0.28" stroke-width="1" stroke-dasharray="4 5" />

      <g v-for="tick in axisTicks" :key="tick">
        <line
          :x1="valueToX(tick)"
          :x2="valueToX(tick)"
          :y1="plotTop + 4"
          :y2="axisY + 8"
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
          {{ formatR(tick) }}
        </text>
      </g>

      <rect
        v-for="bucket in densityBuckets"
        :key="bucket.key"
        :x="bucket.x"
        :y="bucket.y"
        :width="bucket.width"
        :height="bucket.height"
        :rx="Math.min(8, bucket.width / 2)"
        :fill="bucket.fill"
        :opacity="bucket.opacity"
      />

      <circle
        v-for="trade in plottedTrades"
        :key="trade.key"
        class="r-outcome-map__point"
        :cx="trade.x"
        :cy="trade.y"
        :r="activeTradeKey === trade.key ? trade.radius + 2 : trade.radius"
        :fill="trade.fill"
        :stroke="activeTradeKey === trade.key ? '#eef3fb' : '#080b10'"
        :stroke-width="activeTradeKey === trade.key ? 2.4 : 1.7"
        tabindex="0"
        role="button"
        :aria-label="`${trade.label} ${formatR(trade.rMultiple)}`"
        data-testid="r-outcome-point"
        @mouseenter="showTooltip(trade.key, $event)"
        @mousemove="showTooltip(trade.key, $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(trade.key, $event)"
        @blur="hideTooltip"
      />

      <text
        v-if="!plottedTrades.length"
        :x="svgWidth / 2"
        :y="svgHeight / 2"
        fill="#8f98a8"
        font-size="14"
        text-anchor="middle"
      >
        Histogram available, but no closed trade detail rows were provided.
      </text>
    </svg>

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
          <span>P&L</span>
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { CSSProperties } from 'vue'

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

const svgWidth = 640
const svgHeight = 242
const plotLeft = 36
const plotRight = 604
const plotTop = 56
const axisY = 184
const plotHeight = axisY - plotTop
const plotWidth = plotRight - plotLeft

const normalizedRows = computed(() =>
  props.rows.filter(row =>
    Number.isFinite(row.lower)
    && Number.isFinite(row.upper)
    && Number.isFinite(row.count)
    && Number(row.count) >= 0,
  ),
)

const normalizedTrades = computed(() =>
  props.trades.filter(trade => Number.isFinite(Number(trade?.r_multiple))),
)

const hasData = computed(() => normalizedRows.value.length > 0 || normalizedTrades.value.length > 0)

const maxCount = computed(() =>
  Math.max(1, ...normalizedRows.value.map(row => Number(row.count) || 0)),
)

const maxAbsPnl = computed(() =>
  Math.max(1, ...normalizedTrades.value.map(trade => Math.abs(Number(trade.pnl ?? 0)))),
)

const domainMagnitude = computed(() => {
  const maxAbsR = Math.max(
    1,
    ...normalizedRows.value.flatMap(row => [Math.abs(Number(row.lower)), Math.abs(Number(row.upper))]),
    ...normalizedTrades.value.map(trade => Math.abs(Number(trade.r_multiple ?? 0))),
  )
  return Math.max(2, Math.ceil(maxAbsR))
})

const axisTicks = computed(() => {
  const magnitude = domainMagnitude.value
  const step = magnitude > 6 ? Math.ceil(magnitude / 6) : 1
  const ticks: number[] = []
  for (let value = -magnitude; value <= magnitude; value += step) ticks.push(value)
  if (!ticks.includes(0)) ticks.push(0)
  return [...new Set(ticks)].sort((left, right) => left - right)
})

const densityBuckets = computed(() =>
  normalizedRows.value
    .filter(row => Number(row.count) > 0)
    .map((row, index) => {
      const lower = valueToX(Number(row.lower))
      const upper = valueToX(Number(row.upper))
      const height = 18 + (Number(row.count) / maxCount.value) * 94
      const midpoint = (Number(row.lower) + Number(row.upper)) / 2
      const tone = toneForValue(midpoint)
      return {
        key: `${row.lower}-${row.upper}-${index}`,
        x: Math.min(lower, upper),
        y: axisY - height,
        width: Math.max(4, Math.abs(upper - lower)),
        height,
        fill: colorForTone(tone),
        opacity: tone === 'neutral' ? 0.3 : 0.36,
      }
    }),
)

const plottedTrades = computed(() =>
  normalizedTrades.value.map((trade, index) => {
    const rMultiple = Number(trade.r_multiple ?? 0)
    const pnlMagnitude = Math.abs(Number(trade.pnl ?? 0))
    const radius = 5.4 + Math.min(5.8, (pnlMagnitude / maxAbsPnl.value) * 5.8)
    const tone = toneForValue(rMultiple)
    return {
      ...trade,
      key: tradeKey(trade, index),
      label: trade.instrument_symbol || trade.symbol || 'Trade',
      rMultiple,
      tone,
      x: valueToX(rMultiple),
      y: jitterY(index, rMultiple, normalizedTrades.value),
      radius,
      fill: colorForTone(tone),
    }
  }),
)

const activeTradeKey = ref<string | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<CSSProperties>({})
const activeTrade = computed(() =>
  plottedTrades.value.find(trade => trade.key === activeTradeKey.value) ?? null,
)
const zeroX = computed(() => valueToX(0))
const tooltipBaseStyle = {
  position: 'fixed',
  zIndex: '1100',
  display: 'grid',
  gap: '8px',
  width: 'max-content',
  maxWidth: 'min(340px, calc(100vw - 24px))',
  padding: '10px',
  border: '1px solid #263142',
  borderRadius: '8px',
  background: '#0c1119',
  boxShadow: '0 18px 36px rgba(0, 0, 0, 0.42)',
  pointerEvents: 'none',
} satisfies CSSProperties

function valueToPercent(value: number) {
  const magnitude = domainMagnitude.value
  const clamped = Math.max(-magnitude, Math.min(magnitude, Number(value)))
  return ((clamped + magnitude) / (magnitude * 2)) * 100
}

function valueToX(value: number) {
  return plotLeft + (valueToPercent(value) / 100) * plotWidth
}

function jitterY(index: number, value: number, trades: TradeRow[]) {
  const rValue = Number(value)
  const clusterTolerance = Math.max(0.12, domainMagnitude.value * 0.035)
  const clusteredIndexes = trades
    .map((trade, tradeIndex) => ({
      index: tradeIndex,
      distance: Math.abs(Number(trade.r_multiple ?? 0) - rValue),
    }))
    .filter(item => Number.isFinite(item.distance) && item.distance <= clusterTolerance)
    .sort((left, right) => left.index - right.index)
    .map(item => item.index)
  const clusterPosition = Math.max(0, clusteredIndexes.indexOf(index))
  const clusterSize = Math.max(1, clusteredIndexes.length)
  const spread = Math.min(plotHeight - 34, 26 + Math.max(0, clusterSize - 1) * 18)
  const offset = clusterSize === 1
    ? 0
    : -spread / 2 + (spread * clusterPosition) / (clusterSize - 1)
  const wave = clusterSize === 1 ? ((index % 3) - 1) * 14 : 0
  const y = plotTop + plotHeight / 2 + offset + wave
  return Math.max(plotTop + 22, Math.min(axisY - 26, y))
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

function tradeKey(trade: TradeRow, index: number) {
  return `${trade.instrument_symbol || trade.symbol || 'trade'}-${trade.exit_at || index}-${trade.r_multiple ?? 0}-${index}`
}

function formatR(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(value % 1 === 0 ? 0 : 2)}R`
}

function formatSignedPercent(value: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

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
  const numeric = Number(value)
  const formatted = formatMoney(Math.abs(numeric))
  if (numeric > 0) return `+${formatted}`
  if (numeric < 0) return `-${formatted}`
  return formatted
}

function formatShortDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function humanizeToken(value?: string | null) {
  return String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function hideTooltip() {
  activeTradeKey.value = null
}

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
.r-outcome-map {
  display: grid;
  gap: 10px;
}

.r-outcome-map__svg {
  display: block;
  width: 100%;
  height: auto;
  min-height: 242px;
  max-height: 310px;
}

.r-outcome-map__point {
  cursor: pointer;
  transition: r 0.16s ease, stroke 0.16s ease, stroke-width 0.16s ease;
}

.r-outcome-map__point:hover,
.r-outcome-map__point:focus-visible {
  outline: none;
}

.r-outcome-map__empty {
  color: #7d8490;
  font-size: 12px;
}

.r-outcome-map__tooltip {
  position: fixed;
  z-index: 1100;
  display: grid;
  gap: 8px;
  width: max-content;
  max-width: min(340px, calc(100vw - 24px));
  padding: 10px;
  border: 1px solid #263142;
  border-radius: 8px;
  background: #0c1119;
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.42);
  pointer-events: none;
}

.r-outcome-map__tooltip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.r-outcome-map__tooltip-head strong {
  color: #f3f3f3;
  font-size: 12px;
}

.r-outcome-map__tooltip-grid {
  display: grid;
  grid-template-columns: max-content max-content;
  gap: 5px 14px;
  color: #97a1b2;
  font-size: 10px;
}

.r-outcome-map__tooltip-grid strong {
  display: inline-flex;
  gap: 8px;
  justify-content: flex-end;
  color: #dce3ee;
  font-weight: 700;
}

.r-outcome-map__tooltip-grid small {
  color: #8e98a8;
  font: inherit;
}

.positive {
  color: #74e39a;
}

.negative {
  color: #ff9aa7;
}
</style>
