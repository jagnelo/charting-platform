<template>
  <div class="advanced-chart-widget">
    <div v-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="preparing && !hasCurrentBars" class="widget-state" role="status">{{ preparationMessage || `Preparing ${symbol}...` }}</div>
    <div v-else-if="preparationMessage && !hasCurrentBars" class="widget-state" :class="{ error: preparationFailed }" role="status">{{ preparationMessage }}</div>
    <div v-else-if="store.isLoading && !hasCurrentBars" class="widget-state">Loading cached bars for {{ symbol }}...</div>
    <div v-else-if="store.error && !hasCurrentBars" class="widget-state error">{{ store.error }}</div>
    <UPlotChart
      v-else-if="hasCurrentBars"
      :chart-type="chartType"
      :overlay-drawings="showDrawings ? drawings : []"
      :overlay-alerts="showAlerts ? priceAlerts : []"
      :show-indicators="showIndicators"
      :show-overlays="showDrawings || showAlerts"
      :enable-overlay-interactions="false"
      :enable-keyboard="false"
      :show-controls="false"
    />
    <div v-if="hasCurrentBars && preparationMessage" class="preparation-status" role="status">{{ preparationMessage }}</div>
    <div v-if="symbol" class="chart-link">
      <router-link :to="`/chart/${encodeURIComponent(symbol)}`">Open in chart</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import { usePanelStore } from '@/stores/chart'
import { api } from '@/lib/api'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import { dataPreparationCoordinator, instrumentHistoryPreparationRequest, preparationStatusMessage, PreparationProgressRefreshQueue, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
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
const hasCurrentBars = computed(() => store.symbol.toUpperCase() === symbol.value && store.bars.length > 0)
const timeframe = computed<Timeframe>(() => props.config.timeframe ?? 'D1')
const chartType = computed<ChartBarType>(() => props.config.chartType ?? 'candles')
const showIndicators = computed(() => props.config.showIndicators !== false)
const showDrawings = computed(() => props.config.showDrawings !== false)
const showAlerts = computed(() => props.config.showAlerts !== false)
const drawings = ref<ChartDrawing[]>([])
const priceAlerts = ref<PriceAlert[]>([])
const preparationMessage = ref('')
const preparationFailed = ref(false)
const preparing = ref(false)
let refreshSeq = 0
let mounted = false
let refreshController: AbortController | null = null

async function refresh() {
  const seq = ++refreshSeq
  refreshController?.abort()
  const controller = new AbortController()
  refreshController = controller
  let preparationSettled = false
  preparationMessage.value = ''
  preparationFailed.value = false
  preparing.value = !!symbol.value
  if (!symbol.value) {
    store.symbol = ''
    store.bars = []
    drawings.value = []
    priceAlerts.value = []
    preparing.value = false
    if (refreshController === controller) refreshController = null
    return
  }
  try {
    const requestedSymbol = symbol.value
    const selectedTimeframe = timeframe.value
    const target = await resolveTarget(requestedSymbol)
    if (!mounted || seq !== refreshSeq) return
    const isCurrent = () => mounted && seq === refreshSeq && !controller.signal.aborted
    const queue = new PreparationProgressRefreshQueue()
    // The panel store's local-only load uses its generation fence and never
    // takes a provider-capable history route. Start it before joining the
    // durable preparation request so an existing cache remains immediately useful.
    const initialRead = store.loadBars(target, selectedTimeframe, chartType.value, true)
    preparing.value = false
    const refreshForProgress = (response: import('@/lib/dataPreparation').DataEnsureResponse) =>
      queue.request(response, async () => {
        await initialRead
        if (!isCurrent() || !queue.isLatest(response)) return
        await store.refreshLocalBars()
        if (!isCurrent() || !queue.isLatest(response)) return
        await loadReadOnlyOverlays(seq)
      })
    const preparation = dataPreparationCoordinator.ensure(
      instrumentHistoryPreparationRequest({ kind: 'instrument', symbol: target }, selectedTimeframe),
      {
        signal: controller.signal,
        onProgress: progress => {
          if (!isCurrent()) return
          preparationMessage.value = preparationStatusMessage(progress.response)
          if (shouldRefreshAnalysisProgress(progress.response)) {
            void refreshForProgress(progress.response).catch(cause => {
              if (isCurrent() && !store.bars.length) store.error = cause?.message ?? 'Cached chart history could not be refreshed.'
            })
          }
        },
      },
    )
    void preparation.then(async prepared => {
      if (!isCurrent()) return
      preparationMessage.value = prepared.status === 'ready' ? '' : preparationStatusMessage(prepared)
      preparationFailed.value = ['failed', 'unavailable'].includes(prepared.status)
      await refreshForProgress(prepared)
    }).catch(() => {
      if (isCurrent()) preparationMessage.value = 'Data preparation could not be completed; showing cached chart history.'
    }).finally(() => {
      preparationSettled = true
      if (refreshController === controller) refreshController = null
    })
    await initialRead
    if (!isCurrent()) return
    await loadReadOnlyOverlays(seq)
  } catch (e: any) {
    if (mounted && seq === refreshSeq && !controller.signal.aborted) store.error = e?.message ?? 'Chart unavailable'
  } finally {
    if (mounted && seq === refreshSeq) preparing.value = false
    if (preparationSettled && refreshController === controller) refreshController = null
  }
}

async function loadReadOnlyOverlays(seq: number) {
  if (!mounted || seq !== refreshSeq) return
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
  if (!mounted || seq !== refreshSeq) return
  drawings.value = loadedDrawings
  priceAlerts.value = loadedAlerts
}

async function resolveTarget(target: string) {
  return ensureKnownInstrumentSymbol(target)
}

watch(() => [symbol.value, timeframe.value, chartType.value, showDrawings.value, showAlerts.value], refresh)
onMounted(() => {
  mounted = true
  void refresh()
})
onBeforeUnmount(() => {
  mounted = false
  refreshSeq += 1
  refreshController?.abort()
  refreshController = null
})
</script>

<style scoped>
.advanced-chart-widget {
  height: 100%;
  min-height: 0;
  position: relative;
  overflow: hidden;
}
.advanced-chart-widget :deep(.chart-root) { height: 100%; }
.preparation-status { position: absolute; left: 6px; bottom: 4px; z-index: 5; color: #9c9c77; font-size: 9px; }
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
