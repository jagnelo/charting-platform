<template>
  <section class="coverage-summary" role="region" :aria-label="`${symbol} coverage`" :aria-busy="loading || rangeLoading">
    <p v-if="loading" class="coverage-summary__state" role="status" aria-live="polite">Loading local coverage…</p>
    <p v-else-if="error" class="coverage-summary__state coverage-summary__state--error" role="alert" aria-live="assertive">{{ error }}</p>
    <template v-else>
      <div class="coverage-summary__identity">
        <span>Canonical instrument</span><strong>{{ symbol }}</strong>
      </div>
      <div v-if="daily" class="coverage-summary__grid">
        <span>Adjusted daily bars</span><b>{{ daily.bar_count.toLocaleString() }}</b>
        <span>Local range</span><b>{{ formatRange(daily.oldest, daily.newest) }}</b>
      </div>
      <p v-else class="coverage-summary__state">No local adjusted daily observations.</p>
      <div v-if="datasetStates.length" class="coverage-summary__datasets">
        <span>Dataset state</span>
        <ul>
          <li v-for="state in datasetStates" :key="`${state.dataset_type}:${state.dataset_key}`" :class="`coverage-summary__dataset--${state.status}`">
            <span :aria-label="`${state.dataset_type}${state.dataset_key ? ` · ${state.dataset_key}` : ''}: ${state.status}`">{{ state.dataset_type }}{{ state.dataset_key ? ` · ${state.dataset_key}` : '' }}: {{ state.status }}</span>
          </li>
        </ul>
      </div>
      <section class="coverage-summary__range" aria-label="OHLCV range readiness">
        <div class="coverage-summary__range-header">
          <strong>Check OHLCV range</strong>
          <span>Canonical local bars only</span>
        </div>
        <div class="coverage-summary__range-controls">
          <label>Timeframe
            <select v-model="rangeTimeframe" aria-label="Coverage timeframe">
              <option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label>From <input v-model.trim="rangeStart" aria-label="Coverage start date" type="date" /></label>
          <label>To <input v-model.trim="rangeEnd" aria-label="Coverage end date" type="date" /></label>
          <label>Mode
            <select v-model="rangeMode" aria-label="Coverage mode">
              <option value="historical">Historical</option>
              <option value="latest">Latest</option>
            </select>
          </label>
          <label class="coverage-summary__adjusted"><input v-model="rangeAdjusted" aria-label="Coverage split adjusted" type="checkbox" /> Adjusted</label>
          <button type="button" aria-label="Check OHLCV range" :disabled="rangeLoading || !rangeValid" @click="checkRange">{{ rangeLoading ? 'Checking…' : 'Check' }}</button>
        </div>
        <p v-if="rangeValidationError" class="coverage-summary__range-message coverage-summary__range-message--error" role="alert" aria-live="assertive">{{ rangeValidationError }}</p>
        <p v-else-if="rangeError" class="coverage-summary__range-message coverage-summary__range-message--error" role="alert" aria-live="assertive">{{ rangeError }}</p>
        <div v-else-if="rangeAssessment" class="coverage-summary__assessment" role="status" aria-live="polite" :class="`coverage-summary__assessment--${rangeAssessment.status}`">
          <div><span>Status</span><strong>{{ rangeAssessment.status }}</strong></div>
          <div><span>Bars</span><strong>{{ rangeAssessment.bar_count.toLocaleString() }}</strong></div>
          <div><span>Covered</span><strong>{{ formatRange(rangeAssessment.covered_start, rangeAssessment.covered_end) }}</strong></div>
          <p>{{ rangeAssessment.explanation }}</p>
          <div v-if="rangeAssessment.missing_slices.length" class="coverage-summary__missing">
            <span>Missing slices ({{ rangeAssessment.missing_slices.length }})</span>
            <ul>
              <li v-for="slice in rangeAssessment.missing_slices" :key="`${slice.start}:${slice.end}`">{{ formatRange(slice.start, slice.end) }}</li>
            </ul>
          </div>
        </div>
        <p v-else class="coverage-summary__range-message" role="status" aria-live="polite">Choose a date range to inspect local readiness and missing slices.</p>
      </section>
      <p class="coverage-summary__note">Local canonical data only · source and freshness limitations remain explicit in each dataset state.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'

interface CoverageRange { oldest: string | null; newest: string | null; bar_count: number }
interface DatasetState { dataset_type: string; dataset_key: string; status: 'fresh' | 'stale' | 'pending' | 'failed'; updated_at?: string | null }
interface OhlcvCoverageSlice { start: string; end: string }
interface OhlcvCoverageAssessment { status: 'ready' | 'partial' | 'missing' | 'stale'; covered_start: string | null; covered_end: string | null; bar_count: number; missing_slices: OhlcvCoverageSlice[]; explanation: string }

const props = defineProps<{ symbol: string; configuration?: Record<string, unknown> }>()
const queryClient = useQueryClient()
const emit = defineEmits<{ configuration: [configuration: Record<string, unknown>] }>()
const loading = ref(false)
const error = ref<string | null>(null)
const coverage = ref<Record<string, CoverageRange>>({})
const datasetStates = ref<DatasetState[]>([])
const timeframeOptions = [
  { value: 'D1', label: 'Daily' }, { value: 'W1', label: 'Weekly' }, { value: 'MN', label: 'Monthly' },
  { value: 'H1', label: 'Hourly' }, { value: 'M15', label: '15 minute' },
]
const configuredString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const rangeTimeframe = ref(timeframeOptions.some(option => option.value === configuredString('coverage_timeframe', 'D1')) ? configuredString('coverage_timeframe', 'D1') : 'D1')
const rangeStart = ref(configuredString('coverage_start', ''))
const rangeEnd = ref(configuredString('coverage_end', ''))
const rangeMode = ref<'historical' | 'latest'>(configuredString('coverage_mode', 'historical') === 'latest' ? 'latest' : 'historical')
const rangeAdjusted = ref(props.configuration?.coverage_adjusted !== false)
const rangeLoading = ref(false)
const rangeError = ref('')
const rangeAssessment = ref<OhlcvCoverageAssessment | null>(null)
let requestId = 0
let rangeRequestId = 0

const daily = computed(() => coverage.value.D1 ?? null)
const rangeValidationError = computed(() => {
  if (!rangeStart.value || !rangeEnd.value) return ''
  return rangeEnd.value < rangeStart.value ? 'The end date must be on or after the start date.' : ''
})
const rangeValid = computed(() => Boolean(rangeStart.value && rangeEnd.value && !rangeValidationError.value))

watch(() => props.symbol, async symbol => {
  const id = ++requestId
  rangeRequestId += 1
  rangeAssessment.value = null
  rangeError.value = ''
  loading.value = true
  error.value = null
  try {
    const response = await queryClient.fetchQuery<{
      local_coverage: Record<string, CoverageRange>
      dataset_states?: DatasetState[]
    }>({
      queryKey: ['workstation', 'coverage', 'instrument', symbol.toUpperCase()],
      queryFn: () => api.get<{
        local_coverage: Record<string, CoverageRange>
        dataset_states?: DatasetState[]
      }>(`/coverage/instruments/${encodeURIComponent(symbol)}`),
      staleTime: 30_000,
    })
    if (id !== requestId) return
    coverage.value = response.local_coverage ?? {}
    datasetStates.value = (response.dataset_states ?? []).slice(0, 6)
  } catch (caught: any) {
    if (id !== requestId) return
    coverage.value = {}
    datasetStates.value = []
    error.value = caught?.message ?? 'Coverage is unavailable.'
  } finally {
    if (id === requestId) loading.value = false
  }
}, { immediate: true })

watch(() => props.configuration, configuration => {
  const requestedTimeframe = typeof configuration?.coverage_timeframe === 'string' ? configuration.coverage_timeframe : 'D1'
  if (timeframeOptions.some(option => option.value === requestedTimeframe)) rangeTimeframe.value = requestedTimeframe
  rangeStart.value = typeof configuration?.coverage_start === 'string' ? configuration.coverage_start : ''
  rangeEnd.value = typeof configuration?.coverage_end === 'string' ? configuration.coverage_end : ''
  rangeMode.value = configuration?.coverage_mode === 'latest' ? 'latest' : 'historical'
  rangeAdjusted.value = configuration?.coverage_adjusted !== false
}, { deep: true })

watch([rangeTimeframe, rangeStart, rangeEnd, rangeMode, rangeAdjusted], () => {
  emit('configuration', {
    ...(props.configuration ?? {}),
    coverage_timeframe: rangeTimeframe.value,
    coverage_start: rangeStart.value || undefined,
    coverage_end: rangeEnd.value || undefined,
    coverage_mode: rangeMode.value,
    coverage_adjusted: rangeAdjusted.value,
  })
})

function toUtcBoundary(value: string, endOfDay: boolean) {
  return new Date(`${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}Z`).toISOString()
}

async function checkRange() {
  if (!rangeValid.value) return
  const id = ++rangeRequestId
  rangeLoading.value = true
  rangeError.value = ''
  try {
    const params = {
      timeframe: rangeTimeframe.value,
      start: toUtcBoundary(rangeStart.value, false),
      end: toUtcBoundary(rangeEnd.value, true),
      mode: rangeMode.value,
      adjusted: rangeAdjusted.value,
    }
    const response = await queryClient.fetchQuery<OhlcvCoverageAssessment>({
      queryKey: ['workstation', 'coverage', 'ohlcv', props.symbol.toUpperCase(), params],
      queryFn: () => api.get<OhlcvCoverageAssessment>(`/coverage/instruments/${encodeURIComponent(props.symbol)}/ohlcv`, params),
      staleTime: 30_000,
    })
    if (id === rangeRequestId) rangeAssessment.value = response
  } catch (caught: any) {
    if (id === rangeRequestId) {
      rangeAssessment.value = null
      rangeError.value = caught?.message ?? 'OHLCV readiness is unavailable.'
    }
  } finally {
    if (id === rangeRequestId) rangeLoading.value = false
  }
}

function formatRange(start: string | null, end: string | null) {
  if (!start || !end) return 'Unavailable'
  return `${new Date(start).toLocaleDateString()} – ${new Date(end).toLocaleDateString()}`
}
</script>

<style scoped>
.coverage-summary { display: grid; gap: 9px; padding: 9px; font-size: 12px; color: var(--text-secondary, #bdc5d1); }
.coverage-summary__identity, .coverage-summary__grid { display: grid; grid-template-columns: minmax(110px, 1fr) minmax(0, 1.6fr); gap: 5px 9px; align-items: baseline; }
.coverage-summary strong, .coverage-summary b { color: var(--text-primary, #f2f5f8); font-variant-numeric: tabular-nums; }
.coverage-summary__state { margin: 0; color: var(--text-secondary, #bdc5d1); }
.coverage-summary__state--error, .coverage-summary__dataset--failed { color: var(--danger, #ff7b72); }
.coverage-summary__datasets { border-top: 1px solid var(--border, #36404b); padding-top: 8px; }
.coverage-summary__datasets > span { color: var(--text-muted, #8893a1); }
.coverage-summary__datasets ul { display: grid; gap: 3px; margin: 5px 0 0; padding: 0; list-style: none; }
.coverage-summary__range { display: grid; gap: 8px; border-top: 1px solid var(--border, #36404b); padding-top: 9px; }
.coverage-summary__range-header, .coverage-summary__range-controls, .coverage-summary__assessment > div { display: flex; flex-wrap: wrap; gap: 7px 10px; align-items: center; }
.coverage-summary__range-header { justify-content: space-between; }
.coverage-summary__range-header span, .coverage-summary__range-message { color: var(--text-muted, #8893a1); }
.coverage-summary__range-controls label { display: grid; gap: 3px; color: var(--text-muted, #8893a1); font-size: 11px; }
.coverage-summary__range-controls select, .coverage-summary__range-controls input[type="date"] { min-height: 24px; border: 1px solid var(--border, #36404b); background: var(--surface-raised, #202932); color: var(--text-primary, #f2f5f8); font: inherit; padding: 2px 5px; }
.coverage-summary__range-controls button { min-height: 25px; border: 1px solid var(--accent, #5aa9e6); background: var(--accent, #5aa9e6); color: #101820; font: inherit; padding: 3px 9px; cursor: pointer; }
.coverage-summary__range-controls button:disabled { cursor: not-allowed; opacity: .5; }
.coverage-summary__adjusted { display: flex !important; align-items: center; margin-top: 16px; }
.coverage-summary__range-message { margin: 0; }
.coverage-summary__range-message--error { color: var(--danger, #ff7b72); }
.coverage-summary__assessment { display: grid; gap: 6px; border-left: 3px solid var(--accent, #5aa9e6); padding: 5px 0 5px 8px; }
.coverage-summary__assessment--ready { border-color: var(--positive, #61c58c); }
.coverage-summary__assessment--partial, .coverage-summary__assessment--stale { border-color: var(--warning, #e8b44b); }
.coverage-summary__assessment--missing { border-color: var(--danger, #ff7b72); }
.coverage-summary__assessment > div { justify-content: space-between; }
.coverage-summary__assessment > div > span, .coverage-summary__missing > span { color: var(--text-muted, #8893a1); }
.coverage-summary__assessment p { margin: 0; color: var(--text-secondary, #bdc5d1); line-height: 1.35; }
.coverage-summary__missing ul { display: grid; gap: 3px; margin: 4px 0 0; padding-left: 16px; color: var(--text-secondary, #bdc5d1); }
.coverage-summary__dataset--stale { color: var(--warning, #e8b44b); }
.coverage-summary__dataset--pending { color: var(--text-muted, #8893a1); }
.coverage-summary__note { margin: 0; color: var(--text-muted, #8893a1); font-size: 11px; line-height: 1.35; }
</style>
