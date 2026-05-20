<template>
  <div v-if="rows.length" class="distribution-bars">
    <div class="distribution-bars__summary">
      <span class="distribution-bars__summary-chip">{{ normalizedTrades.length }} trades</span>
      <span v-if="normalizedTrades.length" class="distribution-bars__summary-chip">Avg {{ formatR(averageR) }}</span>
      <span v-if="normalizedTrades.length" class="distribution-bars__summary-chip">Median {{ formatR(medianR) }}</span>
      <span v-if="normalizedTrades.length" class="distribution-bars__summary-chip">{{ positiveTradeRateLabel }}</span>
    </div>

    <div v-for="(row, index) in normalizedRows" :key="`${row.lower}-${row.upper}-${index}`" class="distribution-bars__row">
      <button
        type="button"
        class="distribution-bars__row-button"
        :class="{ 'distribution-bars__row-button--active': activeBucketKey === bucketKey(row, index) }"
        @mouseenter="showTooltip(bucketKey(row, index), $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(bucketKey(row, index), $event)"
        @blur="hideTooltip"
      >
        <div class="distribution-bars__meta">
          <span>{{ shortLabel(row.lower, row.upper) }}</span>
          <strong>{{ row.count }}</strong>
        </div>
        <div class="distribution-bars__submeta">
          <span>{{ bucketTradeRate(row.count) }}</span>
          <span v-if="row.count > 0">{{ bucketSummaryLabel(row, index) }}</span>
        </div>
        <div class="distribution-bars__track">
          <div class="distribution-bars__bar" :style="{ width: `${barWidth(row.count)}%` }" />
        </div>
      </button>
    </div>

    <Teleport to="body">
      <div
        v-if="activeBucket"
        ref="tooltipRef"
        class="distribution-bars__tooltip"
        :style="tooltipStyle"
      >
        <div class="distribution-bars__tooltip-head">
          <strong>{{ shortLabel(activeBucket.lower, activeBucket.upper) }}</strong>
          <span>{{ activeBucket.count }} trade{{ activeBucket.count === 1 ? '' : 's' }}</span>
        </div>
        <div v-if="activeTrades.length" class="distribution-bars__tooltip-events">
          <div
            v-for="trade in activeTrades"
            :key="`${trade.instrument_symbol || trade.symbol}-${trade.exit_at}`"
            class="distribution-bars__tooltip-event"
          >
            <span>{{ trade.instrument_symbol || trade.symbol || '—' }}</span>
            <span>{{ formatR(Number(trade.r_multiple ?? 0)) }}</span>
            <span v-if="trade.pnl != null">{{ formatMoney(Number(trade.pnl)) }}</span>
            <span>{{ humanizeToken(trade.exit_reason || trade.reason || 'exit') }}</span>
          </div>
        </div>
        <div v-else class="distribution-bars__tooltip-empty">
          No closed trades in this R bucket.
        </div>
      </div>
    </Teleport>
  </div>
  <div v-else class="distribution-bars__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  rows: Array<{ lower: number; upper: number; count: number }>
  trades?: Array<{
    instrument_symbol?: string | null
    symbol?: string | null
    pnl?: number | null
    r_multiple?: number | null
    exit_reason?: string | null
    reason?: string | null
    exit_at?: string | null
  }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No distribution data yet.',
  trades: () => [],
})

const normalizedRows = computed(() =>
  props.rows
    .filter(row => Number.isFinite(row.lower) && Number.isFinite(row.upper) && Number.isFinite(row.count))
    .slice(0, 8),
)

const normalizedTrades = computed(() =>
  props.trades.filter(trade => Number.isFinite(Number(trade?.r_multiple))),
)

const maxCount = computed(() =>
  Math.max(1, ...normalizedRows.value.map(row => Number(row.count) || 0)),
)

const averageR = computed(() =>
  normalizedTrades.value.length
    ? normalizedTrades.value.reduce((sum, trade) => sum + Number(trade.r_multiple ?? 0), 0) / normalizedTrades.value.length
    : 0,
)

const medianR = computed(() => {
  if (!normalizedTrades.value.length) return 0
  const values = normalizedTrades.value
    .map(trade => Number(trade.r_multiple ?? 0))
    .sort((left, right) => left - right)
  const middle = Math.floor(values.length / 2)
  return values.length % 2 === 0
    ? (values[middle - 1] + values[middle]) / 2
    : values[middle]
})

const positiveTradeRateLabel = computed(() => {
  if (!normalizedTrades.value.length) return 'No closed trades'
  const positiveCount = normalizedTrades.value.filter(trade => Number(trade.r_multiple ?? 0) > 0).length
  const pct = (positiveCount / normalizedTrades.value.length) * 100
  return `${pct.toFixed(0)}% > 0R`
})

const hoveredBucketKey = ref<string | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<Record<string, string>>({})
const activeBucketKey = computed(() => hoveredBucketKey.value)
const activeBucket = computed(() =>
  normalizedRows.value.find((row, index) => bucketKey(row, index) === activeBucketKey.value) ?? null,
)
const activeTrades = computed(() => {
  if (!activeBucket.value) return []
  const activeIndex = normalizedRows.value.findIndex((row, index) => bucketKey(row, index) === activeBucketKey.value)
  return matchingTrades(activeBucket.value, activeIndex).slice(0, 6)
})

function shortLabel(lower: number, upper: number) {
  return `${trim(lower)} → ${trim(upper)}`
}

function trim(value: number) {
  if (Math.abs(value) >= 10) return value.toFixed(1)
  if (Math.abs(value) >= 1) return value.toFixed(2)
  return value.toFixed(3)
}

function barWidth(count: number) {
  return Math.max(10, Math.min(100, (count / maxCount.value) * 100))
}

function bucketTradeRate(count: number) {
  if (!normalizedTrades.value.length) return 'No closed trades'
  return `${((count / normalizedTrades.value.length) * 100).toFixed(0)}% of trades`
}

function bucketSummaryLabel(row: { lower: number; upper: number; count: number }, index: number) {
  const trades = matchingTrades(row, index)
  if (!trades.length) return 'No matching trades'
  const average = trades.reduce((sum, trade) => sum + Number(trade.r_multiple ?? 0), 0) / trades.length
  return `Avg ${formatR(average)}`
}

function formatR(value: number) {
  return `${value.toFixed(2)}R`
}

function formatMoney(value: number) {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })
}

function humanizeToken(value?: string | null) {
  return String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function bucketKey(row: { lower: number; upper: number }, index: number) {
  return `${row.lower}-${row.upper}-${index}`
}

function matchingTrades(row: { lower: number; upper: number }, index: number) {
  const isLastBucket = index === normalizedRows.value.length - 1
  return normalizedTrades.value.filter(trade => {
    const value = Number(trade.r_multiple ?? 0)
    if (!Number.isFinite(value)) return false
    if (row.lower === row.upper) return Math.abs(value - row.lower) < 0.0001
    return isLastBucket ? value >= row.lower && value <= row.upper : value >= row.lower && value < row.upper
  })
}

function hideTooltip() {
  hoveredBucketKey.value = null
}

async function showTooltip(key: string, event: FocusEvent | MouseEvent) {
  hoveredBucketKey.value = key
  await nextTick()
  positionTooltip(event.currentTarget as HTMLElement | null)
}

function positionTooltip(anchor: HTMLElement | null) {
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
.distribution-bars {
  display: grid;
  gap: 12px;
}

.distribution-bars__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.distribution-bars__row {
  display: block;
}

.distribution-bars__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.distribution-bars__row-button {
  width: 100%;
  display: grid;
  gap: 6px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 6px;
  cursor: pointer;
}

.distribution-bars__row-button:hover,
.distribution-bars__row-button:focus-visible,
.distribution-bars__row-button--active {
  border-color: #1f252c;
  background: #10141a;
  outline: none;
}

.distribution-bars__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #d7d7d7;
  font-size: 11px;
}

.distribution-bars__submeta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  color: #8a92a0;
  font-size: 10px;
}

.distribution-bars__track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: #111317;
  border: 1px solid #1f252c;
  overflow: hidden;
}

.distribution-bars__bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #3d5f80 0%, #64b5f6 100%);
}

.distribution-bars__empty {
  color: #7d8490;
  font-size: 12px;
}

.distribution-bars__tooltip {
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

.distribution-bars__tooltip-head,
.distribution-bars__tooltip-event {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
}

.distribution-bars__tooltip-head strong {
  color: #f3f3f3;
  font-size: 12px;
}

.distribution-bars__tooltip-events,
.distribution-bars__tooltip-empty,
.distribution-bars__tooltip-event {
  color: #97a1b2;
  font-size: 10px;
}
</style>
