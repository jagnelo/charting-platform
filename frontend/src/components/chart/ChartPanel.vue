<template>
  <div
    class="chart-panel"
    :class="{ 'is-active': isActive }"
    @mousedown="layoutStore.setActivePanel(panelId)"
  >
    <!-- Panel header -->
    <div class="panel-header">
      <!-- Symbol badge — click to open inline search for this panel -->
      <div class="panel-sym-wrap" ref="symWrapRef">
        <button
          class="panel-sym-btn"
          type="button"
          :title="store.symbol ? 'Change symbol for this panel' : 'Search symbol'"
          aria-haspopup="listbox"
          :aria-expanded="searchOpen ? 'true' : 'false'"
          :aria-controls="symbolSearchResultsId"
          :aria-label="store.symbol ? `Change chart symbol from ${store.symbol}` : 'Search chart symbol'"
          @click.stop="toggleSearch"
        >
          <span v-if="store.symbol" class="psym">{{ store.symbol }}</span>
          <span v-else class="psym-empty">Symbol…</span>
        </button>
        <!-- Inline search dropdown -->
        <div v-if="searchOpen" class="panel-search-dropdown" @click.stop>
          <SearchBar
            ref="searchBarRef"
            :model-value="searchQuery"
            mode="chart"
            fluid
            :show-recent="false"
            :show-screener-link="false"
            :allow-source-discovery="true"
            :results-id="symbolSearchResultsId"
            :input-aria-label="`Search chart symbol for panel ${panelId}`"
            @update:model-value="searchQuery = $event"
            @select="onSearchSelection"
          />
        </div>
      </div>

      <!-- Symbol link group -->
      <div class="panel-link-wrap" ref="linkWrapRef">
        <button
          class="panel-link-btn"
          type="button"
          :class="{ linked: !!linkGroup }"
          :style="{ borderColor: linkGroup ? linkColor : undefined, color: linkGroup ? linkColor : undefined }"
          :title="linkGroup ? `Symbol link group: ${linkGroup}` : 'Symbol link disabled'"
          aria-haspopup="menu"
          :aria-label="linkGroup ? `Symbol link group: ${linkGroup}` : 'Symbol link disabled'"
          :aria-expanded="linkMenuOpen"
          :aria-controls="linkMenuId"
          @click.stop="linkMenuOpen = !linkMenuOpen"
        >
          <span class="link-dot" :style="{ background: linkColor }" />
        </button>
        <div
          v-if="linkMenuOpen"
          :id="linkMenuId"
          class="panel-link-menu"
          role="menu"
          aria-label="Symbol link group"
          @click.stop
          @keydown.esc.stop.prevent="linkMenuOpen = false"
        >
          <button
            v-for="group in PANEL_LINK_GROUPS"
            :key="group.id"
            type="button"
            role="menuitemradio"
            class="plm-item"
            :class="{ active: linkGroup === group.id }"
            :aria-checked="linkGroup === group.id ? 'true' : 'false'"
            @click="setLinkGroup(group.id)"
          >
            <span class="plm-dot" :style="{ background: group.color }" /> {{ group.label }}
          </button>
        </div>
      </div>

      <span v-if="store.instrument?.name" class="psym-name">{{ store.instrument.name }}</span>
      <span v-if="historyProgress" class="panel-history-status" role="status" aria-live="polite">{{ historyProgress }}</span>
      <span v-if="historyError" class="panel-history-status panel-history-status--error" role="alert">{{ historyError }}</span>

      <TimeframeSelector v-if="store.symbol" v-model="localTf" class="panel-tf" />
    </div>

    <!-- Chart area -->
    <div class="panel-body">
      <div v-if="store.isLoading" class="panel-loading">
        Loading {{ store.symbol || '…' }}
      </div>
      <div v-else-if="!store.symbol" class="panel-empty">
        Click symbol to search
      </div>
      <UPlotChart v-else ref="chartRef" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, provide, onMounted, onUnmounted, nextTick } from 'vue'
import { usePanelStore }   from '@/stores/chart'
import { useLayoutStore }  from '@/stores/layout'
import { usePanelLinksStore, PANEL_LINK_GROUPS } from '@/stores/panelLinks'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import TimeframeSelector from '@/components/chart/TimeframeSelector.vue'
import SearchBar from '@/components/common/SearchBar.vue'
import UPlotChart        from '@/components/chart/UPlotChart.vue'
import { type InstrumentAcquireResponse } from '@/lib/onDemandAcquisition'
import { dataPreparationCoordinator, instrumentHistoryPreparationRequest, isPreparationTimeframe, PreparationProgressRefreshQueue, preparationStatusMessage, type DataEnsureResponse } from '@/lib/dataPreparation'
import type { Timeframe } from '@/types'

const props = defineProps<{ panelId: string }>()

// Provide panel ID so UPlotChart uses the correct store instance
provide('panelId', props.panelId)

const layoutStore = useLayoutStore()
const panelLinks  = usePanelLinksStore()
const store       = usePanelStore(props.panelId)
const drawStore   = useDrawingsStore()
const alertsStore = useAlertsStore()
const chartRef    = ref<InstanceType<typeof UPlotChart> | null>(null)

const panelConfig = computed(() => layoutStore.panels.find(p => p.id === props.panelId))
const isActive    = computed(() => layoutStore.activePanelId === props.panelId)

const localTf = ref<Timeframe>(panelConfig.value?.timeframe ?? 'D1')

// ── Inline search ──────────────────────────────────────────────────────────
const searchOpen    = ref(false)
const searchQuery   = ref('')
const symWrapRef    = ref<HTMLDivElement | null>(null)
const linkWrapRef   = ref<HTMLDivElement | null>(null)
const searchBarRef = ref<{ focusInput: () => void } | null>(null)
const linkMenuOpen = ref(false)
const linkMenuId = `panel-link-menu-${props.panelId}`
const symbolSearchResultsId = `chart-panel-search-results-${props.panelId}`
let lifecycleGeneration = 0
let selectionGeneration = 0
let panelMounted = false
let selectedHistoryAbortController: AbortController | null = null
let activeHistoryScopeKey: string | null = null
const historyProgress = ref('')
const historyError = ref('')

function isCurrent(generation: number, selection = selectionGeneration) {
  return generation === lifecycleGeneration && selection === selectionGeneration
}

const linkGroup = computed(() => panelLinks.groupFor(props.panelId))
const linkColor = computed(() => panelLinks.colorFor(props.panelId))

async function toggleSearch() {
  if (searchOpen.value) { closeSearch(); return }
  searchOpen.value = true
  searchQuery.value = store.symbol ?? ''
  await nextTick()
  searchBarRef.value?.focusInput()
}

function closeSearch() {
  searchOpen.value = false
  searchQuery.value = ''
}

function onSearchSelection(
  symbol: string,
  result?: { type?: string },
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  closeSearch()
  void onSymbolSelect(symbol, result?.type !== 'Synthetic', confirmedIdentity)
}

function handleClickOutside(e: MouseEvent) {
  if (symWrapRef.value && !symWrapRef.value.contains(e.target as Node)) closeSearch()
  if (linkWrapRef.value && !linkWrapRef.value.contains(e.target as Node)) linkMenuOpen.value = false
}

onMounted(() => {
  lifecycleGeneration += 1
  panelMounted = true
  document.addEventListener('mousedown', handleClickOutside)
})
onUnmounted(() => {
  panelMounted = false
  lifecycleGeneration += 1
  selectionGeneration += 1
  selectedHistoryAbortController?.abort()
  selectedHistoryAbortController = null
  activeHistoryScopeKey = null
  document.removeEventListener('mousedown', handleClickOutside)
})

// ── Symbol / link actions ──────────────────────────────────────────────────
function setLinkGroup(group: ReturnType<typeof panelLinks.groupFor>) {
  panelLinks.setPanelGroup(props.panelId, group)
  linkMenuOpen.value = false
}

async function onSymbolSelect(
  symbol: string,
  acquireHistory = true,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  const generation = lifecycleGeneration
  const selection = ++selectionGeneration
  selectedHistoryAbortController?.abort()
  selectedHistoryAbortController = null
  activeHistoryScopeKey = null
  const selectedTimeframe = localTf.value
  historyProgress.value = ''
  historyError.value = ''
  layoutStore.updatePanel(props.panelId, { symbol, timeframe: selectedTimeframe })
  if (acquireHistory) {
    startPanelHistoryPreparation(symbol, selectedTimeframe, generation, selection, confirmedIdentity)
  }
  // A deliberate symbol selection may request missing history for this panel.
  const targetIds = panelLinks.linkedPanelIds(props.panelId, layoutStore.panels.map(p => p.id))
  for (const id of targetIds) {
    if (!isCurrent(generation, selection)) return
    const panel = layoutStore.panels.find(p => p.id === id)
    if (!panel) continue
    const tf = id === props.panelId ? localTf.value : panel.timeframe
    const pStore = id === props.panelId ? store : usePanelStore(id)
    layoutStore.updatePanel(id, { symbol, timeframe: tf })
    await pStore.loadBars(symbol, tf)
  }
  if (!isCurrent(generation, selection)) return
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, localTf.value)
    if (!isCurrent(generation, selection)) return
    await alertsStore.loadAlerts(store.instrument.id)
  }
}

function startPanelHistoryPreparation(
  symbol: string,
  timeframe: Timeframe,
  generation: number,
  selection: number,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  const normalized = symbol.trim().toUpperCase()
  if (!normalized || normalized.startsWith('=') || !isPreparationTimeframe(timeframe)) return
  const scopeKey = JSON.stringify([normalized, timeframe])
  if (selectedHistoryAbortController && !selectedHistoryAbortController.signal.aborted && activeHistoryScopeKey === scopeKey) return
  selectedHistoryAbortController?.abort()
  const controller = new AbortController()
  selectedHistoryAbortController = controller
  activeHistoryScopeKey = scopeKey
  void acquirePanelHistory(normalized, timeframe, generation, selection, confirmedIdentity, controller.signal).finally(() => {
    if (selectedHistoryAbortController === controller) {
      selectedHistoryAbortController = null
      activeHistoryScopeKey = null
    }
  })
}

async function acquirePanelHistory(
  symbol: string,
  timeframe: Timeframe,
  generation: number,
  selection: number,
  confirmedIdentity?: InstrumentAcquireResponse,
  signal?: AbortSignal,
) {
  const normalized = symbol.trim().toUpperCase()
  const isSelectedScope = () => {
    const panel = layoutStore.panels.find(item => item.id === props.panelId)
    return isCurrent(generation, selection)
      && !signal?.aborted
      && panel?.symbol.trim().toUpperCase() === normalized
      && panel.timeframe === timeframe
  }
  if (!isPreparationTimeframe(timeframe)) {
    if (isSelectedScope()) historyError.value = `Automatic history preparation is unavailable for ${timeframe}.`
    return
  }
  const confirmedId = confirmedIdentity?.status === 'resolved'
    && confirmedIdentity.instrument?.symbol.trim().toUpperCase() === normalized
    && Number.isSafeInteger(confirmedIdentity.instrument.instrument_id)
    && confirmedIdentity.instrument.instrument_id > 0
    ? confirmedIdentity.instrument.instrument_id
    : null
  const cachedId = store.instrument?.symbol.trim().toUpperCase() === normalized
    && Number.isSafeInteger(store.instrument.id)
    && store.instrument.id > 0
    ? store.instrument.id
    : null
  const target = confirmedId != null || cachedId != null
    ? { kind: 'instrument' as const, instrument_id: confirmedId ?? cachedId! }
    : { kind: 'instrument' as const, symbol: normalized }
  const refreshQueue = new PreparationProgressRefreshQueue()
  const hasUsableHistory = (response: DataEnsureResponse) => response.dependencies.some(dependency =>
    dependency.dataset === 'history'
    && (dependency.covered_ranges.length > 0 || (dependency.covered_start !== null && dependency.covered_end !== null)),
  )
  const refreshCurrentPanel = async () => {
    if (!isSelectedScope()
      || store.symbol.trim().toUpperCase() !== normalized
      || store.timeframe !== timeframe) return
    await store.refreshLocalBars()
  }
  const refreshForProgress = (response: DataEnsureResponse) => refreshQueue.request(response, refreshCurrentPanel)
  try {
    const result = await dataPreparationCoordinator.ensure(
      instrumentHistoryPreparationRequest(target, timeframe, true),
      {
        signal,
        onProgress: ({ response, completed, total }) => {
          if (!isSelectedScope()) return
          historyProgress.value = response.status === 'ready'
            ? `Refreshing available ${timeframe} history for ${normalized}…`
            : response.status === 'partial' && response.has_pending_work === false
              ? preparationStatusMessage(response)
              : `Preparing admitted ${timeframe} history for ${normalized} (${completed}/${total})…`
          if (hasUsableHistory(response)) {
            void refreshForProgress(response).catch(() => {
              if (isSelectedScope()) historyError.value = `Available ${timeframe} history for ${normalized} could not be refreshed; saved bars remain visible.`
            })
          }
        },
      },
    )
    if (!isSelectedScope() || signal?.aborted) return
    historyProgress.value = result.status === 'ready'
      ? `The admitted ${timeframe} history for ${normalized} is available locally.`
      : preparationStatusMessage(result)
    if (hasUsableHistory(result)) await refreshForProgress(result)
  } catch (cause) {
    if (isSelectedScope() && !signal?.aborted) {
      historyError.value = `History for ${normalized} could not be prepared; saved chart data remains visible.`
    }
  }
}

watch(localTf, async (tf) => {
  selectedHistoryAbortController?.abort()
  selectedHistoryAbortController = null
  activeHistoryScopeKey = null
  const generation = lifecycleGeneration
  const selection = ++selectionGeneration
  layoutStore.updatePanel(props.panelId, { timeframe: tf })
  if (!store.symbol) return
  const symbol = store.symbol.trim().toUpperCase()
  if (symbol && !symbol.startsWith('=') && !store.instrument?.is_synthetic) {
    startPanelHistoryPreparation(symbol, tf, generation, selection)
  }
  await store.loadBars(store.symbol, tf)
  if (!isCurrent(generation, selection)) return
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, tf)
    if (!isCurrent(generation, selection)) return
    await alertsStore.loadAlerts(store.instrument.id)
  }
})

// A linked panel may be selected by a sibling chart. Each mounted pane prepares
// its own timeframe as soon as the shared selection reaches its local store.
watch([() => store.symbol, () => store.timeframe], ([symbol, timeframe]) => {
  if (!panelMounted) return
  const normalized = symbol.trim().toUpperCase()
  const panel = panelConfig.value
  if (!normalized || normalized.startsWith('=') || store.instrument?.is_synthetic
    || panel?.symbol.trim().toUpperCase() !== normalized || panel.timeframe !== timeframe) return
  startPanelHistoryPreparation(normalized, timeframe, lifecycleGeneration, selectionGeneration)
})

// Cross-panel cursor sync: when another panel moves the cursor, jump here too
watch(
  () => layoutStore.syncedTs,
  (ts) => {
    if (!ts || layoutStore.syncSourcePanel === props.panelId) return
    chartRef.value?.jumpToTs(ts)
  },
  { flush: 'sync' }
)

// Restore symbol from layout config on mount
onMounted(async () => {
  const generation = lifecycleGeneration
  const selection = ++selectionGeneration
  const cfg = panelConfig.value
  if (cfg?.symbol) {
    const symbol = cfg.symbol.trim().toUpperCase()
    if (symbol && !symbol.startsWith('=') && !store.instrument?.is_synthetic) {
      startPanelHistoryPreparation(symbol, cfg.timeframe, generation, selection)
    }
    await store.loadBars(cfg.symbol, cfg.timeframe)
    if (!isCurrent(generation, selection)) return
    if (store.instrument) {
      await drawStore.loadDrawings(store.instrument.id, cfg.timeframe)
      if (!isCurrent(generation, selection)) return
      await alertsStore.loadAlerts(store.instrument.id)
    }
  }
})
</script>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #1a1a1a;
  background: #0a0a0a;
  position: relative;
}

.chart-panel.is-active { border-color: #2a3a4a; }

.panel-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: #111;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.panel-sym-wrap {
  position: relative;
}

.panel-sym-btn {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.4;
  transition: background 0.1s;
}
.panel-sym-btn:hover { background: #222; border-color: #3a3a3a; }

.psym-empty { color: #444; font-weight: 400; }

.panel-search-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 200;
  background: #111;
  border: 1px solid #333;
  border-radius: 4px;
  min-width: 240px;
  width: min(320px, calc(100vw - 24px));
  padding: 4px;
}

.panel-search-dropdown :deep(.search-bar) { width: 100%; }
.panel-search-dropdown :deep(.search-results) { max-height: 200px; }

.panel-history-status {
  flex: 1 0 100%;
  min-width: 0;
  color: var(--tc-text-muted);
  font-size: 10px;
  overflow-wrap: anywhere;
}
.panel-history-status--error { color: var(--tc-danger, #e58f8f); }

.panel-link-wrap {
  position: relative;
}

.panel-link-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  width: 22px;
  height: 22px;
  padding: 0;
  cursor: pointer;
  line-height: 1;
  opacity: 0.5;
  transition: opacity 0.15s, border-color 0.15s;
}
.panel-link-btn:hover { opacity: 1; border-color: #333; }
.panel-link-btn.linked { opacity: 1; }
.link-dot {
  display: block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #555;
}

.panel-link-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 210;
  min-width: 104px;
  padding: 3px 0;
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.45);
}
.plm-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 9px;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-family: monospace;
  font-size: 11px;
  text-align: left;
}
.plm-item:hover,
.plm-item.active { background: #1d1d1d; color: #ddd; }
.plm-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.plm-dot--none {
  background: transparent;
  border: 1px solid #555;
}

.psym-name {
  font-size: 10px;
  color: #555;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.panel-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.panel-loading,
.panel-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #444;
  font-size: 12px;
}
</style>
