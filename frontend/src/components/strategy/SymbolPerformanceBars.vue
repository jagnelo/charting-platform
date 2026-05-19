<template>
  <div v-if="rows.length" class="symbol-bars">
    <div v-for="row in sortedRows" :key="row.symbol" class="symbol-bars__row">
      <div class="symbol-bars__meta">
        <span class="symbol-bars__label">{{ row.symbol }}</span>
        <strong :class="{ positive: row.net_pnl > 0, negative: row.net_pnl < 0 }">
          {{ formatMoney(row.net_pnl) }}
        </strong>
      </div>
      <div class="symbol-bars__track">
        <div
          class="symbol-bars__bar"
          :class="row.net_pnl >= 0 ? 'symbol-bars__bar--positive' : 'symbol-bars__bar--negative'"
          :style="barStyle(row.net_pnl)"
        />
      </div>
    </div>
  </div>
  <div v-else class="symbol-bars__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  rows: Array<{ symbol: string; net_pnl: number }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No per-symbol attribution yet.',
})

const sortedRows = computed(() =>
  [...props.rows]
    .filter(row => row?.symbol)
    .sort((left, right) => Math.abs(Number(right.net_pnl) || 0) - Math.abs(Number(left.net_pnl) || 0))
    .slice(0, 8),
)

const maxAbsValue = computed(() =>
  Math.max(1, ...sortedRows.value.map(row => Math.abs(Number(row.net_pnl) || 0))),
)

function formatMoney(value: number) {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })
}

function barStyle(value: number) {
  const ratio = Math.max(0.08, Math.min(1, Math.abs(value) / maxAbsValue.value))
  return { width: `${ratio * 100}%` }
}
</script>

<style scoped>
.symbol-bars {
  display: grid;
  gap: 10px;
}

.symbol-bars__row {
  display: grid;
  gap: 6px;
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

.symbol-bars__empty {
  color: #7d8490;
  font-size: 12px;
}
</style>
