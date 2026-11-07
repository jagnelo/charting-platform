<template>
  <div class="radar-preview">
    <div v-if="!detection" class="radar-preview-state">Select a detection</div>
    <template v-else>
      <p v-if="preparationMessage" class="radar-preview__preparation" role="status" aria-live="polite">{{ preparationMessage }}</p>
      <div v-if="store.isLoading" class="radar-preview-state">Loading {{ detection.instrument_symbol }}…</div>
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, provide, ref, watch } from 'vue'

import UPlotChart from '@/components/chart/UPlotChart.vue'
import {
  dataPreparationCoordinator,
  instrumentHistoryPreparationRequest,
  isPreparationTimeframe,
  PreparationProgressRefreshQueue,
  preparationStatusMessage,
  type DataEnsureResponse,
} from '@/lib/dataPreparation'
import { buildRadarDrawingOverlays, buildRadarIndicatorOverlays, mergeChartDrawingsWithRadar } from '@/lib/radar/visuals'
import { usePanelStore } from '@/stores/chart'
import type { RadarDetection } from '@/types'

const props = defineProps<{
  detection: RadarDetection | null
}>()

const preparationMessage = ref('')

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
  previewGeneration += 1
  const generation = previewGeneration
  preparationController?.abort()
  preparationController = null
  if (!props.detection) {
    store.symbol = ''
    store.bars = []
    store.error = null
    preparationMessage.value = ''
    return
  }
  const detection = props.detection
  const symbol = detection.instrument_symbol.trim().toUpperCase()
  const instrumentId = Number(detection.instrument_id)
  const timeframe = detection.timeframe
  const isCurrent = () => previewGeneration === generation
    && props.detection?.id === detection.id
    && props.detection?.instrument_id === detection.instrument_id
    && props.detection?.instrument_symbol.trim().toUpperCase() === symbol
    && props.detection?.timeframe === timeframe
  const historyController = new AbortController()
  preparationController = historyController
  const refreshQueue = new PreparationProgressRefreshQueue()
  const refreshIfCurrent = async (response: DataEnsureResponse) => {
    const history = response.dependencies.find(item => item.dataset === 'history')
    const hasCoverage = Boolean(history?.covered_ranges.length
      || (history?.covered_start && history.covered_end))
    if (!hasCoverage || !isCurrent()) return
    await refreshQueue.request(response, async () => {
      if (isCurrent()) await store.refreshLocalBars()
    })
  }

  // Keep the local preview useful immediately; preparation is a separate
  // authenticated lifecycle and never substitutes for the local read.
  void store.loadBars(symbol, timeframe, 'candles', true).catch(() => undefined)
  if (!Number.isSafeInteger(instrumentId) || instrumentId <= 0) {
    preparationMessage.value = 'This detection has no verified instrument identity; history preparation did not start.'
    return
  }
  if (!isPreparationTimeframe(timeframe)) {
    preparationMessage.value = `History preparation is not available for the ${timeframe} timeframe.`
    return
  }

  preparationMessage.value = `Checking saved ${timeframe} history for ${symbol}…`
  try {
    const result = await dataPreparationCoordinator.ensure(
      instrumentHistoryPreparationRequest({ kind: 'instrument', instrument_id: instrumentId }, timeframe, true),
      {
        signal: historyController.signal,
        onProgress: ({ response, completed, total }) => {
          if (!isCurrent()) return
          preparationMessage.value = response.status === 'ready'
            ? `Refreshing available ${timeframe} history for ${symbol}…`
            : response.status === 'partial' && response.has_pending_work === false
              ? preparationStatusMessage(response)
              : `Preparing ${timeframe} history for ${symbol} (${completed}/${total})…`
          void refreshIfCurrent(response).catch(() => {
            if (isCurrent()) preparationMessage.value = `New ${timeframe} history for ${symbol} is available but the preview could not refresh.`
          })
        },
      },
    )
    if (!isCurrent()) return
    preparationMessage.value = result.status === 'ready'
      ? `Local ${timeframe} history is ready for ${symbol}.`
      : preparationStatusMessage(result)
    await refreshIfCurrent(result)
  } catch (error) {
    if (isCurrent() && (error as { name?: string })?.name !== 'AbortError') {
      preparationMessage.value = `History for ${symbol} could not be prepared; the saved preview remains available.`
    }
  } finally {
    if (preparationController === historyController) preparationController = null
  }
}

let previewGeneration = 0
let preparationController: AbortController | null = null

watch(
  () => [props.detection?.id, props.detection?.instrument_id, props.detection?.timeframe, props.detection?.instrument_symbol],
  () => { void refreshPreview() },
  { immediate: true },
)

onBeforeUnmount(() => {
  previewGeneration += 1
  preparationController?.abort()
  preparationController = null
})
</script>

<style scoped>
.radar-preview {
  position: relative;
  height: 280px;
  min-height: 280px;
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

.radar-preview__preparation {
  position: absolute;
  z-index: 2;
  max-width: calc(100% - 12px);
  margin: 4px 6px;
  padding: 3px 5px;
  border: 1px solid var(--tc-border);
  border-radius: var(--tc-radius);
  background: color-mix(in srgb, var(--tc-panel-bg) 92%, transparent);
  color: var(--tc-text-muted);
  font: 10px/1.25 var(--tc-font-family);
  pointer-events: none;
}
</style>
