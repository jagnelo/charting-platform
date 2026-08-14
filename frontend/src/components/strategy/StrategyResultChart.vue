<template>
  <div
    ref="rootRef"
    class="result-chart"
    :class="{ 'result-chart--hovering': !!tooltip }"
    @mouseleave="clearHover"
  >
    <div v-if="!hasValidData" class="result-chart__empty">
      {{ emptyLabel }}
    </div>
    <template v-else>
      <div v-if="showRangeControls" class="result-chart__controls">
        <span class="result-chart__range-summary">{{ visibleRangeLabel }}</span>
        <div class="result-chart__range-actions">
          <button
            type="button"
            class="result-chart__range-shift"
            :disabled="!canShiftBackward"
            aria-label="Show earlier chart period"
            @click="shiftWindow(-1)"
          >
            ‹
          </button>
          <button
            v-for="option in availableRangeOptions"
            :key="option.key"
            type="button"
            class="result-chart__range-button"
            :class="{ 'result-chart__range-button--active': selectedRangeKey === option.key }"
            @click="selectRange(option.key)"
          >
            {{ option.label }}
          </button>
          <button
            type="button"
            class="result-chart__range-shift"
            :disabled="!canShiftForward"
            aria-label="Show later chart period"
            @click="shiftWindow(1)"
          >
            ›
          </button>
        </div>
      </div>

      <div
        ref="chartHostRef"
        class="result-chart__uplot"
        :style="{ height: `${Math.max(164, height)}px` }"
        role="img"
        :aria-label="label"
      />

      <div
        v-if="tooltip"
        class="result-chart__hovercard result-chart__hovercard--overlay"
        :class="{ 'result-chart__hovercard--dense': tooltip.dense }"
        :style="hovercardStyle"
      >
        <div class="result-chart__hovercard-date">{{ tooltip.date }}</div>
        <div
          class="result-chart__hovercard-items"
          :class="{ 'result-chart__hovercard-items--dense': tooltip.dense }"
        >
          <div v-for="item in tooltip.items" :key="item.label" class="result-chart__tooltip-item">
            <b :style="{ color: item.color }">
              {{ item.label }} {{ item.value }}
            </b>
            <small v-if="item.detail">{{ item.detail }}</small>
          </div>
        </div>
      </div>

      <div v-if="showLegend" class="result-chart__legend">
        <span v-for="item in series" :key="item.label" class="result-chart__legend-item">
          <i :style="{ backgroundColor: item.color }" />
          {{ item.label }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface StrategyResultChartPoint {
  ts: string
  value: number
  detail?: string | null
  marker?: string | null
}

export interface StrategyResultChartSeries {
  label: string
  color: string
  points: StrategyResultChartPoint[]
}

const props = withDefaults(defineProps<{
  series: StrategyResultChartSeries[]
  label: string
  emptyLabel?: string
  percent?: boolean
  currency?: boolean
  integerAxis?: boolean
  showLegend?: boolean
  height?: number
  focusNearestSeries?: boolean
}>(), {
  emptyLabel: 'No chart data available.',
  percent: false,
  currency: false,
  integerAxis: false,
  showLegend: true,
  height: 132,
  focusNearestSeries: false,
})

type RangeKey = 'all' | '1m' | '3m' | '6m' | '1y'
interface RangeOption {
  key: RangeKey
  label: string
  durationMs: number | null
}

const RANGE_OPTIONS: RangeOption[] = [
  { key: 'all', label: 'All', durationMs: null },
  { key: '1m', label: '1M', durationMs: 31 * 24 * 60 * 60 * 1000 },
  { key: '3m', label: '3M', durationMs: 92 * 24 * 60 * 60 * 1000 },
  { key: '6m', label: '6M', durationMs: 183 * 24 * 60 * 60 * 1000 },
  { key: '1y', label: '1Y', durationMs: 366 * 24 * 60 * 60 * 1000 },
]

const rootRef = ref<HTMLElement | null>(null)
const chartHostRef = ref<HTMLDivElement | null>(null)
const chart = ref<uPlot | null>(null)
const selectedRangeKey = ref<RangeKey>('all')
const windowEndTs = ref<number | null>(null)
const tooltipX = ref<number | null>(null)
const tooltip = ref<{
  date: string
  dense: boolean
  items: Array<{ label: string; value: string; color: string; detail?: string | null }>
} | null>(null)
let resizeObserver: ResizeObserver | null = null

const height = computed(() => Math.max(164, props.height))
const timeline = computed(() => {
  const entries = new Map<string, number>()
  for (const item of props.series.flatMap(series => series.points)) {
    const timestamp = new Date(item.ts).getTime()
    if (Number.isFinite(timestamp)) entries.set(item.ts, timestamp)
  }
  return [...entries.entries()]
    .sort((left, right) => left[1] - right[1])
    .map(([ts, value]) => ({ ts, value }))
})
const timeExtent = computed(() => {
  if (!timeline.value.length) return { min: 0, max: 1 }
  const min = timeline.value[0].value
  const max = timeline.value[timeline.value.length - 1].value
  return { min, max: max === min ? min + 1 : max }
})
const hasValidData = computed(() => (
  props.series.length > 0
  && timeline.value.length > 0
  && props.series.some(series => series.points.some(point => (
    typeof point.value === 'number' && Number.isFinite(point.value)
  )))
))
const availableRangeOptions = computed(() => RANGE_OPTIONS)
const activeRangeOption = computed(() => (
  availableRangeOptions.value.find(option => option.key === selectedRangeKey.value)
  ?? RANGE_OPTIONS[0]
))
const showRangeControls = computed(() => timeline.value.length > 1)
const visibleTimeExtent = computed(() => {
  if (activeRangeOption.value.durationMs == null) return timeExtent.value
  const duration = activeRangeOption.value.durationMs
  const max = timeExtent.value.max
  const min = timeExtent.value.min
  const minEnd = Math.min(max, min + duration)
  const currentEnd = Math.min(max, Math.max(minEnd, windowEndTs.value ?? max))
  const currentStart = Math.max(min, currentEnd - duration)
  return { min: currentStart, max: currentEnd === currentStart ? currentEnd + 1 : currentEnd }
})
const visibleTimeline = computed(() => {
  const visible = timeline.value.filter(item => (
    item.value >= visibleTimeExtent.value.min && item.value <= visibleTimeExtent.value.max
  ))
  if (visible.length) return visible
  const fallback = [...timeline.value].reverse().find(item => item.value <= visibleTimeExtent.value.max)
  return fallback ? [fallback] : []
})
const visibleRangeLabel = computed(() => {
  const first = visibleTimeline.value[0]?.ts
  const last = visibleTimeline.value[visibleTimeline.value.length - 1]?.ts
  if (!first || !last) return 'Visible range'
  return `${formatRangeDate(first)} → ${formatRangeDate(last)}`
})
const canShiftBackward = computed(() => (
  activeRangeOption.value.durationMs != null && visibleTimeExtent.value.min > timeExtent.value.min
))
const canShiftForward = computed(() => (
  activeRangeOption.value.durationMs != null && visibleTimeExtent.value.max < timeExtent.value.max
))

const pointMaps = computed(() => props.series.map(series => (
  new Map(series.points.map(point => [point.ts, point]))
)))
const chartData = computed<uPlot.AlignedData>(() => {
  const x = timeline.value.map(item => item.value / 1000)
  const values = props.series.map((series, seriesIndex) => {
    const map = pointMaps.value[seriesIndex]
    return timeline.value.map(item => {
      const value = map.get(item.ts)?.value
      return typeof value === 'number' && Number.isFinite(value) ? value : null
    })
  })
  return [x, ...values] as uPlot.AlignedData
})

function formatValue(value: number) {
  if (!Number.isFinite(value)) return '—'
  if (props.integerAxis) return `${Math.round(value)}`
  if (props.percent) return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  if (props.currency) {
    return value.toLocaleString('en-US', {
      style: 'currency', currency: 'USD', maximumFractionDigits: 2, minimumFractionDigits: 0,
    })
  }
  if (Math.abs(value) >= 1000) return value.toFixed(0)
  if (Math.abs(value) >= 10) return value.toFixed(2)
  return value.toFixed(4)
}

function formatRangeDate(value: string) {
  return new Date(value).toLocaleDateString('en-GB', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function formatAxisDate(seconds: number) {
  if (!Number.isFinite(seconds)) return ''
  return new Date(seconds * 1000).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function formatTooltipDate(ts?: string) {
  if (!ts) return ''
  return new Date(ts).toLocaleString('en-GB', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function clearHover() {
  tooltip.value = null
  tooltipX.value = null
}

function setVisibleScale() {
  const instance = chart.value
  if (!instance || typeof instance.setScale !== 'function') return
  instance.setScale('x', {
    min: visibleTimeExtent.value.min / 1000,
    max: visibleTimeExtent.value.max / 1000,
  })
}

function selectRange(key: RangeKey) {
  selectedRangeKey.value = key
  windowEndTs.value = timeExtent.value.max
  clearHover()
  nextTick(setVisibleScale)
}

function shiftWindow(direction: -1 | 1) {
  const duration = activeRangeOption.value.durationMs
  if (!duration) return
  const extent = timeExtent.value
  const step = duration * 0.75
  const minEnd = Math.min(extent.max, extent.min + duration)
  const currentEnd = Math.min(extent.max, Math.max(minEnd, windowEndTs.value ?? extent.max))
  windowEndTs.value = Math.min(extent.max, Math.max(minEnd, currentEnd + direction * step))
  clearHover()
  nextTick(setVisibleScale)
}

function updateTooltip(instance: uPlot) {
  const index = instance.cursor.idx
  if (index == null || index < 0 || index >= timeline.value.length) {
    clearHover()
    return
  }
  const timestamp = timeline.value[index]
  if (!timestamp) {
    clearHover()
    return
  }
  const cursorTop = instance.cursor.top ?? 0
  const items = props.series.map((series, seriesIndex) => {
    const value = chartData.value[seriesIndex + 1]?.[index]
    if (value == null || typeof value !== 'number' || !Number.isFinite(value)) return null
    const point = pointMaps.value[seriesIndex].get(timestamp.ts)
    const y = instance.valToPos(value, 'y')
    return {
      label: series.label,
      value: formatValue(value),
      color: series.color,
      detail: point?.detail ?? null,
      y,
    }
  }).filter((item): item is { label: string; value: string; color: string; detail: string | null; y: number } => item != null)

  if (props.focusNearestSeries && items.length > 1) {
    items.sort((left, right) => Math.abs(left.y - cursorTop) - Math.abs(right.y - cursorTop))
  }
  tooltip.value = {
    date: formatTooltipDate(timestamp.ts),
    dense: items.length >= 6,
    items: items.map(({ label, value, color, detail }) => ({ label, value, color, detail })),
  }
  tooltipX.value = instance.cursor.left ?? null
}

function buildChart() {
  const host = chartHostRef.value
  if (!host || !timeline.value.length) return
  if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy()
  host.replaceChildren()
  const width = Math.max(240, rootRef.value?.clientWidth ?? 320)
  chart.value = new uPlot({
    width,
    height: height.value,
    legend: { show: false },
    cursor: { drag: { x: false, y: false } },
    scales: {
      x: { time: true, min: visibleTimeExtent.value.min / 1000, max: visibleTimeExtent.value.max / 1000 },
      y: { auto: true },
    },
    axes: [
      {
        stroke: '#666', font: '10px monospace', size: 24, gap: 3,
        grid: { stroke: '#171717', width: 1 }, ticks: { stroke: '#242424' },
        values: (_instance, values) => values.map(value => formatAxisDate(Number(value))),
      },
      {
        stroke: '#777', font: '10px monospace', size: 60, gap: 5,
        grid: { stroke: '#171717', width: 1 }, ticks: { stroke: '#242424' },
        values: (_instance, values) => values.map(value => formatValue(Number(value))),
      },
    ],
    series: [
      {},
      ...props.series.map(series => ({ label: series.label, stroke: series.color, width: 1.6, points: { show: false } })),
    ],
    hooks: { setCursor: [updateTooltip] },
  }, chartData.value, host)
}

function resizeChart() {
  if (!chart.value || !rootRef.value) return
  chart.value.setSize({ width: Math.max(240, rootRef.value.clientWidth), height: height.value })
}

function destroyChart() {
  if (chart.value && typeof chart.value.destroy === 'function') chart.value.destroy()
  chart.value = null
}

function refreshChart() {
  clearHover()
  if (!hasValidData.value) {
    destroyChart()
    return
  }
  nextTick(buildChart)
}

onMounted(() => {
  refreshChart()
  if (typeof ResizeObserver !== 'undefined' && rootRef.value) {
    resizeObserver = new ResizeObserver(resizeChart)
    resizeObserver.observe(rootRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  destroyChart()
})

watch(() => props.series, refreshChart, { deep: true })
watch([() => props.percent, () => props.currency, () => props.integerAxis, () => props.height], refreshChart)
watch([timeExtent, availableRangeOptions], () => {
  if (!availableRangeOptions.value.some(option => option.key === selectedRangeKey.value)) {
    selectedRangeKey.value = availableRangeOptions.value[0]?.key ?? 'all'
  }
  if (selectedRangeKey.value === 'all' || windowEndTs.value == null) {
    windowEndTs.value = timeExtent.value.max
  } else {
    windowEndTs.value = Math.min(timeExtent.value.max, Math.max(timeExtent.value.min, windowEndTs.value))
  }
  nextTick(setVisibleScale)
}, { immediate: true })

const hovercardStyle = computed(() => {
  if (tooltipX.value == null) return {}
  const width = rootRef.value?.clientWidth ?? 320
  return tooltipX.value > width / 2
    ? { right: '8px', left: 'auto' }
    : { left: '8px', right: 'auto' }
})
</script>

<style scoped>
.result-chart {
  position: relative;
  min-height: 164px;
  overflow: visible;
  color: #b8c3cc;
  font-family: 'JetBrains Mono', monospace;
}

.result-chart__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 24px;
  margin-bottom: 2px;
  font-size: 9px;
}

.result-chart__range-summary {
  overflow: hidden;
  color: #81909c;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-chart__range-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 2px;
}

.result-chart__range-button,
.result-chart__range-shift {
  min-width: 24px;
  padding: 2px 5px;
  border: 1px solid #303b45;
  background: #10161b;
  color: #aab6bf;
  cursor: pointer;
  font: inherit;
}

.result-chart__range-button:hover,
.result-chart__range-shift:hover:not(:disabled),
.result-chart__range-button--active {
  border-color: #4e9ac3;
  background: #1c4053;
  color: #e3f4ff;
}

.result-chart__range-button:disabled,
.result-chart__range-shift:disabled {
  cursor: default;
  opacity: 0.45;
}

.result-chart__uplot {
  position: relative;
  min-height: 164px;
  overflow: hidden;
}

.result-chart__uplot :deep(.uplot) {
  width: 100%;
  height: 100%;
}

.result-chart__uplot :deep(.u-axis) {
  color: #788894;
}

.result-chart__hovercard {
  position: absolute;
  z-index: 3;
  top: 30px;
  min-width: 150px;
  max-width: min(270px, calc(100% - 16px));
  padding: 6px 8px;
  border: 1px solid #385064;
  background: rgba(10, 15, 20, 0.96);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  pointer-events: none;
  font-size: 10px;
}

.result-chart__hovercard-date {
  margin-bottom: 4px;
  color: #90a8b8;
}

.result-chart__hovercard-items {
  display: grid;
  gap: 2px;
}

.result-chart__tooltip-item {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.result-chart__tooltip-item small {
  flex-basis: 100%;
  color: #8495a1;
}

.result-chart__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
  color: #8d9ca7;
  font-size: 9px;
}

.result-chart__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.result-chart__legend-item i {
  display: inline-block;
  width: 8px;
  height: 2px;
}

.result-chart__empty {
  display: grid;
  min-height: 164px;
  place-items: center;
  color: #72818c;
  font-size: 10px;
}
</style>
