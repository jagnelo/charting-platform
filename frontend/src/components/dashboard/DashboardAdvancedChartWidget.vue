<template>
  <div class="advanced-chart-widget">
    <div v-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="store.isLoading" class="widget-state">Loading {{ symbol }}...</div>
    <div v-else-if="store.error" class="widget-state error">{{ store.error }}</div>
    <UPlotChart
      v-else-if="store.symbol"
      :chart-type="chartType"
      :overlay-drawings="showDrawings ? drawings : []"
      :overlay-alerts="showAlerts ? priceAlerts : []"
      :show-indicators="showIndicators"
      :show-overlays="showDrawings || showAlerts"
      :enable-overlay-interactions="false"
      :enable-keyboard="false"
      :show-controls="false"
    />
    <div v-if="symbol" class="chart-link">
      <router-link :to="`/chart/${encodeURIComponent(symbol)}`">Open in chart</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import { usePanelStore } from '@/stores/chart'
import { api } from '@/lib/api'
import type { ChartBarType, ChartDrawing, PriceAlert, Timeframe } from '@/types'

const props = defineProps<{
  widgetId: number
  config: Record<string, any>
  overrideSymbol?: string
}>()

const panelId = `dashboard-${props.widgetId}`
provide('panelId', panelId)

const store = usePanelStore(panelId)

const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? '').trim()).toUpperCase()
)
const timeframe = computed<Timeframe>(() => props.config.timeframe ?? 'D1')
const chartType = computed<ChartBarType>(() => props.config.chartType ?? 'candles')
const showIndicators = computed(() => props.config.showIndicators !== false)
const showDrawings = computed(() => props.config.showDrawings !== false)
const showAlerts = computed(() => props.config.showAlerts !== false)
const drawings = ref<ChartDrawing[]>([])
const priceAlerts = ref<PriceAlert[]>([])
const EXPR_RE = /^\s*=/
let refreshSeq = 0

async function refresh() {
  const seq = ++refreshSeq
  if (!symbol.value) {
    store.symbol = ''
    store.bars = []
    drawings.value = []
    priceAlerts.value = []
    return
  }
  try {
    const target = await resolveTarget(symbol.value)
    if (seq !== refreshSeq) return
    await store.loadBars(target, timeframe.value, chartType.value)
    if (seq !== refreshSeq) return
    await loadReadOnlyOverlays(seq)
  } catch (e: any) {
    if (seq === refreshSeq) store.error = e?.message ?? 'Chart unavailable'
  }
}

async function loadReadOnlyOverlays(seq: number) {
  const instrumentId = store.instrument?.id
  if (!instrumentId) {
    drawings.value = []
    priceAlerts.value = []
    return
  }

  const [loadedDrawings, loadedAlerts] = await Promise.all([
    showDrawings.value
      ? api.get<ChartDrawing[]>('/drawings', { instrument_id: instrumentId }).catch(() => [])
      : Promise.resolve([]),
    showAlerts.value
      ? api.get<PriceAlert[]>('/alerts/price', { instrument_id: instrumentId }).catch(() => [])
      : Promise.resolve([]),
  ])
  if (seq !== refreshSeq) return
  drawings.value = loadedDrawings
  priceAlerts.value = loadedAlerts
}

async function resolveTarget(target: string) {
  if (!EXPR_RE.test(target)) return target
  const instrument = await api.post<{ symbol: string }>('/instruments/resolve-expression', {
    expression: target,
  })
  return instrument.symbol
}

watch(() => [symbol.value, timeframe.value, chartType.value, showDrawings.value, showAlerts.value], refresh)
onMounted(refresh)
</script>

<style scoped>
.advanced-chart-widget {
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
}
.advanced-chart-widget :deep(.chart-root) { height: 100%; }
.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
  padding: 12px;
}
.widget-state.error { color: #ef5350; font-size: 10px; }
.chart-link {
  position: absolute;
  top: 6px;
  right: 28px;
  z-index: 5;
  font-size: 10px;
}
.chart-link a {
  color: #64b5f6;
  text-decoration: none;
  background: rgba(10, 10, 10, 0.85);
  border: 1px solid #242424;
  border-radius: 4px;
  padding: 3px 6px;
}
.chart-link a:hover { border-color: #3a3a3a; }
</style>
