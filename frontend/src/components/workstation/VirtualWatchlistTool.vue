<template>
  <section class="watchlist" :aria-label="label">
    <header class="watchlist__controls">
      <span>{{ label }}</span>
      <input v-model="filter" :aria-label="`${label} filter`" placeholder="Filter" />
      <b>{{ filteredRows.length }}</b>
    </header>
    <div class="watchlist__header" :style="gridStyle">
      <button v-for="column in visibleColumns" :key="column.key" type="button" @click="toggleSort(column.key)">
        {{ column.label }}<small v-if="sortKey === column.key">{{ sortDirection === 'asc' ? ' ▲' : ' ▼' }}</small>
      </button>
    </div>
    <div ref="scrollElement" class="watchlist__scroll" tabindex="0" @keydown="onKeydown">
      <div :data-render-epoch="renderEpoch" :style="{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }">
        <button
          v-for="virtualRow in virtualItems"
          :key="filteredRows[virtualRow.index].instrumentId ?? filteredRows[virtualRow.index].symbol"
          type="button"
          class="watchlist__row"
          :class="{ 'watchlist__row--active': filteredRows[virtualRow.index].symbol === selected }"
          :style="{ ...gridStyle, height: `${virtualRow.size}px`, transform: `translateY(${virtualRow.start}px)` }"
          @click="emit('select', filteredRows[virtualRow.index])"
        >
          <span v-for="column in visibleColumns" :key="column.key" :title="display(filteredRows[virtualRow.index], column.key)">
            {{ display(filteredRows[virtualRow.index], column.key) }}
          </span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useVirtualizer } from '@tanstack/vue-virtual'
import { computed, ref, watch } from 'vue'

export interface WatchlistRow {
  instrumentId: number | null
  symbol: string
  name: string
  values?: Record<string, string | number | null>
}

export interface WatchlistColumn {
  key: string
  label: string
  width?: string
}

const props = withDefaults(defineProps<{
  label: string
  rows: WatchlistRow[]
  selected?: string
  columns?: WatchlistColumn[]
}>(), {
  selected: '',
  columns: () => [
    { key: 'symbol', label: 'Symbol', width: '72px' },
    { key: 'name', label: 'Name', width: 'minmax(130px, 1fr)' },
  ],
})
const emit = defineEmits<{ select: [row: WatchlistRow] }>()
const scrollElement = ref<HTMLElement | null>(null)
const filter = ref('')
const sortKey = ref('symbol')
const sortDirection = ref<'asc' | 'desc'>('asc')
const renderEpoch = ref(0)
const visibleColumns = computed(() => props.columns)
const gridStyle = computed(() => ({ gridTemplateColumns: visibleColumns.value.map(column => column.width ?? 'minmax(72px, 1fr)').join(' ') }))
const filteredRows = computed(() => {
  const needle = filter.value.trim().toLowerCase()
  const rows = needle
    ? props.rows.filter(row => `${row.symbol} ${row.name}`.toLowerCase().includes(needle))
    : [...props.rows]
  return rows.sort((left, right) => {
    const leftValue = display(left, sortKey.value)
    const rightValue = display(right, sortKey.value)
    const comparison = leftValue.localeCompare(rightValue, undefined, { numeric: true })
    return sortDirection.value === 'asc' ? comparison : -comparison
  })
})
const virtualizer = useVirtualizer(computed(() => ({
  count: filteredRows.value.length,
  getScrollElement: () => scrollElement.value,
  estimateSize: () => 28,
  initialRect: { width: 480, height: 360 },
  overscan: 12,
})))
const virtualItems = computed(() => {
  const items = virtualizer.value.getVirtualItems()
  if (items.length || !filteredRows.value.length) return items
  // A detached/hidden dock tab has no measurable rectangle. Render one row until
  // Golden Layout makes it measurable; never expand a hidden 10,000-row list.
  return [{ index: 0, key: 'unmeasured-first-row', size: 28, start: 0 }]
})
watch(filteredRows, () => {
  renderEpoch.value += 1
  virtualizer.value.measure()
})

function display(row: WatchlistRow, key: string) {
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  if (value == null || value === '') return '—'
  return typeof value === 'number' ? `${(value * 100).toFixed(2)}%` : String(value)
}

function toggleSort(key: string) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return
  event.preventDefault()
  const current = filteredRows.value.findIndex(row => row.symbol === props.selected)
  if (event.key === 'Enter' || event.key === ' ') {
    if (current >= 0) emit('select', filteredRows.value[current])
    return
  }
  const next = Math.max(0, Math.min(filteredRows.value.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)))
  if (filteredRows.value[next]) emit('select', filteredRows.value[next])
}
</script>

<style scoped>
.watchlist { display: grid; height: 100%; min-height: 0; grid-template-rows: 23px 22px minmax(0, 1fr); color: #c7d0d8; background: #11161b; font: 11px/1.2 "Segoe UI", Arial, sans-serif; }
.watchlist__controls { display: flex; align-items: center; gap: 6px; padding: 0 7px; color: #84939e; background: #181f25; border-bottom: 1px solid #2b343c; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.watchlist__controls input { min-width: 0; width: 80px; margin-left: auto; padding: 1px 4px; border: 1px solid #3d4a54; background: #11161b; color: #dce9f2; font: inherit; text-transform: none; }
.watchlist__controls b { color: #78aac8; font-weight: 600; }
.watchlist__header, .watchlist__row { display: grid; min-width: 0; }
.watchlist__header { background: #20282f; border-bottom: 1px solid #313c45; }
.watchlist__header button { min-width: 0; border: 0; border-right: 1px solid #303a43; background: transparent; color: #97a9b6; overflow: hidden; padding: 4px 6px; text-align: left; text-overflow: ellipsis; white-space: nowrap; font: 600 9px "Segoe UI", Arial, sans-serif; text-transform: uppercase; cursor: pointer; }
.watchlist__header button:hover { color: #e5f1f7; background: #29343d; }
.watchlist__header small { color: #78b9e4; }
.watchlist__scroll { min-height: 0; overflow: auto; outline: none; }
.watchlist__row { position: absolute; left: 0; width: 100%; align-items: center; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.watchlist__row:hover { background: #202a33; }
.watchlist__row--active { background: #1d4057; box-shadow: inset 2px 0 #66b4e8; }
.watchlist__row span { min-width: 0; overflow: hidden; padding: 0 6px; color: #8999a5; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__row span:first-child { color: #dce9f2; font-weight: 600; }
</style>
