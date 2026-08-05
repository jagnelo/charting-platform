<template>
  <div class="chart-view">
    <!-- Top bar -->
    <header class="chart-header">
      <div class="header-left">
        <SearchBar @select="onSymbolSelect" />
        <!-- Single panel: ticker + price -->
        <template v-if="layoutStore.layout === '1'">
          <div class="symbol-info" v-if="chartStore.symbol">
            <span class="sym">{{ chartStore.symbol }}</span>
            <span class="sym-name">{{ chartStore.instrument?.name }}</span>
            <span class="sym-price" :class="priceClass">
              {{ formatMoney(currentPrice, chartStore.instrument?.currency) }}
            </span>
          </div>
        </template>
        <!-- Multi-panel: show active panel symbol -->
        <template v-else>
          <div class="symbol-info" v-if="activePanelStore.symbol">
            <span class="sym">{{ activePanelStore.symbol }}</span>
            <span class="sym-name">{{ activePanelStore.instrument?.name }}</span>
          </div>
          <span v-else class="sync-all-hint">Sync all panels</span>
        </template>
        <!-- Add to watchlist — available in any layout when a symbol is loaded -->
        <div
          v-if="activeSymbol && !isBasketSymbol(activeSymbol)"
          ref="wlStarRef"
          class="wl-star-wrap"
        >
          <button
            class="wl-star"
            :class="{ active: showWlMenu }"
            title="Add to watchlist"
            @click="showWlMenu = !showWlMenu"
          >★</button>
          <div v-if="showWlMenu" class="wl-quick-menu">
            <div class="wqm-title">Add to watchlist</div>
            <div
              v-for="wl in addableWatchlists"
              :key="wl.id"
              class="wqm-item"
              @click="addToWatchlist(wl.id)"
            >{{ wl.name }}</div>
            <div class="wqm-item wqm-new" @click="createAndAddToWatchlist">+ New watchlist</div>
          </div>
        </div>
        <div v-if="layoutStore.layout === '1' && chartStore.symbol" class="compare-wrap">
          <button
            class="compare-btn"
            :class="{ active: showCompareInput || comparisonTargets.length }"
            @click="showCompareInput = !showCompareInput"
          >
            Compare
          </button>
          <div v-if="showCompareInput" class="compare-form">
            <SearchBar
              v-model="compareDraft"
              placeholder="Symbol or =expression"
              mode="picker"
              fluid
              :show-screener-link="false"
              @select="addComparisonSymbol"
            />
          </div>
          <div v-if="comparisonLegend.length" class="compare-chips">
            <button
              v-for="target in comparisonLegend"
              :key="target.symbol"
              class="compare-chip"
              :title="target.label"
              @click="removeComparison(target.symbol)"
            >
              <span class="compare-color" :style="{ background: target.color }" />
              <span>{{ target.symbol }}</span>
              <b :class="(target.percentChange ?? 0) >= 0 ? 'up' : 'dn'">
                {{ formatPercent(target.percentChange) }}
              </b>
              <small>×</small>
            </button>
          </div>
        </div>
      </div>
      <!-- Single panel only: timeframe selector -->
      <div class="header-center" v-if="layoutStore.layout === '1' && chartStore.symbol">
        <TimeframeSelector v-model="currentTf" />
      </div>
      <div class="header-right">
        <LayoutPicker />
        <div v-if="layoutStore.layout === '1' && chartStore.instrument && alertsStore.activeCountForInstrument(chartStore.instrument.id)" class="alert-badge">
          {{ alertsStore.activeCountForInstrument(chartStore.instrument.id) }}
        </div>
        <div class="ws-dot" :class="{ connected: alertsStore.wsConnected }" title="WebSocket status" />
      </div>
    </header>

    <TextPromptModal
      v-model="showCreateWatchlistModal"
      title="Create Watchlist"
      label="Watchlist name"
      placeholder="Watchlist name"
      confirm-label="Create"
      @submit="confirmCreateWatchlist"
    />

    <Transition name="fetch-banner">
      <div v-if="chartStore.isFetchingHistory" class="fetch-banner" role="status" aria-live="polite">
        <span class="fetch-banner-icon">⏳</span>
        <span>Fetching full historical data for <strong>{{ chartStore.symbol }}</strong> in the background — older bars will appear as they arrive.</span>
      </div>
    </Transition>

    <!-- Main body: watchlist panel is always visible regardless of layout -->
    <div class="chart-body">
      <WatchlistPanel :current-symbol="activeSymbol" @select="onSymbolSelect" :body-width="layoutStore.panelWidths.watchlist" />
      <ResizeHandle direction="horizontal" :value="layoutStore.panelWidths.watchlist" :min="160" :max="600" @change="v => layoutStore.setPanelWidth('watchlist', v)" />
      <DrawingToolbar />
      <div v-if="layoutStore.layout === '1'" class="chart-workspace single-workspace">
        <div class="chart-area">
          <div v-if="!chartStore.symbol" class="chart-empty">
            <div class="empty-msg">
              <p class="empty-title">Search for a symbol to begin</p>
              <p class="empty-sub">Stocks, ETFs, Futures, Forex, Crypto</p>
            </div>
          </div>
          <template v-else>
            <div v-if="chartStore.isLoading" class="chart-overlay chart-loading">
              <div class="loading-spinner">Loading {{ chartStore.symbol }}…</div>
            </div>
            <div v-else-if="chartStore.error" class="chart-overlay chart-error">
              {{ chartStore.error }}
            </div>
            <UPlotChart
              :comparison-series="comparisonSeries"
              :overlay-indicators="activeRadarIndicators"
              :overlay-drawings="activeRadarDrawings"
            />
          </template>
        </div>
        <template v-if="showOptionsPanel">
          <ResizeHandle
            direction="vertical"
            :value="optionsPanelHeight"
            :min="collapsedOptionsPanel ? 20 : 180"
            :max="520"
            inverted
            @change="resizeOptionsPanel"
          />
          <div class="options-shell" :style="{ height: `${collapsedOptionsPanel ? 20 : optionsPanelHeight}px` }">
            <button
              class="options-toggle"
              :title="collapsedOptionsPanel ? 'Expand options panel' : 'Collapse options panel'"
              @click="collapsedOptionsPanel = !collapsedOptionsPanel"
            >{{ collapsedOptionsPanel ? '▴' : '▾' }}</button>
            <div v-if="!collapsedOptionsPanel" class="options-tabs">
              <div class="options-tab-group">
                <button
                  class="options-tab"
                  :class="{ active: optionsTab === 'chain' }"
                  @click="optionsTab = 'chain'"
                >Chain</button>
                <button
                  class="options-tab"
                  :class="{ active: optionsTab === 'exposure' }"
                  @click="optionsTab = 'exposure'"
                >Exposure</button>
              </div>
            </div>
            <div v-if="!collapsedOptionsPanel" class="options-content">
              <OptionsChainPanel
                v-if="optionsTab === 'chain'"
                :symbol="chartStore.symbol"
                title="Options Chain"
                @open-symbol="onSymbolSelect"
              />
              <OptionsExposurePanel
                v-else-if="optionsTab === 'exposure'"
                :symbol="chartStore.symbol"
                title="Options Exposure"
              />
            </div>
          </div>
        </template>
        <ETFHoldingsPanel
          v-if="chartStore.symbol && !isBasketSymbol(chartStore.symbol) && chartStore.instrument && !chartStore.instrument.is_synthetic"
          :symbol="chartStore.symbol"
          @open-symbol="onSymbolSelect"
        />
      </div>
      <div v-else class="chart-workspace">
        <MultiChartLayout />
      </div>
      <ResizeHandle direction="horizontal" inverted :value="layoutStore.panelWidths.indicatorPanel" :min="150" :max="500" @change="v => layoutStore.setPanelWidth('indicatorPanel', v)" />
      <!-- IndicatorPanel is always visible; key forces re-mount on active panel switch -->
      <IndicatorPanel
        :panel-id="layoutStore.layout === '1' ? 'main' : layoutStore.activePanelId"
        :key="layoutStore.layout === '1' ? 'main' : layoutStore.activePanelId"
        :panel-width="layoutStore.panelWidths.indicatorPanel"
        @select-symbol="onSymbolSelect"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChartStore, usePanelStore } from '@/stores/chart'
import { useLayoutStore }    from '@/stores/layout'
import { usePanelLinksStore } from '@/stores/panelLinks'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'
import { useWatchlistStore } from '@/stores/watchlist'
import { formatMoney } from '@/lib/format'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore }   from '@/stores/alerts'
import { usePresetsStore }  from '@/stores/presets'
import { useOptionsExposureStore } from '@/stores/optionsExposure'
import { useRadarStore } from '@/stores/radar'
import { api } from '@/lib/api'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import ResizeHandle         from '@/components/common/ResizeHandle.vue'
import SearchBar            from '@/components/common/SearchBar.vue'
import TimeframeSelector    from '@/components/chart/TimeframeSelector.vue'
import UPlotChart           from '@/components/chart/UPlotChart.vue'
import DrawingToolbar       from '@/components/chart/DrawingToolbar.vue'
import IndicatorPanel       from '@/components/chart/IndicatorPanel.vue'
import LayoutPicker         from '@/components/chart/LayoutPicker.vue'
import MultiChartLayout     from '@/components/chart/MultiChartLayout.vue'
import WatchlistPanel       from '@/components/watchlist/WatchlistPanel.vue'
import OptionsChainPanel    from '@/components/options/OptionsChainPanel.vue'
import OptionsExposurePanel from '@/components/options/exposure/OptionsExposurePanel.vue'
import ETFHoldingsPanel     from '@/components/etf/ETFHoldingsPanel.vue'
import TextPromptModal      from '@/components/common/TextPromptModal.vue'
import { buildRadarDrawingOverlays, buildRadarIndicatorOverlays, mergeChartDrawingsWithRadar } from '@/lib/radar/visuals'
import type { ChartComparisonSeries, OHLCVBar, Timeframe } from '@/types'

const chartStore      = useChartStore()
const layoutStore     = useLayoutStore()
const panelLinksStore = usePanelLinksStore()
const recentStore     = useRecentInstrumentsStore()
const watchlistStore  = useWatchlistStore()
const drawStore       = useDrawingsStore()
const alertsStore     = useAlertsStore()
const presetsStore    = usePresetsStore()
const optionsExposureStore = useOptionsExposureStore()
const radarStore      = useRadarStore()

// Active panel store — in single mode this is the global chart store, in multi mode it's the active panel
const activePanelStore = computed(() =>
  layoutStore.layout === '1' ? chartStore : usePanelStore(layoutStore.activePanelId)
)

// Symbol currently focused in the header area (single or active panel)
const activeSymbol = computed(() =>
  layoutStore.layout === '1' ? chartStore.symbol : activePanelStore.value.symbol
)

function isBasketSymbol(symbol: string | null | undefined) {
  return Boolean(symbol?.trim().match(/^BASKET:\d+$/i))
}

// Watchlists that can receive a "add" — exclude locked and managed ones
const addableWatchlists = computed(() =>
  watchlistStore.watchlists.filter(w => !w.is_locked && !w.is_managed)
)

const route  = useRoute()
const router = useRouter()

const currentTf     = ref<Timeframe>('D1')
const showWlMenu    = ref(false)
const showCreateWatchlistModal = ref(false)
const optionsTab    = ref<'chain' | 'exposure'>('chain')
const optionsPanelHeight = ref(340)
const collapsedOptionsPanel = ref(true)
const wlStarRef     = ref<HTMLElement | null>(null)
const showCompareInput = ref(false)
const compareDraft = ref('')
const comparisonTargets = ref<Array<{
  symbol: string
  label: string
  color: string
  bars: OHLCVBar[]
}>>([])
let comparisonSeq = 0

const COMPARE_COLORS = ['#ffb74d', '#64b5f6', '#81c784', '#ba68c8', '#f06292', '#4dd0e1']

function onDocClick(e: MouseEvent) {
  if (showWlMenu.value && wlStarRef.value && !wlStarRef.value.contains(e.target as Node)) {
    showWlMenu.value = false
  }
}

const currentPrice = computed(() => {
  const bars = chartStore.bars
  return bars.length ? bars[bars.length - 1].close : null
})

const lastClose   = ref<number | null>(null)
const priceClass  = computed(() => {
  if (currentPrice.value == null || lastClose.value == null) return ''
  return currentPrice.value >= lastClose.value ? 'price-up' : 'price-down'
})

const comparisonSeries = computed<ChartComparisonSeries[]>(() => {
  const mainBars = chartStore.bars
  const mainAnchor = mainBars.find(bar => Number.isFinite(bar.close) && bar.close > 0)?.close ?? null
  if (!mainBars.length || mainAnchor == null) return []
  return comparisonTargets.value.map(target => {
    const compareByTs = new Map(target.bars.map(bar => [bar.ts, bar.close]))
    const alignedRaw = mainBars.map(bar => compareByTs.get(bar.ts) ?? null)
    const compareAnchor = alignedRaw.find(value => value != null && Number.isFinite(value) && value > 0) ?? null
    const values = compareAnchor == null
      ? mainBars.map(() => null)
      : alignedRaw.map(value => (
          value != null && Number.isFinite(value)
            ? mainAnchor * (value / compareAnchor)
            : null
        ))
    let last: number | null = null
    for (let i = alignedRaw.length - 1; i >= 0; i--) {
      const value = alignedRaw[i]
      if (value != null && Number.isFinite(value) && value > 0) {
        last = value
        break
      }
    }
    const percentChange = compareAnchor != null && last != null
      ? ((last - compareAnchor) / compareAnchor) * 100
      : null
    return {
      symbol: target.symbol,
      label: target.label,
      color: target.color,
      values,
      percentChange,
    }
  })
})

const showOptionsPanel = computed(() =>
  !!chartStore.instrument
  && !chartStore.instrument?.is_synthetic
  && !chartStore.instrument?.option_detail
)

const comparisonLegend = computed(() =>
  comparisonTargets.value.map(target => ({
    ...target,
    percentChange: comparisonSeries.value.find(series => series.symbol === target.symbol)?.percentChange ?? null,
  }))
)

const activeRadarDetections = computed(() =>
  radarStore.chartDetections.filter(detection => radarStore.isChartDetectionActive(detection.id))
)

const activeRadarIndicators = computed(() => {
  const focusedId = radarStore.focusedChartDetectionId
  return buildRadarIndicatorOverlays(activeRadarDetections.value, focusedId)
})

const activeRadarDrawings = computed(() => {
  return mergeChartDrawingsWithRadar(
    drawStore.drawings.filter(drawing => (drawing.indicator_key ?? null) === null),
    buildRadarDrawingOverlays(activeRadarDetections.value, radarStore.focusedChartDetectionId),
    {
      instrumentId: chartStore.instrument?.id ?? null,
      timeframe: chartStore.timeframe,
    },
  )
})

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function resizeOptionsPanel(next: number) {
  optionsPanelHeight.value = Math.max(180, Math.min(520, Math.round(next)))
  collapsedOptionsPanel.value = false
}

async function addComparisonSymbol(symbol: string) {
  if (symbol === chartStore.symbol || comparisonTargets.value.some(target => target.symbol === symbol)) {
    compareDraft.value = ''
    return
  }
  const color = COMPARE_COLORS[comparisonTargets.value.length % COMPARE_COLORS.length]
  comparisonTargets.value.push({ symbol, label: symbol, color, bars: [] })
  compareDraft.value = ''
  await loadComparisonBars()
}

function removeComparison(symbol: string) {
  comparisonTargets.value = comparisonTargets.value.filter(target => target.symbol !== symbol)
}

async function loadComparisonBars() {
  if (!chartStore.symbol || !comparisonTargets.value.length) return
  const seq = ++comparisonSeq
  const tf = currentTf.value
  const targets = [...comparisonTargets.value]
  const loaded = await Promise.all(targets.map(async target => {
    try {
      const limit = Math.max(chartStore.bars.length, 500)
      const raw = await dedupeOhlcvRequest(`raw:${target.symbol.toUpperCase()}:${tf}:adjusted:${limit}`, () => api.get<any[]>(`/ohlcv/${encodeURIComponent(target.symbol)}/${tf}`, { limit, adjusted: true }))
      return {
        symbol: target.symbol,
        bars: raw.map(bar => ({
          ...bar,
          open: Number(bar.open),
          high: Number(bar.high),
          low: Number(bar.low),
          close: Number(bar.close),
          volume: bar.volume != null ? Number(bar.volume) : undefined,
          vwap: bar.vwap != null ? Number(bar.vwap) : undefined,
        })) as OHLCVBar[],
      }
    } catch {
      return { symbol: target.symbol, bars: [] as OHLCVBar[] }
    }
  }))
  if (seq !== comparisonSeq) return
  comparisonTargets.value = comparisonTargets.value.map(target => ({
    ...target,
    bars: loaded.find(item => item.symbol === target.symbol)?.bars ?? [],
  }))
}

async function onSymbolSelect(symbol: string) {
  if (chartStore.symbol !== symbol) {
    radarStore.clearChartDetections()
  }
  if (!isBasketSymbol(symbol)) {
    recentStore.add(symbol)
  }
  if (route.params.symbol !== symbol) {
    router.replace(`/chart/${encodeURIComponent(symbol)}`)
  }
  if (layoutStore.layout === '1') {
    // Single panel: load into the global chart store
    await chartStore.loadBars(symbol, currentTf.value)
    const inst = chartStore.instrument
    if (inst) {
      await drawStore.loadDrawings(inst.id, currentTf.value)
      await alertsStore.loadAlerts(inst.id)
      const def = presetsStore.getDefault()
      if (def) chartStore.setIndicators([...def.indicators])
    }
    lastClose.value = currentPrice.value
    await loadComparisonBars()
    await syncRadarOverlays()
  } else {
    // Multi-panel: broadcast symbol to panels in the same colour link group.
    const targetIds = panelLinksStore.linkedPanelIds(layoutStore.activePanelId, layoutStore.panels.map(p => p.id))
    for (const panelId of targetIds) {
      const p = layoutStore.panels.find(item => item.id === panelId)
      if (!p) continue
      const pStore = usePanelStore(p.id)
      layoutStore.updatePanel(p.id, { symbol })
      await pStore.loadBars(symbol, p.timeframe)
    }
    const activeStore = usePanelStore(layoutStore.activePanelId)
    const activeInst = activeStore.instrument
    if (activeInst) {
      await drawStore.loadDrawings(activeInst.id, activeStore.timeframe)
      await alertsStore.loadAlerts(activeInst.id)
    }
    await syncRadarOverlays()
  }
}

async function syncRadarOverlays() {
  if (!chartStore.instrument) {
    radarStore.clearChartDetections()
    return
  }
  const detectionId = radarStore.consumeChartDetectionForInstrument(
    chartStore.instrument.id,
    chartStore.instrument.symbol,
  )
  await radarStore.loadChartDetections(chartStore.instrument.id, chartStore.timeframe, detectionId)
}

function stripLegacyRadarDetectionQuery() {
  if (!Object.prototype.hasOwnProperty.call(route.query, 'radarDetectionId')) return
  const nextQuery = { ...route.query }
  delete nextQuery.radarDetectionId
  void router.replace({ path: route.path, query: nextQuery })
}

watch(currentTf, async (tf) => {
  if (!chartStore.symbol) return
  lastClose.value = currentPrice.value
  await chartStore.loadBars(chartStore.symbol, tf)
  const inst = chartStore.instrument
  if (inst) {
    await drawStore.loadDrawings(inst.id, tf)
    await alertsStore.loadAlerts(inst.id)
  }
  await loadComparisonBars()
  await syncRadarOverlays()
})

watch(() => chartStore.bars.length, () => {
  if (comparisonTargets.value.length) loadComparisonBars()
})

// When switching from single to multi-panel, carry the current symbol into all panels
watch(() => layoutStore.layout, async (newLayout, oldLayout) => {
  if (oldLayout === '1' && newLayout !== '1' && chartStore.symbol) {
    for (const p of layoutStore.panels) {
      if (!p.linkedToGlobal) continue
      layoutStore.updatePanel(p.id, { symbol: chartStore.symbol })
      const pStore = usePanelStore(p.id)
      await pStore.loadBars(chartStore.symbol, p.timeframe)
    }
  }
})

// When the active panel changes in multi-panel mode, sync drawings and alerts to that panel
watch(() => layoutStore.activePanelId, async (panelId) => {
  if (layoutStore.layout === '1') return
  const pStore = usePanelStore(panelId)
  const inst = pStore.instrument
  if (inst) {
    await drawStore.loadDrawings(inst.id, pStore.timeframe)
    await alertsStore.loadAlerts(inst.id)
  }
})

watch(
  () => [chartStore.symbol, showOptionsPanel.value] as const,
  ([sym, canShow]) => {
    if (!sym || !canShow) {
      optionsExposureStore.reset()
      return
    }
    if (optionsExposureStore.symbol !== sym) {
      void optionsExposureStore.load(sym)
    }
  },
  { immediate: true },
)

watch(
  () => route.query.radarDetectionId,
  () => {
    stripLegacyRadarDetectionQuery()
  },
  { immediate: true },
)

async function addToWatchlist(watchlistId: number) {
  const sym = activeSymbol.value
  if (!sym || isBasketSymbol(sym)) return
  await watchlistStore.addBySymbol(watchlistId, sym)
  showWlMenu.value = false
}

async function createAndAddToWatchlist() {
  showCreateWatchlistModal.value = true
}

async function confirmCreateWatchlist(name: string) {
  const sym = activeSymbol.value
  if (!sym) return
  const wl = await watchlistStore.createWatchlist(name)
  if (!wl) return
  await watchlistStore.addBySymbol(wl.id, sym)
  showCreateWatchlistModal.value = false
  showWlMenu.value = false
}

onMounted(async () => {
  document.addEventListener('click', onDocClick, true)
  await presetsStore.loadPresets()
  // Load ticker from URL param e.g. navigating from /alerts
  const sym = route.params.symbol as string | undefined
  const pending = radarStore.pendingChartDetection
  if (sym && pending?.instrumentSymbol === sym.toUpperCase() && currentTf.value !== pending.timeframe) {
    currentTf.value = pending.timeframe
  }
  if (sym) {
    await onSymbolSelect(sym)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick, true)
  radarStore.clearPendingChartDetection()
})
</script>

<style scoped>
.chart-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0a0a0a;
  color: #ccc;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #111;
  border-bottom: 1px solid #222;
  gap: 12px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.header-left, .header-right { display: flex; align-items: center; gap: 12px; }

.symbol-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.sync-all-hint { font-size: 11px; color: #444; font-style: italic; }

.wl-star-wrap {
  position: relative;
}
.wl-star {
  background: none;
  border: 1px solid #333;
  color: #555;
  border-radius: 3px;
  padding: 3px 7px;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  transition: color 0.15s, border-color 0.15s;
}
.wl-star:hover, .wl-star.active { color: #ffd54f; border-color: #ffd54f; }

.compare-wrap {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.compare-btn,
.compare-chip {
  border: 1px solid #333;
  background: #151515;
  color: #999;
  border-radius: 4px;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}
.compare-btn {
  padding: 4px 8px;
}
.compare-btn:hover,
.compare-btn.active {
  border-color: #64b5f6;
  color: #d8ecff;
}
.compare-form {
  display: flex;
  align-items: center;
  width: 190px;
}
.compare-form :deep(.search-input-wrap) {
  min-height: 28px;
  background: #080808;
}
.compare-form :deep(.search-input) {
  font-size: 11px;
}
.compare-chips {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  flex-wrap: wrap;
}
.compare-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 6px;
  max-width: 170px;
}
.compare-chip span:not(.compare-color) {
  overflow: hidden;
  text-overflow: ellipsis;
}
.compare-chip b {
  font-weight: 600;
}
.compare-chip b.up { color: #26a69a; }
.compare-chip b.dn { color: #ef5350; }
.compare-chip small { color: #666; }
.compare-color {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wl-quick-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  min-width: 160px;
  z-index: 200;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}
.wqm-title {
  padding: 6px 10px 4px;
  font-size: 10px;
  color: #555;
  text-transform: uppercase;
  border-bottom: 1px solid #222;
}
.wqm-item {
  padding: 7px 10px;
  font-size: 12px;
  color: #aaa;
  cursor: pointer;
  transition: background 0.1s;
}
.wqm-item:hover { background: #222; color: #fff; }
.wqm-new { color: #64b5f6; border-top: 1px solid #222; margin-top: 2px; }

.sym      { font-size: 16px; font-weight: 700; color: #fff; }
.sym-name { font-size: 11px; color: #666; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sym-price { font-size: 14px; font-weight: 600; }
.price-up   { color: #26a69a; }
.price-down { color: #ef5350; }

.hdr-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #aaa;
  border-radius: 4px;
  padding: 4px 12px;
  cursor: pointer;
  font-size: 12px;
}
.hdr-btn:hover:not(:disabled) { border-color: #64b5f6; color: #64b5f6; }
.hdr-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.alert-badge {
  background: #ffb74d;
  color: #000;
  border-radius: 10px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  margin-left: -8px;
}

.ws-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #444;
}
.ws-dot.connected { background: #26a69a; }

.fetch-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: rgba(255, 183, 77, 0.12);
  border-bottom: 1px solid rgba(255, 183, 77, 0.3);
  color: #ffb74d;
  font-size: 12px;
  flex-shrink: 0;
}
.fetch-banner-icon { font-size: 14px; }
.fetch-banner strong { font-weight: 700; }
.fetch-banner-enter-active, .fetch-banner-leave-active {
  transition: max-height 0.25s ease, opacity 0.25s ease;
  max-height: 40px;
  overflow: hidden;
}
.fetch-banner-enter-from, .fetch-banner-leave-to { max-height: 0; opacity: 0; }

.alert-form-wrap {
  position: fixed;
  top: 60px;
  right: 16px;
  z-index: 200;
}

.chart-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.chart-workspace {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.single-workspace {
  flex-direction: column;
}

.chart-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.options-shell {
  border-top: 1px solid #171717;
  background: #0c0c0c;
  flex-shrink: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.options-toggle {
  width: 100%;
  height: 20px;
  background: #0c0c0c;
  border: none;
  color: #333;
  cursor: pointer;
  font-size: 10px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: color 0.1s, background 0.1s;
}
.options-toggle:hover { color: #aaa; background: #111; }
.options-tabs {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
  min-height: 43px;
}
.options-tab-group {
  display: flex;
  align-items: center;
}
.options-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: #666;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  padding: 5px 14px;
  cursor: pointer;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.options-tab:hover { color: #aaa; }
.options-tab.active {
  color: #ccc;
  border-bottom-color: #64b5f6;
}

.options-content {
  flex: 1;
  min-height: 0;
}

.chart-loading, .chart-error, .chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #444;
}

.chart-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  background: rgba(10, 10, 10, 0.75);
}

.loading-spinner {
  font-size: 14px;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50%       { opacity: 1; }
}

.empty-title { font-size: 18px; color: #555; margin: 0 0 6px; text-align: center; }
.empty-sub   { font-size: 12px; color: #333; text-align: center; margin: 0; }

.alert-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: #0d0d0d;
  border-top: 1px solid #1a1a1a;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.strip-label { font-size: 10px; color: #555; text-transform: uppercase; }

.alert-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  background: #1a1a1a;
  border: 1px solid #333;
  color: #aaa;
}

.alert-chip--active    { border-color: #ffb74d; color: #ffb74d; }
.alert-chip--triggered { border-color: #555; color: #555; }

.alert-chip button {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 10px;
  padding: 0 0 0 4px;
  opacity: 0.6;
}
.alert-chip button:hover { opacity: 1; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to       { opacity: 0; }
</style>
