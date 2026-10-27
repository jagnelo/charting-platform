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
        <p>Recent {{ HISTORY_RANGE_LIMIT_DAYS[props.timeframe] }} days are selected by default. Custom ranges stay within this limit.</p>
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
import { computed, ref, watch } from 'vue'
import { api } from '@/lib/api'
import {
  acquireInstrumentHistory,
  defaultHistoryRange,
  HISTORY_RANGE_LIMIT_DAYS,
  historyRangeIsAllowed,
  resolveExistingInstrument,
  type HistoryAcquisitionResponse,
  type HistoryCoverageSummary,
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
const stage = ref<'coverage' | 'identity' | 'history' | null>(null)
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
    : `Choose a past range of at most ${HISTORY_RANGE_LIMIT_DAYS[props.timeframe]} days.`
})

const actionLabel = computed(() => stage.value === 'coverage'
  ? 'Checking local history…'
  : stage.value === 'identity'
    ? 'Checking instrument…'
    : stage.value === 'history'
      ? 'Loading missing history…'
      : 'Load missing history')

let actionGeneration = 0

watch(() => [props.symbol, props.timeframe], () => {
  actionGeneration += 1
  stage.value = null
  message.value = ''
  error.value = ''
})

watch(() => [startDate.value, endDate.value], () => {
  actionGeneration += 1
  message.value = ''
  error.value = ''
})

async function loadMissingHistory() {
  const range = selectedRange.value
  if (!props.symbol || !range || rangeError.value || busy.value) return
  const generation = actionGeneration
  const symbol = props.symbol
  const timeframe = props.timeframe
  stage.value = 'coverage'
  message.value = ''
  error.value = ''

  let checked: HistoryCoverageSummary
  try {
    checked = await api.get<HistoryCoverageSummary>(`/coverage/instruments/${encodeURIComponent(symbol)}/ohlcv`, {
      timeframe,
      start: range.start,
      end: range.end,
      mode: 'historical',
      adjusted: props.adjusted !== false,
    })
  } catch {
    if (generation === actionGeneration) error.value = 'Local history could not be checked. No source request was sent.'
    return finish(generation)
  }
  if (generation !== actionGeneration) return
  if (!Array.isArray(checked.missing_slices) || checked.missing_slices.length === 0) {
    message.value = `Recent data for ${symbol} is already available locally. No source request was sent.`
    return finish(generation)
  }

  stage.value = 'identity'
  let instrumentId: number | null = null
  try {
    const identity = await resolveExistingInstrument(symbol)
    if (generation !== actionGeneration) return
    if (identity.status === 'resolved' && identity.instrument
      && identity.instrument.symbol.trim().toUpperCase() === symbol.trim().toUpperCase()
      && Number.isSafeInteger(identity.instrument.instrument_id) && identity.instrument.instrument_id > 0) {
      instrumentId = identity.instrument.instrument_id
    } else {
      error.value = identity.status === 'identity_conflict'
        ? `The identity of ${symbol} is conflicting. No history was requested.`
        : identity.status === 'held'
          ? `Instrument verification for ${symbol} is currently held. No history was requested.`
          : `The instrument for ${symbol} could not be verified. No history was requested.`
    }
  } catch {
    if (generation === actionGeneration) error.value = `Instrument verification for ${symbol} failed. No history was requested.`
  }
  if (generation !== actionGeneration) return
  if (instrumentId == null) return finish(generation)

  stage.value = 'history'
  try {
    const result = await acquireInstrumentHistory(instrumentId, {
      timeframe,
      adjusted: props.adjusted !== false,
      start: range.start,
      end: range.end,
    })
    if (generation !== actionGeneration) return
    message.value = result.status === 'complete'
      ? `History loaded: ${result.coverage.bar_count} bars are available.`
      : result.status === 'partial'
        ? `Some history loaded; ${result.coverage.missing_slices.length} range(s) remain unavailable.`
        : result.status === 'held'
          ? 'The history request is held. Your existing chart remains available.'
          : result.status === 'no_data'
            ? 'No history was returned. Your existing chart remains available.'
            : 'History could not be loaded. Your existing chart remains available.'
    if (result.status === 'complete' || result.status === 'partial') emit('loaded', result)
  } catch {
    if (generation === actionGeneration) error.value = 'History could not be loaded. Your existing chart remains available.'
  }
  return finish(generation)
}

function finish(generation: number) {
  if (generation === actionGeneration) stage.value = null
}
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
