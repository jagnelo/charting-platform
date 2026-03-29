<template>
  <div class="chart-view">
    <!-- Top bar -->
    <header class="chart-header">
      <div class="header-left">
        <SearchBar @select="onSymbolSelect" />
        <div class="symbol-info" v-if="chartStore.symbol">
          <span class="sym">{{ chartStore.symbol }}</span>
          <span class="sym-name">{{ chartStore.instrument?.name }}</span>
          <span class="sym-price" :class="priceClass">
            {{ currentPrice?.toFixed(4) ?? '—' }}
          </span>
        </div>
      </div>
      <div class="header-center">
        <TimeframeSelector v-model="currentTf" />
      </div>
      <div class="header-right">
        <button class="hdr-btn" @click="showAlertForm = !showAlertForm" :disabled="!chartStore.instrument" title="New Alert">
          🔔 Alert
        </button>
        <div v-if="chartStore.instrument && alertsStore.activeCountForInstrument(chartStore.instrument.id)" class="alert-badge">
          {{ alertsStore.activeCountForInstrument(chartStore.instrument.id) }}
        </div>
        <div class="ws-dot" :class="{ connected: alertsStore.wsConnected }" title="WebSocket status" />
      </div>
    </header>

    <!-- Alert form popup -->
    <Transition name="fade">
      <div class="alert-form-wrap" v-if="showAlertForm && chartStore.instrument">
        <AlertForm
          :instrument-id="chartStore.instrument.id"
          :symbol="chartStore.symbol"
          :current-tf="currentTf"
          :seed-indicator="alertSeedIndicator"
          @close="showAlertForm = false"
        />
      </div>
    </Transition>

    <!-- Main workspace -->
    <div class="chart-workspace">
      <DrawingToolbar />
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
      <IndicatorPanel @alert-for-indicator="onAlertForIndicator" />
    </div>

    <!-- Bottom panel: alerts list for current symbol -->
    <div class="alert-strip" v-if="currentAlerts.length">
      <span class="strip-label">ALERTS:</span>
      <span
        v-for="a in currentAlerts"
        :key="a.id"
        :class="['alert-chip', `alert-chip--${a.status}`]"
      >
        {{ a.condition.replace('_', ' ') }} ${{ a.threshold_price }}
        <button @click="alertsStore.deleteAlert(a.id)">✕</button>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useChartStore }   from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore }   from '@/stores/alerts'
import { usePresetsStore }  from '@/stores/presets'
import SearchBar         from '@/components/common/SearchBar.vue'
import TimeframeSelector from '@/components/chart/TimeframeSelector.vue'
import UPlotChart        from '@/components/chart/UPlotChart.vue'
import DrawingToolbar    from '@/components/chart/DrawingToolbar.vue'
import IndicatorPanel    from '@/components/chart/IndicatorPanel.vue'
import AlertForm         from '@/components/alerts/AlertForm.vue'
import type { IndicatorConfig, Timeframe } from '@/types'

const chartStore   = useChartStore()
const drawStore    = useDrawingsStore()
const alertsStore  = useAlertsStore()
const presetsStore = usePresetsStore()

const route = useRoute()

const currentTf          = ref<Timeframe>('D1')
const showAlertForm      = ref(false)
const alertSeedIndicator = ref<IndicatorConfig | null>(null)

const currentPrice = computed(() => {
  const bars = chartStore.bars
  return bars.length ? bars[bars.length - 1].close : null
})

const lastClose   = ref<number | null>(null)
const priceClass  = computed(() => {
  if (currentPrice.value == null || lastClose.value == null) return ''
  return currentPrice.value >= lastClose.value ? 'price-up' : 'price-down'
})

const currentAlerts = computed(() =>
  alertsStore.alerts.filter(a => a.instrument_id === chartStore.instrument?.id)
)

async function onSymbolSelect(symbol: string) {
  await chartStore.loadBars(symbol, currentTf.value)
  if (chartStore.instrument) {
    await drawStore.loadDrawings(chartStore.instrument.id, currentTf.value)
    await alertsStore.loadAlerts(chartStore.instrument.id)
    // Apply default indicator preset if set
    const def = presetsStore.getDefault()
    if (def) chartStore.setIndicators([...def.indicators])
  }
  lastClose.value = currentPrice.value
}

function onAlertForIndicator(config: IndicatorConfig) {
  alertSeedIndicator.value = config
  showAlertForm.value = true
}

watch(currentTf, async (tf) => {
  if (!chartStore.symbol) return
  lastClose.value = currentPrice.value
  await chartStore.loadBars(chartStore.symbol, tf)
  if (chartStore.instrument) {
    await drawStore.loadDrawings(chartStore.instrument.id, tf)
  }
})

watch(showAlertForm, (v) => {
  if (!v) alertSeedIndicator.value = null  // clear seed when form closes
})

onMounted(async () => {
  alertsStore.connectWebSocket()
  await presetsStore.loadPresets()
  // Load ticker from URL param e.g. navigating from /alerts
  const sym = route.params.symbol as string | undefined
  if (sym) await onSymbolSelect(sym)
})
</script>

<style scoped>
.chart-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
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

.alert-form-wrap {
  position: fixed;
  top: 60px;
  right: 16px;
  z-index: 200;
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
