<template>
  <div v-if="matrixRows.length" class="returns-heatmap">
    <div class="returns-heatmap__legend">
      <span>Loss</span>
      <div class="returns-heatmap__legend-bar" aria-hidden="true" />
      <span>Gain</span>
    </div>

    <div
      class="returns-heatmap__grid"
      :style="{ gridTemplateColumns: `56px repeat(${columns.length}, minmax(0, 1fr))` }"
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
          :title="cellTitle(cell)"
        >
          <span>{{ cell.value == null ? '—' : shortPercent(cell.value) }}</span>
        </button>
      </template>
    </div>
  </div>

  <div v-else class="returns-heatmap__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface ReturnRow {
  period: string
  return_pct: number | null
}

interface HeatmapCell {
  key: string
  period: string
  value: number | null
}

const props = withDefaults(defineProps<{
  rows: ReturnRow[]
  mode: 'monthly' | 'quarterly'
  emptyLabel?: string
}>(), {
  emptyLabel: 'No return breakdown yet.',
})

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
    : [
        { key: 'Q1', label: 'Q1' },
        { key: 'Q2', label: 'Q2' },
        { key: 'Q3', label: 'Q3' },
        { key: 'Q4', label: 'Q4' },
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
      const period = props.mode === 'monthly' ? `${year}-${column.key}` : `${year}-${column.key}`
      return {
        key: period,
        period,
        value: cellMap.value.has(period) ? cellMap.value.get(period) ?? null : null,
      } satisfies HeatmapCell
    }),
  }))
})

const maxAbsReturn = computed(() => {
  const values = props.rows
    .map(row => Number(row.return_pct))
    .filter(value => Number.isFinite(value))
    .map(value => Math.abs(value))
  return values.length ? Math.max(...values, 1) : 1
})

function shortPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

function cellTitle(cell: HeatmapCell) {
  return cell.value == null
    ? `${cell.period}: no data`
    : `${cell.period}: ${valuePercent(cell.value)}`
}

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

  const intensity = Math.max(0.18, Math.min(1, Math.abs(value) / maxAbsReturn.value))
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
</script>

<style scoped>
.returns-heatmap {
  display: grid;
  gap: 10px;
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
  text-align: center;
}

.returns-heatmap__row-label {
  padding-right: 6px;
}

.returns-heatmap__cell {
  min-height: 32px;
  padding: 4px 6px;
  border-radius: 8px;
  border: 1px solid var(--cell-border);
  background: var(--cell-bg);
  color: var(--cell-color);
  font: inherit;
  cursor: default;
}

.returns-heatmap__cell span {
  display: block;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
}

.returns-heatmap__cell--empty span {
  font-weight: 500;
}

.returns-heatmap__empty {
  color: #7d8490;
  font-size: 12px;
}
</style>
