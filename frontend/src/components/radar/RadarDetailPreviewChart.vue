<template>
  <div class="radar-preview">
    <div v-if="!detection" class="radar-preview-state">Select a detection</div>
    <div v-else-if="store.isLoading" class="radar-preview-state">Loading {{ detection.instrument_symbol }}…</div>
    <div v-else-if="store.error" class="radar-preview-state radar-preview-state--error">{{ store.error }}</div>
    <UPlotChart
      v-else-if="store.symbol"
      :chart-type="'candles'"
      :show-indicators="false"
      :show-overlays="true"
      :enable-overlay-interactions="false"
      :enable-keyboard="false"
      :show-controls="false"
      :overlay-indicators="previewIndicators"
      :overlay-drawings="previewDrawings"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, provide, watch } from 'vue'

import UPlotChart from '@/components/chart/UPlotChart.vue'
import { buildRadarDrawingOverlays, buildRadarIndicatorOverlays, mergeChartDrawingsWithRadar } from '@/lib/radar/visuals'
import { usePanelStore } from '@/stores/chart'
import type { RadarDetection } from '@/types'

const props = defineProps<{
  detection: RadarDetection | null
}>()

const panelId = computed(() => `radar-preview-${props.detection?.id ?? 'empty'}`)
provide('panelId', panelId.value)

const store = usePanelStore(panelId.value)
const previewDetections = computed(() => (props.detection ? [props.detection] : []))
const previewIndicators = computed(() =>
  buildRadarIndicatorOverlays(previewDetections.value, props.detection?.id ?? null)
)
const previewDrawings = computed(() =>
  mergeChartDrawingsWithRadar(
    [],
    buildRadarDrawingOverlays(previewDetections.value, props.detection?.id ?? null),
    {
      instrumentId: props.detection?.instrument_id ?? null,
      timeframe: props.detection?.timeframe ?? null,
    },
  )
)

async function refreshPreview() {
  if (!props.detection) {
    store.symbol = ''
    store.bars = []
    store.error = null
    return
  }
  await store.loadBars(props.detection.instrument_symbol, props.detection.timeframe, 'candles')
}

watch(
  () => [props.detection?.id, props.detection?.timeframe, props.detection?.instrument_symbol],
  () => {
    refreshPreview()
  },
)

onMounted(refreshPreview)
</script>

<style scoped>
.radar-preview {
  height: 214px;
  min-height: 214px;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  background: #0a0a0a;
  overflow: hidden;
}

.radar-preview :deep(.chart-root) {
  height: 100%;
}

.radar-preview :deep(.help-btn),
.radar-preview :deep(.settings-btn),
.radar-preview :deep(.go-to-latest) {
  display: none;
}

.radar-preview-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  padding: 12px;
  text-align: center;
}

.radar-preview-state--error {
  color: #ef8a85;
}
</style>
