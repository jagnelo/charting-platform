<template>
  <div class="advanced-chart-widget">
    <div v-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="store.isLoading" class="widget-state">Loading {{ symbol }}...</div>
    <div v-else-if="store.error" class="widget-state error">{{ store.error }}</div>
    <UPlotChart v-else-if="store.symbol" :chart-type="chartType" />
    <div v-if="symbol" class="chart-link">
      <router-link :to="`/chart/${encodeURIComponent(symbol)}`">Open in chart</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, watch } from 'vue'
import UPlotChart from '@/components/chart/UPlotChart.vue'
import { usePanelStore } from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import { api } from '@/lib/api'
import type { Timeframe } from '@/types'

const props = defineProps<{
  widgetId: number
  config: Record<string, any>
}>()

const panelId = `dashboard-${props.widgetId}`
provide('panelId', panelId)

const store = usePanelStore(panelId)
const drawStore = useDrawingsStore()
const alertsStore = useAlertsStore()

const symbol = computed(() => String(props.config.symbol ?? '').trim().toUpperCase())
const timeframe = computed<Timeframe>(() => props.config.timeframe ?? 'D1')
const chartType = computed<'candles' | 'line'>(() => props.config.chartType === 'line' ? 'line' : 'candles')
const EXPR_RE = /^[A-Z0-9.^]+(\s*[+\-*/]\s*[A-Z0-9.^]+)+$/i

async function refresh() {
  if (!symbol.value) return
  const target = await resolveTarget(symbol.value)
  await store.loadBars(target, timeframe.value)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, timeframe.value)
    await alertsStore.loadAlerts(store.instrument.id)
  }
}

async function resolveTarget(target: string) {
  if (!EXPR_RE.test(target)) return target
  const instrument = await api.post<{ symbol: string }>('/instruments/resolve-expression', {
    expression: target,
  })
  return instrument.symbol
}

watch(() => [symbol.value, timeframe.value, chartType.value], refresh)
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
