<template>
  <div class="coverage-panel">
    <div v-if="loading" class="coverage-panel__empty">Refreshing coverage…</div>
    <div v-else-if="error" class="coverage-panel__empty coverage-panel__empty--error">{{ error }}</div>
    <div v-else-if="!coverage" class="coverage-panel__empty">{{ emptyLabel }}</div>
    <template v-else>
      <div class="coverage-summary-grid">
        <div class="coverage-summary-card">
          <span class="coverage-summary-card__label">Requested</span>
          <strong>{{ formatRange(coverage.requested_date_from, coverage.requested_date_to) }}</strong>
          <small>{{ coverage.timeframe }}</small>
        </div>
        <div class="coverage-summary-card" :class="summaryStateClass(sharedRangeState)">
          <span class="coverage-summary-card__label">Shared universe</span>
          <strong>{{ formatRange(coverage.universe.collective_coverage_from, coverage.universe.collective_coverage_to) }}</strong>
          <small>{{ sharedRangeDetail }}</small>
        </div>
        <div class="coverage-summary-card">
          <span class="coverage-summary-card__label">Any selected symbol</span>
          <strong>{{ formatRange(coverage.universe.any_coverage_from, coverage.universe.any_coverage_to) }}</strong>
          <small>{{ anyRangeDetail }}</small>
        </div>
        <div class="coverage-summary-card" :class="summaryStateClass(benchmarkState)">
          <span class="coverage-summary-card__label">Benchmark</span>
          <strong>{{ formatRange(coverage.benchmark.available_from, coverage.benchmark.available_to) }}</strong>
          <small>{{ benchmarkDetail }}</small>
        </div>
      </div>

      <div class="coverage-chip-row">
        <span class="coverage-chip coverage-chip--neutral">{{ coverage.universe.instrument_count }} symbols</span>
        <span class="coverage-chip coverage-chip--positive">{{ coverage.universe.instruments_with_full_requested_coverage }} full</span>
        <span class="coverage-chip coverage-chip--warning">{{ coverage.universe.instruments_with_partial_requested_coverage }} partial</span>
        <span class="coverage-chip coverage-chip--negative">{{ coverage.universe.instruments_without_requested_coverage }} none</span>
        <span v-if="coverage.universe.simulatable_instrument_count != null" class="coverage-chip coverage-chip--neutral">
          {{ coverage.universe.simulatable_instrument_count }} simulatable
        </span>
      </div>

      <div v-if="coverageNotes.length" class="coverage-note-list">
        <div
          v-for="note in coverageNotes"
          :key="`${note.tone}-${note.text}`"
          class="coverage-note"
          :class="`coverage-note--${note.tone}`"
        >
          {{ note.text }}
        </div>
      </div>

      <div v-if="coverage.universe.instruments.length" class="coverage-list-section">
        <button
          type="button"
          class="coverage-list-toggle"
          :aria-expanded="instrumentListExpanded ? 'true' : 'false'"
          @click="instrumentListExpanded = !instrumentListExpanded"
        >
          <span class="coverage-list-toggle__icon" :class="{ 'coverage-list-toggle__icon--expanded': instrumentListExpanded }">▸</span>
          <span>Instrument coverage</span>
          <small>{{ sortedInstruments.length }} symbols</small>
        </button>

        <div v-if="instrumentListExpanded" class="coverage-table-wrap">
          <table class="coverage-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Available</th>
                <th>Within request</th>
                <th>Status</th>
                <th>Bars</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="instrument in sortedInstruments" :key="instrument.instrument_id">
                <td>{{ instrument.symbol }}</td>
                <td>{{ formatRange(instrument.available_from, instrument.available_to) }}</td>
                <td>{{ formatRange(instrument.requested_first_bar_at, instrument.requested_last_bar_at) }}</td>
                <td>
                  <span class="coverage-status-pill" :class="statusClass(instrument.requested_status)">
                    {{ humanizeStatus(instrument.requested_status) }}
                  </span>
                </td>
                <td>{{ instrument.requested_bars }} / {{ instrument.total_bars }}</td>
                <td>{{ instrument.note || (instrument.requested_status === 'full' ? 'Requested range is fully covered.' : '—') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import type { StrategyCoverageInstrument, StrategyCoveragePreview } from '@/types'

type CoverageTone = 'positive' | 'warning' | 'negative' | 'neutral'

const props = withDefaults(defineProps<{
  coverage: StrategyCoveragePreview | null
  loading?: boolean
  error?: string | null
  emptyLabel?: string
}>(), {
  loading: false,
  error: null,
  emptyLabel: 'Coverage detail will appear here.',
})

const instrumentListExpanded = ref(false)

const sortedInstruments = computed(() => {
  if (!props.coverage) return []
  const order: Record<string, number> = {
    missing: 0,
    none: 1,
    partial: 2,
    full: 3,
  }
  return [...props.coverage.universe.instruments].sort((left, right) => {
    const leftOrder = order[String(left.requested_status)] ?? 4
    const rightOrder = order[String(right.requested_status)] ?? 4
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return left.symbol.localeCompare(right.symbol)
  })
})

const sharedRangeState = computed<CoverageTone>(() => {
  if (!props.coverage) return 'neutral'
  const fits = props.coverage.universe.requested_fits_collective_range
  if (fits === false) return 'warning'
  if (fits === true) return 'positive'
  return 'neutral'
})

const benchmarkState = computed<CoverageTone>(() => {
  if (!props.coverage) return 'neutral'
  const status = String(props.coverage.benchmark.requested_status || '')
  if (status === 'full') return 'positive'
  if (status === 'partial') return 'warning'
  if (['none', 'missing'].includes(status)) return 'negative'
  return 'neutral'
})

const sharedRangeDetail = computed(() => {
  if (!props.coverage) return 'No shared range yet.'
  if (props.coverage.universe.requested_fits_collective_range === true) {
    return 'Requested window fits every selected symbol.'
  }
  if (props.coverage.universe.requested_fits_collective_range === false) {
    return 'Requested window exceeds at least one symbol.'
  }
  return 'Shared overlap across selected symbols.'
})

const anyRangeDetail = computed(() => {
  if (!props.coverage) return 'No symbol coverage yet.'
  return `${props.coverage.universe.instruments_with_requested_data} symbols have bars inside the request.`
})

const benchmarkDetail = computed(() => {
  if (!props.coverage) return 'No benchmark configured.'
  if (!props.coverage.benchmark.symbol) return 'No benchmark configured.'
  const status = humanizeStatus(props.coverage.benchmark.requested_status)
  const note = props.coverage.benchmark.preview_note
  return note ? `${status} · ${note}` : status
})

const coverageNotes = computed(() => {
  if (!props.coverage) return []
  const notes: Array<{ tone: CoverageTone; text: string }> = []
  const universe = props.coverage.universe
  const benchmark = props.coverage.benchmark

  if (universe.preview_note) {
    notes.push({
      tone: universe.preview_mode === 'signal_derived' ? 'neutral' : 'warning',
      text: universe.preview_note,
    })
  }
  if (universe.requested_fits_collective_range === false) {
    notes.push({
      tone: 'warning',
      text: 'The selected run window exceeds the shared local history available across the chosen universe.',
    })
  }
  if (benchmark.preview_note) {
    notes.push({
      tone: benchmark.requested_status === 'partial' ? 'warning' : benchmark.requested_status === 'full' ? 'neutral' : 'negative',
      text: benchmark.preview_note,
    })
  }
  for (const warning of props.coverage.warnings ?? []) {
    notes.push({ tone: 'warning', text: String(warning) })
  }
  return dedupeNotes(notes)
})

function dedupeNotes(notes: Array<{ tone: CoverageTone; text: string }>) {
  const seen = new Set<string>()
  return notes.filter(note => {
    if (!note.text) return false
    const key = `${note.tone}:${note.text}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function formatRange(start: string | null | undefined, end: string | null | undefined) {
  if (!start && !end) return 'No local data'
  if (start && end) return `${formatShortDate(start)} → ${formatShortDate(end)}`
  return start ? `${formatShortDate(start)} → …` : `… → ${formatShortDate(end)}`
}

function formatShortDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const day = String(date.getUTCDate()).padStart(2, '0')
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const year = String(date.getUTCFullYear())
  return `${day}/${month}/${year}`
}

function humanizeStatus(value: string | null | undefined) {
  return String(value ?? 'unknown')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function statusClass(status: string | null | undefined) {
  if (status === 'full') return 'coverage-status-pill--positive'
  if (status === 'partial') return 'coverage-status-pill--warning'
  if (status === 'none') return 'coverage-status-pill--negative'
  if (status === 'missing') return 'coverage-status-pill--negative'
  return 'coverage-status-pill--neutral'
}

function summaryStateClass(tone: CoverageTone) {
  return `coverage-summary-card--${tone}`
}
</script>

<style scoped>
.coverage-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 12px;
  line-height: 1.35;
}

.coverage-panel__empty {
  padding: 10px 12px;
  border: 1px dashed #2a2f38;
  border-radius: 8px;
  color: #858b95;
  background: rgba(9, 13, 20, 0.5);
  font-size: 12px;
}

.coverage-panel__empty--error {
  color: #f3a1a8;
  border-color: rgba(239, 127, 136, 0.35);
}

.coverage-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.coverage-summary-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid #1d232d;
  background: #0c1016;
}

.coverage-summary-card--positive {
  border-color: rgba(91, 201, 126, 0.35);
}

.coverage-summary-card--warning {
  border-color: rgba(224, 179, 91, 0.35);
}

.coverage-summary-card--negative {
  border-color: rgba(239, 127, 136, 0.35);
}

.coverage-summary-card__label {
  font-size: 10px;
  letter-spacing: 0.11em;
  text-transform: uppercase;
  color: #7a808d;
}

.coverage-summary-card strong {
  color: #f1f4fa;
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.coverage-summary-card small {
  color: #8b919c;
  font-size: 11px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.coverage-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.coverage-chip {
  padding: 4px 7px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  border: 1px solid #29303b;
  color: #c7ced8;
  background: #0d1117;
}

.coverage-chip--positive {
  border-color: rgba(91, 201, 126, 0.4);
  color: #9be8a8;
}

.coverage-chip--warning {
  border-color: rgba(224, 179, 91, 0.4);
  color: #f0d78b;
}

.coverage-chip--negative {
  border-color: rgba(239, 127, 136, 0.4);
  color: #f3a1a8;
}

.coverage-note-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.coverage-note {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #243042;
  background: #0a111c;
  color: #b4bdcb;
  font-size: 12px;
  line-height: 1.35;
}

.coverage-note--warning {
  border-color: rgba(224, 179, 91, 0.28);
  color: #e2c97b;
}

.coverage-note--negative {
  border-color: rgba(239, 127, 136, 0.28);
  color: #f0a2aa;
}

.coverage-list-section {
  display: grid;
  gap: 8px;
}

.coverage-list-toggle {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 7px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #d6dce6;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.coverage-list-toggle:hover,
.coverage-list-toggle:focus-visible {
  color: #f3f6fb;
  outline: none;
}

.coverage-list-toggle__icon {
  display: inline-block;
  color: #8b95a4;
  transform: rotate(0deg);
  transition: transform 0.16s ease, color 0.16s ease;
}

.coverage-list-toggle__icon--expanded {
  transform: rotate(90deg);
  color: #8fcaf2;
}

.coverage-list-toggle small {
  color: #7f8794;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.coverage-table-wrap {
  max-height: 280px;
  overflow: auto;
  border: 1px solid #1b222d;
  border-radius: 8px;
}

.coverage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.coverage-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 10px;
  background: #090f17;
  color: #7d8591;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.11em;
  text-align: left;
}

.coverage-table tbody td {
  padding: 8px 10px;
  border-top: 1px solid #181d25;
  vertical-align: top;
  color: #c8ced7;
  line-height: 1.35;
}

.coverage-status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 6px;
  border-radius: 999px;
  border: 1px solid #29303b;
  font-size: 10px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  background: #0d1117;
}

.coverage-status-pill--positive {
  border-color: rgba(91, 201, 126, 0.4);
  color: #9be8a8;
}

.coverage-status-pill--warning {
  border-color: rgba(224, 179, 91, 0.4);
  color: #f0d78b;
}

.coverage-status-pill--negative {
  border-color: rgba(239, 127, 136, 0.4);
  color: #f3a1a8;
}

.coverage-status-pill--neutral {
  color: #c7ced8;
}

@media (max-width: 1120px) {
  .coverage-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .coverage-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
