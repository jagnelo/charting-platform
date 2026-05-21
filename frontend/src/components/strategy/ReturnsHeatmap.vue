<template>
  <div v-if="matrixRows.length" ref="rootRef" class="returns-heatmap">
    <div class="returns-heatmap__legend">
      <span>{{ legendMinLabel }}</span>
      <div class="returns-heatmap__legend-bar" aria-hidden="true" />
      <span>{{ legendMaxLabel }}</span>
    </div>

    <div
      class="returns-heatmap__viewport"
      :class="{ 'returns-heatmap__viewport--scrollable': isViewportScrollable }"
      :style="viewportStyle"
    >
      <div
        class="returns-heatmap__grid"
        :style="gridStyle"
      >
        <div class="returns-heatmap__corner" />
        <div
          v-for="column in columns"
          :key="column.key"
          class="returns-heatmap__col-label"
        >
          {{ column.label }}
        </div>

        <template v-for="row in matrixRows" :key="row.label">
          <div class="returns-heatmap__row-label">{{ row.label }}</div>
          <button
            v-for="cell in row.cells"
            :key="cell.key"
            type="button"
            class="returns-heatmap__cell"
            :class="{
              'returns-heatmap__cell--empty': cell.value == null,
              'returns-heatmap__cell--positive': (cell.value ?? 0) > 0,
              'returns-heatmap__cell--negative': (cell.value ?? 0) < 0,
            }"
            :style="cellStyle(cell.value)"
            @mouseenter="showCellPopover(cell, $event, false)"
            @mouseleave="hideCellPopover(false)"
            @focus="showCellPopover(cell, $event, false)"
            @blur="hideCellPopover(false)"
            @click="toggleCellPopover(cell, $event)"
          >
            <span>{{ cell.value == null ? '—' : compactPercent(cell.value) }}</span>
          </button>
        </template>
      </div>
    </div>

    <div
      v-if="activePopover"
      ref="tooltipRef"
      class="returns-heatmap__popover"
      :style="popoverStyle"
      @mouseenter="popoverHovered = true"
      @mouseleave="handlePopoverMouseLeave"
    >
      <div class="returns-heatmap__popover-head">
        <strong>{{ activePopover.period }}</strong>
        <span>{{ activePopover.value == null ? 'No realized P&L' : `${valuePercent(activePopover.value)} realized` }}</span>
      </div>

      <div v-if="activePopover.realizedDetails.length" class="returns-heatmap__popover-list">
        <span class="returns-heatmap__popover-section-label">Resolved in period</span>
        <article
          v-for="detail in activePopover.realizedDetails"
          :key="`${detail.position_id}-${detail.event_type}-${detail.ts}`"
          class="returns-heatmap__popover-item"
        >
          <div class="returns-heatmap__popover-item-head">
            <strong>{{ detail.symbol || 'Unknown' }}</strong>
            <span>{{ humanizeEventType(detail.event_type) }}</span>
          </div>
          <div class="returns-heatmap__popover-item-body">
            <span>{{ formatShortDateTime(detail.ts) }}</span>
            <span v-if="detail.reason">{{ humanizeReason(detail.reason) }}</span>
          </div>
          <div class="returns-heatmap__popover-item-body">
            <span>{{ detail.side ? humanizeSide(detail.side) : '—' }}</span>
            <span v-if="detail.quantity != null">{{ formatQuantity(detail.quantity) }} @ {{ formatMoney(detail.price) }}</span>
          </div>
          <div class="returns-heatmap__popover-item-pnl">
            <strong :class="pnlClass(detail.pnl_pct ?? detail.pnl)">
              {{ detail.pnl_pct == null ? formatSignedMoney(detail.pnl) : formatSignedPercent(detail.pnl_pct) }}
            </strong>
            <span v-if="detail.pnl != null">{{ formatSignedMoney(detail.pnl) }}</span>
          </div>
        </article>
      </div>
      <p v-else class="returns-heatmap__popover-empty">
        No closed positions were recorded in this period.
      </p>

      <div v-if="activePopover.unrealizedDetails.length" class="returns-heatmap__popover-list returns-heatmap__popover-list--muted">
        <span class="returns-heatmap__popover-section-label">
          Unrealized marks
          <small :class="pnlClass(unrealizedTotal(activePopover.unrealizedDetails))">{{ formatUnrealizedSummary(activePopover.unrealizedDetails) }}</small>
        </span>
        <article
          v-for="detail in activePopover.unrealizedDetails"
          :key="`${detail.position_id}-${detail.event_type}-${detail.ts}`"
          class="returns-heatmap__popover-item returns-heatmap__popover-item--compact"
        >
          <div class="returns-heatmap__popover-item-head">
            <strong>{{ detail.symbol || 'Unknown' }}</strong>
            <span :class="pnlClass(detail.pnl_pct ?? detail.pnl)">{{ detail.pnl_pct == null ? formatSignedMoney(detail.pnl) : formatSignedPercent(detail.pnl_pct) }}</span>
          </div>
          <div class="returns-heatmap__popover-item-body">
            <span>{{ formatShortDateTime(detail.ts) }}</span>
            <span v-if="detail.pnl != null">{{ formatSignedMoney(detail.pnl) }}</span>
          </div>
        </article>
      </div>
    </div>
  </div>

  <div v-else class="returns-heatmap__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

interface ReturnRow {
  period: string
  return_pct: number | null
}

interface HeatmapCell {
  key: string
  period: string
  value: number | null
}

interface ReturnBreakdownDetail {
  ts: string
  event_type: string
  position_id: string
  symbol?: string | null
  side?: string | null
  quantity?: number | null
  price?: number | null
  pnl?: number | null
  pnl_pct?: number | null
  reason?: string | null
}

interface ActivePopover {
  cellKey: string
  period: string
  value: number | null
  realizedDetails: ReturnBreakdownDetail[]
  unrealizedDetails: ReturnBreakdownDetail[]
  left: number
  top: number
  anchorTop: number
  anchorBottom: number
  anchorLeft: number
  pinned: boolean
}

const props = withDefaults(defineProps<{
  rows: ReturnRow[]
  mode: 'monthly' | 'quarterly' | 'yearly'
  emptyLabel?: string
  maxVisibleRows?: number
  cellDetails?: Record<string, ReturnBreakdownDetail[]>
}>(), {
  emptyLabel: 'No return breakdown yet.',
  maxVisibleRows: 5,
  cellDetails: () => ({}),
})

const rootRef = ref<HTMLElement | null>(null)
const tooltipRef = ref<HTMLElement | null>(null)
const activePopover = ref<ActivePopover | null>(null)
const popoverHovered = ref(false)

const columns = computed(() => (
  props.mode === 'monthly'
    ? [
        { key: '01', label: 'Jan' },
        { key: '02', label: 'Feb' },
        { key: '03', label: 'Mar' },
        { key: '04', label: 'Apr' },
        { key: '05', label: 'May' },
        { key: '06', label: 'Jun' },
        { key: '07', label: 'Jul' },
        { key: '08', label: 'Aug' },
        { key: '09', label: 'Sep' },
        { key: '10', label: 'Oct' },
        { key: '11', label: 'Nov' },
        { key: '12', label: 'Dec' },
      ]
    : props.mode === 'quarterly'
      ? [
        { key: 'Q1', label: 'Q1' },
        { key: 'Q2', label: 'Q2' },
        { key: 'Q3', label: 'Q3' },
        { key: 'Q4', label: 'Q4' },
      ]
      : [
        { key: 'YR', label: 'Return' },
      ]
))

const cellMap = computed(() => {
  const next = new Map<string, number | null>()
  for (const row of props.rows) {
    next.set(row.period, row.return_pct == null ? null : Number(row.return_pct))
  }
  return next
})

const matrixRows = computed(() => {
  const years = Array.from(
    new Set(
      props.rows
        .map(row => String(row.period).slice(0, 4))
        .filter(value => /^\d{4}$/.test(value)),
    ),
  ).sort()

  return years.map(year => ({
    label: year,
    cells: columns.value.map(column => {
      const period = props.mode === 'yearly' ? year : `${year}-${column.key}`
      return {
        key: period,
        period,
        value: cellMap.value.has(period) ? cellMap.value.get(period) ?? null : null,
      } satisfies HeatmapCell
    }),
  }))
})

const gridStyle = computed(() => {
  const rowLabelWidth = 44
  const cellWidth = props.mode === 'monthly' ? 54 : props.mode === 'quarterly' ? 72 : 96
  return {
    gridTemplateColumns: `${rowLabelWidth}px repeat(${columns.value.length}, minmax(${cellWidth}px, 1fr))`,
    minWidth: `${rowLabelWidth + (columns.value.length * cellWidth) + (columns.value.length * 6)}px`,
  }
})

const isViewportScrollable = computed(() => matrixRows.value.length > props.maxVisibleRows)

const viewportStyle = computed(() => {
  if (!isViewportScrollable.value) return {}

  const stickyHeaderHeight = 28
  const rowHeight = 42
  const viewportPadding = 4
  return {
    maxHeight: `${stickyHeaderHeight + (props.maxVisibleRows * rowHeight) + viewportPadding}px`,
  }
})

const maxAbsReturn = computed(() => {
  const values = props.rows
    .map(row => Number(row.return_pct))
    .filter(value => Number.isFinite(value))
    .map(value => Math.abs(value))
  return values.length ? Math.max(...values) : 0
})

const legendMinLabel = computed(() => (
  maxAbsReturn.value > 0 ? valuePercent(-maxAbsReturn.value) : '0.00%'
))

const legendMaxLabel = computed(() => (
  maxAbsReturn.value > 0 ? valuePercent(maxAbsReturn.value) : '0.00%'
))

function compactPercent(value: number) {
  const absValue = Math.abs(value)
  if (absValue >= 10) return `${value.toFixed(0)}%`
  return `${value.toFixed(1)}%`
}

const popoverStyle = computed(() => {
  if (!activePopover.value) return {}
  return {
    left: `${activePopover.value.left}px`,
    top: `${activePopover.value.top}px`,
  }
})

function valuePercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function cellStyle(value: number | null) {
  if (value == null || !Number.isFinite(value) || value === 0) {
    return {
      '--cell-bg': '#111317',
      '--cell-border': '#1f252c',
      '--cell-color': '#6f7680',
    }
  }

  const denominator = maxAbsReturn.value > 0 ? maxAbsReturn.value : 1
  const intensity = Math.max(0.18, Math.min(1, Math.abs(value) / denominator))
  if (value > 0) {
    return {
      '--cell-bg': `color-mix(in srgb, #5fd38d ${18 + intensity * 42}%, #111317)`,
      '--cell-border': `color-mix(in srgb, #7ae8a4 ${28 + intensity * 34}%, #25352c)`,
      '--cell-color': '#d8ffe4',
    }
  }
  return {
    '--cell-bg': `color-mix(in srgb, #ef7f88 ${18 + intensity * 42}%, #111317)`,
    '--cell-border': `color-mix(in srgb, #ff9da5 ${28 + intensity * 34}%, #352529)`,
    '--cell-color': '#ffe0e3',
  }
}

function showCellPopover(cell: HeatmapCell, event: Event, pinned: boolean) {
  const currentTarget = event.currentTarget
  const button = currentTarget instanceof HTMLElement ? currentTarget : null
  const root = rootRef.value
  if (!button || !root) return

  const rect = button.getBoundingClientRect()
  const details = props.cellDetails[cell.period] ?? []
  popoverHovered.value = false
  activePopover.value = {
    cellKey: cell.key,
    period: cell.period,
    value: cell.value,
    realizedDetails: details.filter(detail => String(detail.event_type ?? '') === 'exit'),
    unrealizedDetails: details.filter(detail => String(detail.event_type ?? '') === 'open_at_end'),
    left: rect.left,
    top: rect.bottom + 10,
    anchorTop: rect.top,
    anchorBottom: rect.bottom,
    anchorLeft: rect.left,
    pinned,
  }
  void nextTick(() => positionPopover())
}

function toggleCellPopover(cell: HeatmapCell, event: Event) {
  if (activePopover.value?.cellKey === cell.key && activePopover.value.pinned) {
    activePopover.value = null
    return
  }
  showCellPopover(cell, event, true)
}

function hideCellPopover(force: boolean) {
  if (!activePopover.value) return
  if (!force && activePopover.value.pinned) return
  if (!force && popoverHovered.value) return
  activePopover.value = null
}

function handlePopoverMouseLeave() {
  popoverHovered.value = false
  hideCellPopover(false)
}

function positionPopover() {
  if (!activePopover.value || !tooltipRef.value) return

  const tooltipRect = tooltipRef.value.getBoundingClientRect()
  const viewportPadding = 12
  const maxLeft = window.innerWidth - tooltipRect.width - viewportPadding
  const minLeft = viewportPadding
  const preferredLeft = activePopover.value.anchorLeft
  const fitsBelow = activePopover.value.anchorBottom + 10 + tooltipRect.height <= window.innerHeight - viewportPadding
  const top = fitsBelow
    ? activePopover.value.anchorBottom + 10
    : Math.max(viewportPadding, activePopover.value.anchorTop - tooltipRect.height - 10)

  activePopover.value = {
    ...activePopover.value,
    left: Math.min(Math.max(preferredLeft, minLeft), Math.max(minLeft, maxLeft)),
    top,
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!activePopover.value?.pinned) return
  const root = rootRef.value
  const tooltip = tooltipRef.value
  const target = event.target
  if (root && target instanceof Node && root.contains(target)) return
  if (tooltip && target instanceof Node && tooltip.contains(target)) return
  activePopover.value = null
}

onMounted(() => {
  window.addEventListener('pointerdown', handleDocumentPointerDown, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleDocumentPointerDown, true)
})

function humanizeEventType(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase())
}

function humanizeReason(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase())
}

function humanizeSide(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function formatMoney(value: number | null | undefined) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function formatSignedMoney(value: number | null | undefined) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const formatted = formatMoney(Math.abs(Number(value)))
  if (Number(value) > 0) return `+${formatted}`
  if (Number(value) < 0) return `-${formatted}`
  return formatted
}

function formatSignedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`
}

function formatUnrealizedSummary(details: ReturnBreakdownDetail[]) {
  const pct = unrealizedPctTotal(details)
  const money = formatSignedMoney(unrealizedTotal(details))
  return pct == null
    ? `${details.length} open · ${money}`
    : `${details.length} open · ${formatSignedPercent(pct)} · ${money}`
}

function unrealizedTotal(details: ReturnBreakdownDetail[]) {
  return details.reduce((sum, detail) => sum + (Number(detail.pnl) || 0), 0)
}

function unrealizedPctTotal(details: ReturnBreakdownDetail[]) {
  const values = details
    .map(detail => Number(detail.pnl_pct))
    .filter(value => Number.isFinite(value))
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0)
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function formatQuantity(value: number) {
  return Number(value).toFixed(2)
}

function formatShortDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(date).replace(',', '')
}
</script>

<style scoped>
.returns-heatmap {
  display: grid;
  gap: 10px;
  position: relative;
}

.returns-heatmap__viewport {
  overflow: auto;
  padding-bottom: 4px;
}

.returns-heatmap__legend {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #7d8490;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.returns-heatmap__legend-bar {
  width: 72px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ef7f88 0%, #111317 50%, #5fd38d 100%);
  border: 1px solid #1f252c;
}

.returns-heatmap__grid {
  display: grid;
  gap: 6px;
  align-items: center;
}

.returns-heatmap__corner,
.returns-heatmap__col-label,
.returns-heatmap__row-label {
  color: #7d8490;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.returns-heatmap__col-label {
  position: sticky;
  top: 0;
  z-index: 2;
  padding-block: 4px;
  background: rgba(16, 19, 24, 0.98);
  text-align: center;
}

.returns-heatmap__row-label {
  position: sticky;
  left: 0;
  z-index: 1;
  padding-right: 4px;
  background: rgba(16, 19, 24, 0.98);
  text-align: right;
}

.returns-heatmap__corner {
  position: sticky;
  top: 0;
  left: 0;
  z-index: 3;
  background: rgba(16, 19, 24, 0.98);
}

.returns-heatmap__cell {
  min-height: 36px;
  padding: 5px 6px;
  border-radius: 8px;
  border: 1px solid var(--cell-border);
  background: var(--cell-bg);
  color: var(--cell-color);
  font: inherit;
  cursor: default;
}

.returns-heatmap__cell span {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
}

.returns-heatmap__cell--empty span {
  font-weight: 500;
}

.returns-heatmap__popover {
  position: fixed;
  z-index: 220;
  display: grid;
  gap: 10px;
  inline-size: clamp(280px, 32vw, 360px);
  max-inline-size: min(360px, calc(100vw - 24px));
  max-block-size: min(460px, calc(100vh - 24px));
  overflow: auto;
  overscroll-behavior: contain;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid #243042;
  background: rgba(10, 14, 21, 0.97);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.42);
  backdrop-filter: blur(10px);
}

.returns-heatmap__popover-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 14px;
  color: #d8dde6;
  font-size: 11px;
}

.returns-heatmap__popover-head span {
  color: #8b93a1;
}

.returns-heatmap__popover-list {
  display: grid;
  gap: 10px;
}

.returns-heatmap__popover-section-label {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #7f8794;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.returns-heatmap__popover-section-label small {
  color: #9aa3b1;
  font: inherit;
  letter-spacing: 0;
  text-transform: none;
}

.returns-heatmap__popover-list--muted {
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid rgba(36, 48, 66, 0.65);
}

.returns-heatmap__popover-item {
  display: grid;
  gap: 4px;
  padding-top: 10px;
  border-top: 1px solid rgba(36, 48, 66, 0.65);
}

.returns-heatmap__popover-item:first-child {
  padding-top: 0;
  border-top: 0;
}

.returns-heatmap__popover-item--compact {
  gap: 2px;
  padding-top: 6px;
}

.returns-heatmap__popover-item-head,
.returns-heatmap__popover-item-body,
.returns-heatmap__popover-item-pnl {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.returns-heatmap__popover-item-head {
  color: #d8dde6;
}

.returns-heatmap__popover-item-head strong {
  color: #ffffff;
}

.returns-heatmap__popover-item-body {
  color: #8b93a1;
  font-size: 10px;
}

.returns-heatmap__popover-item-pnl {
  align-items: baseline;
  color: #8b93a1;
  font-size: 10px;
}

.returns-heatmap__popover-item-pnl strong {
  color: #d8dde6;
  font-size: 11px;
}

.returns-heatmap__popover-item-pnl strong.positive {
  color: #8be3a7;
}

.returns-heatmap__popover-item-pnl strong.negative {
  color: #f2a0a6;
}

.positive {
  color: #8be3a7;
}

.negative {
  color: #f2a0a6;
}

.returns-heatmap__popover-empty {
  margin: 0;
  color: #8b93a1;
  font-size: 10px;
  line-height: 1.5;
  white-space: normal;
}

.returns-heatmap__empty {
  color: #7d8490;
  font-size: 12px;
}
</style>
