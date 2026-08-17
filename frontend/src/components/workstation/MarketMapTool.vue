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
    </div>
    <p v-if="sourcesError" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ sourcesError }}</p>
    <p v-if="error" class="market-map-tool__status market-map-tool__status--error" role="alert">{{ error }}</p>
    <p v-if="map?.warnings.length" class="market-map-tool__status" role="status">{{ map.warnings.map(item => item.message).join(' · ') }}</p>
    <div v-if="map" class="market-map-tool__summary">
      <span>{{ map.source.name }}</span><span>{{ map.evaluated_count }}/{{ map.requested_count }} covered</span><span>{{ formatFreshness(map.freshness) }}</span><span v-if="map.source.locked">Locked source · {{ map.source.membership_version }}</span>
    </div>
    <div v-if="map" class="market-map-tool__nodes" aria-label="Market Map groups">
      <button v-for="node in visibleNodes" :key="node.node_id" type="button" :class="{ active: selectedNode === node.node_id }" @click="selectedNode = selectedNode === node.node_id ? null : node.node_id">{{ node.label }} <small>{{ node.member_count }}</small></button>
    </div>
    <div v-if="map" class="market-map-tool__legend" aria-label="Market Map colour legend"><span class="market-map-tool__legend--negative">−</span><span>{{ colorLabel }}</span><span class="market-map-tool__legend--positive">+</span><span class="market-map-tool__legend__coverage">Coverage {{ Math.round(map.coverage * 100) }}%</span></div>
    <div v-if="map" class="market-map-tool__tiles" aria-label="Market Map tiles">
      <button v-for="cell in visibleLayoutCells" :key="cell.instrument_id" type="button" class="market-map-tool__tile" :class="[tileClass(cell.color_value), { 'market-map-tool__tile--selected': selectedIds.includes(cell.instrument_id) }]" :style="tileStyle(cell)" :title="`${cell.symbol} · ${cell.name}`" @mouseenter="hoveredCell = cell" @mouseleave="hoveredCell = null" @click="selectCell($event, cell)">
        <strong>{{ cell.symbol }}</strong><span>{{ formatMetric(cell.color_value) }}</span><small>{{ cell.group_path.join(' · ') || 'All members' }}</small>
      </button>
      <p v-if="!visibleCells.length" class="market-map-tool__status">No covered members match this group.</p>
    </div>
    <aside v-if="hoveredCell" class="market-map-tool__hover" role="status"><strong>{{ hoveredCell.symbol }}</strong><span>{{ hoveredCell.name }}</span><span>{{ hoveredCell.group_path.join(' · ') || 'All members' }}</span><span v-if="hoveredCell.warnings.length">{{ hoveredCell.warnings.map(item => item.message).join(' · ') }}</span></aside>
    <p v-else-if="!loading" class="market-map-tool__status">Choose a managed index/ETF universe or personal watchlist to build a map.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useWatchlistStore } from '@/stores/watchlist'
import { fetchMarketMap, layoutMarketMapCells, type MarketMapLayoutCell } from '@/lib/workstation/marketMap'
import type { MarketMap, MarketMapAreaMetric, MarketMapCell, MarketMapColorMetric, MarketMapGroupBy, WatchlistSource } from '@/types'

const props = withDefaults(defineProps<{ configuration?: Record<string, unknown> }>(), { configuration: () => ({}) })
const emit = defineEmits<{ configuration: [value: Record<string, unknown>]; select: [symbol: string, instrumentId: number] }>()
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
const loadingSources = computed(() => watchlistStore.watchlistSourcesLoading)
const sourcesError = computed(() => watchlistStore.watchlistSourcesError)

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
const visibleNodes = computed(() => (map.value?.nodes ?? []).filter(node => node.level !== 'root'))
const visibleCells = computed(() => {
  if (!map.value) return []
  if (!selectedNode.value || selectedNode.value === 'root') return map.value.cells
  return map.value.cells.filter(cell => cell.group_path.length && (`group:${cell.group_path.join('/')}` === selectedNode.value || `group:${cell.group_path[0]}` === selectedNode.value))
})
const visibleLayoutCells = computed<MarketMapLayoutCell[]>(() => layoutMarketMapCells(visibleCells.value))
const colorLabel = computed(() => colorMetric.value.replace(/_/g, ' '))

async function run() {
  if (!sourceId.value) return
  loading.value = true
  error.value = ''
  try {
    map.value = await fetchMarketMap({ source_id: sourceId.value, group_by: groupBy.value, period: period.value, area_metric: areaMetric.value, color_metric: colorMetric.value, reference_symbol: colorMetric.value === 'relative_return' ? referenceSymbol.value.toUpperCase() : null, timeframe: 'D1', adjusted: true })
    selectedNode.value = null
    selectedIds.value = []
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
watch(sourceId, () => { if (sourceId.value) void run() })
onMounted(async () => {
  if (!sources.value.length) await watchlistStore.loadWatchlistSources()
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
.market-map-tool__summary, .market-map-tool__nodes { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 0 8px; color: #9eabbb; }
.market-map-tool__summary span:first-child { color: #f1f4f8; font-weight: 700; }
.market-map-tool__nodes button { cursor: pointer; }
.market-map-tool__nodes button.active { border-color: #70b4ff; color: #fff; }
.market-map-tool__nodes small { color: #8e9bad; }
.market-map-tool__legend { display: flex; gap: 8px; align-items: center; padding: 2px 8px; color: #aeb8c7; text-transform: capitalize; }
.market-map-tool__legend--negative { color: #ff9a9a; font-weight: 800; }.market-map-tool__legend--positive { color: #82e2ac; font-weight: 800; }.market-map-tool__legend__coverage { margin-left: auto; text-transform: none; }
.market-map-tool__tiles { position: relative; min-height: 300px; margin: 0 8px 8px; border: 1px solid #303a48; background: #0d1218; }
.market-map-tool__tile { position: absolute; display: flex; min-width: 28px; min-height: 28px; flex-direction: column; justify-content: center; align-items: center; gap: 3px; cursor: pointer; color: #fff !important; overflow: hidden; border-radius: 0 !important; }
.market-map-tool__tile strong { font-size: 16px; }
.market-map-tool__tile small { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .75; }
.market-map-tool__tile--positive { background: #207d56 !important; }
.market-map-tool__tile--negative { background: #843f50 !important; }
.market-map-tool__tile--unknown { background: #3c4652 !important; }
.market-map-tool__tile--selected { outline: 2px solid #f7d87b; outline-offset: -2px; z-index: 2; }
.market-map-tool__hover { position: absolute; right: 12px; bottom: 12px; z-index: 5; display: flex; flex-direction: column; gap: 2px; max-width: 300px; padding: 8px 10px; border: 1px solid #60758d; background: #18222e; box-shadow: 0 4px 18px #0008; }
</style>
