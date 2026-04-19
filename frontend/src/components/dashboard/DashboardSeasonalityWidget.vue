<template>
  <div class="seasonality-widget">
    <div class="seasonality-toolbar">
      <button
        v-for="metric in metrics"
        :key="metric.value"
        class="metric-btn"
        :class="{ active: selectedMetric === metric.value }"
        @click="selectedMetric = metric.value"
      >
        {{ metric.label }}
      </button>
    </div>

    <div v-if="!symbol" class="widget-state">Choose an instrument</div>
    <div v-else-if="loading" class="widget-state">Loading seasonality...</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!months.length" class="widget-state">No monthly history available</div>

    <div v-else class="seasonality-body">
      <div class="month-grid">
        <button
          v-for="month in months"
          :key="month.month"
          class="month-cell"
          :class="{ selected: selectedMonth?.month === month.month }"
          :style="{ background: colorFor(metricValue(month)) }"
          @click="selectedMonth = month"
        >
          <span class="month-name">{{ month.label }}</span>
          <b>{{ formatMetric(metricValue(month)) }}</b>
          <small>{{ month.sample_count }} yrs · {{ formatPct(month.win_rate) }} win</small>
        </button>
      </div>

      <div v-if="selectedMonth" class="month-detail">
        <div class="detail-head">
          <strong>{{ selectedMonth.label }} Detail</strong>
          <span>{{ selectedMonth.sample_count }} samples</span>
        </div>
        <div class="stat-strip">
          <span>Avg <b>{{ formatPct(selectedMonth.avg_performance) }}</b></span>
          <span>Median <b>{{ formatPct(selectedMonth.median_performance) }}</b></span>
          <span>Best <b>{{ formatPct(selectedMonth.best) }}</b></span>
          <span>Worst <b>{{ formatPct(selectedMonth.worst) }}</b></span>
        </div>
        <div class="record-table">
          <div class="record-row head">
            <span>Year</span>
            <span>Perf</span>
            <span>Range</span>
            <span>Vol</span>
          </div>
          <div v-for="record in selectedMonth.records" :key="record.year" class="record-row">
            <span>{{ record.year }}</span>
            <b :class="record.performance >= 0 ? 'pos' : 'neg'">{{ formatPct(record.performance) }}</b>
            <span>{{ formatPct(record.high_low_range) }}</span>
            <span>{{ formatCompact(record.volume) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

type Metric = 'performance' | 'range' | 'volatility' | 'volume'

interface SeasonalityRecord {
  year: number
  month: number
  open: number
  high: number
  low: number
  close: number
  volume?: number | null
  performance: number
  high_low_range: number
  volatility: number
  volume_change?: number | null
}

interface SeasonalityMonth {
  month: number
  label: string
  sample_count: number
  avg_performance?: number | null
  median_performance?: number | null
  win_rate?: number | null
  best?: number | null
  worst?: number | null
  avg_high_low_range?: number | null
  avg_volatility?: number | null
  avg_volume_change?: number | null
  records: SeasonalityRecord[]
}

interface SeasonalityResponse {
  symbol: string
  months: SeasonalityMonth[]
}

const props = defineProps<{ config: Record<string, any>; overrideSymbol?: string }>()

const metrics: Array<{ value: Metric; label: string }> = [
  { value: 'performance', label: 'Perf' },
  { value: 'range', label: 'Range' },
  { value: 'volatility', label: 'Vol' },
  { value: 'volume', label: 'Volume' },
]

const symbol = computed(() =>
  (props.overrideSymbol?.trim() || String(props.config.symbol ?? 'SPY').trim()).toUpperCase()
)
const selectedMetric = ref<Metric>('performance')
const months = ref<SeasonalityMonth[]>([])
const selectedMonth = ref<SeasonalityMonth | null>(null)
const loading = ref(false)
const error = ref('')
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  if (!symbol.value) {
    months.value = []
    selectedMonth.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await api.get<SeasonalityResponse>(
      `/instruments/${encodeURIComponent(symbol.value)}/seasonality/monthly`,
    )
    if (seq !== loadSeq) return
    months.value = data.months
    selectedMonth.value = data.months[new Date().getMonth()] ?? data.months[0] ?? null
  } catch (e: any) {
    if (seq === loadSeq) {
      error.value = e?.message ?? 'Seasonality unavailable'
      months.value = []
      selectedMonth.value = null
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function metricValue(month: SeasonalityMonth): number | null | undefined {
  if (selectedMetric.value === 'range') return month.avg_high_low_range
  if (selectedMetric.value === 'volatility') return month.avg_volatility
  if (selectedMetric.value === 'volume') return month.avg_volume_change
  return month.avg_performance
}

function colorFor(value: number | null | undefined) {
  if (value == null) return '#242424'
  if (selectedMetric.value === 'range' || selectedMetric.value === 'volatility') {
    const intensity = Math.max(0.18, Math.min(0.82, value / 0.22))
    return `rgba(100,181,246,${intensity.toFixed(2)})`
  }
  const cap = selectedMetric.value === 'volume' ? 0.8 : 0.12
  const intensity = Math.max(0.18, Math.min(0.82, Math.abs(value) / cap))
  return value >= 0
    ? `rgba(38,166,154,${intensity.toFixed(2)})`
    : `rgba(239,83,80,${intensity.toFixed(2)})`
}

function formatMetric(value: number | null | undefined) {
  if (selectedMetric.value === 'volume') return formatPct(value)
  return formatPct(value)
}

function formatPct(value: number | null | undefined) {
  if (value == null) return '-'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

function formatCompact(value: number | null | undefined) {
  if (value == null) return '-'
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)}K`
  return value.toFixed(0)
}

watch(symbol, load)
onMounted(load)
</script>

<style scoped>
.seasonality-widget {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.seasonality-toolbar {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  overflow-x: auto;
}
.metric-btn {
  background: #151515;
  color: #777;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 3px 7px;
  font-family: inherit;
  font-size: 10px;
  cursor: pointer;
}
.metric-btn.active {
  color: #64b5f6;
  border-color: #245177;
  background: #0e1a24;
}
.seasonality-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(118px, 0.9fr) minmax(120px, 1fr);
  gap: 8px;
}
.month-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
}
.month-cell {
  min-width: 0;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  color: #f0f0f0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: 5px;
  font-family: inherit;
  cursor: pointer;
  overflow: hidden;
}
.month-cell.selected {
  border-color: rgba(255,255,255,0.55);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
}
.month-name {
  font-size: 10px;
  font-weight: 700;
}
.month-cell b {
  font-size: 13px;
}
.month-cell small {
  font-size: 8px;
  color: rgba(255,255,255,0.76);
  white-space: nowrap;
}
.month-detail {
  min-height: 0;
  border-top: 1px solid #1c1c1c;
  padding-top: 7px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-head,
.stat-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-head strong { color: #ddd; font-size: 11px; }
.detail-head span,
.stat-strip span { color: #777; font-size: 9px; }
.stat-strip b { color: #ddd; font-weight: 600; }
.record-table {
  min-height: 0;
  overflow: auto;
}
.record-row {
  display: grid;
  grid-template-columns: 42px 1fr 1fr 1fr;
  gap: 7px;
  align-items: center;
  min-height: 23px;
  border-bottom: 1px solid #181818;
  font-size: 10px;
  color: #aaa;
}
.record-row.head {
  color: #666;
  font-size: 9px;
  position: sticky;
  top: 0;
  background: #0d0d0d;
}
.record-row b { text-align: right; }
.record-row span:not(:first-child) { text-align: right; }
.pos { color: #26a69a; }
.neg { color: #ef5350; }
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
</style>
