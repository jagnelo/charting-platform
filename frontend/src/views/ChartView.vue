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
          <!-- Add to watchlist -->
          <div
            v-if="chartStore.symbol && watchlistStore.watchlists.length"
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
                v-for="wl in watchlistStore.watchlists"
                :key="wl.id"
                class="wqm-item"
                @click="addToWatchlist(wl.id)"
              >{{ wl.name }}</div>
            </div>
          </div>
        </template>
        <!-- Multi-panel: search bar acts as "sync all panels" -->
        <template v-else>
          <span class="sync-all-hint">Sync all panels</span>
        </template>
      </div>
      <!-- Single panel only: timeframe selector -->
      <div class="header-center" v-if="layoutStore.layout === '1'">
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

    <Transition name="fetch-banner">
      <div v-if="chartStore.isFetchingHistory" class="fetch-banner" role="status" aria-live="polite">
        <span class="fetch-banner-icon">⏳</span>
        <span>Fetching full historical data for <strong>{{ chartStore.symbol }}</strong> in the background — older bars will appear as they arrive.</span>
      </div>
    </Transition>

    <!-- Main body: watchlist panel is always visible regardless of layout -->
    <div class="chart-body">
      <WatchlistPanel :current-symbol="chartStore.symbol" @select="onSymbolSelect" />
      <DrawingToolbar />
      <div v-if="layoutStore.layout === '1'" class="chart-workspace">
        <div class="chart-area">
          <div v-if="chartStore.isLoading" class="chart-loading">
            <div class="loading-spinner">Loading {{ chartStore.symbol }}…</div>
          </div>
          <div v-else-if="chartStore.error" class="chart-error">
            {{ chartStore.error }}
          </div>
          <div v-else-if="!chartStore.symbol" class="chart-empty">
            <div class="empty-msg">
              <p class="empty-title">Search for a symbol to begin</p>
              <p class="empty-sub">Stocks, ETFs, Futures, Forex, Crypto</p>
            </div>
          </div>
          <UPlotChart v-else />
        </div>
      </div>
      <div v-else class="chart-workspace">
        <MultiChartLayout />
      </div>
      <!-- IndicatorPanel is always visible; key forces re-mount on active panel switch -->
      <IndicatorPanel
        :panel-id="layoutStore.layout === '1' ? 'main' : layoutStore.activePanelId"
        :key="layoutStore.layout === '1' ? 'main' : layoutStore.activePanelId"
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
import { useWatchlistStore } from '@/stores/watchlist'
import { formatMoney } from '@/lib/format'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore }   from '@/stores/alerts'
import { usePresetsStore }  from '@/stores/presets'
import SearchBar            from '@/components/common/SearchBar.vue'
import TimeframeSelector    from '@/components/chart/TimeframeSelector.vue'
import UPlotChart           from '@/components/chart/UPlotChart.vue'
import DrawingToolbar       from '@/components/chart/DrawingToolbar.vue'
import IndicatorPanel       from '@/components/chart/IndicatorPanel.vue'
import LayoutPicker         from '@/components/chart/LayoutPicker.vue'
import MultiChartLayout     from '@/components/chart/MultiChartLayout.vue'
import WatchlistPanel       from '@/components/watchlist/WatchlistPanel.vue'
import type { Timeframe } from '@/types'

const chartStore      = useChartStore()
const layoutStore     = useLayoutStore()
const watchlistStore  = useWatchlistStore()
const drawStore       = useDrawingsStore()
const alertsStore     = useAlertsStore()
const presetsStore    = usePresetsStore()

const route  = useRoute()
const router = useRouter()

const currentTf     = ref<Timeframe>('D1')
const showWlMenu    = ref(false)
const wlStarRef     = ref<HTMLElement | null>(null)

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

async function onSymbolSelect(symbol: string) {
  if (layoutStore.layout === '1') {
    // Single panel: load into the global chart store
    await chartStore.loadBars(symbol, currentTf.value)
    if (chartStore.instrument) {
      await drawStore.loadDrawings(chartStore.instrument.id, currentTf.value)
      await alertsStore.loadAlerts(chartStore.instrument.id)
      const def = presetsStore.getDefault()
      if (def) chartStore.setIndicators([...def.indicators])
    }
    lastClose.value = currentPrice.value
  } else {
    // Multi-panel: broadcast symbol to every panel
    for (const p of layoutStore.panels) {
      const pStore = usePanelStore(p.id)
      layoutStore.updatePanel(p.id, { symbol })
      await pStore.loadBars(symbol, p.timeframe)
    }
  }
  if (route.params.symbol !== symbol) {
    router.replace(`/chart/${encodeURIComponent(symbol)}`)
  }
}

watch(currentTf, async (tf) => {
  if (!chartStore.symbol) return
  lastClose.value = currentPrice.value
  await chartStore.loadBars(chartStore.symbol, tf)
  if (chartStore.instrument) {
    await drawStore.loadDrawings(chartStore.instrument.id, tf)
  }
})

// When switching from single to multi-panel, carry the current symbol into all panels
watch(() => layoutStore.layout, async (newLayout, oldLayout) => {
  if (oldLayout === '1' && newLayout !== '1' && chartStore.symbol) {
    for (const p of layoutStore.panels) {
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
  if (pStore.instrument) {
    await drawStore.loadDrawings(pStore.instrument.id, pStore.timeframe)
    await alertsStore.loadAlerts(pStore.instrument.id)
  }
})


async function addToWatchlist(watchlistId: number) {
  if (!chartStore.symbol) return
  await watchlistStore.addBySymbol(watchlistId, chartStore.symbol)
  showWlMenu.value = false
}

onMounted(async () => {
  document.addEventListener('click', onDocClick, true)
  alertsStore.connectWebSocket()
  await presetsStore.loadPresets()
  // Load ticker from URL param e.g. navigating from /alerts
  const sym = route.params.symbol as string | undefined
  if (sym) await onSymbolSelect(sym)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick, true)
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

.chart-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.chart-loading, .chart-error, .chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #444;
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
