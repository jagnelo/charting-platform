<template>
  <section class="watchlist" :class="{ 'watchlist--columns-open': columnMenuOpen, 'watchlist--sets-open': columnSetMenuOpen, 'watchlist--grouped': hasColumnGroups }" :aria-label="label">
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
      <button class="watchlist__columns-button" type="button" aria-label="Column sets" @click="columnSetMenuOpen = !columnSetMenuOpen">Sets</button>
      <b>{{ filteredRows.length }}</b>
    </header>
    <p v-if="conditionFilterState" class="watchlist__condition-state">{{ conditionFilterState }}</p>
    <div v-if="columnMenuOpen" class="watchlist__column-menu">
      <label v-for="column in effectiveColumns" :key="column.key"><input type="checkbox" :checked="activeColumnKeys.includes(column.key)" @change="toggleColumn(column.key)" />{{ column.label }}<button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} left`" :disabled="!canMoveColumn(column.key, -1)" @click="moveColumn(column.key, -1)">←</button><button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} right`" :disabled="!canMoveColumn(column.key, 1)" @click="moveColumn(column.key, 1)">→</button><input class="watchlist__group-input" :aria-label="`${column.label} group`" :value="columnGroups[column.key] ?? ''" placeholder="Group" @change="setColumnGroup(column.key, ($event.target as HTMLInputElement).value)" /><button class="watchlist__stack-button" type="button" :aria-pressed="stackedColumnKeys.includes(column.key)" @click="toggleStackedColumn(column.key)">Stack</button><button v-if="column.kind === 'boolean'" class="watchlist__pin-button" type="button" :aria-pressed="pinnedBooleanKeys.includes(column.key)" @click="togglePinnedBoolean(column.key)">Pin</button></label>
      <div class="watchlist__python"><select v-model="selectedPythonVersion" aria-label="Python column asset"><option value="">Add Python column…</option><option v-for="asset in pythonAssets" :key="asset.versionId" :value="String(asset.versionId)">{{ asset.name }}</option></select><button type="button" :disabled="!selectedPythonVersion" @click="addPythonColumn">Add</button></div>
    </div>
    <div v-if="columnSetMenuOpen" class="watchlist__column-set-menu" aria-label="Saved column sets">
      <input v-model.trim="columnSetName" aria-label="Column set name" placeholder="Column set name" @keydown.enter.prevent="saveColumnSet" />
      <button type="button" :disabled="!columnSetName || columnSetBusy" @click="saveColumnSet">Save set</button>
      <small v-if="columnSetError" class="watchlist__column-set-error">{{ columnSetError }}</small>
      <small v-else-if="columnSetLoading">Loading saved sets…</small>
      <template v-else-if="columnSets.length">
        <span v-for="set in columnSets" :key="set.stable_key"><button type="button" @click="applyColumnSet(set)">{{ set.name }} <small>v{{ set.version }}</small></button><button type="button" :aria-label="`Delete column set ${set.name}`" :disabled="columnSetBusy" @click="deleteColumnSet(set)">×</button></span>
      </template>
      <small v-else>No saved column sets.</small>
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
    <div ref="scrollElement" class="watchlist__scroll" tabindex="0" @keydown="onKeydown" @wheel.ctrl.prevent="onCtrlWheel">
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
interface ColumnSetItem {
  stable_key: string
  name: string
  version: number
  payload: { configuration?: Record<string, unknown> }
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
  pythonColumns?: Array<{ code_version_id: number; name: string }>
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
  pythonColumns: () => [],
})
const emit = defineEmits<{ select: [row: WatchlistRow]; 'update:visibleColumnKeys': [keys: string[]]; 'update:filterText': [value: string]; 'update:conditionScreenerId': [id: number | null]; 'update:conditionFilterMode': [mode: 'active' | 'inactive' | 'off']; 'update:pinnedBooleanKeys': [keys: string[]]; 'update:columnGroups': [groups: Record<string, string>]; 'update:stackedColumnKeys': [keys: string[]]; 'update:pythonColumns': [columns: Array<{ code_version_id: number; name: string }>] }>()
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
const columnSetMenuOpen = ref(false)
const columnSetName = ref('')
const columnSetLoading = ref(false)
const columnSetBusy = ref(false)
const columnSetError = ref('')
const columnSets = ref<ColumnSetItem[]>([])
const selectedPythonVersion = ref('')
const pythonAssets = ref<Array<{ versionId: number; name: string }>>([])
const pythonCells = ref<Record<string, Record<string, { value?: number | boolean; error?: string }>>>({})
const runningPythonColumns = new Set<number>()
const renderEpoch = ref(0)
const pythonColumns = computed(() => props.pythonColumns.filter(column => Number.isInteger(column.code_version_id) && column.code_version_id > 0 && typeof column.name === 'string'))
const effectiveColumns = computed<WatchlistColumn[]>(() => [...props.columns, ...pythonColumns.value.map(column => ({ key: pythonKey(column.code_version_id), label: column.name, width: '78px', format: 'number' as const }))])
const activeColumnKeys = computed(() => props.visibleColumnKeys.length ? props.visibleColumnKeys : effectiveColumns.value.map(column => column.key))
const visibleColumns = computed(() => activeColumnKeys.value
  .map(key => effectiveColumns.value.find(column => column.key === key))
  .filter((column): column is WatchlistColumn => column != null))
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

function pythonKey(versionId: number) { return `python:${versionId}` }
async function loadPythonAssets() {
  try {
    const assets = await api.get<Array<{ kind: string; name: string; versions: Array<{ id: number; version_number: number }> }>>('/code/assets')
    pythonAssets.value = assets.filter(asset => asset.kind === 'column').flatMap(asset => asset.versions.slice(-1).map(version => ({ versionId: version.id, name: `${asset.name} v${version.version_number}` })))
  } catch { pythonAssets.value = [] }
}
function sleep(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)) }
async function runPythonColumn(column: { code_version_id: number; name: string }) {
  if (runningPythonColumns.has(column.code_version_id)) return
  const symbols = [...new Set(props.rows.map(row => row.symbol).filter(Boolean))]
  if (!symbols.length) return
  runningPythonColumns.add(column.code_version_id)
  const key = pythonKey(column.code_version_id)
  pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(symbols.map(symbol => [symbol, { error: 'Queued' }])) }
  try {
    const run = await api.post<{ id: number }>('/research/runs', { code_version_id: column.code_version_id, run_config: { symbols }, dataset_manifest: { source: 'canonical_database' } })
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const result = await api.get<{ status: string; cells: Array<{ symbol: string; status: string; value?: number | boolean; error?: string }> }>(`/research/runs/${run.id}/batch-results`)
      if (result.status === 'completed' || result.status === 'failed' || result.status === 'canceled') {
        pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(result.cells.map(cell => [cell.symbol, cell.status === 'completed' ? { value: cell.value } : { error: cell.error ?? cell.status }])) }
        return
      }
      await sleep(250)
    }
  } catch (cause: any) { pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(symbols.map(symbol => [symbol, { error: cause?.message ?? 'Unavailable' }])) } }
  finally { runningPythonColumns.delete(column.code_version_id) }
}
function addPythonColumn() {
  const versionId = Number(selectedPythonVersion.value)
  const asset = pythonAssets.value.find(item => item.versionId === versionId)
  if (!asset || pythonColumns.value.some(column => column.code_version_id === versionId)) return
  const column = { code_version_id: versionId, name: asset.name }
  emit('update:pythonColumns', [...pythonColumns.value, column])
  selectedPythonVersion.value = ''
  void runPythonColumn(column)
}

function columnSetKey(name: string) {
  const normalized = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'column-set'
  return `${normalized}-${crypto.randomUUID().slice(0, 8)}`
}

function columnSetConfiguration() {
  return {
    column_keys: [...activeColumnKeys.value],
    pinned_boolean_keys: [...props.pinnedBooleanKeys],
    column_groups: { ...props.columnGroups },
    stacked_column_keys: [...props.stackedColumnKeys],
  }
}

async function loadColumnSets() {
  columnSetLoading.value = true
  columnSetError.value = ''
  try { columnSets.value = await api.get<ColumnSetItem[]>('/workspaces/library/items', { kind: 'column_set' }) }
  catch (cause: any) { columnSetError.value = cause?.message ?? 'Unable to load saved column sets' }
  finally { columnSetLoading.value = false }
}

async function saveColumnSet() {
  if (!columnSetName.value) return
  columnSetBusy.value = true
  columnSetError.value = ''
  try {
    const stableKey = columnSetKey(columnSetName.value)
    await api.put(`/workspaces/library/items/column_set/${encodeURIComponent(stableKey)}`, {
      kind: 'column_set', stable_key: stableKey, name: columnSetName.value,
      payload: { configuration: columnSetConfiguration(), schema_version: 1 },
      dependency_metadata: { contract: 'workstation_column_set_v1' },
    })
    columnSetName.value = ''
    await loadColumnSets()
  } catch (cause: any) { columnSetError.value = cause?.message ?? 'Unable to save column set' }
  finally { columnSetBusy.value = false }
}

function applyColumnSet(item: ColumnSetItem) {
  const configuration = item.payload.configuration
  if (!configuration || typeof configuration !== 'object') return
  const allowed = new Set(effectiveColumns.value.map(column => column.key))
  const keys = Array.isArray(configuration.column_keys)
    ? configuration.column_keys.filter((key): key is string => typeof key === 'string' && allowed.has(key))
    : []
  if (keys.length) emit('update:visibleColumnKeys', keys)
  const pinned = Array.isArray(configuration.pinned_boolean_keys)
    ? configuration.pinned_boolean_keys.filter((key): key is string => typeof key === 'string' && allowed.has(key))
    : []
  const stacked = Array.isArray(configuration.stacked_column_keys)
    ? configuration.stacked_column_keys.filter((key): key is string => typeof key === 'string' && allowed.has(key))
    : []
  const groupsRaw = configuration.column_groups
  const groups = groupsRaw && typeof groupsRaw === 'object' && !Array.isArray(groupsRaw)
    ? Object.fromEntries(Object.entries(groupsRaw).filter(([key, value]) => allowed.has(key) && typeof value === 'string'))
    : {}
  emit('update:pinnedBooleanKeys', pinned)
  emit('update:columnGroups', groups)
  emit('update:stackedColumnKeys', stacked)
  columnSetMenuOpen.value = false
}

async function deleteColumnSet(item: ColumnSetItem) {
  columnSetBusy.value = true
  columnSetError.value = ''
  try { await api.delete(`/workspaces/library/items/column_set/${encodeURIComponent(item.stable_key)}`); await loadColumnSets() }
  catch (cause: any) { columnSetError.value = cause?.message ?? 'Unable to delete column set' }
  finally { columnSetBusy.value = false }
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
  void loadColumnSets()
  void loadPythonAssets()
  for (const column of pythonColumns.value) void runPythonColumn(column)
  if (conditionFilter.value) void applyConditionFilter(conditionFilter.value)
})
watch(pythonColumns, columns => {
  for (const column of columns) {
    if (!pythonCells.value[pythonKey(column.code_version_id)]) void runPythonColumn(column)
  }
}, { deep: true })

function display(row: WatchlistRow, key: string) {
  if (key.startsWith('python:')) {
    const cell = pythonCells.value[key]?.[row.symbol]
    return cell?.error ? cell.error : cell?.value == null ? '—' : typeof cell.value === 'boolean' ? cell.value ? 'True' : 'False' : cell.value.toFixed(4)
  }
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  if (value == null || value === '') return '—'
  if (typeof value !== 'number') return String(value)
  const format = effectiveColumns.value.find(column => column.key === key)?.format ?? 'percent'
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
    emit('update:visibleColumnKeys', [...current, key])
  }
}

function canMoveColumn(key: string, direction: -1 | 1) {
  const position = activeColumnKeys.value.indexOf(key)
  return position >= 0 && position + direction >= 0 && position + direction < activeColumnKeys.value.length
}

function moveColumn(key: string, direction: -1 | 1) {
  const current = [...activeColumnKeys.value]
  const position = current.indexOf(key)
  const nextPosition = position + direction
  if (position < 0 || nextPosition < 0 || nextPosition >= current.length) return
  ;[current[position], current[nextPosition]] = [current[nextPosition], current[position]]
  emit('update:visibleColumnKeys', current)
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
  const current = props.stackedColumnKeys.filter(columnKey => effectiveColumns.value.some(column => column.key === columnKey))
  emit('update:stackedColumnKeys', current.includes(key) ? current.filter(columnKey => columnKey !== key) : [...current, key])
}

function onKeydown(event: KeyboardEvent) {
  if (!['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return
  event.preventDefault()
  const current = filteredRows.value.findIndex(row => row.symbol === props.selected)
  if (event.key === 'Enter') {
    if (current >= 0) emit('select', filteredRows.value[current])
    return
  }
  const forward = event.key === 'ArrowDown' || (event.key === ' ' && !event.shiftKey)
  const next = Math.max(0, Math.min(filteredRows.value.length - 1, current + (forward ? 1 : -1)))
  if (filteredRows.value[next]) emit('select', filteredRows.value[next])
}

function onCtrlWheel(event: WheelEvent) {
  const current = filteredRows.value.findIndex(row => row.symbol === props.selected)
  const direction = event.deltaY > 0 ? 1 : -1
  const next = Math.max(0, Math.min(filteredRows.value.length - 1, current + direction))
  if (filteredRows.value[next]) emit('select', filteredRows.value[next])
}
</script>

<style scoped>
.watchlist { display: grid; height: 100%; min-height: 0; grid-template-rows: 23px auto 22px minmax(0, 1fr); color: #c7d0d8; background: #11161b; font: 11px/1.2 "Segoe UI", Arial, sans-serif; }
.watchlist--columns-open { grid-template-rows: 23px auto auto 22px minmax(0, 1fr); }
.watchlist--sets-open { grid-template-rows: 23px auto auto 22px minmax(0, 1fr); }
.watchlist--grouped { grid-template-rows: 23px auto 32px minmax(0, 1fr); }
.watchlist--columns-open.watchlist--grouped,.watchlist--sets-open.watchlist--grouped { grid-template-rows: 23px auto auto 32px minmax(0, 1fr); }
.watchlist__controls { display: flex; align-items: center; gap: 6px; padding: 0 7px; color: #84939e; background: #181f25; border-bottom: 1px solid #2b343c; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.watchlist__controls input { min-width: 0; width: 80px; margin-left: auto; padding: 1px 4px; border: 1px solid #3d4a54; background: #11161b; color: #dce9f2; font: inherit; text-transform: none; }
.watchlist__controls select { min-width: 0; max-width: 120px; padding: 1px 2px; border: 1px solid #3d4a54; background: #11161b; color: #a9c0d0; font: inherit; text-transform: none; }
.watchlist__columns-button { border: 1px solid #3d4a54; background: #1b252d; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__controls b { color: #78aac8; font-weight: 600; }
.watchlist__column-menu { display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 4px 7px; background: #253039; border-bottom: 1px solid #384550; color: #b7c6d0; font-size: 10px; text-transform: none; letter-spacing: normal; }
.watchlist__column-set-menu { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:4px 7px; background:#202b33; border-bottom:1px solid #384550; color:#b7c6d0; font-size:10px; }.watchlist__column-set-menu input,.watchlist__column-set-menu button{min-width:0;border:1px solid #42515c;background:#182128;color:#d7e3eb;font:inherit;padding:1px 4px}.watchlist__column-set-menu input{width:108px}.watchlist__column-set-menu span{display:flex;gap:2px}.watchlist__column-set-menu small{color:#8498a6}.watchlist__column-set-error{color:#e49a9a!important}
.watchlist__condition-state { overflow: hidden; margin: 0; padding: 2px 7px; border-bottom: 1px solid #2b343c; color: #8498a6; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__column-menu label { white-space: nowrap; }
.watchlist__group-input { width: 52px; margin-left: 3px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__order-button { margin-left: 2px; min-width: 15px; border: 1px solid #42515c; background: #182128; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__order-button:disabled { cursor: default; opacity: .45; }
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
