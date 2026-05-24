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

      <div v-if="coverageRows.length" class="coverage-list-section">
        <button
          type="button"
          class="coverage-list-toggle"
          :aria-expanded="instrumentListExpanded ? 'true' : 'false'"
          @click="instrumentListExpanded = !instrumentListExpanded"
        >
          <span class="coverage-list-toggle__icon" :class="{ 'coverage-list-toggle__icon--expanded': instrumentListExpanded }">▸</span>
          <span>Coverage issues</span>
          <small>{{ issueCoverageRows.length }} issues</small>
        </button>

        <div v-if="instrumentListExpanded" class="coverage-timeline-panel">
          <div class="coverage-timeline-axis">
            <span>{{ formatShortDate(coverageDomain.start) }}</span>
            <span>Requested strategy range</span>
            <span>{{ formatShortDate(coverageDomain.end) }}</span>
          </div>

          <div class="coverage-timeline-wrap">
            <div
              v-for="row in issueCoverageRows"
              :key="row.key"
              class="coverage-timeline-row"
              :class="{ 'coverage-timeline-row--benchmark': row.kind === 'benchmark' }"
            >
              <div class="coverage-timeline-row__label">
                <strong>{{ row.symbol }}</strong>
                <span>{{ row.kind === 'benchmark' ? 'Benchmark' : `${row.requestedBars} bars in range` }}</span>
              </div>
              <div class="coverage-timeline-row__track">
                <span
                  v-if="requestedSpanStyle"
                  class="coverage-timeline-row__requested"
                  :style="requestedSpanStyle"
                />
                <span
                  v-for="segment in rowSegments(row)"
                  :key="`${row.key}-${segment.start}-${segment.end}`"
                  class="coverage-timeline-row__segment"
                  :class="`coverage-timeline-row__segment--${statusTone(row.status)}`"
                  :style="segment.style"
                />
                <span v-if="!rowSegments(row).length" class="coverage-timeline-row__empty">No local coverage</span>
              </div>
              <div class="coverage-timeline-row__meta">
                <span class="coverage-status-pill" :class="statusClass(row.status)">
                  {{ humanizeStatus(row.status) }}
                </span>
                <span>{{ rowRequestedCoverageLabel(row) }}</span>
              </div>
              <p v-if="row.note" class="coverage-timeline-row__note">{{ row.note }}</p>
            </div>
            <div v-if="!issueCoverageRows.length" class="coverage-timeline-empty">
              Requested range is fully covered by every selected instrument and benchmark.
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import type { StrategyCoverageInstrument, StrategyCoveragePreview } from '@/types'

type CoverageTone = 'positive' | 'warning' | 'negative' | 'neutral'
type CoverageRow = {
  key: string
  kind: 'instrument' | 'benchmark'
  symbol: string
  status: string
  availableFrom?: string | null
  availableTo?: string | null
  requestedFirst?: string | null
  requestedLast?: string | null
  totalBars: number
  requestedBars: number
  note?: string | null
}

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

const coverageRows = computed<CoverageRow[]>(() => {
  if (!props.coverage) return []
  const rows: CoverageRow[] = []
  const benchmark = props.coverage.benchmark
  if (benchmark.symbol) {
    rows.push({
      key: `benchmark-${benchmark.symbol}`,
      kind: 'benchmark',
      symbol: benchmark.symbol,
      status: benchmark.requested_status,
      availableFrom: benchmark.available_from,
      availableTo: benchmark.available_to,
      requestedFirst: benchmark.requested_first_bar_at,
      requestedLast: benchmark.requested_last_bar_at,
      requestedBars: benchmark.requested_bars,
      totalBars: benchmark.total_bars,
      note: benchmark.preview_note,
    })
  }
  for (const instrument of sortedInstruments.value) {
    rows.push({
      key: `instrument-${instrument.instrument_id}`,
      kind: 'instrument',
      symbol: instrument.symbol,
      status: instrument.requested_status,
      availableFrom: instrument.available_from,
      availableTo: instrument.available_to,
      requestedFirst: instrument.requested_first_bar_at,
      requestedLast: instrument.requested_last_bar_at,
      requestedBars: instrument.requested_bars,
      totalBars: instrument.total_bars,
      note: instrument.note || (instrument.requested_status === 'full' ? 'Requested range is fully covered.' : null),
    })
  }
  return rows
})

const issueCoverageRows = computed(() =>
  coverageRows.value.filter(row => ['partial', 'none', 'missing'].includes(String(row.status))),
)

const coverageDomain = computed(() => {
  const values = [
    toTimestamp(props.coverage?.requested_date_from),
    toTimestamp(props.coverage?.requested_date_to),
  ].filter((value): value is number => Number.isFinite(value))
  if (!values.length) return { start: null, end: null, startMs: null, endMs: null }
  const startMs = Math.min(...values)
  const endMs = Math.max(...values)
  return {
    start: new Date(startMs).toISOString(),
    end: new Date(endMs).toISOString(),
    startMs,
    endMs,
  }
})

const requestedSpanStyle = computed(() =>
  spanStyle(props.coverage?.requested_date_from, props.coverage?.requested_date_to),
)

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

function rowSegments(row: CoverageRow) {
  const style = spanStyle(row.requestedFirst, row.requestedLast)
  return style ? [{ start: row.requestedFirst, end: row.requestedLast, style }] : []
}

function toTimestamp(value: string | null | undefined) {
  if (!value) return Number.NaN
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : Number.NaN
}

function spanStyle(start: string | null | undefined, end: string | null | undefined) {
  const domain = coverageDomain.value
  if (domain.startMs == null || domain.endMs == null || domain.startMs === domain.endMs) return null
  const startMs = toTimestamp(start)
  const endMs = toTimestamp(end)
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null
  const domainWidth = domain.endMs - domain.startMs
  const left = Math.max(0, Math.min(100, ((startMs - domain.startMs) / domainWidth) * 100))
  const right = Math.max(0, Math.min(100, ((endMs - domain.startMs) / domainWidth) * 100))
  return {
    left: `${Math.min(left, right)}%`,
    width: `${Math.max(1.5, Math.abs(right - left))}%`,
  }
}

function formatRange(start: string | null | undefined, end: string | null | undefined) {
  if (!start && !end) return 'No local data'
  if (start && end) return `${formatShortDate(start)} → ${formatShortDate(end)}`
  return start ? `${formatShortDate(start)} → …` : `… → ${formatShortDate(end)}`
}

function rowRequestedCoverageLabel(row: CoverageRow) {
  if (!row.requestedFirst && !row.requestedLast) return 'No bars inside requested range'
  return formatRange(row.requestedFirst, row.requestedLast)
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

function statusTone(status: string | null | undefined) {
  if (status === 'full') return 'positive'
  if (status === 'partial') return 'warning'
  if (['none', 'missing'].includes(String(status))) return 'negative'
  return 'neutral'
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

.coverage-timeline-panel {
  display: grid;
  gap: 8px;
}

.coverage-timeline-axis {
  display: grid;
  grid-template-columns: minmax(72px, max-content) 1fr minmax(72px, max-content);
  gap: 10px;
  align-items: center;
  color: #7e8795;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.coverage-timeline-axis span:nth-child(2) {
  text-align: center;
  color: #6f7785;
}

.coverage-timeline-axis span:last-child {
  text-align: right;
}

.coverage-timeline-wrap {
  display: grid;
  max-height: 340px;
  overflow: auto;
  border: 1px solid #1b222d;
  border-radius: 10px;
  background: rgba(6, 9, 14, 0.74);
}

.coverage-timeline-row {
  display: grid;
  grid-template-columns: minmax(96px, 0.9fr) minmax(180px, 3fr) minmax(128px, 1.1fr);
  gap: 10px;
  align-items: center;
  min-height: 50px;
  padding: 9px 10px;
  border-top: 1px solid #171d26;
}

.coverage-timeline-row:first-child {
  border-top: 0;
}

.coverage-timeline-row--benchmark {
  background: rgba(224, 179, 91, 0.05);
}

.coverage-timeline-row__label,
.coverage-timeline-row__meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.coverage-timeline-row__label strong {
  overflow: hidden;
  color: #eef3fb;
  font-size: 12px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coverage-timeline-row__label span,
.coverage-timeline-row__meta span:last-child,
.coverage-timeline-row__note {
  color: #8a929f;
  font-size: 10px;
  line-height: 1.25;
}

.coverage-timeline-row__track {
  position: relative;
  min-height: 18px;
  border-radius: 999px;
  background:
    linear-gradient(90deg, rgba(24, 30, 40, 0.92), rgba(18, 23, 31, 0.92)),
    #0a0f16;
  box-shadow: inset 0 0 0 1px #1c2531;
}

.coverage-timeline-row__requested,
.coverage-timeline-row__segment {
  position: absolute;
  top: 50%;
  height: 8px;
  border-radius: 999px;
  transform: translateY(-50%);
}

.coverage-timeline-row__requested {
  background: rgba(143, 202, 242, 0.08);
  box-shadow: inset 0 0 0 1px rgba(143, 202, 242, 0.16);
}

.coverage-timeline-row__segment {
  min-width: 6px;
  box-shadow: 0 0 0 1px rgba(5, 8, 12, 0.72), 0 0 14px rgba(91, 169, 230, 0.12);
}

.coverage-timeline-row__segment--positive {
  background: linear-gradient(90deg, #4eac70, #84e89f);
}

.coverage-timeline-row__segment--warning {
  background: linear-gradient(90deg, #a9792b, #f0ca6d);
}

.coverage-timeline-row__segment--negative {
  background: linear-gradient(90deg, #75343c, #ef7f88);
}

.coverage-timeline-row__segment--neutral {
  background: linear-gradient(90deg, #3d6788, #6fb9ed);
}

.coverage-timeline-row__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #6c7481;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.coverage-timeline-row__meta {
  align-items: flex-start;
}

.coverage-timeline-row__note {
  grid-column: 2 / -1;
  margin: -4px 0 0;
  overflow-wrap: anywhere;
}

.coverage-timeline-empty {
  padding: 12px;
  color: #7f8794;
  font-size: 12px;
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

  .coverage-timeline-axis {
    grid-template-columns: 1fr 1fr;
  }

  .coverage-timeline-axis span:nth-child(2) {
    display: none;
  }

  .coverage-timeline-row {
    grid-template-columns: 1fr;
    gap: 7px;
  }

  .coverage-timeline-row__track {
    min-height: 20px;
  }

  .coverage-timeline-row__meta {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
  }

  .coverage-timeline-row__note {
    grid-column: auto;
    margin-top: 0;
  }
}
</style>
