<template>
  <div v-if="sortedRows.length" class="optimization-panel">
    <div class="optimization-panel__summary">
      <span class="optimization-panel__summary-chip">{{ sortedRows.length }} configs</span>
      <span class="optimization-panel__summary-chip">
        Best <b :class="pnlClass(sortedRows[0].net_pnl)">{{ formatSignedMoney(sortedRows[0].net_pnl) }}</b>
      </span>
      <span class="optimization-panel__summary-chip">Avg <b :class="pnlClass(averageR)">{{ formatR(averageR) }}</b></span>
    </div>

    <div class="optimization-panel__table-wrap">
      <table class="optimization-panel__table">
        <thead>
          <tr>
            <th>#</th>
            <th>Stop</th>
            <th>Target</th>
            <th>Bars</th>
            <th>Trades</th>
            <th>Avg R</th>
            <th>P&amp;L</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in sortedRows"
            :key="`${row.stop_loss_pct}-${row.take_profit_rr}-${row.max_bars_in_trade}-${index}`"
            :class="{ 'optimization-panel__row--active': activeIndex === index }"
            tabindex="0"
            @mouseenter="hoveredIndex = index"
            @mouseleave="hoveredIndex = null"
            @focus="hoveredIndex = index"
            @blur="hoveredIndex = null"
            @click="togglePinned(index)"
          >
            <td>{{ index + 1 }}</td>
            <td>{{ row.stop_loss_pct }}%</td>
            <td>{{ row.take_profit_rr }}R</td>
            <td>{{ row.max_bars_in_trade }}</td>
            <td>{{ row.trade_count }}</td>
            <td :class="pnlClass(row.avg_r)">{{ formatR(row.avg_r) }}</td>
            <td :class="pnlClass(row.net_pnl)">{{ formatSignedMoney(row.net_pnl) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="activeRow" class="optimization-panel__detail">
      <div class="optimization-panel__detail-head">
        <strong>Rank #{{ activeIndex! + 1 }}</strong>
        <span :class="pnlClass(activeRow.net_pnl)">{{ formatSignedMoney(activeRow.net_pnl) }}</span>
      </div>
      <div class="optimization-panel__detail-grid">
        <span>Stop {{ activeRow.stop_loss_pct }}%</span>
        <span>Target {{ activeRow.take_profit_rr }}R</span>
        <span>{{ activeRow.max_bars_in_trade }} bars max</span>
        <span>{{ activeRow.trade_count }} trades</span>
        <span><b :class="pnlClass(activeRow.avg_r)">{{ formatR(activeRow.avg_r) }}</b> average</span>
      </div>
    </div>
  </div>
  <div v-else class="optimization-panel__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  rows: Array<{
    stop_loss_pct: number
    take_profit_rr: number
    max_bars_in_trade: number
    trade_count: number
    net_pnl: number
    avg_r: number
  }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No optimization leaderboard yet.',
})

const sortedRows = computed(() =>
  [...props.rows].sort((left, right) => {
    const pnlDelta = Number(right.net_pnl ?? 0) - Number(left.net_pnl ?? 0)
    if (pnlDelta !== 0) return pnlDelta
    return Number(right.avg_r ?? 0) - Number(left.avg_r ?? 0)
  }),
)

const averageR = computed(() =>
  sortedRows.value.length
    ? sortedRows.value.reduce((sum, row) => sum + Number(row.avg_r ?? 0), 0) / sortedRows.value.length
    : 0,
)

const hoveredIndex = ref<number | null>(null)
const pinnedIndex = ref<number | null>(null)
const activeIndex = computed(() => pinnedIndex.value ?? hoveredIndex.value)
const activeRow = computed(() =>
  activeIndex.value == null ? null : sortedRows.value[activeIndex.value] ?? null,
)

function togglePinned(index: number) {
  pinnedIndex.value = pinnedIndex.value === index ? null : index
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

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function formatR(value: number) {
  return `${Number(value ?? 0).toFixed(2)}R`
}
</script>

<style scoped>
.optimization-panel {
  display: grid;
  gap: 12px;
}

.optimization-panel__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.optimization-panel__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.optimization-panel__table-wrap {
  overflow: auto;
  border: 1px solid #1f252c;
  border-radius: 8px;
}

.optimization-panel__table {
  width: 100%;
  border-collapse: collapse;
  min-width: 420px;
}

.optimization-panel__table th,
.optimization-panel__table td {
  padding: 8px 10px;
  border-bottom: 1px solid #181c22;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
}

.optimization-panel__table th {
  position: sticky;
  top: 0;
  background: #0f1217;
  color: #7f8896;
}

.optimization-panel__table tbody tr {
  cursor: pointer;
}

.optimization-panel__table tbody tr:hover,
.optimization-panel__table tbody tr:focus-visible,
.optimization-panel__row--active {
  background: #10141a;
  outline: none;
}

.optimization-panel__detail {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #1f252c;
  border-radius: 8px;
  background: #0f141b;
}

.optimization-panel__detail-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #d7d7d7;
  font-size: 11px;
}

.optimization-panel__detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #9aa3b2;
  font-size: 11px;
}

.optimization-panel__empty {
  color: #737373;
  font-size: 12px;
}

.positive {
  color: #90d89e;
}

.negative {
  color: #ef9e9e;
}
</style>
