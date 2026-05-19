<template>
  <div v-if="rows.length" class="distribution-bars">
    <div v-for="(row, index) in normalizedRows" :key="`${row.lower}-${row.upper}-${index}`" class="distribution-bars__row">
      <div class="distribution-bars__meta">
        <span>{{ shortLabel(row.lower, row.upper) }}</span>
        <strong>{{ row.count }}</strong>
      </div>
      <div class="distribution-bars__track">
        <div class="distribution-bars__bar" :style="{ width: `${barWidth(row.count)}%` }" />
      </div>
    </div>
  </div>
  <div v-else class="distribution-bars__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  rows: Array<{ lower: number; upper: number; count: number }>
  emptyLabel?: string
}>(), {
  emptyLabel: 'No distribution data yet.',
})

const normalizedRows = computed(() =>
  props.rows
    .filter(row => Number.isFinite(row.lower) && Number.isFinite(row.upper) && Number.isFinite(row.count))
    .slice(0, 8),
)

const maxCount = computed(() =>
  Math.max(1, ...normalizedRows.value.map(row => Number(row.count) || 0)),
)

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
</script>

<style scoped>
.distribution-bars {
  display: grid;
  gap: 10px;
}

.distribution-bars__row {
  display: grid;
  gap: 6px;
}

.distribution-bars__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #d7d7d7;
  font-size: 11px;
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
</style>
