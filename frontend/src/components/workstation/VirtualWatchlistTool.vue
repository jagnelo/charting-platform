<template>
  <section class="watchlist" :class="{ 'watchlist--columns-open': columnMenuOpen, 'watchlist--grouped': hasColumnGroups }" :aria-label="label">
    <header class="watchlist__controls">
      <span>{{ label }}</span>
      <input v-model="filter" :aria-label="`${label} filter`" placeholder="Filter" />
      <select v-model="conditionFilter" :aria-label="`${label} saved condition filter`" :title="conditionFilterState">
        <option value="">Filter: Off</option>
        <option v-for="screener in screeners" :key="screener.id" :value="String(screener.id)">Filter: {{ screener.name }}</option>
      </select>
      <select v-if="conditionFilter" v-model="conditionFilterMode" :aria-label="`${label} saved condition filter mode`">
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
        <option value="off">Off</option>
      </select>
      <button class="watchlist__columns-button" type="button" @click="columnMenuOpen = !columnMenuOpen">Columns</button>
      <b>{{ filteredRows.length }}</b>
    </header>
    <p v-if="conditionFilterState" class="watchlist__condition-state">{{ conditionFilterState }}</p>
    <div v-if="columnMenuOpen" class="watchlist__column-menu">
      <label v-for="column in columns" :key="column.key"><input type="checkbox" :checked="activeColumnKeys.includes(column.key)" @change="toggleColumn(column.key)" />{{ column.label }}<input class="watchlist__group-input" :aria-label="`${column.label} group`" :value="columnGroups[column.key] ?? ''" placeholder="Group" @change="setColumnGroup(column.key, ($event.target as HTMLInputElement).value)" /><button class="watchlist__stack-button" type="button" :aria-pressed="stackedColumnKeys.includes(column.key)" @click="toggleStackedColumn(column.key)">Stack</button><button v-if="column.kind === 'boolean'" type="button" :aria-pressed="pinnedBooleanKeys.includes(column.key)" @click="togglePinnedBoolean(column.key)">Pin</button></label>
    </div>
    <div class="watchlist__header" :style="gridStyle">
      <template v-for="column in renderedColumns" :key="column.key">
      <div v-if="column.key === stackedColumnKey" class="watchlist__stack-header">
        <button v-for="stackedColumn in stackedColumns" :key="stackedColumn.key" type="button" @click="toggleSort(stackedColumn.key)"><em v-if="columnGroups[stackedColumn.key]">{{ columnGroups[stackedColumn.key] }}</em>{{ stackedColumn.label }}<small v-if="sortKey === stackedColumn.key">{{ sortDirection === 'asc' ? ' ▲' : ' ▼' }}</small></button>
      </div>
      <button v-else type="button" @click="toggleSort(column.key)">
        <em v-if="columnGroups[column.key]">{{ columnGroups[column.key] }}</em>{{ column.label }}<small v-if="sortKey === column.key">{{ sortDirection === 'asc' ? ' ▲' : ' ▼' }}</small>
      </button>
      </template>
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
          <template v-for="column in renderedColumns" :key="column.key">
            <span v-if="column.key !== stackedColumnKey" :title="display(filteredRows[virtualRow.index], column.key)">{{ display(filteredRows[virtualRow.index], column.key) }}</span>
            <span v-else class="watchlist__stack-cell"><small v-for="stackedColumn in stackedColumns" :key="stackedColumn.key" :title="display(filteredRows[virtualRow.index], stackedColumn.key)"><em>{{ stackedColumn.label }}</em>{{ display(filteredRows[virtualRow.index], stackedColumn.key) }}</small></span>
          </template>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useVirtualizer } from '@tanstack/vue-virtual'
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

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
  format?: 'percent' | 'number'
  kind?: 'boolean'
}

interface SavedScreener {
  id: number
  name: string
}

interface ScreenerResult {
  matched_ids: number[]
  run_at: string
}

const props = withDefaults(defineProps<{
  label: string
  rows: WatchlistRow[]
  selected?: string
  columns?: WatchlistColumn[]
  visibleColumnKeys?: string[]
  filterText?: string
  conditionScreenerId?: number | null
  conditionFilterMode?: 'active' | 'inactive' | 'off'
  pinnedBooleanKeys?: string[]
  columnGroups?: Record<string, string>
  stackedColumnKeys?: string[]
}>(), {
  selected: '',
  columns: () => [
    { key: 'symbol', label: 'Symbol', width: '72px' },
    { key: 'name', label: 'Name', width: 'minmax(130px, 1fr)' },
  ],
  visibleColumnKeys: () => [],
  filterText: '',
  conditionScreenerId: null,
  conditionFilterMode: 'off',
  pinnedBooleanKeys: () => [],
  columnGroups: () => ({}),
  stackedColumnKeys: () => [],
})
const emit = defineEmits<{ select: [row: WatchlistRow]; 'update:visibleColumnKeys': [keys: string[]]; 'update:filterText': [value: string]; 'update:conditionScreenerId': [id: number | null]; 'update:conditionFilterMode': [mode: 'active' | 'inactive' | 'off']; 'update:pinnedBooleanKeys': [keys: string[]]; 'update:columnGroups': [groups: Record<string, string>]; 'update:stackedColumnKeys': [keys: string[]] }>()
const scrollElement = ref<HTMLElement | null>(null)
const filter = ref(props.filterText)
const conditionFilter = ref(props.conditionScreenerId == null ? '' : String(props.conditionScreenerId))
const conditionFilterMode = ref(props.conditionFilterMode)
const screeners = ref<SavedScreener[]>([])
const conditionMatchedIds = ref<Set<number> | null>(null)
const conditionFilterState = ref('')
const sortKey = ref('symbol')
const sortDirection = ref<'asc' | 'desc'>('asc')
const columnMenuOpen = ref(false)
const renderEpoch = ref(0)
const activeColumnKeys = computed(() => props.visibleColumnKeys.length ? props.visibleColumnKeys : props.columns.map(column => column.key))
const visibleColumns = computed(() => props.columns.filter(column => activeColumnKeys.value.includes(column.key)))
const hasColumnGroups = computed(() => visibleColumns.value.some(column => Boolean(props.columnGroups[column.key])))
const stackedColumnKey = '__stacked_columns__'
const stackedColumns = computed(() => visibleColumns.value.filter(column => props.stackedColumnKeys.includes(column.key)))
const renderedColumns = computed(() => [
  ...visibleColumns.value.filter(column => !props.stackedColumnKeys.includes(column.key)),
  ...(stackedColumns.value.length ? [{ key: stackedColumnKey, label: 'Stacked', width: 'minmax(120px, 1fr)' }] : []),
])
const gridStyle = computed(() => ({ gridTemplateColumns: renderedColumns.value.map(column => column.width ?? 'minmax(72px, 1fr)').join(' ') }))
const filteredRows = computed(() => {
  const needle = filter.value.trim().toLowerCase()
  const textRows = needle
    ? props.rows.filter(row => `${row.symbol} ${row.name}`.toLowerCase().includes(needle))
    : [...props.rows]
  const rows = conditionMatchedIds.value === null
    ? textRows
    : textRows.filter(row => row.instrumentId != null && conditionMatchedIds.value?.has(row.instrumentId))
  return rows.sort((left, right) => {
    for (const key of props.pinnedBooleanKeys) {
      const leftPinned = Boolean(left.values?.[key])
      const rightPinned = Boolean(right.values?.[key])
      if (leftPinned !== rightPinned) return leftPinned ? -1 : 1
    }
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
watch(filter, value => emit('update:filterText', value))
watch(() => props.filterText, value => { if (value !== filter.value) filter.value = value })
watch(() => props.conditionScreenerId, value => {
  const normalized = value == null ? '' : String(value)
  if (normalized !== conditionFilter.value) conditionFilter.value = normalized
})
watch(() => props.conditionFilterMode, value => { if (value !== conditionFilterMode.value) conditionFilterMode.value = value })
watch(conditionFilter, value => { void applyConditionFilter(value) })
watch(conditionFilterMode, mode => {
  emit('update:conditionFilterMode', mode)
  if (mode === 'active') void applyConditionFilter(conditionFilter.value)
  else if (mode === 'off') {
    conditionFilter.value = ''
    conditionMatchedIds.value = null
    conditionFilterState.value = ''
  } else {
    conditionMatchedIds.value = null
    conditionFilterState.value = 'Saved condition inactive; its last result is retained but does not filter rows.'
  }
})

async function loadScreeners() {
  try {
    screeners.value = await api.get<SavedScreener[]>('/screeners')
  } catch {
    conditionFilterState.value = 'Saved condition filters are unavailable.'
  }
}

async function applyConditionFilter(value: string) {
  const screenerId = Number(value)
  conditionMatchedIds.value = null
  conditionFilterState.value = ''
  if (!Number.isInteger(screenerId) || screenerId <= 0) {
    emit('update:conditionScreenerId', null)
    return
  }
  if (conditionFilterMode.value === 'off') conditionFilterMode.value = 'active'
  emit('update:conditionScreenerId', screenerId)
  if (conditionFilterMode.value === 'inactive') {
    conditionFilterState.value = 'Saved condition inactive; it does not filter rows.'
    return
  }
  conditionFilterState.value = 'Loading saved condition result…'
  try {
    const results = await api.get<ScreenerResult[]>(`/screeners/${screenerId}/results`, { limit: 1 })
    const result = results[0]
    if (!result) {
      conditionMatchedIds.value = new Set()
      conditionFilterState.value = 'Saved condition is active but has not been run yet.'
      return
    }
    conditionMatchedIds.value = new Set(result.matched_ids)
    conditionFilterState.value = `Saved condition active · latest result ${new Date(result.run_at).toLocaleString()}`
  } catch {
    conditionMatchedIds.value = new Set()
    conditionFilterState.value = 'Saved condition result is unavailable; no rows are shown.'
  }
}

onMounted(() => {
  void loadScreeners()
  if (conditionFilter.value) void applyConditionFilter(conditionFilter.value)
})

function display(row: WatchlistRow, key: string) {
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  if (value == null || value === '') return '—'
  if (typeof value !== 'number') return String(value)
  const format = props.columns.find(column => column.key === key)?.format ?? 'percent'
  return format === 'number' ? value.toFixed(2) : `${(value * 100).toFixed(2)}%`
}

function toggleSort(key: string) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
}

function toggleColumn(key: string) {
  const current = activeColumnKeys.value
  if (current.includes(key)) {
    if (current.length === 1) return
    emit('update:visibleColumnKeys', current.filter(item => item !== key))
  } else {
    emit('update:visibleColumnKeys', props.columns.filter(column => current.includes(column.key) || column.key === key).map(column => column.key))
  }
}

function togglePinnedBoolean(key: string) {
  const current = props.pinnedBooleanKeys
  emit('update:pinnedBooleanKeys', current.includes(key) ? current.filter(item => item !== key) : [...current, key])
}

function setColumnGroup(key: string, value: string) {
  const group = value.trim()
  const groups = { ...props.columnGroups }
  if (group) groups[key] = group
  else delete groups[key]
  emit('update:columnGroups', groups)
}

function toggleStackedColumn(key: string) {
  const current = props.stackedColumnKeys.filter(columnKey => props.columns.some(column => column.key === columnKey))
  emit('update:stackedColumnKeys', current.includes(key) ? current.filter(columnKey => columnKey !== key) : [...current, key])
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
.watchlist { display: grid; height: 100%; min-height: 0; grid-template-rows: 23px auto 22px minmax(0, 1fr); color: #c7d0d8; background: #11161b; font: 11px/1.2 "Segoe UI", Arial, sans-serif; }
.watchlist--columns-open { grid-template-rows: 23px auto auto 22px minmax(0, 1fr); }
.watchlist--grouped { grid-template-rows: 23px auto 32px minmax(0, 1fr); }
.watchlist--columns-open.watchlist--grouped { grid-template-rows: 23px auto auto 32px minmax(0, 1fr); }
.watchlist__controls { display: flex; align-items: center; gap: 6px; padding: 0 7px; color: #84939e; background: #181f25; border-bottom: 1px solid #2b343c; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.watchlist__controls input { min-width: 0; width: 80px; margin-left: auto; padding: 1px 4px; border: 1px solid #3d4a54; background: #11161b; color: #dce9f2; font: inherit; text-transform: none; }
.watchlist__controls select { min-width: 0; max-width: 120px; padding: 1px 2px; border: 1px solid #3d4a54; background: #11161b; color: #a9c0d0; font: inherit; text-transform: none; }
.watchlist__columns-button { border: 1px solid #3d4a54; background: #1b252d; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__controls b { color: #78aac8; font-weight: 600; }
.watchlist__column-menu { display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 4px 7px; background: #253039; border-bottom: 1px solid #384550; color: #b7c6d0; font-size: 10px; text-transform: none; letter-spacing: normal; }
.watchlist__condition-state { overflow: hidden; margin: 0; padding: 2px 7px; border-bottom: 1px solid #2b343c; color: #8498a6; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__column-menu label { white-space: nowrap; }
.watchlist__group-input { width: 52px; margin-left: 3px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__stack-button { margin-left: 3px; border: 1px solid #42515c; background: #182128; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__stack-button[aria-pressed="true"] { border-color: #5faed7; background: #1d4057; color: #e3f2fb; }
.watchlist__header, .watchlist__row { display: grid; min-width: 0; }
.watchlist__header { background: #20282f; border-bottom: 1px solid #313c45; }
.watchlist__header button { min-width: 0; border: 0; border-right: 1px solid #303a43; background: transparent; color: #97a9b6; overflow: hidden; padding: 4px 6px; text-align: left; text-overflow: ellipsis; white-space: nowrap; font: 600 9px "Segoe UI", Arial, sans-serif; text-transform: uppercase; cursor: pointer; }
.watchlist__header button:hover { color: #e5f1f7; background: #29343d; }
.watchlist__stack-header { display: grid; min-width: 0; grid-auto-rows: 1fr; border-right: 1px solid #303a43; }
.watchlist__stack-header button { border-right: 0; }
.watchlist__header small { color: #78b9e4; }
.watchlist__header em { display: block; overflow: hidden; color: #718c9f; font: 8px "Segoe UI", Arial, sans-serif; font-style: normal; text-transform: none; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__scroll { min-height: 0; overflow: auto; outline: none; }
.watchlist__row { position: absolute; left: 0; width: 100%; align-items: center; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.watchlist__row:hover { background: #202a33; }
.watchlist__row--active { background: #1d4057; box-shadow: inset 2px 0 #66b4e8; }
.watchlist__row span { min-width: 0; overflow: hidden; padding: 0 6px; color: #8999a5; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__row span:first-child { color: #dce9f2; font-weight: 600; }
.watchlist__stack-cell { display: grid; min-width: 0; align-self: stretch; padding: 1px 6px; }
.watchlist__stack-cell small { overflow: hidden; color: #8999a5; font: 9px/1.15 "Segoe UI", Arial, sans-serif; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__stack-cell em { display: inline-block; min-width: 27px; margin-right: 4px; color: #718c9f; font-style: normal; }
</style>
