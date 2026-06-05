<template>
  <div v-if="rows.length" class="comparison-panel">
    <div class="comparison-panel__summary">
      <span class="comparison-panel__summary-chip">{{ currentLabel }}</span>
      <span class="comparison-panel__summary-chip">vs {{ compareLabel }}</span>
      <span class="comparison-panel__summary-chip">{{ winCount }} ahead</span>
      <span class="comparison-panel__summary-chip">{{ lossCount }} behind</span>
    </div>

    <div class="comparison-panel__table-wrap">
      <table class="comparison-panel__table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>{{ currentLabel }}</th>
            <th>{{ compareLabel }}</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.label">
            <td>{{ row.label }}</td>
            <td :class="valueClass(row, row.current, 'current')">{{ row.current }}</td>
            <td :class="valueClass(row, row.compare, 'compare')">{{ row.compare }}</td>
            <td :class="deltaClass(row)">{{ row.delta }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div v-else class="comparison-panel__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  currentLabel: string
  compareLabel: string
  rows: Array<{
    label: string
    current: string
    compare: string
    delta: string
    deltaValue: number
    winner: 'current' | 'compare' | 'tie' | null
  }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No comparison selected.',
})

const winCount = computed(() => props.rows.filter(row => row.winner === 'current').length)
const lossCount = computed(() => props.rows.filter(row => row.winner === 'compare').length)

function isPnlLike(row: { label: string }) {
  return /return|p&l|unrealized|realized/i.test(row.label)
}

function signedNumber(value: string) {
  const normalized = String(value ?? '').replace(/[$,%\s]/g, '').replace(/,/g, '')
  const numeric = Number(normalized)
  return Number.isFinite(numeric) ? numeric : null
}

function signClass(value: string) {
  const numeric = signedNumber(value)
  return {
    positive: numeric != null && numeric > 0,
    negative: numeric != null && numeric < 0,
  }
}

function valueClass(
  row: { label: string; winner: 'current' | 'compare' | 'tie' | null },
  value: string,
  side: 'current' | 'compare',
) {
  if (isPnlLike(row)) return signClass(value)
  return {
    positive: row.winner === side,
    negative: row.winner != null && row.winner !== 'tie' && row.winner !== side,
  }
}

function deltaClass(row: { label: string; delta: string; winner: 'current' | 'compare' | 'tie' | null }) {
  if (isPnlLike(row)) return signClass(row.delta)
  return {
    positive: row.winner === 'current',
    negative: row.winner === 'compare',
  }
}
</script>

<style scoped>
.comparison-panel {
  display: grid;
  gap: 12px;
}

.comparison-panel__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.comparison-panel__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.comparison-panel__table-wrap {
  overflow: auto;
  border: 1px solid #1f252c;
  border-radius: 8px;
}

.comparison-panel__table {
  width: 100%;
  border-collapse: collapse;
  min-width: 420px;
}

.comparison-panel__table th,
.comparison-panel__table td {
  padding: 8px 10px;
  border-bottom: 1px solid #181c22;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
}

.comparison-panel__table th {
  position: sticky;
  top: 0;
  background: #0f1217;
  color: #7f8896;
}

.comparison-panel__empty {
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
