<template>
  <section class="watchlist" :class="{ 'watchlist--columns-open': columnMenuOpen, 'watchlist--sets-open': columnSetMenuOpen, 'watchlist--grouped': hasColumnGroups, 'watchlist--plot-drop-active': plotDropActive }" :aria-label="label" @click="contextMenu = null" @keydown.esc="contextMenu = null" @dragover.prevent="dragOverPlot" @dragleave="dragLeavePlot" @drop.prevent="dropPlot">
    <p v-if="plotDropActive" class="watchlist__plot-drop-hint" role="status">Drop to add the chart plot as a numeric column</p>
    <p v-if="dropError" class="watchlist__drop-error" role="alert">{{ dropError }}</p>
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
      <select v-if="pythonConditionAssets.length" v-model="selectedPythonConditionVersion" :aria-label="`${label} Python condition filter`" :title="pythonConditionState">
        <option value="">Python filter: Off</option>
        <option v-for="asset in pythonConditionAssets" :key="asset.versionId" :value="String(asset.versionId)">Python filter: {{ asset.name }}</option>
      </select>
      <select v-if="pythonCondition" v-model="pythonConditionMode" :aria-label="`${label} Python condition filter mode`">
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
        <option value="off">Off</option>
      </select>
      <select v-if="pythonCondition" :value="pythonCondition.timeframe ?? timeframe" :aria-label="`${label} Python condition timeframe`" @change="setPythonConditionTimeframe(($event.target as HTMLSelectElement).value)">
        <option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <button class="watchlist__columns-button" type="button" @click="columnMenuOpen = !columnMenuOpen">Columns</button>
      <button class="watchlist__columns-button" type="button" aria-label="Column sets" @click="columnSetMenuOpen = !columnSetMenuOpen">Sets</button>
      <b>{{ selectedSymbols.length ? `${selectedSymbols.length} selected · ` : '' }}{{ filteredRows.length }}</b>
      <button v-if="selectedSymbols.length > 1" type="button" class="watchlist__compare-button" @click="emit('compare', selectedSymbols)">Compare</button>
    </header>
    <p v-if="conditionFilterState" class="watchlist__condition-state">{{ conditionFilterState }}</p>
    <p v-if="pythonConditionState" class="watchlist__condition-state">{{ pythonConditionState }}<button v-if="pythonRunIds.python_condition" type="button" aria-label="Cancel Python condition" @click="cancelPythonRun('python_condition')">Cancel</button><button v-if="pythonCondition?.mode === 'active' && !pythonAlertBusy" type="button" aria-label="Create alert from Python condition" @click="createPythonConditionAlert">Alert</button><small v-if="pythonAlertState">{{ pythonAlertState }}</small></p>
    <div v-if="columnMenuOpen" class="watchlist__column-menu">
      <div class="watchlist__column-clipboard"><button type="button" @click="pasteColumn">Paste column settings</button><small v-if="columnClipboardState">{{ columnClipboardState }}</small></div>
      <label v-for="column in effectiveColumns" :key="column.key" class="watchlist__column-editor-row" :class="{ 'watchlist__column-editor-row--dragging': draggedColumnKey === column.key }" draggable="true" @dragstart="dragColumn(column.key)" @dragover.prevent @drop.prevent="dropColumn(column.key)" @dragend="draggedColumnKey = null"><input type="checkbox" :checked="activeColumnKeys.includes(column.key)" @change="toggleColumn(column.key)" /><input class="watchlist__label-input" :aria-label="`${column.label} label`" :value="column.label" @change="setColumnOverride(column.key, { label: ($event.target as HTMLInputElement).value })" /><input class="watchlist__width-input" :aria-label="`${column.label} width`" :value="column.width ?? ''" placeholder="px/fr" @change="setColumnOverride(column.key, { width: ($event.target as HTMLInputElement).value })" /><select v-if="column.kind !== 'boolean'" class="watchlist__format-input" :aria-label="`${column.label} format`" :value="column.format ?? 'percent'" @change="setColumnOverride(column.key, { format: ($event.target as HTMLSelectElement).value as 'percent' | 'number' })"><option value="percent">%</option><option value="number">#</option></select><input v-if="column.kind !== 'boolean'" class="watchlist__decimals-input" type="number" min="0" max="6" :aria-label="`${column.label} decimals`" :value="column.decimals ?? ''" placeholder="dp" @change="setColumnOverride(column.key, { decimals: Number(($event.target as HTMLInputElement).value) })" /><button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} left`" :disabled="!canMoveColumn(column.key, -1)" @click="moveColumn(column.key, -1)">←</button><button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} right`" :disabled="!canMoveColumn(column.key, 1)" @click="moveColumn(column.key, 1)">→</button><input class="watchlist__group-input" :aria-label="`${column.label} group`" :value="columnGroups[column.key] ?? ''" placeholder="Group" @change="setColumnGroup(column.key, ($event.target as HTMLInputElement).value)" /><button class="watchlist__stack-button" type="button" :aria-pressed="stackedColumnKeys.includes(column.key)" @click="toggleStackedColumn(column.key)">Stack</button><button v-if="column.kind === 'boolean'" class="watchlist__pin-button" type="button" :aria-pressed="pinnedBooleanKeys.includes(column.key)" @click="togglePinnedBoolean(column.key)">Pin</button><button class="watchlist__copy-button" type="button" :aria-label="`Copy ${column.label} settings`" @click="copyColumn(column)">Copy</button></label>
      <div class="watchlist__python"><select v-model="selectedPythonVersion" aria-label="Python column asset"><option value="">Add Python column…</option><option v-for="asset in pythonAssets" :key="asset.versionId" :value="String(asset.versionId)">{{ asset.name }}</option></select><button type="button" :disabled="!selectedPythonVersion" @click="addPythonColumn">Add</button><label v-for="column in pythonColumns" :key="`timeframe-${column.code_version_id}`">{{ column.name }} <select :aria-label="`${column.name} timeframe`" :value="column.timeframe ?? timeframe" @change="setPythonColumnTimeframe(column.code_version_id, ($event.target as HTMLSelectElement).value)"><option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><template v-for="column in pythonColumns" :key="`progress-${column.code_version_id}`"><small v-if="pythonProgress[pythonKey(column.code_version_id)]">{{ column.name }} · {{ pythonProgress[pythonKey(column.code_version_id)] }}<button v-if="pythonRunIds[pythonKey(column.code_version_id)]" type="button" :aria-label="`Cancel ${column.name}`" @click="cancelPythonRun(pythonKey(column.code_version_id))">Cancel</button></small></template></div>
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
    <div ref="scrollElement" class="watchlist__scroll" tabindex="0" @keydown.stop="onKeydown" @wheel.ctrl.prevent="onCtrlWheel">
      <div :data-render-epoch="renderEpoch" :style="{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }">
        <button
          v-for="virtualRow in virtualItems"
          :key="filteredRows[virtualRow.index].instrumentId ?? filteredRows[virtualRow.index].symbol"
          type="button"
          class="watchlist__row"
          :class="{ 'watchlist__row--active': filteredRows[virtualRow.index].symbol === selected, 'watchlist__row--selected': selectedSymbols.includes(filteredRows[virtualRow.index].symbol) }"
          :draggable="reorderable && filteredRows[virtualRow.index].itemId != null"
          :style="{ ...gridStyle, height: `${virtualRow.size}px`, transform: `translateY(${virtualRow.start}px)` }"
          @click="selectRow(filteredRows[virtualRow.index], $event)"
          @dragstart="dragStart(filteredRows[virtualRow.index])"
          @dragover.prevent
          @drop.prevent.stop="dropRow(filteredRows[virtualRow.index])"
          @contextmenu.prevent.stop="openContextMenu($event, filteredRows[virtualRow.index])"
        >
          <template v-for="column in renderedColumns" :key="column.key">
            <span v-if="column.key !== stackedColumnKey" :class="numericCellClass(filteredRows[virtualRow.index], column.key)" :title="display(filteredRows[virtualRow.index], column.key)"><b v-if="column.key === 'symbol' && filteredRows[virtualRow.index].flagged" class="watchlist__flag" aria-label="Flagged">⚑</b>{{ display(filteredRows[virtualRow.index], column.key) }}</span>
            <span v-else class="watchlist__stack-cell"><small v-for="stackedColumn in stackedColumns" :key="stackedColumn.key" :class="numericCellClass(filteredRows[virtualRow.index], stackedColumn.key)" :title="display(filteredRows[virtualRow.index], stackedColumn.key)"><em>{{ stackedColumn.label }}</em>{{ display(filteredRows[virtualRow.index], stackedColumn.key) }}</small></span>
          </template>
        </button>
      </div>
    </div>
    <div v-if="contextMenu" class="watchlist__context-menu" role="menu" :style="{ left: `${contextMenu.left}px`, top: `${contextMenu.top}px` }" @click.stop>
      <strong>{{ contextMenu.row.symbol }}</strong>
      <button type="button" role="menuitem" @click="runContextAction('chart')">Open chart</button>
      <button type="button" role="menuitem" @click="runContextAction('compare')">Compare with active</button>
      <button type="button" role="menuitem" @click="runContextAction('note')">Open note</button>
      <button type="button" role="menuitem" @click="runContextAction('alert')">Open alerts</button>
      <button type="button" role="menuitem" @click="runContextAction('copy')">Copy symbol</button>
      <button v-if="contextMenu.row.itemId != null" type="button" role="menuitem" @click="runContextAction('flag')">{{ contextMenu.row.flagged ? 'Unflag' : 'Flag' }}</button>
      <button v-if="relatedLists.length" type="button" role="menuitem" @click="membershipInspectionOpen = !membershipInspectionOpen">{{ membershipInspectionOpen ? 'Hide list membership' : 'Show list membership' }}</button>
      <div v-if="membershipInspectionOpen" class="watchlist__membership-inspection" aria-label="List membership">
        <small v-for="target in relatedLists" :key="target.id">{{ target.name }}{{ target.id === sourceWatchlistId ? ' · current' : '' }}</small>
      </div>
      <template v-if="membershipTargets.length">
        <select v-model="membershipTargetId" class="watchlist__membership-target" aria-label="Target watchlist">
          <option value="">List actions…</option>
          <option v-for="target in membershipTargets" :key="target.id" :value="String(target.id)" :disabled="target.locked || target.id === sourceWatchlistId">{{ target.name }}{{ target.locked ? ' · Locked' : '' }}</option>
        </select>
        <button type="button" role="menuitem" :disabled="!canCopyToTarget" @click="runContextAction('copy-to-watchlist')">Copy to list</button>
        <button type="button" role="menuitem" :disabled="!canMoveToTarget" @click="runContextAction('move-to-watchlist')">Move to list</button>
      </template>
      <button v-if="allowRemove" type="button" role="menuitem" @click="runContextAction('remove')">Remove from list</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useVirtualizer } from '@tanstack/vue-virtual'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { CHART_PLOT_DRAG_MIME, readAnalysisDrag, type ChartPlotDragPayload, type TechnicalConditionDragPayload } from '@/lib/workstation/plotDrag'

export interface WatchlistRow {
  itemId?: number
  sourceWatchlistId?: number
  instrumentId: number | null
  symbol: string
  name: string
  flagged?: boolean
  values?: Record<string, string | number | null>
  /** Cell-level canonical analysis warnings are rendered instead of silent blanks. */
  warnings?: Record<string, string | null | undefined>
}

export interface WatchlistColumn {
  key: string
  label: string
  width?: string
  format?: 'percent' | 'number'
  decimals?: number
  kind?: 'boolean'
}

export interface WatchlistMembershipTarget {
  id: number
  name: string
  locked?: boolean
  instrumentIds?: number[]
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
  pythonColumns?: Array<{ code_version_id: number; name: string; timeframe?: string }>
  timeframe?: string
  indicatorColumns?: Array<{ key: string; name: string; indicator: string; params: Record<string, unknown>; timeframe: string; output?: string }>
  indicatorValues?: Record<string, Record<string, number | null>>
  indicatorWarnings?: Record<string, Record<string, string | null>>
  conditionColumns?: Array<{ key: string; name: string; screener_id: number; timeframe: string }>
  conditionValues?: Record<string, Record<string, boolean | null>>
  dropError?: string
  pythonCondition?: { code_version_id: number; name: string; mode: 'active' | 'inactive' | 'off'; timeframe?: string } | null
  reorderable?: boolean
  allowRemove?: boolean
  sourceWatchlistId?: number | null
  membershipTargets?: WatchlistMembershipTarget[]
  columnOverrides?: Record<string, { label?: string; width?: string; format?: 'percent' | 'number'; decimals?: number }>
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
  timeframe: 'D1',
  indicatorColumns: () => [],
  indicatorValues: () => ({}),
  indicatorWarnings: () => ({}),
  conditionColumns: () => [],
  conditionValues: () => ({}),
  dropError: '',
  pythonCondition: null,
  reorderable: false,
  allowRemove: false,
  sourceWatchlistId: null,
  membershipTargets: () => [],
  columnOverrides: () => ({}),
})
const queryClient = useQueryClient()
const emit = defineEmits<{ select: [row: WatchlistRow]; compare: [symbols: string[]]; reorder: [itemIds: number[]]; 'plot-drop': [payload: ChartPlotDragPayload]; 'condition-drop': [payload: TechnicalConditionDragPayload]; 'row-action': [action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: WatchlistRow, targetWatchlistId?: number]; 'update:visibleColumnKeys': [keys: string[]]; 'update:filterText': [value: string]; 'update:conditionScreenerId': [id: number | null]; 'update:conditionFilterMode': [mode: 'active' | 'inactive' | 'off']; 'update:pinnedBooleanKeys': [keys: string[]]; 'update:columnGroups': [groups: Record<string, string>]; 'update:stackedColumnKeys': [keys: string[]]; 'update:columnOverrides': [overrides: Record<string, { label?: string; width?: string; format?: 'percent' | 'number'; decimals?: number }>]; 'update:pythonColumns': [columns: Array<{ code_version_id: number; name: string; timeframe?: string }>]; 'update:pythonCondition': [condition: { code_version_id: number; name: string; mode: 'active' | 'inactive' | 'off'; timeframe?: string } | null] }>()
const scrollElement = ref<HTMLElement | null>(null)
const filter = ref(props.filterText)
const conditionFilter = ref(props.conditionScreenerId == null ? '' : String(props.conditionScreenerId))
const conditionFilterMode = ref(props.conditionFilterMode)
const screeners = ref<SavedScreener[]>([])
const conditionMatchedIds = ref<Set<number> | null>(null)
const conditionFilterState = ref('')
const selectedPythonConditionVersion = ref(props.pythonCondition?.code_version_id ? String(props.pythonCondition.code_version_id) : '')
const pythonConditionMode = ref<'active' | 'inactive' | 'off'>(props.pythonCondition?.mode ?? 'off')
const pythonConditionMatchedSymbols = ref<Set<string> | null>(null)
const pythonConditionState = ref('')
const pythonAlertBusy = ref(false)
const pythonAlertState = ref('')
const sortKey = ref('symbol')
const sortDirection = ref<'asc' | 'desc'>('asc')
const selectedSymbols = ref<string[]>([])
const selectionAnchor = ref<string | null>(null)
const contextMenu = ref<{ row: WatchlistRow; left: number; top: number } | null>(null)
const membershipTargetId = ref('')
const membershipInspectionOpen = ref(false)
const draggedItemId = ref<number | null>(null)
const draggedColumnKey = ref<string | null>(null)
const plotDropActive = ref(false)
const columnMenuOpen = ref(false)
const columnSetMenuOpen = ref(false)
const columnSetName = ref('')
const columnSetLoading = ref(false)
const columnSetBusy = ref(false)
const columnSetError = ref('')
const columnSets = ref<ColumnSetItem[]>([])
const columnClipboard = ref('')
const columnClipboardState = ref('')
const selectedPythonVersion = ref('')
const pythonAssets = ref<Array<{ versionId: number; name: string }>>([])
const pythonConditionAssets = ref<Array<{ versionId: number; name: string }>>([])
const pythonCells = ref<Record<string, Record<string, { value?: number | boolean; error?: string }>>>({})
const pythonRunIds = ref<Record<string, number>>({})
const pythonProgress = ref<Record<string, string>>({})
const runningPythonColumns = new Set<number>()
const runningPythonConditions = new Set<number>()
const rowsGeneration = ref(0)
const conditionRequestGeneration = ref(0)
const pythonConditionRequestGeneration = ref(0)
const pythonColumnRequestGenerations = new Map<number, number>()
const timeframeOptions = [{ value: 'M15', label: '15m' }, { value: 'D1', label: 'Daily' }, { value: 'W1', label: 'Weekly' }, { value: 'MN', label: 'Monthly' }]
const renderEpoch = ref(0)
const pythonColumns = computed(() => props.pythonColumns.filter(column => Number.isInteger(column.code_version_id) && column.code_version_id > 0 && typeof column.name === 'string'))
const indicatorColumns = computed(() => props.indicatorColumns.filter(column => typeof column.key === 'string' && column.key.startsWith('indicator:') && typeof column.name === 'string' && typeof column.indicator === 'string'))
const conditionColumns = computed(() => props.conditionColumns.filter(column => typeof column.key === 'string' && column.key.startsWith('condition:') && typeof column.name === 'string' && Number.isInteger(column.screener_id)))
const membershipTargets = computed(() => props.membershipTargets.filter(target => Number.isInteger(target.id) && target.id > 0 && typeof target.name === 'string'))
const selectedMembershipTarget = computed(() => membershipTargets.value.find(target => target.id === Number(membershipTargetId.value)) ?? null)
const relatedLists = computed(() => {
  const instrumentId = contextMenu.value?.row.instrumentId
  if (instrumentId == null) return []
  return membershipTargets.value.filter(target => target.instrumentIds?.includes(instrumentId))
})
const canCopyToTarget = computed(() => Boolean(contextMenu.value?.row.instrumentId && selectedMembershipTarget.value && !selectedMembershipTarget.value.locked && selectedMembershipTarget.value.id !== props.sourceWatchlistId))
const canMoveToTarget = computed(() => Boolean(canCopyToTarget.value && props.sourceWatchlistId != null && props.allowRemove))
const pythonCondition = computed(() => props.pythonCondition && Number.isInteger(props.pythonCondition.code_version_id) && props.pythonCondition.code_version_id > 0 && typeof props.pythonCondition.name === 'string' ? props.pythonCondition : null)
const effectiveColumns = computed<WatchlistColumn[]>(() => ([...props.columns, ...indicatorColumns.value.map(column => ({ key: column.key, label: column.name, width: '78px', format: 'number' as const })), ...conditionColumns.value.map(column => ({ key: column.key, label: column.name, width: '78px', kind: 'boolean' as const })), ...pythonColumns.value.map(column => ({ key: pythonKey(column.code_version_id), label: column.name, width: '78px', format: 'number' as const }))] as WatchlistColumn[]).map(column => ({
  ...column,
  label: props.columnOverrides[column.key]?.label?.trim() || column.label,
  width: props.columnOverrides[column.key]?.width?.trim() || column.width,
  format: props.columnOverrides[column.key]?.format || column.format,
  decimals: props.columnOverrides[column.key]?.decimals ?? column.decimals,
})))
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
  const screenerRows = conditionMatchedIds.value === null
    ? textRows
    : textRows.filter(row => row.instrumentId != null && conditionMatchedIds.value?.has(row.instrumentId))
  const rows = pythonConditionMatchedSymbols.value === null
    ? screenerRows
    : screenerRows.filter(row => pythonConditionMatchedSymbols.value?.has(row.symbol))
  if (props.reorderable) return rows
  return rows.sort((left, right) => {
    for (const key of props.pinnedBooleanKeys) {
      const leftPinned = Boolean(left.values?.[key])
      const rightPinned = Boolean(right.values?.[key])
      if (leftPinned !== rightPinned) return leftPinned ? -1 : 1
    }
    const leftValue = sortValue(left, sortKey.value)
    const rightValue = sortValue(right, sortKey.value)
    if (leftValue == null || rightValue == null) {
      if (leftValue == null && rightValue == null) return 0
      return leftValue == null ? 1 : -1
    }
    const comparison = typeof leftValue === 'number' && typeof rightValue === 'number'
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue), undefined, { numeric: true })
    return sortDirection.value === 'asc' ? comparison : -comparison
  })
})

function dragStart(row: WatchlistRow) {
  if (!props.reorderable || row.itemId == null) return
  draggedItemId.value = row.itemId
}

function dragOverPlot(event: DragEvent) {
  const types = event.dataTransfer ? Array.from(event.dataTransfer.types) : []
  if (types.includes(CHART_PLOT_DRAG_MIME)) plotDropActive.value = true
}

function dragLeavePlot(event: DragEvent) {
  const current = event.currentTarget as HTMLElement | null
  const related = event.relatedTarget as Node | null
  if (!current || !related || !current.contains(related)) plotDropActive.value = false
}

function dropPlot(event: DragEvent) {
  plotDropActive.value = false
  const payload = readAnalysisDrag(event.dataTransfer)
  if (payload?.kind === 'chart-plot') emit('plot-drop', payload)
  if (payload?.kind === 'technical-condition') emit('condition-drop', payload)
}

function dropRow(row: WatchlistRow) {
  const source = draggedItemId.value
  draggedItemId.value = null
  if (!props.reorderable || source == null || row.itemId == null || source === row.itemId) return
  const ids = props.rows.map(item => item.itemId).filter((id): id is number => id != null)
  const from = ids.indexOf(source)
  const to = ids.indexOf(row.itemId)
  if (from < 0 || to < 0) return
  ids.splice(from, 1)
  ids.splice(to, 0, source)
  emit('reorder', ids)
}
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
watch(filteredRows, rows => {
  renderEpoch.value += 1
  virtualizer.value.measure()
  const availableSymbols = new Set(rows.map(row => row.symbol))
  selectedSymbols.value = selectedSymbols.value.filter(symbol => availableSymbols.has(symbol))
  if (selectionAnchor.value && !availableSymbols.has(selectionAnchor.value)) selectionAnchor.value = null
})
watch(filter, value => emit('update:filterText', value))
watch(() => props.filterText, value => { if (value !== filter.value) filter.value = value })
watch(() => props.conditionScreenerId, value => {
  const normalized = value == null ? '' : String(value)
  if (normalized !== conditionFilter.value) conditionFilter.value = normalized
})
watch(() => props.conditionFilterMode, value => { if (value !== conditionFilterMode.value) conditionFilterMode.value = value })
watch(() => props.pythonCondition, value => {
  const nextId = value?.code_version_id ? String(value.code_version_id) : ''
  if (nextId !== selectedPythonConditionVersion.value) selectedPythonConditionVersion.value = nextId
  const nextMode = value?.mode ?? 'off'
  if (nextMode !== pythonConditionMode.value) pythonConditionMode.value = nextMode
})
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
watch(selectedPythonConditionVersion, value => { configurePythonCondition(value) })
watch(pythonConditionMode, mode => {
  const configured = pythonCondition.value
  if (!configured) return
  if (mode === 'off') {
    pythonConditionMatchedSymbols.value = null
    pythonConditionState.value = ''
    selectedPythonConditionVersion.value = ''
    emit('update:pythonCondition', null)
    return
  }
  emit('update:pythonCondition', { ...configured, mode })
  if (mode === 'inactive') {
    pythonConditionMatchedSymbols.value = null
    pythonConditionState.value = 'Python condition inactive; it does not filter rows.'
  } else void runPythonCondition(configured)
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
    pythonConditionAssets.value = assets.filter(asset => asset.kind === 'condition').flatMap(asset => asset.versions.slice(-1).map(version => ({ versionId: version.id, name: `${asset.name} v${version.version_number}` })))
  } catch { pythonAssets.value = []; pythonConditionAssets.value = [] }
}
function sleep(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)) }
type PythonBatchResult = { status: string; progress?: { completed_cells?: number; total_cells?: number; status?: string }; cells: Array<{ symbol: string; status: string; value?: number | boolean; error?: string }> }
function fetchPythonBatchResult(runId: number) {
  return queryClient.fetchQuery<PythonBatchResult>({
    queryKey: ['workstation', 'research-batch-result', runId],
    queryFn: () => api.get<PythonBatchResult>(`/research/runs/${runId}/batch-results`),
    staleTime: 0,
  })
}
function progressLabel(progress?: { completed_cells?: number; total_cells?: number; status?: string }) {
  if (!progress) return 'Queued'
  const completed = Number(progress.completed_cells ?? 0)
  const total = Number(progress.total_cells ?? 0)
  return total > 0 ? `Running ${completed}/${total}` : progress.status === 'running' ? 'Running' : 'Queued'
}
async function cancelPythonRun(key: string) {
  const runId = pythonRunIds.value[key]
  if (!runId) return
  pythonProgress.value = { ...pythonProgress.value, [key]: 'Canceling…' }
  if (key === 'python_condition') pythonConditionState.value = 'Canceling Python condition…'
  try { await api.post(`/research/runs/${runId}/cancel`, {}) }
  catch (cause: any) { pythonProgress.value = { ...pythonProgress.value, [key]: cause?.message ?? 'Cancel failed' } }
}

function invalidatePythonColumn(codeVersionId: number) {
  const key = pythonKey(codeVersionId)
  void cancelPythonRun(key)
  pythonColumnRequestGenerations.set(codeVersionId, (pythonColumnRequestGenerations.get(codeVersionId) ?? 0) + 1)
  runningPythonColumns.delete(codeVersionId)
  const { [key]: _run, ...remainingRuns } = pythonRunIds.value
  pythonRunIds.value = remainingRuns
  const { [key]: _progress, ...remainingProgress } = pythonProgress.value
  pythonProgress.value = remainingProgress
}

function invalidatePythonCondition() {
  void cancelPythonRun('python_condition')
  pythonConditionRequestGeneration.value += 1
  if (pythonCondition.value) runningPythonConditions.delete(pythonCondition.value.code_version_id)
  const { python_condition: _run, ...remainingRuns } = pythonRunIds.value
  pythonRunIds.value = remainingRuns
  const { python_condition: _progress, ...remainingProgress } = pythonProgress.value
  pythonProgress.value = remainingProgress
}
async function runPythonColumn(column: { code_version_id: number; name: string; timeframe?: string }) {
  if (runningPythonColumns.has(column.code_version_id)) return
  const symbols = [...new Set(props.rows.map(row => row.symbol).filter(Boolean))]
  if (!symbols.length) return
  runningPythonColumns.add(column.code_version_id)
  const key = pythonKey(column.code_version_id)
  const requestGeneration = (pythonColumnRequestGenerations.get(column.code_version_id) ?? 0) + 1
  pythonColumnRequestGenerations.set(column.code_version_id, requestGeneration)
  const universeGeneration = rowsGeneration.value
  const isCurrent = () => pythonColumnRequestGenerations.get(column.code_version_id) === requestGeneration && rowsGeneration.value === universeGeneration
  pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(symbols.map(symbol => [symbol, { error: 'Queued' }])) }
  pythonProgress.value = { ...pythonProgress.value, [key]: 'Queued' }
  try {
    const runTimeframe = column.timeframe ?? props.timeframe
    const run = await api.post<{ id: number }>('/research/runs', { code_version_id: column.code_version_id, run_config: { symbols, timeframe: runTimeframe }, dataset_manifest: { source: 'canonical_database', timeframe: runTimeframe } })
    if (!isCurrent()) return
    pythonRunIds.value = { ...pythonRunIds.value, [key]: run.id }
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const result = await fetchPythonBatchResult(run.id)
      if (!isCurrent()) return
      pythonProgress.value = { ...pythonProgress.value, [key]: progressLabel(result.progress) }
      if (result.status === 'completed' || result.status === 'failed' || result.status === 'canceled') {
        pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(result.cells.map(cell => [cell.symbol, cell.status === 'completed' ? { value: cell.value } : { error: cell.error ?? cell.status }])) }
        return
      }
      await sleep(250)
    }
  } catch (cause: any) {
    if (isCurrent()) {
      pythonCells.value = { ...pythonCells.value, [key]: Object.fromEntries(symbols.map(symbol => [symbol, { error: cause?.message ?? 'Unavailable' }])) }
      pythonProgress.value = { ...pythonProgress.value, [key]: cause?.message ?? 'Unavailable' }
    }
  }
  finally {
    if (pythonColumnRequestGenerations.get(column.code_version_id) === requestGeneration) {
      runningPythonColumns.delete(column.code_version_id)
      const { [key]: _, ...rest } = pythonRunIds.value
      pythonRunIds.value = rest
    }
  }
}
function addPythonColumn() {
  const versionId = Number(selectedPythonVersion.value)
  const asset = pythonAssets.value.find(item => item.versionId === versionId)
  if (!asset || pythonColumns.value.some(column => column.code_version_id === versionId)) return
  const column = { code_version_id: versionId, name: asset.name, timeframe: props.timeframe }
  emit('update:pythonColumns', [...pythonColumns.value, column])
  selectedPythonVersion.value = ''
  void runPythonColumn(column)
}
function setPythonColumnTimeframe(codeVersionId: number, timeframe: string) {
  invalidatePythonColumn(codeVersionId)
  const next = pythonColumns.value.map(column => column.code_version_id === codeVersionId ? { ...column, timeframe } : column)
  emit('update:pythonColumns', next)
  const changed = next.find(column => column.code_version_id === codeVersionId)
  if (changed) void runPythonColumn(changed)
}

function configurePythonCondition(value: string) {
  const versionId = Number(value)
  const asset = pythonConditionAssets.value.find(item => item.versionId === versionId)
  if (!asset) {
    if (!value) {
      pythonConditionMatchedSymbols.value = null
      pythonConditionState.value = ''
      emit('update:pythonCondition', null)
    }
    return
  }
  const condition = { code_version_id: versionId, name: asset.name, mode: 'active' as const, timeframe: props.timeframe }
  if (pythonConditionMode.value === 'off') pythonConditionMode.value = 'active'
  emit('update:pythonCondition', condition)
  void runPythonCondition(condition)
}

function setPythonConditionTimeframe(timeframe: string) {
  if (!pythonCondition.value) return
  invalidatePythonCondition()
  const condition = { ...pythonCondition.value, timeframe }
  emit('update:pythonCondition', condition)
  void runPythonCondition(condition)
}

async function runPythonCondition(condition: { code_version_id: number; name: string; mode: 'active' | 'inactive' | 'off'; timeframe?: string }) {
  if (condition.mode !== 'active' || runningPythonConditions.has(condition.code_version_id)) return
  const symbols = [...new Set(props.rows.map(row => row.symbol).filter(Boolean))]
  if (!symbols.length) return
  runningPythonConditions.add(condition.code_version_id)
  const requestGeneration = ++pythonConditionRequestGeneration.value
  const universeGeneration = rowsGeneration.value
  const isCurrent = () => pythonConditionRequestGeneration.value === requestGeneration && rowsGeneration.value === universeGeneration
  pythonConditionMatchedSymbols.value = null
  pythonConditionState.value = 'Running Python condition…'
  pythonProgress.value = { ...pythonProgress.value, python_condition: 'Queued' }
  try {
    const runTimeframe = condition.timeframe ?? props.timeframe
    const run = await api.post<{ id: number }>('/research/runs', { code_version_id: condition.code_version_id, run_config: { symbols, timeframe: runTimeframe }, dataset_manifest: { source: 'canonical_database', timeframe: runTimeframe } })
    if (!isCurrent()) return
    pythonRunIds.value = { ...pythonRunIds.value, python_condition: run.id }
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const result = await fetchPythonBatchResult(run.id)
      if (!isCurrent()) return
      pythonProgress.value = { ...pythonProgress.value, python_condition: progressLabel(result.progress) }
      if (result.status !== 'completed' && result.status !== 'failed' && result.status !== 'canceled') pythonConditionState.value = `Python condition ${progressLabel(result.progress).toLowerCase()}…`
      if (result.status === 'completed' || result.status === 'failed' || result.status === 'canceled') {
        const completed = result.cells.filter(cell => cell.status === 'completed')
        const errors = result.cells.length - completed.length
        pythonConditionMatchedSymbols.value = new Set(completed.filter(cell => cell.value === true).map(cell => cell.symbol))
        pythonConditionState.value = errors ? `Python condition active · ${completed.length}/${result.cells.length} evaluated; ${errors} unavailable.` : `Python condition active · ${pythonConditionMatchedSymbols.value.size}/${completed.length} match.`
        return
      }
      await sleep(250)
    }
    pythonConditionMatchedSymbols.value = new Set()
    pythonConditionState.value = 'Python condition timed out; no rows are shown.'
  } catch (cause: any) {
    if (isCurrent()) {
      pythonConditionMatchedSymbols.value = new Set()
      pythonConditionState.value = `Python condition unavailable: ${cause?.message ?? 'Unknown error'}`
    }
  } finally {
    if (pythonConditionRequestGeneration.value === requestGeneration) {
      runningPythonConditions.delete(condition.code_version_id)
      const { python_condition: _, ...rest } = pythonRunIds.value
      pythonRunIds.value = rest
    }
  }
}

async function createPythonConditionAlert() {
  const condition = pythonCondition.value
  if (!condition || condition.mode !== 'active' || pythonAlertBusy.value) return
  pythonAlertBusy.value = true
  pythonAlertState.value = ''
  try {
    const name = `${condition.name} alert`
    const screener = await api.post<{ id: number }>(`/screeners/from-python-condition/${condition.code_version_id}`, {
      name,
      universe_type: 'all',
      timeframe: condition.timeframe ?? props.timeframe,
    })
    await api.post('/alerts/screener', { screener_id: screener.id, trigger_type: 'both', repeat: true, notes: `Created from Python condition ${condition.name}` })
    pythonAlertState.value = 'Alert active for future condition entries/exits.'
  } catch (cause: any) {
    pythonAlertState.value = cause?.message ?? 'Unable to create Python condition alert.'
  } finally {
    pythonAlertBusy.value = false
  }
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
  const requestGeneration = ++conditionRequestGeneration.value
  const universeGeneration = rowsGeneration.value
  const isCurrent = () => conditionRequestGeneration.value === requestGeneration && rowsGeneration.value === universeGeneration
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
    if (!isCurrent()) return
    const result = results[0]
    if (!result) {
      conditionMatchedIds.value = new Set()
      conditionFilterState.value = 'Saved condition is active but has not been run yet.'
      return
    }
    conditionMatchedIds.value = new Set(result.matched_ids)
    conditionFilterState.value = `Saved condition active · latest result ${new Date(result.run_at).toLocaleString()}`
  } catch {
    if (isCurrent()) {
      conditionMatchedIds.value = new Set()
      conditionFilterState.value = 'Saved condition result is unavailable; no rows are shown.'
    }
  }
}

const rowUniverseKey = computed(() => props.rows.map(row => `${row.instrumentId ?? ''}:${row.symbol}`).join('|'))
watch(rowUniverseKey, () => {
  rowsGeneration.value += 1
  // A changed universe invalidates active prepared-universe jobs. Cancel them
  // at the backend as well as ignoring late results locally; otherwise a large
  // Python column/condition run keeps consuming sandbox resources after the
  // user has moved to another list or symbol set.
  for (const key of Object.keys(pythonRunIds.value)) void cancelPythonRun(key)
  conditionMatchedIds.value = null
  pythonConditionMatchedSymbols.value = null
  for (const column of pythonColumns.value) {
    runningPythonColumns.delete(column.code_version_id)
    const key = pythonKey(column.code_version_id)
    const { [key]: _run, ...remainingRuns } = pythonRunIds.value
    pythonRunIds.value = remainingRuns
    const { [key]: _progress, ...remainingProgress } = pythonProgress.value
    pythonProgress.value = remainingProgress
  }
  if (pythonCondition.value) {
    runningPythonConditions.delete(pythonCondition.value.code_version_id)
    const { python_condition: _run, ...remainingRuns } = pythonRunIds.value
    pythonRunIds.value = remainingRuns
    const { python_condition: _progress, ...remainingProgress } = pythonProgress.value
    pythonProgress.value = remainingProgress
  }
  if (conditionFilter.value) void applyConditionFilter(conditionFilter.value)
  if (pythonCondition.value) void runPythonCondition(pythonCondition.value)
  for (const column of pythonColumns.value) void runPythonColumn(column)
})

onMounted(() => {
  void loadScreeners()
  void loadColumnSets()
  void loadPythonAssets()
  for (const column of pythonColumns.value) void runPythonColumn(column)
  if (conditionFilter.value) void applyConditionFilter(conditionFilter.value)
  if (pythonCondition.value) void runPythonCondition(pythonCondition.value)
})
watch(pythonColumns, columns => {
  for (const column of columns) {
    if (!pythonCells.value[pythonKey(column.code_version_id)]) void runPythonColumn(column)
  }
}, { deep: true })
watch(pythonCondition, condition => { if (condition) void runPythonCondition(condition) }, { deep: true })

onBeforeUnmount(() => {
  // Closing a docked tool or pop-out must release any prepared-universe work it
  // started. Invalidate local generations first so a late POST/poll response
  // cannot repopulate state after the component has been destroyed.
  rowsGeneration.value += 1
  for (const codeVersionId of pythonColumnRequestGenerations.keys()) {
    pythonColumnRequestGenerations.set(codeVersionId, (pythonColumnRequestGenerations.get(codeVersionId) ?? 0) + 1)
  }
  pythonConditionRequestGeneration.value += 1
  for (const key of Object.keys(pythonRunIds.value)) void cancelPythonRun(key)
})

function formatNumeric(key: string, value: number, fallbackDecimals = 2) {
  const column = effectiveColumns.value.find(item => item.key === key)
  const format = column?.format ?? 'percent'
  const decimals = column?.decimals ?? fallbackDecimals
  return format === 'number' ? value.toFixed(decimals) : `${(value * 100).toFixed(decimals)}%`
}

function numericCellValue(row: WatchlistRow, key: string): number | null {
  if (effectiveColumns.value.find(column => column.key === key)?.kind === 'boolean') return null
  if (key.startsWith('indicator:')) return props.indicatorValues[key]?.[row.symbol] ?? null
  if (key.startsWith('python:')) {
    const value = pythonCells.value[key]?.[row.symbol]?.value
    return typeof value === 'number' ? value : null
  }
  const value = key === 'symbol' || key === 'name' ? null : row.values?.[key]
  return typeof value === 'number' ? value : null
}

function numericCellClass(row: WatchlistRow, key: string) {
  const value = numericCellValue(row, key)
  return value == null ? '' : value > 0 ? 'watchlist__cell--positive' : value < 0 ? 'watchlist__cell--negative' : 'watchlist__cell--zero'
}

function display(row: WatchlistRow, key: string) {
  if (key.startsWith('indicator:')) {
    const value = props.indicatorValues[key]?.[row.symbol]
    const warning = props.indicatorWarnings[key]?.[row.symbol]
    return value == null ? warning ? `⚠ ${warning}` : '—' : formatNumeric(key, value)
  }
  if (key.startsWith('python:')) {
    const cell = pythonCells.value[key]?.[row.symbol]
    return cell?.error ? cell.error : cell?.value == null ? '—' : typeof cell.value === 'boolean' ? cell.value ? 'True' : 'False' : formatNumeric(key, cell.value, 4)
  }
  if (key.startsWith('condition:')) {
    const value = props.conditionValues[key]?.[row.symbol]
    return value == null ? '—' : value ? 'True' : 'False'
  }
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  if (value == null || value === '') {
    const warning = row.warnings?.[key]
    return warning ? `⚠ ${warning}` : '—'
  }
  if (typeof value !== 'number') return String(value)
  return formatNumeric(key, value, key.startsWith('python:') ? 4 : 2)
}

function sortValue(row: WatchlistRow, key: string): number | string | null {
  if (key.startsWith('indicator:')) return props.indicatorValues[key]?.[row.symbol] ?? null
  if (key.startsWith('condition:')) {
    const value = props.conditionValues[key]?.[row.symbol]
    return value == null ? null : value ? 'True' : 'False'
  }
  if (key.startsWith('python:')) {
    const value = pythonCells.value[key]?.[row.symbol]?.value
    return value == null || typeof value === 'boolean' ? value == null ? null : String(value) : value
  }
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  return value == null || value === '' ? null : typeof value === 'number' ? value : String(value)
}

function toggleSort(key: string) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
}

function selectRow(row: WatchlistRow, event: MouseEvent) {
  contextMenu.value = null
  const symbols = filteredRows.value.map(item => item.symbol)
  if (event.shiftKey && selectionAnchor.value) {
    const start = symbols.indexOf(selectionAnchor.value)
    const end = symbols.indexOf(row.symbol)
    if (start >= 0 && end >= 0) selectedSymbols.value = symbols.slice(Math.min(start, end), Math.max(start, end) + 1)
  } else if (event.ctrlKey || event.metaKey) {
    selectedSymbols.value = selectedSymbols.value.includes(row.symbol)
      ? selectedSymbols.value.filter(symbol => symbol !== row.symbol)
      : [...selectedSymbols.value, row.symbol]
    selectionAnchor.value = row.symbol
  } else {
    selectedSymbols.value = [row.symbol]
    selectionAnchor.value = row.symbol
  }
  emit('select', row)
}

function openContextMenu(event: MouseEvent, row: WatchlistRow) {
  const bounds = (event.currentTarget as HTMLElement).closest('.watchlist')?.getBoundingClientRect()
  membershipTargetId.value = ''
  membershipInspectionOpen.value = false
  contextMenu.value = { row, left: Math.max(2, event.clientX - (bounds?.left ?? 0)), top: Math.max(2, event.clientY - (bounds?.top ?? 0)) }
}

function runContextAction(action: 'chart' | 'compare' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove') {
  if (!contextMenu.value) return
  const row = contextMenu.value.row
  const targetId = Number(membershipTargetId.value)
  contextMenu.value = null
  if ((action === 'copy-to-watchlist' || action === 'move-to-watchlist') && Number.isInteger(targetId) && targetId > 0) {
    emit('row-action', action, row, targetId)
  } else {
    emit('row-action', action, row)
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

function setColumnOverride(key: string, changes: { label?: string; width?: string; format?: 'percent' | 'number'; decimals?: number }) {
  const overrides = { ...props.columnOverrides }
  const next = { ...(overrides[key] ?? {}), ...changes }
  const width = next.width?.trim() ?? ''
  if (width && !/^\d+(?:\.\d+)?(?:px|fr|%)$/.test(width)) return
  const decimals = next.decimals == null || Number.isNaN(next.decimals) ? undefined : Math.min(6, Math.max(0, Math.round(next.decimals)))
  if (!next.label?.trim() && !next.width?.trim() && !next.format && decimals == null) delete overrides[key]
  else overrides[key] = {
    ...(next.label?.trim() ? { label: next.label.trim() } : {}),
    ...(width ? { width } : {}),
    ...(next.format ? { format: next.format } : {}),
    ...(decimals != null ? { decimals } : {}),
  }
  emit('update:columnOverrides', overrides)
}

async function copyColumn(column: WatchlistColumn) {
  const payload = JSON.stringify({
    type: 'workstation-column-settings',
    key: column.key,
    label: column.label,
    width: column.width,
    format: column.format,
    decimals: column.decimals,
    group: props.columnGroups[column.key] ?? '',
    stacked: props.stackedColumnKeys.includes(column.key),
    pinned: props.pinnedBooleanKeys.includes(column.key),
  })
  columnClipboard.value = payload
  try { await navigator.clipboard?.writeText(payload) } catch { /* in-memory copy remains available */ }
  columnClipboardState.value = `Copied ${column.label} settings.`
}

async function pasteColumn() {
  let raw = columnClipboard.value
  try { raw = await navigator.clipboard?.readText() || raw } catch { /* use the in-memory fallback */ }
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>
    const key = typeof payload.key === 'string' ? payload.key : ''
    const column = effectiveColumns.value.find(item => item.key === key)
    if (!column) {
      columnClipboardState.value = 'Copied column is not available in this watchlist.'
      return
    }
    setColumnOverride(key, {
      ...(typeof payload.label === 'string' ? { label: payload.label } : {}),
      ...(typeof payload.width === 'string' ? { width: payload.width } : {}),
      ...(payload.format === 'percent' || payload.format === 'number' ? { format: payload.format } : {}),
      ...(typeof payload.decimals === 'number' ? { decimals: payload.decimals } : {}),
    })
    setColumnGroup(key, typeof payload.group === 'string' ? payload.group : '')
    if (typeof payload.stacked === 'boolean' && payload.stacked !== props.stackedColumnKeys.includes(key)) toggleStackedColumn(key)
    if (column.kind === 'boolean' && typeof payload.pinned === 'boolean' && payload.pinned !== props.pinnedBooleanKeys.includes(key)) togglePinnedBoolean(key)
    columnClipboardState.value = `Pasted ${column.label} settings.`
  } catch {
    columnClipboardState.value = 'Clipboard does not contain workstation column settings.'
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

function dragColumn(key: string) {
  draggedColumnKey.value = key
}

function dropColumn(targetKey: string) {
  const sourceKey = draggedColumnKey.value
  draggedColumnKey.value = null
  if (!sourceKey || sourceKey === targetKey) return
  const current = [...activeColumnKeys.value]
  const sourceIndex = current.indexOf(sourceKey)
  const targetIndex = current.indexOf(targetKey)
  if (sourceIndex < 0 || targetIndex < 0) return
  current.splice(sourceIndex, 1)
  current.splice(targetIndex, 0, sourceKey)
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
  if (filteredRows.value[next]) selectRow(filteredRows.value[next], { shiftKey: event.shiftKey, ctrlKey: event.ctrlKey, metaKey: event.metaKey } as MouseEvent)
}

function onCtrlWheel(event: WheelEvent) {
  const current = filteredRows.value.findIndex(row => row.symbol === props.selected)
  const direction = event.deltaY > 0 ? 1 : -1
  const next = Math.max(0, Math.min(filteredRows.value.length - 1, current + direction))
  if (filteredRows.value[next]) selectRow(filteredRows.value[next], { shiftKey: false, ctrlKey: false, metaKey: false } as MouseEvent)
}
</script>

<style scoped>
.watchlist { position: relative; display: grid; height: 100%; min-height: 0; grid-template-rows: 23px auto 22px minmax(0, 1fr); color: #c7d0d8; background: #11161b; font: 11px/1.2 "Segoe UI", Arial, sans-serif; }
.watchlist--plot-drop-active { outline: 1px solid #69a9d2; outline-offset: -1px; }
.watchlist__plot-drop-hint { position: absolute; z-index: 4; inset: 3px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #69a9d2; background: #193040eF; color: #dcecf6; text-align: center; pointer-events: none; }
.watchlist__drop-error { position: absolute; z-index: 4; inset: 3px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #9e5b5b; background: #3a1d1d; color: #f1b0b0; pointer-events: none; }
.watchlist--columns-open { grid-template-rows: 23px auto auto 22px minmax(0, 1fr); }
.watchlist--sets-open { grid-template-rows: 23px auto auto 22px minmax(0, 1fr); }
.watchlist--grouped { grid-template-rows: 23px auto 32px minmax(0, 1fr); }
.watchlist--columns-open.watchlist--grouped,.watchlist--sets-open.watchlist--grouped { grid-template-rows: 23px auto auto 32px minmax(0, 1fr); }
.watchlist__controls { display: flex; align-items: center; gap: 6px; padding: 0 7px; color: #84939e; background: #181f25; border-bottom: 1px solid #2b343c; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.watchlist__controls input { min-width: 0; width: 80px; margin-left: auto; padding: 1px 4px; border: 1px solid #3d4a54; background: #11161b; color: #dce9f2; font: inherit; text-transform: none; }
.watchlist__controls select { min-width: 0; max-width: 120px; padding: 1px 2px; border: 1px solid #3d4a54; background: #11161b; color: #a9c0d0; font: inherit; text-transform: none; }
.watchlist__columns-button { border: 1px solid #3d4a54; background: #1b252d; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__controls b { color: #78aac8; font-weight: 600; }.watchlist__compare-button { border: 1px solid #4b697b; background: #1e3b4c; color: #d9edf7; padding: 1px 5px; font: inherit; cursor: pointer; }.watchlist__compare-button:hover { background: #2a5268; }
.watchlist__column-menu { display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 4px 7px; background: #253039; border-bottom: 1px solid #384550; color: #b7c6d0; font-size: 10px; text-transform: none; letter-spacing: normal; }
.watchlist__column-set-menu { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:4px 7px; background:#202b33; border-bottom:1px solid #384550; color:#b7c6d0; font-size:10px; }.watchlist__column-set-menu input,.watchlist__column-set-menu button{min-width:0;border:1px solid #42515c;background:#182128;color:#d7e3eb;font:inherit;padding:1px 4px}.watchlist__column-set-menu input{width:108px}.watchlist__column-set-menu span{display:flex;gap:2px}.watchlist__column-set-menu small{color:#8498a6}.watchlist__column-set-error{color:#e49a9a!important}
.watchlist__condition-state { overflow: hidden; margin: 0; padding: 2px 7px; border-bottom: 1px solid #2b343c; color: #8498a6; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__column-menu label { white-space: nowrap; cursor: grab; }
.watchlist__column-editor-row--dragging { opacity: .55; }
.watchlist__label-input { width: 72px; margin-left: 3px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__width-input { width: 38px; margin-left: 2px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__format-input { width: 34px; margin-left: 2px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__decimals-input { width: 28px; margin-left: 2px; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
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
.watchlist__row[draggable="true"] { cursor: grab; }
.watchlist__row[draggable="true"]:active { cursor: grabbing; }
.watchlist__row:hover { background: #202a33; }
.watchlist__row--active { background: #1d4057; box-shadow: inset 2px 0 #66b4e8; }
.watchlist__row--selected { outline: 1px solid #71bfe8; outline-offset: -1px; }
.watchlist__context-menu { position: absolute; z-index: 140; display: grid; min-width: 146px; gap: 2px; padding: 4px; border: 1px solid #526673; background: #182128; box-shadow: 0 5px 14px #000b; }
.watchlist__context-menu strong { padding: 2px 5px 3px; border-bottom: 1px solid #32424d; color: #dceaf2; font-size: 10px; }
.watchlist__context-menu button { border: 0; background: transparent; color: #c3d2dc; padding: 3px 5px; text-align: left; font: inherit; cursor: pointer; }
.watchlist__context-menu button:disabled { color: #657782; cursor: not-allowed; }
.watchlist__membership-target { min-width: 136px; border: 1px solid #526673; background: #10171d; color: #c3d2dc; padding: 3px 4px; font: inherit; }
.watchlist__flag { margin-right: 3px; color: #f0c674; font-weight: 700; }
.watchlist__membership-inspection { display: grid; gap: 1px; padding: 2px 5px 3px; border-top: 1px solid #32424d; color: #8fb2c3; font-size: 10px; }
.watchlist__context-menu button:hover,.watchlist__context-menu button:focus-visible { background: #28506a; color: #fff; outline: 0; }
.watchlist__row span { min-width: 0; overflow: hidden; padding: 0 6px; color: #8999a5; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__row .watchlist__cell--positive { color: #72c995; }
.watchlist__row .watchlist__cell--negative { color: #df8b8b; }
.watchlist__row .watchlist__cell--zero { color: #a8b6bf; }
.watchlist__row span:first-child { color: #dce9f2; font-weight: 600; }
.watchlist__stack-cell { display: grid; min-width: 0; align-self: stretch; padding: 1px 6px; }
.watchlist__stack-cell small { overflow: hidden; color: #8999a5; font: 9px/1.15 "Segoe UI", Arial, sans-serif; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__stack-cell em { display: inline-block; min-width: 27px; margin-right: 4px; color: #718c9f; font-style: normal; }
</style>
