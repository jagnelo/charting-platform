<template>
  <section class="watchlist" :class="{ 'watchlist--columns-open': columnMenuOpen, 'watchlist--sets-open': columnSetMenuOpen, 'watchlist--condition-open': Boolean(conditionFilterState || pythonConditionState), 'watchlist--grouped': hasColumnGroups, 'watchlist--plot-drop-active': plotDropActive }" :aria-label="label" :aria-busy="loading ? 'true' : 'false'" @click="contextMenu = null" @keydown.esc="handleWatchlistEscape" @dragenter.prevent="dragOverPlot" @dragover.prevent="dragOverPlot" @dragleave="dragLeavePlot" @drop.prevent="dropPlot">
    <p v-if="plotDropActive" class="watchlist__plot-drop-hint" role="status">Drop to add the chart plot as a numeric column</p>
    <p v-if="dropError" class="watchlist__drop-error" role="alert">{{ dropError }}</p>
    <p v-if="loading" class="watchlist__loading-status" role="status" aria-live="polite">{{ loadingLabel }}</p>
    <p v-if="errorMessage" class="watchlist__data-error" role="alert">{{ errorMessage }}</p>
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
      <button ref="columnMenuTrigger" class="watchlist__columns-button" type="button" aria-label="Columns" aria-haspopup="dialog" :aria-expanded="columnMenuOpen" @click="toggleColumnMenu" @keydown="handleEditorTriggerKeydown('columns', $event)">Columns</button>
      <button ref="columnSetMenuTrigger" class="watchlist__columns-button" type="button" aria-label="Column sets" aria-haspopup="dialog" :aria-expanded="columnSetMenuOpen" @click="toggleColumnSetMenu" @keydown="handleEditorTriggerKeydown('sets', $event)">Sets</button>
      <b>{{ selectedSymbols.length ? `${selectedSymbols.length} selected · ` : '' }}{{ filteredRows.length }}</b>
      <button v-if="selectedSymbols.length > 1" type="button" class="watchlist__compare-button" @click="emit('compare', selectedSymbols)">Compare</button>
    </header>
    <p v-if="conditionFilterState" class="watchlist__condition-state">{{ conditionFilterState }}</p>
    <p v-if="pythonConditionState" class="watchlist__condition-state">{{ pythonConditionState }}<button v-if="pythonRunIds.python_condition" type="button" aria-label="Cancel Python condition" @click="cancelPythonRun('python_condition')">Cancel</button><button v-if="pythonCondition?.mode === 'active' && !pythonAlertBusy" type="button" aria-label="Create alert from Python condition" @click="createPythonConditionAlert">Alert</button><small v-if="pythonAlertState">{{ pythonAlertState }}</small></p>
    <div v-if="columnMenuOpen" ref="columnMenuRoot" class="watchlist__column-menu" role="dialog" aria-label="Column editor" @keydown="handleEditorKeydown('columns', $event)">
      <div class="watchlist__column-clipboard"><button type="button" @click="pasteColumn">Paste column settings</button><small v-if="columnClipboardState">{{ columnClipboardState }}</small></div>
      <label v-for="column in effectiveColumns" :key="column.key" class="watchlist__column-editor-row" :class="{ 'watchlist__column-editor-row--dragging': draggedColumnKey === column.key }" draggable="true" @dragstart="dragColumn(column.key)" @dragover.prevent @drop.prevent="dropColumn(column.key)" @dragend="draggedColumnKey = null"><input type="checkbox" :checked="activeColumnKeys.includes(column.key)" @change="toggleColumn(column.key)" /><input class="watchlist__label-input" :aria-label="`${column.label} label`" :value="column.label" @change="setColumnOverride(column.key, { label: ($event.target as HTMLInputElement).value })" /><input class="watchlist__width-input" :aria-label="`${column.label} width`" :value="column.width ?? ''" placeholder="px/fr" @change="setColumnOverride(column.key, { width: ($event.target as HTMLInputElement).value })" /><select v-if="column.kind !== 'boolean'" class="watchlist__format-input" :aria-label="`${column.label} format`" :value="column.format ?? 'percent'" @change="setColumnOverride(column.key, { format: ($event.target as HTMLSelectElement).value as 'percent' | 'number' })"><option value="percent">%</option><option value="number">#</option></select><input v-if="column.kind !== 'boolean'" class="watchlist__decimals-input" type="number" min="0" max="6" :aria-label="`${column.label} decimals`" :value="column.decimals ?? ''" placeholder="dp" @change="setColumnOverride(column.key, { decimals: Number(($event.target as HTMLInputElement).value) })" /><button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} left`" :disabled="!canMoveColumn(column.key, -1)" @click="moveColumn(column.key, -1)"><WorkstationGlyph kind="move-left" /></button><button class="watchlist__order-button" type="button" :aria-label="`Move ${column.label} right`" :disabled="!canMoveColumn(column.key, 1)" @click="moveColumn(column.key, 1)"><WorkstationGlyph kind="move-right" /></button><input class="watchlist__group-input" :aria-label="`${column.label} group`" :value="columnGroups[column.key] ?? ''" placeholder="Group" @input="setColumnGroup(column.key, ($event.target as HTMLInputElement).value)" /><button class="watchlist__stack-button" type="button" :aria-pressed="stackedColumnKeys.includes(column.key)" @click="toggleStackedColumn(column.key)">Stack</button><button v-if="column.kind === 'boolean'" class="watchlist__pin-button" type="button" :aria-pressed="pinnedBooleanKeys.includes(column.key)" @click="togglePinnedBoolean(column.key)">Pin</button><button class="watchlist__copy-button" type="button" :aria-label="`Copy ${column.label} settings`" @click="copyColumn(column)">Copy</button></label>
      <div class="watchlist__python"><select v-model="selectedPythonVersion" aria-label="Python column asset"><option value="">Add Python column…</option><option v-for="asset in pythonAssets" :key="asset.versionId" :value="String(asset.versionId)">{{ asset.name }}</option></select><button type="button" :disabled="!selectedPythonVersion" @click="addPythonColumn">Add</button><label v-for="column in pythonColumns" :key="`timeframe-${column.code_version_id}`">{{ column.name }} <select :aria-label="`${column.name} timeframe`" :value="column.timeframe ?? timeframe" @change="setPythonColumnTimeframe(column.code_version_id, ($event.target as HTMLSelectElement).value)"><option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><template v-for="column in pythonColumns" :key="`progress-${column.code_version_id}`"><small v-if="pythonProgress[pythonKey(column.code_version_id)]">{{ column.name }} · {{ pythonProgress[pythonKey(column.code_version_id)] }}<button v-if="pythonRunIds[pythonKey(column.code_version_id)]" type="button" :aria-label="`Cancel ${column.name}`" @click="cancelPythonRun(pythonKey(column.code_version_id))">Cancel</button></small></template></div>
    </div>
    <div v-if="columnSetMenuOpen" ref="columnSetMenuRoot" class="watchlist__column-set-menu" role="dialog" aria-label="Saved column sets" @keydown="handleEditorKeydown('sets', $event)">
      <input ref="columnSetNameInput" v-model.trim="columnSetName" aria-label="Column set name" placeholder="Column set name" @keydown.enter.prevent="saveColumnSet" />
      <button type="button" :disabled="!columnSetName || columnSetBusy" @click="saveColumnSet">Save set</button>
      <small v-if="columnSetError" class="watchlist__column-set-error">{{ columnSetError }}</small>
      <small v-else-if="columnSetLoading">Loading saved sets…</small>
      <template v-else-if="columnSets.length">
        <span v-for="set in columnSets" :key="set.stable_key"><button type="button" @click="applyColumnSet(set)">{{ set.name }} <small>v{{ set.version }}</small></button><button class="watchlist__column-set-delete" type="button" :aria-label="`Delete column set ${set.name}`" :disabled="columnSetBusy" @click="deleteColumnSet(set)"><WorkstationGlyph kind="close" /></button></span>
      </template>
      <small v-else>No saved column sets.</small>
    </div>
    <div class="watchlist__header-viewport">
      <div class="watchlist__header" :style="headerStyle">
        <template v-for="item in columnRenderItems" :key="item.column.key">
        <div class="watchlist__header-cell" :style="columnCellStyle(item)" @mousedown.capture="handleColumnMouseDown($event, item)">
          <div v-if="item.column.key === stackedColumnKey" class="watchlist__stack-header">
            <button v-for="stackedColumn in stackedColumns" :key="stackedColumn.key" type="button" @click="toggleSort(stackedColumn.key)"><em v-if="columnGroups[stackedColumn.key]">{{ columnGroups[stackedColumn.key] }}</em>{{ stackedColumn.label }}<small v-if="sortKey === stackedColumn.key">{{ sortDirection === 'asc' ? ' ▲' : ' ▼' }}</small></button>
          </div>
          <button v-else type="button" @click="toggleSort(item.column.key)">
            <em v-if="columnGroups[item.column.key]">{{ columnGroups[item.column.key] }}</em>{{ item.column.label }}<small v-if="sortKey === item.column.key">{{ sortDirection === 'asc' ? ' ▲' : ' ▼' }}</small>
          </button>
          <span v-if="item.column.key !== stackedColumnKey" class="watchlist__column-resize-handle" role="separator" tabindex="0" :aria-label="`Resize ${item.column.label} column`" @mousedown.prevent.stop="beginColumnMouseResize($event, item)" />
        </div>
        </template>
      </div>
    </div>
    <div ref="scrollElement" class="watchlist__scroll" role="listbox" :aria-label="`${label} symbols`" :aria-multiselectable="true" :aria-activedescendant="activeDescendantId" tabindex="0" @scroll="syncHeaderScroll" @keydown.stop="onKeydown" @wheel.ctrl.prevent.stop="onCtrlWheel">
      <div :data-render-epoch="renderEpoch" :style="rowCanvasStyle">
        <button
          v-for="virtualRow in virtualItems"
          :key="filteredRows[virtualRow.index].instrumentId ?? filteredRows[virtualRow.index].symbol"
          type="button"
          role="option"
          :id="rowDomId(filteredRows[virtualRow.index])"
          :aria-label="`${filteredRows[virtualRow.index].symbol} ${filteredRows[virtualRow.index].name}`"
          :aria-selected="selectedSymbols.includes(filteredRows[virtualRow.index].symbol) || filteredRows[virtualRow.index].symbol === selected"
          class="watchlist__row"
          :class="{ 'watchlist__row--active': filteredRows[virtualRow.index].symbol === selected, 'watchlist__row--selected': selectedSymbols.includes(filteredRows[virtualRow.index].symbol) }"
          :draggable="reorderable && filteredRows[virtualRow.index].itemId != null"
          :style="rowStyle(virtualRow)"
          @click="selectRow(filteredRows[virtualRow.index], $event)"
          @dragstart="dragStart(filteredRows[virtualRow.index])"
          @dragover.prevent
          @drop.prevent="dropRow(filteredRows[virtualRow.index])"
          @contextmenu.prevent.stop="openContextMenu($event, filteredRows[virtualRow.index])"
        >
          <template v-for="item in columnRenderItems" :key="item.column.key">
            <span v-if="item.column.key !== stackedColumnKey" :style="columnCellStyle(item)" :class="numericCellClass(filteredRows[virtualRow.index], item.column.key)" :title="display(filteredRows[virtualRow.index], item.column.key)"><b v-if="item.column.key === 'symbol' && filteredRows[virtualRow.index].flagged" class="watchlist__flag" aria-label="Flagged">⚑</b><WorkstationGlyph v-if="cellWarning(filteredRows[virtualRow.index], item.column.key)" kind="warning" :title="cellWarning(filteredRows[virtualRow.index], item.column.key) ?? undefined" />{{ display(filteredRows[virtualRow.index], item.column.key) }}</span>
            <span v-else :style="columnCellStyle(item)" class="watchlist__stack-cell"><small v-for="stackedColumn in stackedColumns" :key="stackedColumn.key" :class="numericCellClass(filteredRows[virtualRow.index], stackedColumn.key)" :title="display(filteredRows[virtualRow.index], stackedColumn.key)"><em>{{ stackedColumn.label }}</em><WorkstationGlyph v-if="cellWarning(filteredRows[virtualRow.index], stackedColumn.key)" kind="warning" :title="cellWarning(filteredRows[virtualRow.index], stackedColumn.key) ?? undefined" />{{ display(filteredRows[virtualRow.index], stackedColumn.key) }}</small></span>
          </template>
        </button>
      </div>
    </div>
    <div v-if="contextMenu" ref="contextMenuRoot" class="watchlist__context-menu" role="menu" :aria-label="`${contextMenu.row.symbol} actions`" :style="{ left: `${contextMenu.left}px`, top: `${contextMenu.top}px` }" @click.stop @keydown="handleContextMenuKeydown">
      <strong>{{ contextMenu.row.symbol }}</strong>
      <button type="button" role="menuitem" tabindex="-1" @click="runContextAction('chart')">Open chart</button>
      <button type="button" role="menuitem" tabindex="-1" @click="runContextAction('compare')">Compare with active</button>
      <button type="button" role="menuitem" tabindex="-1" :disabled="!selected || contextMenu.row.symbol.toUpperCase() === selected.toUpperCase()" @click="runContextAction('ratio')">Open ratio vs active</button>
      <button type="button" role="menuitem" tabindex="-1" @click="runContextAction('note')">Open note</button>
      <button type="button" role="menuitem" tabindex="-1" @click="runContextAction('alert')">Open alerts</button>
      <button type="button" role="menuitem" tabindex="-1" @click="runContextAction('copy')">Copy symbol</button>
      <button v-if="contextMenu.row.itemId != null" type="button" role="menuitem" tabindex="-1" @click="runContextAction('flag')">{{ contextMenu.row.flagged ? 'Unflag' : 'Flag' }}</button>
      <button v-if="relatedLists.length" type="button" role="menuitem" tabindex="-1" @click="membershipInspectionOpen = !membershipInspectionOpen">{{ membershipInspectionOpen ? 'Hide list membership' : 'Show list membership' }}</button>
      <div v-if="membershipInspectionOpen" class="watchlist__membership-inspection" aria-label="List membership">
        <small v-for="target in relatedLists" :key="target.id">{{ target.name }}{{ target.id === sourceWatchlistId ? ' · current' : '' }}</small>
      </div>
      <template v-if="membershipTargets.length">
        <select v-model="membershipTargetId" class="watchlist__membership-target" aria-label="Target watchlist">
          <option value="">List actions…</option>
          <option v-for="target in membershipTargets" :key="target.id" :value="String(target.id)" :disabled="target.locked || target.id === contextSourceWatchlistId">{{ target.name }}{{ target.locked ? ' · Locked' : '' }}</option>
        </select>
        <button type="button" role="menuitem" tabindex="-1" :disabled="!canCopyToTarget" @click="runContextAction('copy-to-watchlist')">{{ contextSelectionRows.length > 1 ? `Copy ${contextSelectionRows.length} selected to list` : 'Copy to list' }}</button>
        <button type="button" role="menuitem" tabindex="-1" :disabled="!canMoveToTarget" @click="runContextAction('move-to-watchlist')">{{ contextSelectionRows.length > 1 ? `Move ${contextSelectionRows.length} selected to list` : 'Move to list' }}</button>
      </template>
      <button v-if="allowRemove" type="button" role="menuitem" tabindex="-1" @click="runContextAction('remove')">Remove from list</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useVirtualizer } from '@tanstack/vue-virtual'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'
import { api } from '@/lib/api'
import { fetchCodeAssets } from '@/lib/workstation/libraryQueries'
import { CHART_PLOT_DRAG_MIME, clearAnalysisDrag, hasActiveAnalysisDrag, readAnalysisDrag, scheduleAnalysisDragCleanup, type ChartAnalysisDragPayload, type TechnicalConditionDragPayload } from '@/lib/workstation/plotDrag'
import WorkstationGlyph from '@/components/workstation/WorkstationGlyph.vue'

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

interface ColumnRenderItem {
  column: WatchlistColumn
  index: number
  start: number
  size: number
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
  loading?: boolean
  loadingLabel?: string
  errorMessage?: string
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
  loading: false,
  loadingLabel: 'Loading…',
  errorMessage: '',
  pythonCondition: null,
  reorderable: false,
  allowRemove: false,
  sourceWatchlistId: null,
  membershipTargets: () => [],
  columnOverrides: () => ({}),
})
const queryClient = useQueryClient()
const emit = defineEmits<{ select: [row: WatchlistRow]; compare: [symbols: string[]]; reorder: [itemIds: number[]]; 'plot-drop': [payload: ChartAnalysisDragPayload]; 'condition-drop': [payload: TechnicalConditionDragPayload]; 'row-action': [action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove', row: WatchlistRow, targetWatchlistId?: number, selectedRows?: WatchlistRow[]]; 'update:visibleColumnKeys': [keys: string[]]; 'update:filterText': [value: string]; 'update:conditionScreenerId': [id: number | null]; 'update:conditionFilterMode': [mode: 'active' | 'inactive' | 'off']; 'update:pinnedBooleanKeys': [keys: string[]]; 'update:columnGroups': [groups: Record<string, string>]; 'update:stackedColumnKeys': [keys: string[]]; 'update:columnOverrides': [overrides: Record<string, { label?: string; width?: string; format?: 'percent' | 'number'; decimals?: number }>]; 'update:pythonColumns': [columns: Array<{ code_version_id: number; name: string; timeframe?: string }>]; 'update:pythonCondition': [condition: { code_version_id: number; name: string; mode: 'active' | 'inactive' | 'off'; timeframe?: string } | null] }>()
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
const keyboardActiveSymbol = ref<string | null>(props.selected || null)
const contextMenu = ref<{ row: WatchlistRow; left: number; top: number } | null>(null)
const contextMenuRoot = ref<HTMLElement | null>(null)
const contextRowElement = ref<HTMLElement | null>(null)
const columnMenuTrigger = ref<HTMLButtonElement | null>(null)
const columnMenuRoot = ref<HTMLElement | null>(null)
const columnSetMenuTrigger = ref<HTMLButtonElement | null>(null)
const columnSetMenuRoot = ref<HTMLElement | null>(null)
const columnSetNameInput = ref<HTMLInputElement | null>(null)

function contextMenuItems() {
  return Array.from(contextMenuRoot.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])
}

function focusContextMenuItem(index: number) {
  const items = contextMenuItems()
  if (!items.length) return
  items[Math.max(0, Math.min(index, items.length - 1))]?.focus()
}

function closeContextMenuToRow() {
  if (!contextMenu.value) return
  contextMenu.value = null
  void nextTick(() => contextRowElement.value?.focus())
}

function handleContextMenuKeydown(event: KeyboardEvent) {
  const items = contextMenuItems()
  if (!items.length) return
  const target = event.target instanceof HTMLElement ? event.target : null
  const currentIndex = target ? items.indexOf(target as HTMLButtonElement) : -1
  if (event.key === 'Escape') {
    event.preventDefault()
    closeContextMenuToRow()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
    event.preventDefault()
    focusContextMenuItem((currentIndex + 1 + items.length) % items.length)
  } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
    event.preventDefault()
    focusContextMenuItem((currentIndex - 1 + items.length) % items.length)
  } else if (event.key === 'Home') {
    event.preventDefault()
    focusContextMenuItem(0)
  } else if (event.key === 'End') {
    event.preventDefault()
    focusContextMenuItem(items.length - 1)
  } else if ((event.key === 'Enter' || event.key === ' ') && target) {
    event.preventDefault()
    target.click()
  }
}
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
const resizingColumn = ref<{ key: string; startX: number; startWidth: number; width: number } | null>(null)
const localColumnWidths = ref<Record<string, string>>({})

type WatchlistEditor = 'columns' | 'sets'

// DOM identity is deliberately local to this mounted list. Golden Layout can
// mount several copies of the same watchlist (including browser pop-outs), so
// instrument IDs alone are not sufficient for aria-activedescendant targets.
const watchlistDomId = `watchlist-${globalThis.crypto?.randomUUID?.().replace(/-/g, '').slice(0, 12) ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`}`
function rowDomId(row: WatchlistRow) {
  const identity = row.instrumentId != null ? String(row.instrumentId) : row.symbol
  return `${watchlistDomId}-row-${identity.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}
const activeDescendantId = computed(() => {
  const symbol = keyboardActiveSymbol.value || props.selected
  const row = filteredRows.value.find(candidate => candidate.symbol === symbol)
  return row ? rowDomId(row) : undefined
})

watch(() => props.selected, value => {
  keyboardActiveSymbol.value = value || null
})
function editorRoot(editor: WatchlistEditor) {
  return editor === 'columns' ? columnMenuRoot.value : columnSetMenuRoot.value
}
function editorTrigger(editor: WatchlistEditor) {
  return editor === 'columns' ? columnMenuTrigger.value : columnSetMenuTrigger.value
}
function editorFocusable(editor: WatchlistEditor) {
  return Array.from(editorRoot(editor)?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)') ?? [])
}
function focusEditorStart(editor: WatchlistEditor) {
  const focusable = editorFocusable(editor)
  if (editor === 'sets') columnSetNameInput.value?.focus()
  else focusable[0]?.focus()
}
function toggleColumnMenu() {
  columnMenuOpen.value = !columnMenuOpen.value
  if (columnMenuOpen.value) {
    columnSetMenuOpen.value = false
    void nextTick(() => focusEditorStart('columns'))
  } else columnMenuTrigger.value?.focus()
}
function toggleColumnSetMenu() {
  columnSetMenuOpen.value = !columnSetMenuOpen.value
  if (columnSetMenuOpen.value) {
    columnMenuOpen.value = false
    void nextTick(() => focusEditorStart('sets'))
  } else columnSetMenuTrigger.value?.focus()
}
function closeEditorToTrigger(editor: WatchlistEditor) {
  if (editor === 'columns') columnMenuOpen.value = false
  else columnSetMenuOpen.value = false
  void nextTick(() => editorTrigger(editor)?.focus())
}
function handleEditorTriggerKeydown(editor: WatchlistEditor, event: KeyboardEvent) {
  if (!['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  const open = editor === 'columns' ? columnMenuOpen.value : columnSetMenuOpen.value
  if (!open) {
    if (editor === 'columns') toggleColumnMenu()
    else toggleColumnSetMenu()
  } else focusEditorStart(editor)
}
function handleEditorKeydown(editor: WatchlistEditor, event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeEditorToTrigger(editor)
    return
  }
  const focusable = editorFocusable(editor)
  const current = focusable.indexOf(document.activeElement as HTMLElement)
  let next: number | null = null
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') next = (current + 1 + focusable.length) % focusable.length
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') next = (current - 1 + focusable.length) % focusable.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = focusable.length - 1
  if (next === null || !focusable.length) return
  event.preventDefault()
  focusable[next]?.focus()
}
function handleWatchlistEscape(event: KeyboardEvent) {
  if (columnMenuOpen.value) {
    closeEditorToTrigger('columns')
    return
  }
  if (columnSetMenuOpen.value) closeEditorToTrigger('sets')
  else closeContextMenuToRow()
}
type PythonColumn = { code_version_id: number; name: string; timeframe?: string }
const pendingPythonColumns = ref<PythonColumn[]>([])
const pythonColumns = computed(() => {
  const persisted = props.pythonColumns.filter(column => Number.isInteger(column.code_version_id) && column.code_version_id > 0 && typeof column.name === 'string')
  const persistedIds = new Set(persisted.map(column => column.code_version_id))
  return [...persisted, ...pendingPythonColumns.value.filter(column => !persistedIds.has(column.code_version_id))]
})
watch(() => props.pythonColumns, columns => {
  const persistedIds = new Set(columns.map(column => column.code_version_id))
  pendingPythonColumns.value = pendingPythonColumns.value.filter(column => !persistedIds.has(column.code_version_id))
}, { deep: true })
const indicatorColumns = computed(() => props.indicatorColumns.filter(column => typeof column.key === 'string' && column.key.startsWith('indicator:') && typeof column.name === 'string' && typeof column.indicator === 'string'))
const conditionColumns = computed(() => props.conditionColumns.filter(column => typeof column.key === 'string' && column.key.startsWith('condition:') && typeof column.name === 'string' && Number.isInteger(column.screener_id)))
const membershipTargets = computed(() => props.membershipTargets.filter(target => Number.isInteger(target.id) && target.id > 0 && typeof target.name === 'string'))
const selectedMembershipTarget = computed(() => membershipTargets.value.find(target => target.id === Number(membershipTargetId.value)) ?? null)
const contextSelectionRows = computed(() => {
  const row = contextMenu.value?.row
  if (!row) return []
  if (!selectedSymbols.value.includes(row.symbol)) return [row]
  const selected = filteredRows.value.filter(candidate => selectedSymbols.value.includes(candidate.symbol))
  return selected.length ? selected : [row]
})
const contextSourceWatchlistId = computed(() => contextMenu.value?.row.sourceWatchlistId ?? props.sourceWatchlistId)
const relatedLists = computed(() => {
  const instrumentId = contextMenu.value?.row.instrumentId
  if (instrumentId == null) return []
  return membershipTargets.value.filter(target => target.instrumentIds?.includes(instrumentId))
})
const canCopyToTarget = computed(() => Boolean(contextMenu.value?.row.instrumentId && selectedMembershipTarget.value && !selectedMembershipTarget.value.locked && selectedMembershipTarget.value.id !== contextSourceWatchlistId.value))
const canMoveToTarget = computed(() => {
  const targetId = selectedMembershipTarget.value?.id
  const sourceIds = [contextSourceWatchlistId.value, props.sourceWatchlistId]
    .filter((id): id is number => id != null)
  // The parent revalidates lock/managed state against the canonical source
  // watchlist before mutating. During rapid list traversal either the row or
  // tool prop can briefly carry the destination's stale identity; keep the
  // action available when another valid source identity exists.
  return Boolean(canCopyToTarget.value && sourceIds.some(id => id !== targetId))
})
const pythonCondition = computed(() => props.pythonCondition && Number.isInteger(props.pythonCondition.code_version_id) && props.pythonCondition.code_version_id > 0 && typeof props.pythonCondition.name === 'string' ? props.pythonCondition : null)
const effectiveColumns = computed<WatchlistColumn[]>(() => ([...props.columns, ...indicatorColumns.value.map(column => ({ key: column.key, label: column.name, width: '78px', format: 'number' as const })), ...conditionColumns.value.map(column => ({ key: column.key, label: column.name, width: '78px', kind: 'boolean' as const })), ...pythonColumns.value.map(column => ({ key: pythonKey(column.code_version_id), label: column.name, width: '78px', format: 'number' as const }))] as WatchlistColumn[]).map(column => ({
  ...column,
  label: props.columnOverrides[column.key]?.label?.trim() || column.label,
  width: localColumnWidths.value[column.key] || props.columnOverrides[column.key]?.width?.trim() || column.width,
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
const renderedColumns = computed(() => {
  if (!stackedColumns.value.length) return visibleColumns.value
  // Keep the synthetic stack where the first stacked column was. This preserves
  // the user's column position and keeps the result visible when the first
  // column is stacked, rather than silently moving it past a wide virtualized
  // viewport.
  const firstStackedIndex = visibleColumns.value.findIndex(column => props.stackedColumnKeys.includes(column.key))
  const columns = visibleColumns.value.filter(column => !props.stackedColumnKeys.includes(column.key))
  columns.splice(Math.max(0, firstStackedIndex), 0, { key: stackedColumnKey, label: 'Stacked', width: 'minmax(120px, 1fr)' })
  return columns
})
const gridStyle = computed(() => ({ gridTemplateColumns: renderedColumns.value.map(column => column.width ?? 'minmax(72px, 1fr)').join(' ') }))
function estimateColumnWidth(column: WatchlistColumn) {
  const width = column.width?.trim() ?? ''
  const pixels = width.match(/^(\d+(?:\.\d+)?)px$/)
  if (pixels) return Math.max(48, Number(pixels[1]))
  const minimum = width.match(/^minmax\((\d+(?:\.\d+)?)px/)
  if (minimum) return Math.max(48, Number(minimum[1]))
  if (width.endsWith('%')) return 110
  return 116
}
const columnWidths = computed(() => renderedColumns.value.map(estimateColumnWidth))
const columnTotalWidth = computed(() => columnWidths.value.reduce((total, width) => total + width, 0))
// Keep ordinary V25-sized lists on the existing CSS grid. Once users add enough
// columns for the horizontal surface itself to become expensive, render only the
// visible column window while retaining absolute offsets in the scroll canvas.
const columnVirtualized = computed(() => renderedColumns.value.length > 12)
const columnVirtualizer = useVirtualizer(computed(() => ({
  count: renderedColumns.value.length,
  horizontal: true,
  getScrollElement: () => scrollElement.value,
  estimateSize: (index: number) => columnWidths.value[index] ?? 116,
  initialRect: { width: 480, height: 360 },
  overscan: 2,
})))
const columnVirtualItems = computed(() => {
  const items = columnVirtualizer.value.getVirtualItems()
  if (items.length || !renderedColumns.value.length) return items
  return [{ index: 0, key: 'unmeasured-first-column', size: columnWidths.value[0] ?? 116, start: 0, end: columnWidths.value[0] ?? 116, lane: 0 }]
})
const columnRenderItems = computed<ColumnRenderItem[]>(() => {
  if (!columnVirtualized.value) {
    return renderedColumns.value.map((column, index) => ({ column, index, start: 0, size: 0 }))
  }
  return columnVirtualItems.value
    .map(item => ({ column: renderedColumns.value[item.index], index: item.index, start: item.start, size: item.size }))
    .filter((item): item is ColumnRenderItem => item.column != null)
})
const headerScrollLeft = ref(0)
const headerStyle = computed(() => columnVirtualized.value
  ? { width: `${columnTotalWidth.value}px`, minWidth: `${columnTotalWidth.value}px`, transform: `translateX(-${headerScrollLeft.value}px)` }
  : gridStyle.value)
const rowCanvasStyle = computed(() => ({
  height: `${virtualizer.value.getTotalSize()}px`,
  position: 'relative' as const,
  ...(columnVirtualized.value ? { width: `${columnTotalWidth.value}px` } : {}),
}))
function columnCellStyle(item: ColumnRenderItem): CSSProperties | undefined {
  if (!columnVirtualized.value) return undefined
  return {
    position: 'absolute',
    left: `${item.start}px`,
    width: `${item.size}px`,
    top: '0',
    bottom: '0',
  }
}
function beginColumnMouseResize(event: MouseEvent, item: ColumnRenderItem) {
  if (item.column.key === stackedColumnKey) return
  const target = event.currentTarget as HTMLElement
  const width = Math.max(48, Math.round(target.parentElement?.getBoundingClientRect().width ?? estimateColumnWidth(item.column)))
  resizingColumn.value = { key: item.column.key, startX: event.clientX, startWidth: width, width }
}
function handleColumnMouseDown(event: MouseEvent, item: ColumnRenderItem) {
  const cell = event.currentTarget as HTMLElement
  if (item.column.key !== stackedColumnKey && cell.getBoundingClientRect().right - event.clientX <= 10) beginColumnMouseResize(event, item)
}
function continueColumnResize(event: PointerEvent) {
  const active = resizingColumn.value
  if (!active) return
  active.width = Math.min(600, Math.max(48, Math.round(active.startWidth + event.clientX - active.startX)))
  setColumnOverride(active.key, { width: `${active.width}px` })
}
function finishColumnResize(event: PointerEvent) {
  const active = resizingColumn.value
  if (!active) return
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture?.(event.pointerId)) target.releasePointerCapture(event.pointerId)
  setColumnOverride(active.key, { width: `${active.width}px` })
  resizingColumn.value = null
}
function handleWindowColumnMouseMove(event: MouseEvent) { continueColumnResize(event as unknown as PointerEvent) }
function handleWindowColumnMouseEnd(event: MouseEvent) { finishColumnResize(event as unknown as PointerEvent) }
function rowStyle(virtualRow: { size: number; start: number }) {
  return {
    ...(columnVirtualized.value ? { width: `${columnTotalWidth.value}px` } : gridStyle.value),
    height: `${virtualRow.size}px`,
    transform: `translateY(${virtualRow.start}px)`,
  }
}
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
  if (types.includes(CHART_PLOT_DRAG_MIME) || hasActiveAnalysisDrag()) {
    // A teleported/fixed source can dispatch dragend before Chromium delivers
    // the final dragover/drop. Refresh the bounded same-document grace while
    // the pointer is demonstrably over a compatible target.
    scheduleAnalysisDragCleanup()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
    plotDropActive.value = true
  }
}

function dragLeavePlot(event: DragEvent) {
  const current = event.currentTarget as HTMLElement | null
  const related = event.relatedTarget as Node | null
  if (!current || !related || !current.contains(related)) plotDropActive.value = false
}

function dropPlot(event: DragEvent) {
  plotDropActive.value = false
  const payload = readAnalysisDrag(event.dataTransfer)
  if (payload?.kind === 'chart-plot' || payload?.kind === 'python-plot') emit('plot-drop', payload)
  if (payload?.kind === 'technical-condition') emit('condition-drop', payload)
  clearAnalysisDrag()
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
let virtualizerAnimationFrame: number | null = null
let virtualizerSecondAnimationFrame: number | null = null
function refreshVirtualizerMeasurement() {
  virtualizer.value.measure()
  columnVirtualizer.value.measure()
}
function syncHeaderScroll() {
  headerScrollLeft.value = scrollElement.value?.scrollLeft ?? 0
}
const virtualItems = computed(() => {
  const items = virtualizer.value.getVirtualItems()
  if (items.length || !filteredRows.value.length) return items
  // A detached/hidden dock tab has no measurable rectangle. Render one row until
  // Golden Layout makes it measurable; never expand a hidden 10,000-row list.
  return [{ index: 0, key: 'unmeasured-first-row', size: 28, start: 0 }]
})
const renderedRowUniverse = ref('')
watch(filteredRows, rows => {
  // Live analysis refreshes replace row values and freshness metadata without
  // changing the symbol universe. Avoid re-measuring/recreating the virtual
  // canvas for those value-only updates: a dense row must remain clickable while
  // its cells refresh. Measure only when the actual rendered universe changes.
  const universe = rows.map(row => `${row.instrumentId ?? ''}:${row.symbol}`).join('|')
  if (universe !== renderedRowUniverse.value) {
    renderedRowUniverse.value = universe
    renderEpoch.value += 1
    virtualizer.value.measure()
  }
  const availableSymbols = new Set(rows.map(row => row.symbol))
  selectedSymbols.value = selectedSymbols.value.filter(symbol => availableSymbols.has(symbol))
  if (selectionAnchor.value && !availableSymbols.has(selectionAnchor.value)) selectionAnchor.value = null
  if (!keyboardActiveSymbol.value || !availableSymbols.has(keyboardActiveSymbol.value)) {
    keyboardActiveSymbol.value = props.selected && availableSymbols.has(props.selected)
      ? props.selected
      : rows[0]?.symbol ?? null
  }
}, { immediate: true })
watch(renderedColumns, () => columnVirtualizer.value.measure(), { deep: true })
watch(
  () => effectiveColumns.value.map(column => column.key),
  (keys, previousKeys) => {
    if (!previousKeys || keys.length <= previousKeys.length || !columnVirtualized.value) return
    const added = keys.filter(key => !previousKeys.includes(key))
    // Indicator outputs may arrive asynchronously during initial hydration;
    // revealing those would yank every freshly-opened list to its far-right
    // edge. User-promoted Python and condition columns are explicit additions
    // and should be revealed immediately.
    if (!added.some(key => key.startsWith('python:') || key.startsWith('condition:'))) return
    // Newly promoted plots/conditions/Python columns are appended to the
    // configured list. Reveal them immediately so the result is discoverable
    // and keyboard/screen-reader users do not have to hunt through a dense
    // horizontal canvas.
    void nextTick(() => {
      const reveal = () => {
        const element = scrollElement.value
        if (!element) return
        element.scrollLeft = element.scrollWidth
        syncHeaderScroll()
      }
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(reveal)
      else reveal()
    })
  },
)
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
    screeners.value = await queryClient.fetchQuery<SavedScreener[]>({
      queryKey: ['workstation', 'screeners'],
      queryFn: async () => (await api.get<SavedScreener[]>('/screeners')) ?? [],
      staleTime: 30_000,
    })
  } catch {
    conditionFilterState.value = 'Saved condition filters are unavailable.'
  }
}

function pythonKey(versionId: number) { return `python:${versionId}` }
async function loadPythonAssets() {
  try {
    const assets = await fetchCodeAssets(queryClient)
    pythonAssets.value = assets.filter(asset => asset.kind === 'column' || asset.kind === 'study').flatMap(asset => asset.versions.slice(-1).flatMap(version => version.id != null && (asset.kind === 'column' || version.output_contract === 'scalar') ? [{ versionId: version.id, name: `${asset.name} v${version.version_number}` }] : []))
    pythonConditionAssets.value = assets.filter(asset => asset.kind === 'condition' || asset.kind === 'study').flatMap(asset => asset.versions.slice(-1).flatMap(version => version.id != null && (asset.kind === 'condition' || version.output_contract === 'boolean') ? [{ versionId: version.id, name: `${asset.name} v${version.version_number}` }] : []))
  } catch { pythonAssets.value = []; pythonConditionAssets.value = [] }
}
function sleep(ms: number) { return new Promise(resolve => setTimeout(resolve, ms)) }
type PythonBatchResult = { status: string; progress?: { completed_cells?: number; total_cells?: number; status?: string }; cells: Array<{ symbol: string; status: string; value?: number | boolean; error?: string }> }
function fetchPythonBatchResult(runId: number) {
  return queryClient.fetchQuery<PythonBatchResult>({
    queryKey: ['workstation', 'research-batch-result', runId],
    queryFn: async () => {
      const result = await api.get<PythonBatchResult>(`/research/runs/${runId}/batch-results`)
      if (!result) throw new Error('Python batch refresh returned no data')
      return result
    },
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
  const nextColumns = [...pythonColumns.value, column]
  pendingPythonColumns.value = [...pendingPythonColumns.value, column]
  emit('update:pythonColumns', nextColumns)
  // A configured column set is an explicit visibility list. Keep the newly
  // promoted Python column visible immediately instead of adding it to the
  // reusable definition while silently omitting it from the rendered header.
  if (props.visibleColumnKeys.length) {
    emit('update:visibleColumnKeys', [...new Set([...props.visibleColumnKeys, pythonKey(versionId)])])
  }
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
  try {
    columnSets.value = await queryClient.fetchQuery<ColumnSetItem[]>({
      queryKey: ['workstation', 'library-items', 'column_set'],
      queryFn: async () => (await api.get<ColumnSetItem[]>('/workspaces/library/items', { kind: 'column_set' })) ?? [],
      staleTime: 30_000,
    })
  }
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
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'column_set'] })
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
  try {
    await api.delete(`/workspaces/library/items/column_set/${encodeURIComponent(item.stable_key)}`)
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'library-items', 'column_set'] })
    await loadColumnSets()
  }
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
    const universeKey = props.rows.map(row => row.instrumentId).join(',')
    const results = await queryClient.fetchQuery<ScreenerResult[]>({
      queryKey: ['workstation', 'screener-results', screenerId, 'summary', universeKey],
      queryFn: async () => (await api.get<ScreenerResult[]>(`/screeners/${screenerId}/results`, { limit: 1 })) ?? [],
      staleTime: 5_000,
    })
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
  // Golden Layout can attach a virtual tool after the initial Vue mount. At
  // that moment the scroll element may still report a zero rectangle, which
  // intentionally selects the one-row detached fallback above. Re-measure on
  // two animation frames so a now-visible tool renders its full viewport and
  // not just the first benchmark/sector row.
  refreshVirtualizerMeasurement()
  virtualizerAnimationFrame = window.requestAnimationFrame(() => {
    refreshVirtualizerMeasurement()
    virtualizerSecondAnimationFrame = window.requestAnimationFrame(refreshVirtualizerMeasurement)
  })
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

onMounted(() => {
  window.addEventListener('mousemove', handleWindowColumnMouseMove)
  window.addEventListener('mouseup', handleWindowColumnMouseEnd)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleWindowColumnMouseMove)
  window.removeEventListener('mouseup', handleWindowColumnMouseEnd)
  if (virtualizerAnimationFrame != null) window.cancelAnimationFrame(virtualizerAnimationFrame)
  if (virtualizerSecondAnimationFrame != null) window.cancelAnimationFrame(virtualizerSecondAnimationFrame)
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

function cellWarning(row: WatchlistRow, key: string): string | null {
  if (key.startsWith('indicator:')) return props.indicatorValues[key]?.[row.symbol] == null ? props.indicatorWarnings[key]?.[row.symbol] ?? null : null
  if (key.startsWith('python:')) return null
  if (key.startsWith('condition:')) return null
  const value = key === 'symbol' ? row.symbol : key === 'name' ? row.name : row.values?.[key]
  return value == null || value === '' ? row.warnings?.[key] ?? null : null
}

function display(row: WatchlistRow, key: string) {
  if (key.startsWith('indicator:')) {
    const value = props.indicatorValues[key]?.[row.symbol]
    const warning = props.indicatorWarnings[key]?.[row.symbol]
    return value == null ? '—' : formatNumeric(key, value)
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
    return '—'
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
  keyboardActiveSymbol.value = row.symbol
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
  contextRowElement.value = event.currentTarget as HTMLElement
  membershipTargetId.value = ''
  membershipInspectionOpen.value = false
  contextMenu.value = { row, left: Math.max(2, event.clientX - (bounds?.left ?? 0)), top: Math.max(2, event.clientY - (bounds?.top ?? 0)) }
  void nextTick(() => focusContextMenuItem(0))
}

function runContextAction(action: 'chart' | 'compare' | 'ratio' | 'note' | 'alert' | 'copy' | 'copy-to-watchlist' | 'move-to-watchlist' | 'flag' | 'remove') {
  if (!contextMenu.value) return
  const row = contextMenu.value.row
  const targetId = Number(membershipTargetId.value)
  const selectedRows = contextSelectionRows.value
  contextMenu.value = null
  if ((action === 'copy-to-watchlist' || action === 'move-to-watchlist') && Number.isInteger(targetId) && targetId > 0) {
    if (selectedRows.length > 1) emit('row-action', action, row, targetId, selectedRows)
    else emit('row-action', action, row, targetId)
  } else {
    if (selectedRows.length > 1) emit('row-action', action, row, undefined, selectedRows)
    else emit('row-action', action, row)
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
  if (changes.width?.trim()) localColumnWidths.value[key] = changes.width.trim()
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
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) return
  event.preventDefault()
  const current = filteredRows.value.findIndex(row => row.symbol === (keyboardActiveSymbol.value || props.selected))
  if (event.key === 'Enter') {
    if (current >= 0) emit('select', filteredRows.value[current])
    return
  }
  if (!filteredRows.value.length) return
  let next: number
  if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = filteredRows.value.length - 1
  else {
    const forward = event.key === 'ArrowDown' || (event.key === ' ' && !event.shiftKey)
    const origin = current < 0 ? (forward ? -1 : filteredRows.value.length) : current
    next = Math.max(0, Math.min(filteredRows.value.length - 1, origin + (forward ? 1 : -1)))
  }
  const row = filteredRows.value[next]
  if (!row) return
  keyboardActiveSymbol.value = row.symbol
  virtualizer.value.scrollToIndex(next, { align: 'auto' })
  selectRow(row, { shiftKey: event.shiftKey, ctrlKey: event.ctrlKey, metaKey: event.metaKey } as MouseEvent)
}

function onCtrlWheel(event: WheelEvent) {
  const current = filteredRows.value.findIndex(row => row.symbol === props.selected)
  const direction = event.deltaY > 0 ? 1 : -1
  const next = Math.max(0, Math.min(filteredRows.value.length - 1, current + direction))
  if (filteredRows.value[next]) {
    keyboardActiveSymbol.value = filteredRows.value[next].symbol
    virtualizer.value.scrollToIndex(next, { align: 'auto' })
    selectRow(filteredRows.value[next], { shiftKey: false, ctrlKey: false, metaKey: false } as MouseEvent)
  }
}
</script>

<style scoped>
.watchlist { position: relative; display: grid; height: 100%; min-height: 0; grid-template-rows: 23px auto minmax(0, 1fr); color: #c7d0d8; background: #11161b; font: 11px/1.2 "Segoe UI", Arial, sans-serif; }
.watchlist--plot-drop-active { outline: 1px solid #69a9d2; outline-offset: -1px; }
.watchlist__plot-drop-hint { position: absolute; z-index: 4; inset: 3px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #69a9d2; background: #193040eF; color: #dcecf6; text-align: center; pointer-events: none; }
.watchlist__drop-error { position: absolute; z-index: 4; inset: 3px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #9e5b5b; background: #3a1d1d; color: #f1b0b0; pointer-events: none; }
.watchlist__loading-status { position: absolute; z-index: 3; inset: 25px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #4d7084; background: #193040eF; color: #c7e4f4; text-align: center; pointer-events: none; }
.watchlist__data-error { position: absolute; z-index: 3; inset: 25px 3px auto; margin: 0; padding: 4px 6px; border: 1px solid #9e5b5b; background: #3a1d1d; color: #f1b0b0; text-align: center; pointer-events: none; }
.watchlist--columns-open, .watchlist--sets-open { grid-template-rows: 23px auto auto minmax(0, 1fr); }
.watchlist--condition-open { grid-template-rows: 23px auto auto minmax(0, 1fr); }
.watchlist--grouped { grid-template-rows: 23px 32px minmax(0, 1fr); }
.watchlist--condition-open.watchlist--grouped { grid-template-rows: 23px auto 32px minmax(0, 1fr); }
.watchlist--columns-open.watchlist--grouped,.watchlist--sets-open.watchlist--grouped { grid-template-rows: 23px auto auto 32px minmax(0, 1fr); }
.watchlist__controls { display: flex; align-items: center; gap: 6px; padding: 0 7px; color: #84939e; background: #181f25; border-bottom: 1px solid #2b343c; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.watchlist__controls input { min-width: 0; width: 80px; margin-left: auto; padding: 1px 4px; border: 1px solid #3d4a54; background: #11161b; color: #dce9f2; font: inherit; text-transform: none; }
.watchlist__controls select { min-width: 0; max-width: 120px; padding: 1px 2px; border: 1px solid #3d4a54; background: #11161b; color: #a9c0d0; font: inherit; text-transform: none; }
.watchlist__columns-button { border: 1px solid #3d4a54; background: #1b252d; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__controls b { color: #78aac8; font-weight: 600; }.watchlist__compare-button { border: 1px solid #4b697b; background: #1e3b4c; color: #d9edf7; padding: 1px 5px; font: inherit; cursor: pointer; }.watchlist__compare-button:hover { background: #2a5268; }
.watchlist__column-menu { display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; min-height: 0; max-height: min(220px, 42vh); overflow: auto; padding: 3px 5px 4px; background: #151b20; border-bottom: 1px solid #384550; color: #b7c6d0; font-size: 10px; text-transform: none; letter-spacing: normal; }
.watchlist__column-clipboard { position: sticky; z-index: 1; top: -3px; display: flex; align-items: center; gap: 4px; min-height: 20px; padding: 2px 0; background: #151b20; border-bottom: 1px solid #2d3942; }
.watchlist__column-clipboard button { border: 1px solid #42515c; background: #1d2a33; color: #d7e3eb; padding: 2px 5px; font: inherit; cursor: pointer; }
.watchlist__column-clipboard small { overflow: hidden; color: #8498a6; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__column-set-menu { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:4px 7px; background:#202b33; border-bottom:1px solid #384550; color:#b7c6d0; font-size:10px; }.watchlist__column-set-menu input,.watchlist__column-set-menu button{min-width:0;border:1px solid #42515c;background:#182128;color:#d7e3eb;font:inherit;padding:1px 4px}.watchlist__column-set-menu input{width:108px}.watchlist__column-set-menu span{display:flex;gap:2px}.watchlist__column-set-menu small{color:#8498a6}.watchlist__column-set-error{color:#e49a9a!important}
.watchlist__condition-state { overflow: hidden; margin: 0; padding: 2px 7px; border-bottom: 1px solid #2b343c; color: #8498a6; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__column-menu label { display: grid; grid-template-columns: 15px minmax(62px, 1fr) 40px 36px 30px 18px 18px 54px 38px 38px 38px; align-items: center; gap: 2px; min-height: 22px; padding: 1px 3px; border: 1px solid transparent; background: #1a2228; white-space: nowrap; cursor: grab; }
.watchlist__column-menu label:hover { border-color: #3b5667; background: #202d36; }
.watchlist__column-editor-row--dragging { opacity: .55; }
.watchlist__column-menu input, .watchlist__column-menu select { min-width: 0; height: 18px; margin: 0; border: 1px solid #42515c; background: #182128; color: #c7d0d8; font: inherit; }
.watchlist__label-input { width: auto; }
.watchlist__width-input { width: auto; }
.watchlist__format-input { width: auto; }
.watchlist__decimals-input { width: auto; }
.watchlist__group-input { width: auto; }
.watchlist__order-button { min-width: 18px; height: 18px; border: 1px solid #42515c; background: #182128; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__order-button:disabled { cursor: default; opacity: .45; }
.watchlist__stack-button, .watchlist__pin-button, .watchlist__copy-button { min-width: 0; height: 18px; border: 1px solid #42515c; background: #182128; color: #a9c0d0; font: inherit; cursor: pointer; }
.watchlist__stack-button[aria-pressed="true"] { border-color: #5faed7; background: #1d4057; color: #e3f2fb; }
.watchlist__header-viewport { position: relative; z-index: 3; min-width: 0; overflow: hidden; }
.watchlist__header, .watchlist__row { display: grid; min-width: 0; }
.watchlist__header { position: relative; min-height: 23px; background: #20282f; border-bottom: 1px solid #313c45; }
.watchlist__header-cell { position: relative; display: flex; min-width: 0; min-height: 23px; }
.watchlist__header-cell > button, .watchlist__header-cell > .watchlist__stack-header { min-width: 0; width: 100%; height: 100%; }
.watchlist__header button { min-width: 0; border: 0; border-right: 1px solid #303a43; background: transparent; color: #97a9b6; overflow: hidden; padding: 4px 7px 4px 6px; text-align: left; text-overflow: ellipsis; white-space: nowrap; font: 600 9px "Segoe UI", Arial, sans-serif; text-transform: uppercase; cursor: pointer; }
.watchlist__header button:hover { color: #e5f1f7; background: #29343d; }
.watchlist__stack-header { display: grid; min-width: 0; grid-auto-rows: 1fr; border-right: 1px solid #303a43; }
.watchlist__stack-header button { border-right: 0; }
.watchlist__column-resize-handle { position: absolute; z-index: 20; display: block; pointer-events: auto; top: 0; right: -3px; bottom: 0; width: 7px; cursor: col-resize; }
.watchlist__column-resize-handle::after { content: ''; position: absolute; top: 4px; bottom: 4px; left: 3px; width: 1px; background: transparent; }
.watchlist__column-resize-handle:hover::after, .watchlist__column-resize-handle:focus-visible::after { background: #6eb6dc; }
.watchlist__column-resize-handle:focus-visible { outline: 1px solid #6eb6dc; outline-offset: -1px; }
.watchlist__header small { color: #78b9e4; }
.watchlist__header em { display: block; overflow: hidden; color: #718c9f; font: 8px "Segoe UI", Arial, sans-serif; font-style: normal; text-transform: none; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__scroll { min-height: 0; overflow: auto; outline: none; }
.watchlist__row { position: absolute; left: 0; align-items: center; border: 0; border-bottom: 1px solid #20282f; background: transparent; color: inherit; text-align: left; cursor: pointer; }
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
.watchlist__row span[style*="position: absolute"] { display: flex; align-items: center; }
.watchlist__row .watchlist__cell--positive { color: #72c995; }
.watchlist__row .watchlist__cell--negative { color: #df8b8b; }
.watchlist__row .watchlist__cell--zero { color: #a8b6bf; }
.watchlist__row span:first-child { color: #dce9f2; font-weight: 600; }
.watchlist__stack-cell { display: grid; min-width: 0; align-self: stretch; padding: 1px 6px; }
.watchlist__stack-cell small { overflow: hidden; color: #8999a5; font: 9px/1.15 "Segoe UI", Arial, sans-serif; text-overflow: ellipsis; white-space: nowrap; }
.watchlist__stack-cell em { display: inline-block; min-width: 27px; margin-right: 4px; color: #718c9f; font-style: normal; }
</style>
