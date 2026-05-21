<template>
  <div v-if="rows.length" class="symbol-bars">
    <div class="symbol-bars__summary">
      <span class="symbol-bars__summary-chip">{{ sortedRows.length }} symbols</span>
      <span v-if="bestRow" class="symbol-bars__summary-chip">
        Best realized {{ bestRow.symbol }} {{ formatSignedMoney(realizedPnl(bestRow)) }}
      </span>
      <span v-if="worstRow" class="symbol-bars__summary-chip">
        Worst realized {{ worstRow.symbol }} {{ formatSignedMoney(realizedPnl(worstRow)) }}
      </span>
    </div>

    <div v-for="row in sortedRows" :key="row.symbol" class="symbol-bars__row">
      <button
        type="button"
        class="symbol-bars__row-button"
        :class="{ 'symbol-bars__row-button--active': activeSymbol === row.symbol }"
        @mouseenter="showTooltip(row.symbol, $event)"
        @mouseleave="hideTooltip"
        @focus="showTooltip(row.symbol, $event)"
        @blur="hideTooltip"
      >
        <div class="symbol-bars__meta">
          <span class="symbol-bars__label">{{ row.symbol }}</span>
          <strong :class="pnlClass(realizedPnl(row))">
            {{ formatSignedMoney(realizedPnl(row)) }}
          </strong>
        </div>
        <div class="symbol-bars__submeta">
          <span>{{ summarizeTrades(row) }}</span>
          <span class="symbol-bars__submeta-primary" :class="pnlClass(realizedPnl(row))">realized</span>
          <span v-if="Number(row.open_position_count ?? 0) > 0" class="symbol-bars__submeta-secondary" :class="pnlClass(unrealizedPnl(row))">{{ formatSignedMoney(unrealizedPnl(row)) }} unrealized</span>
          <span class="symbol-bars__submeta-muted" :class="pnlClass(totalPnl(row))">{{ formatSignedMoney(totalPnl(row)) }} marked</span>
          <span v-if="row.avg_r != null">{{ formatR(row.avg_r) }} avg</span>
        </div>
        <div class="symbol-bars__track">
          <div
            class="symbol-bars__bar"
            :class="barToneClass(realizedPnl(row))"
            :style="barStyle(realizedPnl(row))"
          />
        </div>
      </button>
    </div>

    <Teleport to="body">
      <div
        v-if="activeRow"
        ref="tooltipRef"
        class="symbol-bars__tooltip"
        :style="tooltipStyle"
      >
        <div class="symbol-bars__tooltip-head">
          <strong>{{ activeRow.symbol }}</strong>
          <span :class="pnlClass(realizedPnl(activeRow))">
            {{ formatSignedMoney(realizedPnl(activeRow)) }} realized
          </span>
        </div>
        <div class="symbol-bars__tooltip-metrics">
          <span>{{ summarizeTrades(activeRow) }}</span>
          <span class="symbol-bars__tooltip-secondary" :class="pnlClass(unrealizedPnl(activeRow))">{{ formatSignedMoney(unrealizedPnl(activeRow)) }} unrealized</span>
          <span class="symbol-bars__tooltip-secondary" :class="pnlClass(totalPnl(activeRow))">{{ formatSignedMoney(totalPnl(activeRow)) }} marked</span>
          <span v-if="activeRow.win_rate != null">{{ formatPercent(activeRow.win_rate) }} win</span>
          <span v-if="activeRow.avg_r != null">{{ formatR(activeRow.avg_r) }} avg</span>
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

const sortedRows = computed(() =>
  [...props.rows]
    .filter(row => row?.symbol)
    .sort((left, right) => {
      const realizedDelta = Math.abs(realizedPnl(right)) - Math.abs(realizedPnl(left))
      if (realizedDelta !== 0) return realizedDelta
      return Math.abs(unrealizedPnl(right)) - Math.abs(unrealizedPnl(left))
    })
    .slice(0, 8),
)

const bestRow = computed(() =>
  sortedRows.value.length
    ? [...sortedRows.value].sort((left, right) => realizedPnl(right) - realizedPnl(left))[0]
    : null,
)

const worstRow = computed(() =>
  sortedRows.value.length
    ? [...sortedRows.value].sort((left, right) => realizedPnl(left) - realizedPnl(right))[0]
    : null,
)

const maxAbsValue = computed(() =>
  Math.max(1, ...sortedRows.value.map(row => Math.abs(realizedPnl(row)))),
)

const hoveredSymbol = ref<string | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipStyle = ref<Record<string, string>>({})

const activeSymbol = computed(() => hoveredSymbol.value)
const activeRow = computed(() =>
  sortedRows.value.find(row => row.symbol === activeSymbol.value) ?? null,
)
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

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function barToneClass(value: unknown) {
  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) return 'symbol-bars__bar--positive'
  if (Number.isFinite(numeric) && numeric < 0) return 'symbol-bars__bar--negative'
  return 'symbol-bars__bar--neutral'
}

function summarizeTrades(row: {
  trade_count?: number | null
  closed_trade_count?: number | null
  open_position_count?: number | null
  win_rate?: number | null
}) {
  const tradeCount = Number(row.closed_trade_count ?? row.trade_count ?? 0)
  const openCount = Number(row.open_position_count ?? 0)
  if (!tradeCount && !openCount) return 'No marked trades'
  const parts = [
    `${tradeCount} closed`,
    `${openCount} open`,
  ]
  if (row.win_rate != null) parts.push(`${formatPercent(Number(row.win_rate))} win`)
  return parts.join(' · ')
}

function humanizeToken(value?: string | null) {
  return String(value ?? '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function barStyle(value: number) {
  const ratio = Math.max(0.08, Math.min(1, Math.abs(value) / maxAbsValue.value))
  return { width: `${ratio * 100}%` }
}

function hideTooltip() {
  hoveredSymbol.value = null
}

async function showTooltip(symbol: string, event: FocusEvent | MouseEvent) {
  hoveredSymbol.value = symbol
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
.symbol-bars {
  display: grid;
  gap: 12px;
  align-content: start;
}

.symbol-bars__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.symbol-bars__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.symbol-bars__row {
  display: block;
}

.symbol-bars__row-button {
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

.symbol-bars__row-button:hover,
.symbol-bars__row-button:focus-visible,
.symbol-bars__row-button--active {
  border-color: #1f252c;
  background: #10141a;
  outline: none;
}

.symbol-bars__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.symbol-bars__label {
  color: #d7d7d7;
  font-size: 12px;
  font-weight: 700;
}

.symbol-bars__meta strong {
  color: #aeb7c5;
}

.symbol-bars__submeta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #8a92a0;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.symbol-bars__submeta-primary {
  font-weight: 700;
}

.symbol-bars__submeta-secondary {
  opacity: 0.86;
}

.symbol-bars__submeta-muted {
  opacity: 0.64;
}

.symbol-bars__track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: #111317;
  border: 1px solid #1f252c;
  overflow: hidden;
}

.symbol-bars__bar {
  height: 100%;
  border-radius: inherit;
}

.symbol-bars__bar--positive {
  background: linear-gradient(90deg, #2a7e50 0%, #6ddb95 100%);
}

.symbol-bars__bar--negative {
  background: linear-gradient(90deg, #7a3137 0%, #ef7f88 100%);
}

.symbol-bars__bar--neutral {
  background: linear-gradient(90deg, #303844 0%, #657284 100%);
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
