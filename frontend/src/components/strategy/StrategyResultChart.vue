<template>
  <div
    ref="rootRef"
    class="result-chart"
    @mouseleave="hoverIndex = null; hoverX = null; hoverY = null"
  >
    <div v-if="!series.length || !timeline.length" class="result-chart__empty">
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
      <svg
        ref="svgRef"
        class="result-chart__svg"
        :style="{ height: `${Math.max(164, height)}px` }"
        :viewBox="`0 0 ${svgWidth} ${height}`"
        preserveAspectRatio="none"
        role="img"
        :aria-label="label"
        @mousemove="handleMove"
      >
        <g class="result-chart__grid">
          <line
            v-for="tick in yTicks"
            :key="tick.value"
            :x1="chartPadding.left"
            :x2="svgWidth - chartPadding.right"
            :y1="tick.y"
            :y2="tick.y"
          />
        </g>
        <g class="result-chart__axes">
          <text
            v-for="tick in yTicks"
            :key="`label-${tick.value}`"
            :ref="registerAxisLabel"
            :x="chartPadding.left - 8"
            :y="tick.y + 3"
            text-anchor="end"
          >
            {{ formatValue(tick.value) }}
          </text>
        </g>
        <g v-if="hoverX != null" class="result-chart__crosshair">
          <line :x1="hoverX" :x2="hoverX" :y1="chartPadding.top" :y2="height - chartPadding.bottom" />
        </g>
        <g v-for="item in renderedSeries" :key="item.label">
          <polyline
            class="result-chart__line"
            :style="{ '--series-color': item.color }"
            :points="item.points"
          />
          <circle
            v-for="endpoint in item.endpoints"
            :key="`${item.label}-${endpoint.kind}-${endpoint.ts}`"
            class="result-chart__endpoint"
            :class="`result-chart__endpoint--${endpoint.kind}`"
            :style="{ '--series-color': item.color }"
            :cx="endpoint.x"
            :cy="endpoint.y"
            r="2.7"
          />
          <circle
            v-if="hoverIndex != null && item.hoverPoint"
            class="result-chart__point"
            :style="{ '--series-color': item.color }"
            :cx="item.hoverPoint.x"
            :cy="item.hoverPoint.y"
            r="3.2"
          />
        </g>
      </svg>

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
        <span
          v-for="item in series"
          :key="item.label"
          class="result-chart__legend-item"
        >
          <i :style="{ backgroundColor: item.color }" />
          {{ item.label }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

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
  showLegend?: boolean
  height?: number
  focusNearestSeries?: boolean
}>(), {
  emptyLabel: 'No chart data available.',
  percent: false,
  currency: false,
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

const svgWidth = ref(320)
const height = computed(() => props.height)
const basePadding = {
  top: 10,
  right: 2,
  bottom: 18,
}

const rootRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)
const hoverX = ref<number | null>(null)
const hoverY = ref<number | null>(null)
const selectedRangeKey = ref<RangeKey>('all')
const windowEndTs = ref<number | null>(null)
let resizeObserver: ResizeObserver | null = null
let textMeasureContext: CanvasRenderingContext2D | null = null
const axisLabelRefs = ref<SVGTextElement[]>([])
const measuredAxisLabelWidth = ref(0)

const timeline = computed(() => {
  const entries = new Map<string, number>()
  for (const series of props.series) {
    for (const point of series.points) {
      const tsValue = new Date(point.ts).getTime()
      if (Number.isFinite(tsValue)) entries.set(point.ts, tsValue)
    }
  }
  return Array.from(entries.entries())
    .sort((a, b) => a[1] - b[1])
    .map(([ts, value]) => ({ ts, value }))
})

const timeExtent = computed(() => {
  if (!timeline.value.length) return { min: 0, max: 1 }
  const values = timeline.value.map(item => item.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  return { min, max: max === min ? min + 1 : max }
})

const totalSpanMs = computed(() => Math.max(0, timeExtent.value.max - timeExtent.value.min))

const availableRangeOptions = computed(() => RANGE_OPTIONS)

const activeRangeOption = computed(() => (
  availableRangeOptions.value.find(option => option.key === selectedRangeKey.value)
  ?? availableRangeOptions.value[0]
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
  return {
    min: currentStart,
    max: currentEnd === currentStart ? currentEnd + 1 : currentEnd,
  }
})

const visibleTimeline = computed(() => {
  const filtered = timeline.value.filter(item => (
    item.value >= visibleTimeExtent.value.min && item.value <= visibleTimeExtent.value.max
  ))
  if (filtered.length) return filtered
  const fallback = [...timeline.value].reverse().find(item => item.value <= visibleTimeExtent.value.max)
  return fallback ? [fallback] : []
})

const visibleTsSet = computed(() => new Set(visibleTimeline.value.map(item => item.ts)))

const visibleRangeLabel = computed(() => {
  const first = visibleTimeline.value[0]?.ts
  const last = visibleTimeline.value[visibleTimeline.value.length - 1]?.ts
  if (!first || !last) return 'Visible range'
  return `${formatRangeDate(first)} → ${formatRangeDate(last)}`
})

const canShiftBackward = computed(() => {
  if (activeRangeOption.value.durationMs == null) return false
  return visibleTimeExtent.value.min > timeExtent.value.min
})

const canShiftForward = computed(() => {
  if (activeRangeOption.value.durationMs == null) return false
  return visibleTimeExtent.value.max < timeExtent.value.max
})

const valueExtent = computed(() => {
  const values = props.series
    .flatMap(series => series.points
      .filter(point => visibleTsSet.value.has(point.ts))
      .map(point => Number(point.value)))
    .filter(Number.isFinite)
  const fallbackValues = props.series
    .flatMap(series => series.points.map(point => Number(point.value)))
    .filter(Number.isFinite)
  const inputValues = values.length ? values : fallbackValues
  if (!inputValues.length) return { min: 0, max: 1 }
  let min = Math.min(...inputValues)
  let max = Math.max(...inputValues)
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.1
    min -= pad
    max += pad
  } else {
    const pad = (max - min) * 0.12
    min -= pad
    max += pad
  }
  return { min, max }
})

const chartPadding = computed(() => {
  const yLabelValues: number[] = []
  const { min, max } = valueExtent.value
  for (let index = 0; index < 4; index += 1) {
    const ratio = index / 3
    yLabelValues.push(max - (max - min) * ratio)
  }
  const estimatedLabelWidth = Math.max(
    0,
    ...yLabelValues.map(value => measureTextWidth(formatValue(value))),
  )
  const maxLabelWidth = Math.max(estimatedLabelWidth, measuredAxisLabelWidth.value)
  return {
    top: basePadding.top,
    right: basePadding.right,
    bottom: basePadding.bottom,
    left: Math.max(28, Math.ceil(maxLabelWidth + 18)),
  }
})

const yTicks = computed(() => {
  const ticks: Array<{ value: number; y: number }> = []
  const { min, max } = valueExtent.value
  for (let index = 0; index < 4; index += 1) {
    const ratio = index / 3
    const value = max - (max - min) * ratio
    ticks.push({ value, y: lerp(chartPadding.value.top, height.value - chartPadding.value.bottom, ratio) })
  }
  return ticks
})

const renderedSeries = computed(() => {
  const allTimeline = visibleTimeline.value
  const { min, max } = valueExtent.value

  return props.series.map(series => {
    const valueMap = new Map(series.points.map(point => [point.ts, Number(point.value)]))
    const sourcePointMap = new Map(series.points.map(point => [point.ts, point]))
    const chartPoints: Array<{
      x: number
      y: number
      value: number
      ts: string
      detail?: string | null
      marker?: string | null
    }> = []
    const polyline: string[] = []

    allTimeline.forEach(({ ts, value: tsValue }) => {
      const value = valueMap.get(ts)
      if (!Number.isFinite(value)) return
      const sourcePoint = sourcePointMap.get(ts)
      const x = timeToX(tsValue)
      const y = valueToY(value as number, min, max)
      chartPoints.push({
        x,
        y,
        value: value as number,
        ts,
        detail: sourcePoint?.detail ?? null,
        marker: sourcePoint?.marker ?? null,
      })
      polyline.push(`${x.toFixed(2)},${y.toFixed(2)}`)
    })

    const currentHoverIndex = hoverIndex.value
    const hoverPoint = currentHoverIndex == null
      ? null
      : chartPoints.find(point => point.ts === allTimeline[currentHoverIndex]?.ts) ?? null

    const endpoints = chartPoints.length <= 1
      ? chartPoints.map(point => ({
          x: point.x,
          y: point.y,
          ts: point.ts,
          kind: point.marker || 'point',
        }))
      : [
          {
            x: chartPoints[0].x,
            y: chartPoints[0].y,
            ts: chartPoints[0].ts,
            kind: chartPoints[0].marker || 'entry',
          },
          {
            x: chartPoints[chartPoints.length - 1].x,
            y: chartPoints[chartPoints.length - 1].y,
            ts: chartPoints[chartPoints.length - 1].ts,
            kind: chartPoints[chartPoints.length - 1].marker || 'exit',
          },
        ]

    return {
      label: series.label,
      color: series.color,
      points: polyline.join(' '),
      hoverPoint,
      valueMap,
      endpoints,
    }
  })
})

const tooltip = computed(() => {
  if (hoverIndex.value == null) return null
  const ts = visibleTimeline.value[hoverIndex.value]?.ts
  if (!ts) return null
  const items = renderedSeries.value
    .map(series => {
      const value = series.valueMap.get(ts)
      const detail = series.hoverPoint?.ts === ts ? series.hoverPoint.detail ?? null : null
      const y = series.hoverPoint?.ts === ts ? series.hoverPoint.y : null
      return value == null
        ? null
        : { label: series.label, value: formatValue(value), color: series.color, detail, y }
    })
    .filter((item): item is { label: string; value: string; color: string; detail: string | null; y: number | null } => item != null)

  if (props.focusNearestSeries && items.length > 1 && hoverY.value != null) {
    items.sort((left, right) => {
      const leftDistance = left.y == null ? Number.POSITIVE_INFINITY : Math.abs(left.y - hoverY.value!)
      const rightDistance = right.y == null ? Number.POSITIVE_INFINITY : Math.abs(right.y - hoverY.value!)
      return leftDistance - rightDistance
    })
  }

  return {
    date: new Date(ts).toLocaleString('en-GB', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }),
    dense: items.length >= 6,
    items: items.map(({ label, value, color, detail }) => ({ label, value, color, detail })),
  }
})

const hovercardStyle = computed(() => {
  if (hoverX.value == null) return {}
  const withinRightHalf = hoverX.value > svgWidth.value / 2
  return withinRightHalf
    ? {
        right: `${chartPadding.value.right + 8}px`,
        left: 'auto',
      }
    : {
        left: `${chartPadding.value.left + 8}px`,
        right: 'auto',
      }
})

function valueToY(value: number, min: number, max: number) {
  if (max === min) return (chartPadding.value.top + height.value - chartPadding.value.bottom) / 2
  const ratio = (value - min) / (max - min)
  return height.value - chartPadding.value.bottom - ratio * (height.value - chartPadding.value.top - chartPadding.value.bottom)
}

function timeToX(value: number) {
  const { min, max } = visibleTimeExtent.value
  if (max === min || visibleTimeline.value.length === 1) {
    return (chartPadding.value.left + svgWidth.value - chartPadding.value.right) / 2
  }
  const ratio = (value - min) / (max - min)
  return chartPadding.value.left + ratio * (svgWidth.value - chartPadding.value.left - chartPadding.value.right)
}

function lerp(start: number, end: number, ratio: number) {
  return start + (end - start) * ratio
}

function formatValue(value: number) {
  if (!Number.isFinite(value)) return '—'
  if (props.percent) return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  if (props.currency) {
    return value.toLocaleString('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 2,
      minimumFractionDigits: 0,
    })
  }
  if (Math.abs(value) >= 1000) return value.toFixed(0)
  if (Math.abs(value) >= 10) return value.toFixed(2)
  return value.toFixed(4)
}

function formatRangeDate(value: string) {
  return new Date(value).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function clearHover() {
  hoverIndex.value = null
  hoverX.value = null
  hoverY.value = null
}

function selectRange(key: RangeKey) {
  selectedRangeKey.value = key
  windowEndTs.value = timeExtent.value.max
  clearHover()
}

function shiftWindow(direction: -1 | 1) {
  const duration = activeRangeOption.value.durationMs
  if (!duration) return
  const extent = timeExtent.value
  const step = duration * 0.75
  const minEnd = Math.min(extent.max, extent.min + duration)
  const currentEnd = Math.min(extent.max, Math.max(minEnd, windowEndTs.value ?? extent.max))
  const nextEnd = Math.min(extent.max, Math.max(minEnd, currentEnd + (direction * step)))
  windowEndTs.value = nextEnd
  clearHover()
}

function measureTextWidth(value: string) {
  if (typeof document === 'undefined') {
    return value.length * 8
  }
  if (typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent)) {
    return value.length * 8
  }
  if (!textMeasureContext) {
    try {
      const canvas = document.createElement('canvas')
      textMeasureContext = canvas.getContext('2d')
    } catch {
      textMeasureContext = null
    }
  }
  if (!textMeasureContext) {
    return value.length * 8
  }
  textMeasureContext.font = '8px JetBrains Mono, monospace'
  return textMeasureContext.measureText(value).width
}

function registerAxisLabel(element: Element | { $el?: Element | null } | null) {
  const node = element instanceof Element
    ? element
    : element && '$el' in element
      ? element.$el ?? null
      : null
  if (!(node instanceof SVGElement) || node.tagName.toLowerCase() !== 'text') return
  const textNode = node as SVGTextElement
  if (!axisLabelRefs.value.includes(textNode)) {
    axisLabelRefs.value.push(textNode)
  }
}

async function syncAxisLabelWidth() {
  await nextTick()
  const nextWidth = axisLabelRefs.value.reduce((maxWidth, label) => {
    try {
      return Math.max(maxWidth, label.getBBox().width)
    } catch {
      return maxWidth
    }
  }, 0)
  if (Math.abs(nextWidth - measuredAxisLabelWidth.value) > 0.5) {
    measuredAxisLabelWidth.value = nextWidth
  }
  axisLabelRefs.value = []
}

function handleMove(event: MouseEvent) {
  if (!visibleTimeline.value.length) return
  const target = event.currentTarget instanceof SVGSVGElement ? event.currentTarget : svgRef.value
  if (!target) return
  const rect = target.getBoundingClientRect()
  const relativeX = Math.min(
    svgWidth.value - chartPadding.value.right,
    Math.max(chartPadding.value.left, ((event.clientX - rect.left) / Math.max(rect.width, 1)) * svgWidth.value),
  )
  const { min, max } = visibleTimeExtent.value
  const hoverTime = max === min
    ? visibleTimeline.value[0].value
    : min + (
        ((relativeX - chartPadding.value.left) / Math.max(svgWidth.value - chartPadding.value.left - chartPadding.value.right, 1))
        * (max - min)
      )
  let index = 0
  for (let cursor = 0; cursor < visibleTimeline.value.length; cursor += 1) {
    if (visibleTimeline.value[cursor].value <= hoverTime) {
      index = cursor
      continue
    }
    break
  }
  hoverIndex.value = index
  hoverX.value = relativeX
  hoverY.value = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * height.value
}

onMounted(() => {
  const syncWidth = () => {
    const nextWidth = svgRef.value?.clientWidth || rootRef.value?.clientWidth || 320
    svgWidth.value = Math.max(240, Math.round(nextWidth))
  }
  syncWidth()
  void syncAxisLabelWidth()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      syncWidth()
      void syncAxisLabelWidth()
    })
    if (rootRef.value) resizeObserver.observe(rootRef.value)
    if (svgRef.value) resizeObserver.observe(svgRef.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

watch(
  [
    visibleTimeline,
    valueExtent,
    svgWidth,
    () => props.percent,
    () => props.currency,
  ],
  () => {
    void syncAxisLabelWidth()
  },
  { deep: true, immediate: true },
)

watch(
  [timeExtent, availableRangeOptions],
  () => {
    if (!availableRangeOptions.value.some(option => option.key === selectedRangeKey.value)) {
      selectedRangeKey.value = availableRangeOptions.value[0]?.key ?? 'all'
    }
    if (selectedRangeKey.value === 'all' || windowEndTs.value == null) {
      windowEndTs.value = timeExtent.value.max
    } else {
      windowEndTs.value = Math.min(timeExtent.value.max, Math.max(timeExtent.value.min, windowEndTs.value))
    }
    clearHover()
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.result-chart {
  position: relative;
  min-height: 164px;
  overflow: visible;
  z-index: 0;
}

.result-chart__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.result-chart__range-summary {
  color: #707070;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.result-chart__range-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.result-chart__range-button,
.result-chart__range-shift {
  border: 1px solid #242424;
  background: #121212;
  color: #8a8a8a;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1;
  padding: 5px 9px;
  min-height: 26px;
  cursor: pointer;
  transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
}

.result-chart__range-shift {
  min-width: 26px;
  padding-inline: 0;
}

.result-chart__range-button:hover,
.result-chart__range-shift:hover {
  border-color: #32587a;
  color: #d7ebff;
}

.result-chart__range-button--active {
  border-color: #2f5f91;
  background: #102133;
  color: #84c4ff;
}

.result-chart__range-button:disabled,
.result-chart__range-shift:disabled {
  opacity: 0.4;
  cursor: default;
}

.result-chart__svg {
  width: 100%;
  display: block;
  background: #0d0d0d;
  border: 1px solid #1a1a1a;
  border-radius: 18px;
}

.result-chart__grid line,
.result-chart__crosshair line {
  stroke: #1d1d1d;
  stroke-width: 1;
}

.result-chart__crosshair line {
  stroke: #2e3f4f;
  stroke-dasharray: 3 3;
}

.result-chart__axes text {
  fill: #666;
  font-size: 8px;
  font-family: 'JetBrains Mono', monospace;
}

.result-chart__line {
  fill: none;
  stroke: var(--series-color);
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.result-chart__point {
  fill: var(--series-color);
  stroke: #0d0d0d;
  stroke-width: 1.5;
}

.result-chart__endpoint {
  fill: #0d0d0d;
  stroke: var(--series-color);
  stroke-width: 1.3;
  opacity: 0.9;
}

.result-chart__hovercard {
  display: grid;
  gap: 6px;
  padding: 9px 10px;
  border: 1px solid #1c1f24;
  border-radius: 8px;
  background: #0d1116;
  color: #aaa;
  font-size: 10px;
  line-height: 1.35;
  min-height: 48px;
}

.result-chart__hovercard--overlay {
  position: absolute;
  top: 18px;
  width: clamp(260px, 30vw, 380px);
  max-height: min(72vh, 520px);
  overflow: visible;
  pointer-events: none;
  backdrop-filter: blur(4px);
  background: color-mix(in srgb, #0d1116 92%, transparent);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.24);
  z-index: 30;
}

.result-chart__hovercard-date {
  color: #777;
}

.result-chart__hovercard-items {
  display: grid;
  gap: 6px;
}

.result-chart__hovercard--dense {
  width: clamp(320px, 40vw, 540px);
}

.result-chart__hovercard-items--dense {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  align-items: start;
  gap: 10px 12px;
}

.result-chart__tooltip-item {
  display: grid;
  gap: 2px;
}

.result-chart__tooltip b {
  font-weight: 700;
}

.result-chart__tooltip small {
  color: #8d8d8d;
  font-size: 9px;
}

.result-chart__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
}

.result-chart__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #8a8a8a;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.result-chart__legend-item i {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}

.result-chart__empty {
  min-height: 164px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  font-size: 12px;
  text-align: center;
  border: 1px solid #1a1a1a;
  border-radius: 18px;
  background: #0d0d0d;
  padding: 12px;
}
</style>
