<template>
  <section class="history-acquisition" :aria-busy="busy ? 'true' : 'false'">
    <button
      type="button"
      class="history-acquisition__load"
      data-testid="history-load-missing"
      :disabled="!props.symbol || !selectedRange || Boolean(rangeError) || busy"
      @click="loadMissingHistory"
    >{{ actionLabel }}</button>
    <details class="history-acquisition__advanced">
      <summary>Custom date range</summary>
      <div class="history-acquisition__body">
        <p>The default range is {{ HISTORY_DEFAULT_RANGE_DAYS[props.timeframe] }} days. Each request is limited to {{ HISTORY_ACQUISITION_MAX_REQUESTED_BARS }} time slots; provider history and entitlement limits still apply.</p>
        <p>Sources may not cover every date. Partial or held results are reported, and existing chart data stays available.</p>
        <label>From <input v-model="startDate" type="date" aria-label="History start date" :max="today" :disabled="busy" /></label>
        <label>To <input v-model="endDate" type="date" aria-label="History end date" :max="today" :disabled="busy" /></label>
        <p v-if="rangeError" role="alert">{{ rangeError }}</p>
      </div>
    </details>
    <p v-if="message" role="status" aria-live="polite">{{ message }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  acquireSelectedHistory,
  defaultHistoryRange,
  HISTORY_DEFAULT_RANGE_DAYS,
  HISTORY_ACQUISITION_MAX_REQUESTED_BARS,
  historyRangeIsAllowed,
  type HistoryAcquisitionResponse,
  type SelectedHistoryStage,
} from '@/lib/onDemandAcquisition'
import type { Timeframe } from '@/types'

const props = withDefaults(defineProps<{
  symbol: string
  timeframe: Timeframe
  adjusted?: boolean
}>(), {
  // Vue casts an absent Boolean prop to false unless a default is explicit.
  // Charts use adjusted candles by default, so acquisition must match them.
  adjusted: true,
})
const emit = defineEmits<{ loaded: [result: HistoryAcquisitionResponse] }>()
const startDate = ref('')
const endDate = ref('')
const stage = ref<SelectedHistoryStage | null>(null)
const message = ref('')
const error = ref('')
const busy = computed(() => stage.value !== null)
const hasCustomDate = computed(() => Boolean(startDate.value || endDate.value))
const today = computed(() => new Date().toISOString().slice(0, 10))

function customDateTime(day: string, end: boolean): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null
  const time = Date.parse(`${day}T${end ? '23:59:59.999' : '00:00:00.000'}Z`)
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== day) return null
  return new Date(time).toISOString()
}

const selectedRange = computed(() => {
  if (!hasCustomDate.value) return defaultHistoryRange(props.timeframe)
  if (!startDate.value || !endDate.value) return null
  try {
    const start = customDateTime(startDate.value, false)
    const endDateTime = customDateTime(endDate.value, true)
    if (!start || !endDateTime) return null
    const endOfDay = Date.parse(endDateTime)
    const end = Math.min(endOfDay, Date.now())
    return { start, end: new Date(end).toISOString() }
  } catch {
    return null
  }
})

const rangeError = computed(() => {
  if (!hasCustomDate.value) return ''
  if (!startDate.value || !endDate.value) return 'Choose both dates or clear them to use the recent range.'
  const range = selectedRange.value
  return range && historyRangeIsAllowed(props.timeframe, range.start, range.end)
    ? ''
    : `Choose a past range within ${HISTORY_ACQUISITION_MAX_REQUESTED_BARS} time slots.`
})

const actionLabel = computed(() => stage.value === 'coverage'
  ? 'Checking local history…'
  : stage.value === 'identity'
    ? 'Checking instrument…'
    : stage.value === 'history'
      ? 'Loading missing history…'
      : stage.value === 'waiting'
        ? 'Waiting to retry…'
      : 'Load missing history')

let actionGeneration = 0
let actionAbortController: AbortController | null = null

function cancelCurrentAction() {
  actionAbortController?.abort()
  actionAbortController = null
}

watch(() => [props.symbol, props.timeframe], () => {
  cancelCurrentAction()
  actionGeneration += 1
  stage.value = null
  message.value = ''
  error.value = ''
})

watch(() => [startDate.value, endDate.value], () => {
  cancelCurrentAction()
  actionGeneration += 1
  message.value = ''
  error.value = ''
})

async function loadMissingHistory() {
  const range = selectedRange.value
  if (!props.symbol || !range || rangeError.value || busy.value) return
  cancelCurrentAction()
  const controller = new AbortController()
  actionAbortController = controller
  const generation = ++actionGeneration
  const symbol = props.symbol
  const timeframe = props.timeframe
  stage.value = 'coverage'
  let activeStage: SelectedHistoryStage = 'coverage'
  const stageAtFailure = (): SelectedHistoryStage => activeStage
  message.value = ''
  error.value = ''
  const adjusted = props.adjusted !== false
  try {
    const outcome = await acquireSelectedHistory(symbol, timeframe, adjusted, {
      timeframe, adjusted, start: range.start, end: range.end,
    }, (nextStage: SelectedHistoryStage, retryAt?: string) => {
      if (generation === actionGeneration) {
        activeStage = nextStage
        stage.value = nextStage
        if (nextStage === 'waiting' && retryAt) {
          message.value = `Waiting to retry history for ${symbol} after ${new Date(retryAt).toLocaleTimeString()}…`
        }
      }
    }, () => generation === actionGeneration && !controller.signal.aborted,
    undefined,
    { signal: controller.signal })
    if (generation !== actionGeneration) return
    if (outcome.kind === 'superseded') return
    if (outcome.kind === 'already-covered') {
      message.value = `Requested history for ${symbol} is already saved locally. No source request was sent.`
      return finish(generation)
    }
    if (outcome.kind === 'identity-unavailable') {
      message.value = outcome.status === 'held'
        ? `Instrument verification for ${symbol} is temporarily held${outcome.retryAt ? `; try again after ${new Date(outcome.retryAt).toLocaleTimeString()}` : ''}. No history was requested.`
        : outcome.status === 'identity_conflict'
          ? `The identity of ${symbol} conflicts with the selected instrument. No history was requested.`
          : `The instrument for ${symbol} could not be verified. No history was requested.`
      return finish(generation)
    }
    if (outcome.kind === 'admission-held') {
      message.value = `History for ${symbol} is temporarily held by the current admission limits. Your existing chart remains available.`
      return finish(generation)
    }
    if (outcome.kind === 'admission-unavailable') {
      message.value = `The allowed history window for ${symbol} could not be confirmed. Your existing chart remains available.`
      return finish(generation)
    }
    if (outcome.kind === 'coverage-unavailable') {
      message.value = `Saved history coverage for ${symbol} could not be confirmed. Your existing chart remains available.`
      return finish(generation)
    }
    if (outcome.kind === 'at-earliest-bound') {
      message.value = `The available history for ${symbol} begins ${new Date(outcome.earliestStart).toLocaleDateString()}.`
      return finish(generation)
    }
    activeStage = 'history'
    stage.value = 'history'
    const result = outcome.result
    const requestedStart = Date.parse(range.start)
    const effectiveStart = Date.parse(result.requested_start)
    const clippedMessage = Number.isFinite(requestedStart) && Number.isFinite(effectiveStart) && effectiveStart > requestedStart
      ? ` The admitted range begins ${new Date(result.requested_start).toLocaleDateString()}.`
      : ''
    message.value = result.status === 'complete'
      ? `History loaded: ${result.coverage.bar_count} bars are available.${clippedMessage}`
      : result.status === 'partial'
        ? `Some history loaded; ${result.coverage.missing_slices.length} range(s) remain unavailable.${clippedMessage}`
        : result.status === 'held'
          ? `The history request is temporarily held${result.retry_at ? `; try again after ${new Date(result.retry_at).toLocaleTimeString()}` : ''}. Your existing chart remains available.`
          : result.status === 'no_data'
            ? 'No history was returned. Your existing chart remains available.'
            : 'History could not be loaded. Your existing chart remains available.'
    if (result.status === 'complete' || result.status === 'partial') emit('loaded', result)
  } catch {
    if (generation === actionGeneration) {
      const failedAt = stageAtFailure()
      error.value = failedAt === 'coverage'
        ? 'Local history could not be checked. No source request was sent.'
        : failedAt === 'identity'
          ? `Instrument verification for ${symbol} failed. No history was requested.`
          : 'History could not be loaded. Your existing chart remains available.'
    }
  }
  return finish(generation)
}

function finish(generation: number) {
  if (generation === actionGeneration) {
    stage.value = null
    actionAbortController = null
  }
}

onBeforeUnmount(cancelCurrentAction)
</script>

<style scoped>
.history-acquisition { display: flex; align-items: center; gap: 6px; min-width: 0; position: relative; }
.history-acquisition__load { min-height: 30px; max-width: min(92vw, 360px); white-space: nowrap; }
.history-acquisition__advanced { position: relative; }
.history-acquisition__advanced summary { cursor: pointer; font-size: 12px; }
.history-acquisition__body { position: absolute; z-index: 30; top: calc(100% + 6px); right: 0; display: grid; gap: 8px; width: min(320px, 92vw); box-sizing: border-box; padding: 12px; color: var(--tc-text, #d5dde4); background: var(--tc-surface, #20282e); border: 1px solid var(--tc-border, #38444c); border-radius: 6px; box-shadow: 0 8px 24px #0008; }
.history-acquisition__body label { display: grid; gap: 3px; font-size: 12px; }
.history-acquisition__body input { min-width: 0; max-width: 100%; }
.history-acquisition__body p, .history-acquisition > p { margin: 0; font-size: 12px; }
@media (max-width: 600px) {
  .history-acquisition { flex-wrap: wrap; }
  .history-acquisition__body { right: auto; left: 0; }
}
</style>
