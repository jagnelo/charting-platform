<template>
  <section class="market-map-tool" aria-label="Universe market map" :aria-busy="loading ? 'true' : 'false'">
    <div class="market-map-tool__controls">
      <label>Universe
        <select v-model="sourceId" aria-label="Market Map universe" :disabled="loadingSources">
          <option value="">Select a universe</option>
          <option v-for="source in sources" :key="source.source_id" :value="source.source_id">
            {{ source.name }}{{ source.locked ? ' · Managed' : '' }}
          </option>
        </select>
      </label>
      <label>Group
        <select v-model="groupBy" aria-label="Market Map grouping">
          <option value="sector_industry">Sector → Industry</option>
          <option value="sector">Sector</option>
          <option value="industry">Industry</option>
          <option value="none">Ungrouped</option>
        </select>
      </label>
      <label>Period
        <select v-model="period" aria-label="Market Map period">
          <option v-for="value in periods" :key="value" :value="value">{{ value }}</option>
        </select>
      </label>
      <label>Area
        <select v-model="areaMetric" aria-label="Market Map area metric">
          <option value="market_cap">Market cap</option><option value="weight">Source weight</option><option value="equal">Equal</option><option value="volume">Volume</option>
        </select>
      </label>
      <label>Colour
        <select v-model="colorMetric" aria-label="Market Map colour metric">
          <option value="return">Return</option><option value="relative_return">Relative return</option><option value="rsi_14">RSI(14)</option><option value="relative_volume">Relative volume</option><option value="distance_52w_high">Distance to 52W high</option><option value="distance_52w_low">Distance to 52W low</option>
        </select>
      </label>
      <label v-if="colorMetric === 'relative_return'">Reference
        <input v-model="referenceSymbol" aria-label="Market Map relative-return reference" placeholder="SPY" maxlength="20" />
      </label>
      <button type="button" class="market-map-tool__run" :disabled="loading || !sourceId" @click="run">{{ loading ? 'Loading…' : 'Refresh' }}</button>
      <label>Snapshot
        <select v-model="snapshotSelectionId" aria-label="Market Map snapshot" :disabled="snapshotLoading">
          <option value="">Live / cached result</option>
          <option v-for="snapshot in snapshots" :key="snapshot.id" :value="String(snapshot.id)">{{ snapshot.name }}</option>
        </select>
      </label>
      <input v-model="snapshotName" aria-label="Market Map snapshot name" placeholder="Snapshot name" maxlength="160" />
      <button type="button" :disabled="snapshotLoading || !map || !snapshotName.trim()" @click="saveSnapshot">{{ snapshotLoading ? 'Saving…' : 'Save snapshot' }}</button>
      <button v-if="snapshotSelectionId" type="button" :disabled="snapshotLoading" @click="deleteSnapshot">Delete snapshot</button>
    </div>
    <p v-if="sourcesError" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ sourcesError }}</p>
    <p v-if="error" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ error }}</p>
    <p v-if="snapshotError" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ snapshotError }}</p>
    <p v-if="map?.warnings.length" class="market-map-tool__status" role="status">{{ map.warnings.map(item => item.message).join(' · ') }}</p>
    <div v-if="map" class="market-map-tool__summary">
      <span>{{ map.source.name }}</span><span>{{ map.evaluated_count }}/{{ map.requested_count }} covered</span><span>{{ formatFreshness(map.freshness) }}</span><span v-if="activeSnapshotName">Snapshot · {{ activeSnapshotName }}</span><span v-else-if="map.cache_hit">Cached result · {{ map.cached_at ? new Date(map.cached_at).toLocaleTimeString() : 'saved' }}</span><span v-if="map.source.locked">Locked source · {{ map.source.membership_version }}</span>
    </div>
    <div v-if="map" class="market-map-tool__nodes" aria-label="Market Map groups">
      <button v-if="selectedNode" type="button" aria-label="Market Map parent group" @click="selectNode(activeNode?.parent_id ?? null)">← Up</button>
      <button v-for="node in visibleNodes" :key="node.node_id" type="button" :class="{ active: selectedNode === node.node_id }" @click="selectNode(node.node_id)">{{ node.label }} <small>{{ node.member_count }}</small></button>
    </div>
    <nav v-if="map" class="market-map-tool__breadcrumbs" aria-label="Market Map hierarchy">
      <button type="button" :class="{ active: !selectedNode }" @click="selectNode(null)">All members</button>
      <template v-for="node in breadcrumbs" :key="node.node_id">
        <span aria-hidden="true">›</span>
        <button type="button" :class="{ active: selectedNode === node.node_id }" @click="selectNode(node.node_id)">{{ node.label }}</button>
      </template>
    </nav>
    <div v-if="map" class="market-map-tool__legend" aria-label="Market Map colour legend"><span class="market-map-tool__legend--negative">−</span><span>{{ colorLabel }}</span><span class="market-map-tool__legend--positive">+</span><span class="market-map-tool__legend__coverage">Coverage {{ Math.round(map.coverage * 100) }}%</span></div>
    <div v-if="map" class="market-map-tool__viewport-controls" aria-label="Market Map viewport controls">
      <button type="button" aria-label="Zoom out Market Map" :disabled="viewportZoom <= 1" @click="zoomBy(-0.25)">−</button>
      <span aria-live="polite">{{ Math.round(viewportZoom * 100) }}%</span>
      <button type="button" aria-label="Zoom in Market Map" :disabled="viewportZoom >= 4" @click="zoomBy(0.25)">+</button>
      <button type="button" aria-label="Reset Market Map viewport" :disabled="viewportZoom === 1 && !panX && !panY" @click="resetViewport">Reset</button>
      <small v-if="viewportZoom > 1">Drag empty map space or use the wheel to pan and zoom.</small>
    </div>
    <div v-if="map && selectedIds.length" class="market-map-tool__selection-actions" aria-label="Market Map selection actions">
      <strong>{{ selectedIds.length }} selected</strong>
      <select v-model="publicationTargetId" aria-label="Market Map target watchlist">
        <option value="">New personal watchlist…</option>
        <option v-for="target in publicationTargets" :key="target.id" :value="String(target.id)">{{ target.name }}</option>
      </select>
      <input v-if="!publicationTargetId" v-model="newPublicationName" aria-label="Market Map new watchlist name" placeholder="Watchlist name" maxlength="80" @keydown.enter.prevent="publishSelection" />
      <button type="button" :disabled="publishing || (!publicationTargetId && !newPublicationName.trim())" @click="publishSelection">{{ publishing ? 'Saving…' : 'Save selection' }}</button>
      <button type="button" aria-label="Open source in Market Breadth" @click="publishAnalysis('breadth')">Open source in Breadth</button>
      <button type="button" aria-label="Open source in Study Lab" @click="publishAnalysis('study_lab')">Open source in Study Lab</button>
      <span v-if="publicationMessage" role="status">{{ publicationMessage }}</span>
      <span v-if="publicationError" class="market-map-tool__status--error" role="alert">{{ publicationError }}</span>
    </div>
    <div v-if="map" ref="viewportRef" class="market-map-tool__tiles" aria-label="Market Map tiles" @wheel.prevent="zoomByWheel" @pointerdown="startPan" @pointermove="movePan" @pointerup="endPan" @pointercancel="endPan">
      <div class="market-map-tool__canvas" :style="canvasStyle">
        <button v-for="cell in visibleLayoutCells" :key="cell.instrument_id" type="button" class="market-map-tool__tile" :class="[tileClass(cell.color_value), { 'market-map-tool__tile--selected': selectedIds.includes(cell.instrument_id) }]" :style="tileStyle(cell)" :title="`${cell.symbol} · ${cell.name}`" @pointerdown.stop @mouseenter="hoveredCell = cell" @mouseleave="hoveredCell = null" @click="selectCell($event, cell)">
          <strong>{{ cell.symbol }}</strong><span>{{ formatMetric(cell.color_value) }}</span><small>{{ cell.group_path.join(' · ') || 'All members' }}</small>
        </button>
        <p v-if="!visibleCells.length" class="market-map-tool__status">No covered members match this group.</p>
      </div>
    </div>
    <aside v-if="hoveredCell" class="market-map-tool__hover" role="status"><strong>{{ hoveredCell.symbol }}</strong><span>{{ hoveredCell.name }}</span><span>{{ hoveredCell.group_path.join(' · ') || 'All members' }}</span><span v-if="hoveredCell.warnings.length">{{ hoveredCell.warnings.map(item => item.message).join(' · ') }}</span></aside>
    <p v-if="!map && !loading" class="market-map-tool__status">Choose a managed index/ETF universe or personal watchlist to build a map.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useWatchlistStore } from '@/stores/watchlist'
import { deleteMarketMapSnapshot, fetchMarketMap, fetchMarketMapSnapshot, fetchMarketMapSnapshots, layoutMarketMapCells, saveMarketMapSnapshot, type MarketMapLayoutCell } from '@/lib/workstation/marketMap'
import type { MarketMap, MarketMapAreaMetric, MarketMapCell, MarketMapColorMetric, MarketMapGroupBy, MarketMapSnapshotSummary, WatchlistSource } from '@/types'

const props = withDefaults(defineProps<{ configuration?: Record<string, unknown> }>(), { configuration: () => ({}) })
const emit = defineEmits<{
  configuration: [value: Record<string, unknown>]
  select: [symbol: string, instrumentId: number]
  publishAnalysis: [payload: { target: 'breadth' | 'study_lab'; sourceId: string; selectedIds: number[]; selectedSymbols: string[] }]
}>()
const watchlistStore = useWatchlistStore()
const sources = computed(() => watchlistStore.watchlistSources)
const sourceId = ref(String(props.configuration.source_id ?? ''))
const groupBy = ref<MarketMapGroupBy>((props.configuration.group_by as MarketMapGroupBy) ?? 'sector_industry')
const period = ref(String(props.configuration.period ?? '1D'))
const areaMetric = ref<MarketMapAreaMetric>((props.configuration.area_metric as MarketMapAreaMetric) ?? 'market_cap')
const colorMetric = ref<MarketMapColorMetric>((props.configuration.color_metric as MarketMapColorMetric) ?? 'return')
const referenceSymbol = ref(String(props.configuration.reference_symbol ?? ''))
const periods = ['1D', '1W', 'MTD', 'YTD', '1M', '3M', '6M', '1Y']
const loading = ref(false)
const error = ref('')
const map = ref<MarketMap | null>(null)
const selectedNode = ref<string | null>(null)
const selectedIds = ref<number[]>([])
const hoveredCell = ref<MarketMapCell | null>(null)
const viewportRef = ref<HTMLElement | null>(null)
const viewportZoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const panStart = ref<{ pointerX: number; pointerY: number; x: number; y: number } | null>(null)
const publicationTargetId = ref('')
const newPublicationName = ref('')
const publishing = ref(false)
const publicationMessage = ref('')
const publicationError = ref('')
const snapshots = ref<MarketMapSnapshotSummary[]>([])
const snapshotSelectionId = ref('')
const snapshotName = ref('')
const activeSnapshotName = ref('')
const snapshotLoading = ref(false)
const snapshotError = ref('')
const skipNextSourceRun = ref(false)
const loadingSources = computed(() => watchlistStore.watchlistSourcesLoading)
const sourcesError = computed(() => watchlistStore.watchlistSourcesError)
const publicationTargets = computed(() => watchlistStore.watchlists.filter(watchlist => !watchlist.is_managed && !watchlist.is_locked))

function formatFreshness(value: string) { return value.replace(/_/g, ' ') }
function formatMetric(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (colorMetric.value === 'rsi_14') return value.toFixed(1)
  return `${(value * 100).toFixed(2)}%`
}
function tileClass(value: number | null | undefined) {
  if (value == null) return 'market-map-tool__tile--unknown'
  return value >= 0 ? 'market-map-tool__tile--positive' : 'market-map-tool__tile--negative'
}
function tileStyle(cell: MarketMapLayoutCell) {
  return { left: `${cell.x}%`, top: `${cell.y}%`, width: `${cell.width}%`, height: `${cell.height}%` }
}
function selectCell(event: MouseEvent, cell: MarketMapCell) {
  const additive = event.shiftKey || event.ctrlKey || event.metaKey
  selectedIds.value = additive
    ? (selectedIds.value.includes(cell.instrument_id) ? selectedIds.value.filter(id => id !== cell.instrument_id) : [...selectedIds.value, cell.instrument_id])
    : [cell.instrument_id]
  emit('select', cell.symbol, cell.instrument_id)
}
const activeNode = computed(() => map.value?.nodes.find(node => node.node_id === selectedNode.value) ?? null)
const visibleNodes = computed(() => {
  const parentId = selectedNode.value ?? 'root'
  return (map.value?.nodes ?? []).filter(node => node.node_id !== 'root' && (node.parent_id ?? 'root') === parentId)
})
const breadcrumbs = computed(() => {
  if (!activeNode.value || !map.value) return []
  return activeNode.value.group_path
    .map((_, index) => activeNode.value?.group_path.slice(0, index + 1) ?? [])
    .map(path => map.value?.nodes.find(node => node.group_path.length === path.length && node.group_path.every((part, index) => part === path[index])))
    .filter((node): node is NonNullable<typeof node> => Boolean(node))
})
const visibleCells = computed(() => {
  if (!map.value) return []
  const path = activeNode.value?.group_path ?? []
  if (!path.length) return map.value.cells
  return map.value.cells.filter(cell => path.every((part, index) => cell.group_path[index] === part))
})
const visibleLayoutCells = computed<MarketMapLayoutCell[]>(() => layoutMarketMapCells(visibleCells.value))
const colorLabel = computed(() => colorMetric.value.replace(/_/g, ' '))
const canvasStyle = computed(() => ({ transform: `translate(${panX.value}%, ${panY.value}%) scale(${viewportZoom.value})` }))

function selectNode(nodeId: string | null) {
  selectedNode.value = nodeId
  selectedIds.value = []
  resetViewport()
}
function clampPan(value: number) {
  const limit = (viewportZoom.value - 1) * 100
  return Math.max(-limit, Math.min(0, value))
}
function resetViewport() {
  viewportZoom.value = 1
  panX.value = 0
  panY.value = 0
  panStart.value = null
}
function zoomBy(delta: number) {
  const next = Math.max(1, Math.min(4, Number((viewportZoom.value + delta).toFixed(2))))
  viewportZoom.value = next
  panX.value = clampPan(panX.value)
  panY.value = clampPan(panY.value)
}
function zoomByWheel(event: WheelEvent) {
  zoomBy(event.deltaY > 0 ? -0.25 : 0.25)
}
function startPan(event: PointerEvent) {
  if (viewportZoom.value <= 1 || (event.target instanceof Element && event.target.closest('button'))) return
  const element = event.currentTarget
  if (!(element instanceof HTMLElement)) return
  panStart.value = { pointerX: event.clientX, pointerY: event.clientY, x: panX.value, y: panY.value }
  element.setPointerCapture(event.pointerId)
}
function movePan(event: PointerEvent) {
  if (!panStart.value || !viewportRef.value) return
  const bounds = viewportRef.value.getBoundingClientRect()
  panX.value = clampPan(panStart.value.x + ((event.clientX - panStart.value.pointerX) / Math.max(bounds.width, 1)) * 100)
  panY.value = clampPan(panStart.value.y + ((event.clientY - panStart.value.pointerY) / Math.max(bounds.height, 1)) * 100)
}
function endPan(event: PointerEvent) {
  const element = event.currentTarget
  if (element instanceof HTMLElement && element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId)
  panStart.value = null
}
async function publishSelection() {
  if (!selectedIds.value.length || publishing.value) return
  publishing.value = true
  publicationMessage.value = ''
  publicationError.value = ''
  try {
    let targetId = Number(publicationTargetId.value)
    if (!Number.isInteger(targetId) || targetId <= 0) {
      const name = newPublicationName.value.trim()
      if (!name) return
      const created = await watchlistStore.createWatchlist(name)
      if (!created) throw new Error('Unable to create personal watchlist')
      targetId = created.id
      publicationTargetId.value = String(targetId)
    }
    const results = await Promise.all(selectedIds.value.map(instrumentId => watchlistStore.addItem(targetId, instrumentId)))
    const added = results.filter(Boolean).length
    publicationMessage.value = `${added} selected member${added === 1 ? '' : 's'} saved`
  } catch (cause) {
    publicationError.value = cause instanceof Error ? cause.message : 'Unable to save selected members'
  } finally {
    publishing.value = false
  }
}

function publishAnalysis(target: 'breadth' | 'study_lab') {
  if (!sourceId.value || !selectedIds.value.length) return
  const selectedSymbols = selectedIds.value
    .map(instrumentId => map.value?.cells.find(cell => cell.instrument_id === instrumentId)?.symbol)
    .filter((symbol): symbol is string => Boolean(symbol))
  emit('publishAnalysis', {
    target,
    sourceId: sourceId.value,
    selectedIds: [...selectedIds.value],
    selectedSymbols,
  })
}

async function loadSnapshot() {
  const snapshotId = Number(snapshotSelectionId.value)
  if (!Number.isInteger(snapshotId) || snapshotId <= 0) {
    activeSnapshotName.value = ''
    return
  }
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const snapshot = await fetchMarketMapSnapshot(snapshotId)
    skipNextSourceRun.value = true
    sourceId.value = snapshot.source_id
    map.value = snapshot.map
    activeSnapshotName.value = snapshot.name
    snapshotName.value = snapshot.name
    selectedNode.value = null
    selectedIds.value = []
    resetViewport()
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to load Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

async function saveSnapshot() {
  if (!map.value || !snapshotName.value.trim() || snapshotLoading.value) return
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    const snapshot = await saveMarketMapSnapshot(snapshotName.value.trim(), map.value.cache_key)
    snapshots.value = [snapshot, ...snapshots.value.filter(item => item.id !== snapshot.id)]
    snapshotSelectionId.value = String(snapshot.id)
    activeSnapshotName.value = snapshot.name
    snapshotName.value = snapshot.name
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to save Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

async function deleteSnapshot() {
  const snapshotId = Number(snapshotSelectionId.value)
  if (!Number.isInteger(snapshotId) || snapshotId <= 0 || snapshotLoading.value) return
  snapshotLoading.value = true
  snapshotError.value = ''
  try {
    await deleteMarketMapSnapshot(snapshotId)
    snapshots.value = snapshots.value.filter(item => item.id !== snapshotId)
    snapshotSelectionId.value = ''
    activeSnapshotName.value = ''
    snapshotName.value = ''
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to delete Market Map snapshot'
  } finally {
    snapshotLoading.value = false
  }
}

async function run() {
  if (!sourceId.value) return
  loading.value = true
  error.value = ''
  try {
    map.value = await fetchMarketMap({ source_id: sourceId.value, group_by: groupBy.value, period: period.value, area_metric: areaMetric.value, color_metric: colorMetric.value, reference_symbol: colorMetric.value === 'relative_return' ? referenceSymbol.value.toUpperCase() : null, timeframe: 'D1', adjusted: true })
    snapshotSelectionId.value = ''
    activeSnapshotName.value = ''
    selectedNode.value = null
    selectedIds.value = []
    resetViewport()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Unable to load Market Map'
  } finally {
    loading.value = false
  }
}
function persist() {
  emit('configuration', { ...props.configuration, source_id: sourceId.value, group_by: groupBy.value, period: period.value, area_metric: areaMetric.value, color_metric: colorMetric.value, reference_symbol: referenceSymbol.value })
}
watch([sourceId, groupBy, period, areaMetric, colorMetric, referenceSymbol], persist)
watch(sourceId, () => {
  if (skipNextSourceRun.value) {
    skipNextSourceRun.value = false
    return
  }
  if (sourceId.value) void run()
})
watch(snapshotSelectionId, () => { void loadSnapshot() })
onMounted(async () => {
  if (!sources.value.length) await watchlistStore.loadWatchlistSources()
  if (!watchlistStore.watchlists.length) await watchlistStore.loadWatchlists()
  try {
    snapshots.value = await fetchMarketMapSnapshots()
  } catch (cause) {
    snapshotError.value = cause instanceof Error ? cause.message : 'Unable to load Market Map snapshots'
  }
  if (!sourceId.value) {
    const preferred = sources.value.find((item: WatchlistSource) => item.source_kind === 'index_membership' || item.source_kind === 'etf_holdings') ?? sources.value[0]
    if (preferred) sourceId.value = preferred.source_id
  }
  if (sourceId.value) await run()
})
</script>

<style scoped>
.market-map-tool { display: flex; flex-direction: column; gap: 8px; min-height: 100%; background: #11161d; color: #d4d9e2; font-size: 12px; }
.market-map-tool__controls { display: flex; flex-wrap: wrap; gap: 6px; align-items: end; padding: 8px; background: #1b222c; border-bottom: 1px solid #303a48; }
.market-map-tool__controls label { display: flex; flex-direction: column; gap: 3px; color: #8e9bad; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.market-map-tool select, .market-map-tool input, .market-map-tool button { border: 1px solid #3c4858; background: #151c25; color: #d4d9e2; border-radius: 2px; padding: 5px 7px; font: inherit; }
.market-map-tool__run { background: #2d8cff !important; border-color: #2d8cff !important; color: white !important; cursor: pointer; }
.market-map-tool__run:disabled { opacity: .55; cursor: default; }
.market-map-tool__status { margin: 0; padding: 6px 9px; color: #aeb8c7; }
.market-map-tool__status--error { color: #ff9898; }
.market-map-tool__summary, .market-map-tool__nodes, .market-map-tool__breadcrumbs, .market-map-tool__viewport-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 0 8px; color: #9eabbb; }
.market-map-tool__summary span:first-child { color: #f1f4f8; font-weight: 700; }
.market-map-tool__nodes button { cursor: pointer; }
.market-map-tool__nodes button.active { border-color: #70b4ff; color: #fff; }
.market-map-tool__nodes small { color: #8e9bad; }
.market-map-tool__breadcrumbs { gap: 5px; color: #8e9bad; }
.market-map-tool__breadcrumbs button { padding: 3px 5px; cursor: pointer; }
.market-map-tool__breadcrumbs button.active { border-color: #70b4ff; color: #fff; }
.market-map-tool__viewport-controls { justify-content: flex-end; }
.market-map-tool__viewport-controls button { min-width: 26px; padding: 3px 6px; cursor: pointer; }
.market-map-tool__viewport-controls button:disabled { cursor: default; opacity: .5; }
.market-map-tool__viewport-controls small { margin-left: auto; color: #7d8a9b; }
.market-map-tool__selection-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; padding: 4px 8px; border-top: 1px solid #303a48; border-bottom: 1px solid #303a48; background: #18212c; }
.market-map-tool__selection-actions strong { color: #f7d87b; }
.market-map-tool__selection-actions button { cursor: pointer; }
.market-map-tool__selection-actions button:disabled { cursor: default; opacity: .55; }
.market-map-tool__selection-actions span[role="status"] { color: #82e2ac; }
.market-map-tool__legend { display: flex; gap: 8px; align-items: center; padding: 2px 8px; color: #aeb8c7; text-transform: capitalize; }
.market-map-tool__legend--negative { color: #ff9a9a; font-weight: 800; }.market-map-tool__legend--positive { color: #82e2ac; font-weight: 800; }.market-map-tool__legend__coverage { margin-left: auto; text-transform: none; }
.market-map-tool__tiles { position: relative; min-height: 300px; margin: 0 8px 8px; overflow: hidden; border: 1px solid #303a48; background: #0d1218; cursor: grab; touch-action: none; }
.market-map-tool__tiles:active { cursor: grabbing; }
.market-map-tool__canvas { position: absolute; inset: 0; transform-origin: top left; transition: transform 120ms ease-out; }
.market-map-tool__tile { position: absolute; display: flex; min-width: 28px; min-height: 28px; flex-direction: column; justify-content: center; align-items: center; gap: 3px; cursor: pointer; color: #fff !important; overflow: hidden; border-radius: 0 !important; }
.market-map-tool__tile strong { font-size: 16px; }
.market-map-tool__tile small { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .75; }
.market-map-tool__tile--positive { background: #207d56 !important; }
.market-map-tool__tile--negative { background: #843f50 !important; }
.market-map-tool__tile--unknown { background: #3c4652 !important; }
.market-map-tool__tile--selected { outline: 2px solid #f7d87b; outline-offset: -2px; z-index: 2; }
.market-map-tool__hover { position: absolute; right: 12px; bottom: 12px; z-index: 5; display: flex; flex-direction: column; gap: 2px; max-width: 300px; padding: 8px 10px; border: 1px solid #60758d; background: #18222e; box-shadow: 0 4px 18px #0008; }
</style>
