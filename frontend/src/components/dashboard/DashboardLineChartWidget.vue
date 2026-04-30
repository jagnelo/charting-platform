<template>
  <div class="line-chart-widget" ref="rootRef">
    <div v-if="loading" class="widget-state">Loading {{ displayTarget }}...</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!loadedSeries.length" class="widget-state">Choose an instrument</div>
    <template v-else>
      <div ref="chartRef" class="uplot-host" />
      <div v-if="tooltip" class="chart-tooltip">
        <span>{{ tooltip.date }}</span>
        <b v-for="item in tooltip.items" :key="item.label" :style="{ color: item.color }">
          {{ item.label }} {{ item.value }}
        </b>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'
import type { OHLCVBar, Timeframe } from '@/types'

const props = defineProps<{
  type: string
  config: Record<string, any>
  overrideSymbol?: string
}>()

interface LoadedSeries {
  key: string
  label: string
  color: string
  bars: OHLCVBar[]
  values: number[]
}

const DEFAULT_COLORS = ['#64b5f6', '#81c784', '#ffb74d', '#ba68c8', '#f06292', '#4dd0e1']

const rootRef = ref<HTMLDivElement | null>(null)
const chartRef = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const loadedSeries = ref<LoadedSeries[]>([])
const tooltip = ref<{ date: string; items: Array<{ label: string; value: string; color: string }> } | null>(null)
let plot: uPlot | null = null
let resizeObserver: ResizeObserver | null = null
let refreshSeq = 0

const timeframe = computed<Timeframe>(() => props.config.timeframe ?? 'D1')
const barLimit = computed(() => {
  const value = Number(props.config.barLimit ?? 300)
  if (!Number.isFinite(value)) return 300
  return Math.max(50, Math.min(5000, Math.round(value)))
})
const normalize = computed(() =>
  props.type === 'comparison_chart' ? props.config.normalize !== false : props.config.normalize === true
)
const targets = computed(() => {
  if (props.type === 'comparison_chart') {
    const configured = Array.isArray(props.config.targets) ? props.config.targets : []
    if (configured.length) {
      return configured
        .map((target: any, index: number) => ({
          symbol: String(target.symbol ?? '').trim(),
          label: String(target.label ?? target.symbol ?? '').trim(),
          color: String(target.color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length]),
        }))
        .filter((target: any) => target.symbol)
        .slice(0, 6)
    }
    return String(props.config.symbols ?? 'SPY,QQQ,DIA')
      .split(',')
      .map((symbol, index) => ({
        symbol: symbol.trim(),
        label: symbol.trim(),
        color: DEFAULT_COLORS[index % DEFAULT_COLORS.length],
      }))
      .filter(target => target.symbol)
      .slice(0, 6)
  }
  const symbol = (props.overrideSymbol?.trim() || String(props.config.symbol ?? props.config.expression ?? '').trim())
  return symbol ? [{ symbol, label: symbol, color: props.config.color ?? DEFAULT_COLORS[0] }] : []
})
const displayTarget = computed(() => targets.value.map(t => t.label || t.symbol).join(', '))

async function ensureTarget(target: string) {
  return ensureKnownInstrumentSymbol(target)
}

async function loadBars(target: string) {
  const symbol = await ensureTarget(target)
  const raw = await api.get<any[]>(`/ohlcv/${encodeURIComponent(symbol)}/${timeframe.value}`, {
    limit: barLimit.value,
  })
  return {
    symbol,
    bars: raw.slice(-barLimit.value).map(b => ({
      ...b,
      open: Number(b.open),
      high: Number(b.high),
      low: Number(b.low),
      close: Number(b.close),
      volume: b.volume != null ? Number(b.volume) : undefined,
      vwap: b.vwap != null ? Number(b.vwap) : undefined,
    })) as OHLCVBar[],
  }
}

async function refresh() {
  const seq = ++refreshSeq
  destroyPlot()
  tooltip.value = null
  if (!targets.value.length) {
    loadedSeries.value = []
    error.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    const loaded = await Promise.all(
      targets.value.map(async (target, index) => {
        const { symbol, bars } = await loadBars(target.symbol)
        const rawValues = bars.map(b => b.close)
        const first = rawValues.find(v => Number.isFinite(v) && v !== 0) ?? 1
        return {
          key: `${symbol}-${index}`,
          label: target.label || symbol,
          color: target.color,
          bars,
          values: normalize.value ? rawValues.map(v => ((v - first) / first) * 100) : rawValues,
        }
      }),
    )
    if (seq !== refreshSeq) return
    loadedSeries.value = loaded.filter(item => item.bars.length)
    loading.value = false
    await nextTick()
    if (seq === refreshSeq) buildPlot()
  } catch (e: any) {
    if (seq === refreshSeq) {
      error.value = e?.message ?? 'Chart unavailable'
      loadedSeries.value = []
      loading.value = false
    }
  }
}

function buildPlot() {
  if (!chartRef.value || !rootRef.value || !loadedSeries.value.length) return
  const width = Math.max(220, rootRef.value.clientWidth)
  const height = Math.max(120, rootRef.value.clientHeight)
  const longest = Math.max(...loadedSeries.value.map(s => s.values.length))
  const x = Array.from({ length: longest }, (_, index) => index)
  const aligned = loadedSeries.value.map(series => {
    const offset = longest - series.values.length
    return x.map((_, index) => index < offset ? null : series.values[index - offset])
  })
  const data = [x, ...aligned] as uPlot.AlignedData
  const opts: uPlot.Options = {
    width,
    height,
    legend: { show: false },
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: false }, y: { auto: true } },
    axes: [
      {
        scale: 'x',
        size: 24,
        gap: 3,
        stroke: '#666',
        font: '10px monospace',
        grid: { stroke: '#171717', width: 1 },
        ticks: { stroke: '#242424' },
        values: (_u, ticks) => ticks.map(t => formatTickDate(Number(t), longest)),
      },
      {
        scale: 'y',
        side: 1,
        size: 54,
        gap: 5,
        stroke: '#777',
        font: '10px monospace',
        grid: { stroke: '#171717', width: 1 },
        ticks: { stroke: '#242424' },
        values: (_u, ticks) => ticks.map(t => formatValue(Number(t))),
      },
    ],
    series: [
      {},
      ...loadedSeries.value.map(series => ({
        label: series.label,
        stroke: series.color,
        width: 1.6,
        points: { show: false },
      })),
    ],
    hooks: {
      setCursor: [(u) => {
        const idx = u.cursor.idx
        if (idx == null) {
          tooltip.value = null
          return
        }
        const firstSeries = loadedSeries.value[0]
        const barIndex = idx - (longest - firstSeries.bars.length)
        const date = firstSeries.bars[barIndex]?.ts
        tooltip.value = {
          date: formatTooltipDate(date),
          items: loadedSeries.value.map((series, index) => {
            const values = u.data[index + 1] as Array<number | null>
            return {
              label: series.label,
              color: series.color,
              value: formatValue(Number(values[idx])),
            }
          }),
        }
      }],
    },
  }
  plot = new uPlot(opts, data, chartRef.value)
}

function destroyPlot() {
  plot?.destroy()
  plot = null
  if (chartRef.value) chartRef.value.innerHTML = ''
}

function resizePlot() {
  if (!rootRef.value) return
  if (!plot) {
    if (loadedSeries.value.length && chartRef.value) buildPlot()
    return
  }
  plot.setSize({
    width: Math.max(220, rootRef.value.clientWidth),
    height: Math.max(120, rootRef.value.clientHeight),
  })
}

function formatTickDate(index: number, longest: number) {
  const firstSeries = loadedSeries.value[0]
  const barIndex = Math.round(index) - (longest - firstSeries.bars.length)
  const ts = firstSeries.bars[barIndex]?.ts
  if (!ts) return ''
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function formatTooltipDate(ts?: string) {
  if (!ts) return ''
  return new Date(ts).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatValue(value: number) {
  if (!Number.isFinite(value)) return '-'
  if (normalize.value) return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  if (Math.abs(value) >= 1000) return value.toFixed(0)
  if (Math.abs(value) >= 10) return value.toFixed(2)
  return value.toFixed(4)
}

watch(() => [props.type, props.overrideSymbol, JSON.stringify(props.config)], refresh)
onMounted(() => {
  resizeObserver = new ResizeObserver(resizePlot)
  if (rootRef.value) resizeObserver.observe(rootRef.value)
  refresh()
})
onUnmounted(() => {
  refreshSeq++
  resizeObserver?.disconnect()
  destroyPlot()
})
</script>

<style scoped>
.line-chart-widget {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.uplot-host {
  width: 100%;
  height: 100%;
}
.line-chart-widget :deep(.uplot) {
  background: #0d0d0d;
}
.line-chart-widget :deep(.u-over) {
  cursor: crosshair;
}
.chart-tooltip {
  position: absolute;
  top: 6px;
  left: 8px;
  right: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  pointer-events: none;
  color: #aaa;
  font-size: 10px;
  line-height: 1.35;
}
.chart-tooltip span { color: #777; }
.chart-tooltip b { font-weight: 700; }
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
