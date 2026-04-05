<template>
  <div
    class="chart-panel"
    :class="{ 'is-active': isActive }"
    @mousedown="layoutStore.setActivePanel(panelId)"
  >
    <!-- Panel header -->
    <div class="panel-header">
      <SearchBar class="panel-search" @select="onSymbolSelect" />
      <div class="panel-sym-info" v-if="store.symbol">
        <span class="psym">{{ store.symbol }}</span>
        <span class="psym-name">{{ store.instrument?.name }}</span>
      </div>
      <TimeframeSelector v-model="localTf" class="panel-tf" />
    </div>

    <!-- Chart area -->
    <div class="panel-body">
      <div v-if="store.isLoading" class="panel-loading">
        Loading {{ store.symbol || '…' }}
      </div>
      <div v-else-if="!store.symbol" class="panel-empty">
        Search for a symbol
      </div>
      <UPlotChart v-else ref="chartRef" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, provide, onMounted } from 'vue'
import { usePanelStore }   from '@/stores/chart'
import { useLayoutStore }  from '@/stores/layout'
import { useDrawingsStore } from '@/stores/drawings'
import SearchBar         from '@/components/common/SearchBar.vue'
import TimeframeSelector from '@/components/chart/TimeframeSelector.vue'
import UPlotChart        from '@/components/chart/UPlotChart.vue'
import type { Timeframe } from '@/types'

const props = defineProps<{ panelId: string }>()

// Provide panel ID so UPlotChart uses the correct store instance
provide('panelId', props.panelId)

const layoutStore = useLayoutStore()
const store       = usePanelStore(props.panelId)
const drawStore   = useDrawingsStore()
const chartRef    = ref<InstanceType<typeof UPlotChart> | null>(null)

const panelConfig = computed(() => layoutStore.panels.find(p => p.id === props.panelId))
const isActive    = computed(() => layoutStore.activePanelId === props.panelId)

const localTf = ref<Timeframe>(panelConfig.value?.timeframe ?? 'D1')

async function onSymbolSelect(symbol: string) {
  layoutStore.updatePanel(props.panelId, { symbol, timeframe: localTf.value })
  await store.loadBars(symbol, localTf.value)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, localTf.value)
  }
}

watch(localTf, async (tf) => {
  layoutStore.updatePanel(props.panelId, { timeframe: tf })
  if (!store.symbol) return
  await store.loadBars(store.symbol, tf)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, tf)
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
  const cfg = panelConfig.value
  if (cfg?.symbol) {
    await store.loadBars(cfg.symbol, cfg.timeframe)
    if (store.instrument) {
      await drawStore.loadDrawings(store.instrument.id, cfg.timeframe)
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
  gap: 8px;
  padding: 4px 8px;
  background: #111;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.panel-search { width: 180px; }

.panel-sym-info {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.psym      { font-size: 13px; font-weight: 700; color: #fff; }
.psym-name { font-size: 10px; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

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
