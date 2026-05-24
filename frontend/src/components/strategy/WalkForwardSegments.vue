<template>
  <div v-if="segments.length" class="walk-forward-panel">
    <div class="walk-forward-panel__summary">
      <span class="walk-forward-panel__summary-chip">{{ segments.length }} segments</span>
      <span class="walk-forward-panel__summary-chip">{{ trainingShareLabel }}</span>
      <span v-if="avgOutSampleLabel !== '—'" class="walk-forward-panel__summary-chip">
        Avg OOS <b :class="pnlClass(props.avgOutSampleReturnPct)">{{ avgOutSampleLabel }}</b>
      </span>
    </div>

    <div class="walk-forward-panel__rows">
      <button
        v-for="segment in normalizedSegments"
        :key="segment.segment"
        type="button"
        class="walk-forward-panel__row"
        :class="{ 'walk-forward-panel__row--active': activeSegment === segment.segment }"
        @mouseenter="hoveredSegment = segment.segment"
        @mouseleave="hoveredSegment = null"
        @focus="hoveredSegment = segment.segment"
        @blur="hoveredSegment = null"
        @click="togglePinned(segment.segment)"
      >
        <div class="walk-forward-panel__row-head">
          <strong>Segment {{ segment.segment }}</strong>
          <span :class="{ positive: segment.outSample > 0, negative: segment.outSample < 0 }">
            {{ formatPercent(segment.outSample) }}
          </span>
        </div>
        <div class="walk-forward-panel__row-meta">
          <span>IS <b :class="pnlClass(segment.inSample)">{{ formatPercent(segment.inSample) }}</b></span>
          <span>{{ segment.outRange }}</span>
        </div>
        <div class="walk-forward-panel__track">
          <div
            class="walk-forward-panel__bar"
            :class="segment.outSample >= 0 ? 'walk-forward-panel__bar--positive' : 'walk-forward-panel__bar--negative'"
            :style="{ width: `${segment.width}%` }"
          />
        </div>
      </button>
    </div>

    <div v-if="activeRow" class="walk-forward-panel__detail">
      <div class="walk-forward-panel__detail-head">
        <strong>Segment {{ activeRow.segment }}</strong>
        <span>{{ activeRow.outRange }}</span>
      </div>
      <div class="walk-forward-panel__detail-grid">
        <span>In-sample {{ activeRow.inRange }}</span>
        <span>In-sample <b :class="pnlClass(activeRow.inSample)">{{ formatPercent(activeRow.inSample) }}</b></span>
        <span>Out-sample <b :class="pnlClass(activeRow.outSample)">{{ formatPercent(activeRow.outSample) }}</b></span>
      </div>
    </div>
  </div>
  <div v-else class="walk-forward-panel__empty">
    {{ emptyLabel }}
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  segments: Array<{
    segment: number
    in_sample_from?: string | null
    in_sample_to?: string | null
    out_sample_from?: string | null
    out_sample_to?: string | null
    in_sample_return_pct?: number | null
    out_sample_return_pct?: number | null
  }>
  trainingShare?: number | null
  avgOutSampleReturnPct?: number | null
  emptyLabel?: string
}>(), {
  trainingShare: null,
  avgOutSampleReturnPct: null,
  emptyLabel: 'No walk-forward segments yet.',
})

const normalizedSegments = computed(() => {
  const values = props.segments.map(segment => ({
    segment: Number(segment.segment),
    inSample: Number(segment.in_sample_return_pct ?? 0),
    outSample: Number(segment.out_sample_return_pct ?? 0),
    inRange: formatRange(segment.in_sample_from, segment.in_sample_to),
    outRange: formatRange(segment.out_sample_from, segment.out_sample_to),
  }))
  const maxAbs = Math.max(1, ...values.map(row => Math.abs(row.outSample)))
  return values.map(row => ({
    ...row,
    width: Math.max(10, Math.min(100, (Math.abs(row.outSample) / maxAbs) * 100)),
  }))
})

const trainingShareLabel = computed(() =>
  props.trainingShare == null ? 'Training share —' : `Training ${(Number(props.trainingShare) * 100).toFixed(0)}%`,
)
const avgOutSampleLabel = computed(() =>
  props.avgOutSampleReturnPct == null ? '—' : formatPercent(Number(props.avgOutSampleReturnPct)),
)

const hoveredSegment = ref<number | null>(null)
const pinnedSegment = ref<number | null>(null)
const activeSegment = computed(() => pinnedSegment.value ?? hoveredSegment.value)
const activeRow = computed(() =>
  normalizedSegments.value.find(segment => segment.segment === activeSegment.value) ?? null,
)

function togglePinned(segment: number) {
  pinnedSegment.value = pinnedSegment.value === segment ? null : segment
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`
}

function pnlClass(value: unknown) {
  const numeric = Number(value)
  return {
    positive: Number.isFinite(numeric) && numeric > 0,
    negative: Number.isFinite(numeric) && numeric < 0,
  }
}

function formatRange(start?: string | null, end?: string | null) {
  const left = formatShortDate(start)
  const right = formatShortDate(end)
  if (left === '—' && right === '—') return 'No range'
  return `${left} → ${right}`
}

function formatShortDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}
</script>

<style scoped>
.walk-forward-panel {
  display: grid;
  gap: 12px;
}

.walk-forward-panel__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.walk-forward-panel__summary-chip {
  border: 1px solid #1f252c;
  border-radius: 999px;
  padding: 3px 8px;
  color: #97a1b2;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.walk-forward-panel__rows {
  display: grid;
  gap: 8px;
}

.walk-forward-panel__row {
  width: 100%;
  display: grid;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 6px;
  text-align: left;
  cursor: pointer;
}

.walk-forward-panel__row:hover,
.walk-forward-panel__row:focus-visible,
.walk-forward-panel__row--active {
  background: #10141a;
  border-color: #1f252c;
  outline: none;
}

.walk-forward-panel__row-head,
.walk-forward-panel__detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #d7d7d7;
  font-size: 11px;
}

.walk-forward-panel__row-meta,
.walk-forward-panel__detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: #8a92a0;
  font-size: 10px;
}

.walk-forward-panel__track {
  position: relative;
  height: 10px;
  border-radius: 999px;
  background: #111317;
  border: 1px solid #1d2837;
  overflow: hidden;
}

.walk-forward-panel__bar {
  height: 100%;
  border-radius: inherit;
}

.walk-forward-panel__bar--positive {
  background: linear-gradient(90deg, #2d7452, #66c790);
}

.walk-forward-panel__bar--negative {
  background: linear-gradient(90deg, #7a3c46, #ef8d96);
}

.walk-forward-panel__detail {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #1f252c;
  border-radius: 8px;
  background: #0f141b;
}

.walk-forward-panel__empty {
  color: #737373;
  font-size: 12px;
}

.positive {
  color: #90d89e;
}

.negative {
  color: #ef9e9e;
}
</style>
