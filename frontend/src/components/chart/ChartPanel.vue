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
import { acquireSelectedHistory, defaultHistoryRange, type InstrumentAcquireResponse, type SelectedHistoryStage } from '@/lib/onDemandAcquisition'
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
  document.addEventListener('mousedown', handleClickOutside)
})
onUnmounted(() => {
  lifecycleGeneration += 1
  selectionGeneration += 1
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
  const selectedTimeframe = localTf.value
  historyProgress.value = ''
  historyError.value = ''
  layoutStore.updatePanel(props.panelId, { symbol, timeframe: selectedTimeframe })
  // A deliberate symbol selection may request missing history for this panel.
  // Layout restoration and timeframe changes remain local-only.
  if (acquireHistory) void acquirePanelHistory(symbol, selectedTimeframe, generation, selection, confirmedIdentity)
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

async function acquirePanelHistory(
  symbol: string,
  timeframe: Timeframe,
  generation: number,
  selection: number,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  const normalized = symbol.trim().toUpperCase()
  const isSelectedScope = () => {
    const panel = layoutStore.panels.find(item => item.id === props.panelId)
    return isCurrent(generation, selection)
      && panel?.symbol.trim().toUpperCase() === normalized
      && panel.timeframe === timeframe
  }
  const range = defaultHistoryRange(timeframe)
  const stageMessage: Record<SelectedHistoryStage, string> = {
    coverage: `Checking local ${timeframe} history for ${normalized}…`,
    identity: `Confirming ${normalized}…`,
    history: `Loading missing ${timeframe} history for ${normalized}…`,
  }
  try {
    const outcome = await acquireSelectedHistory(
      normalized,
      timeframe,
      true,
      { timeframe, adjusted: true, start: range.start, end: range.end },
      stage => { if (isSelectedScope()) historyProgress.value = stageMessage[stage] },
      isSelectedScope,
      confirmedIdentity ? Promise.resolve(confirmedIdentity) : undefined,
    )
    if (!isSelectedScope() || outcome.kind === 'superseded') return
    if (outcome.kind === 'already-covered') {
      historyProgress.value = `Local ${timeframe} history is available for ${normalized}.`
      return
    }
    if (outcome.kind === 'identity-unavailable') {
      historyProgress.value = outcome.status === 'held'
        ? `History for ${normalized} is currently unavailable; saved chart data remains visible.`
        : `The canonical identity for ${normalized} could not be confirmed; no history was requested.`
      return
    }
    const result = outcome.result
    historyProgress.value = result.status === 'complete'
      ? `Loaded ${result.coverage.bar_count} local ${timeframe} bars for ${normalized}.`
      : result.status === 'partial'
        ? `Some ${timeframe} history for ${normalized} loaded; the rest remains unavailable.`
        : result.status === 'held'
          ? `History for ${normalized} is currently unavailable; saved chart data remains visible.`
          : result.status === 'no_data'
            ? `No ${timeframe} history is available for ${normalized}; saved chart data remains visible.`
            : `History for ${normalized} could not be loaded; saved chart data remains visible.`
    if ((result.status === 'complete' || result.status === 'partial')
      && isSelectedScope()
      && store.symbol.trim().toUpperCase() === normalized
      && store.timeframe === timeframe) {
      await store.refreshLocalBars()
    }
  } catch {
    if (isSelectedScope()) {
      historyError.value = `History for ${normalized} could not be checked or loaded; saved chart data remains visible.`
    }
  }
}

watch(localTf, async (tf) => {
  const generation = lifecycleGeneration
  const selection = ++selectionGeneration
  layoutStore.updatePanel(props.panelId, { timeframe: tf })
  if (!store.symbol) return
  await store.loadBars(store.symbol, tf)
  if (!isCurrent(generation, selection)) return
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, tf)
    if (!isCurrent(generation, selection)) return
    await alertsStore.loadAlerts(store.instrument.id)
  }
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
