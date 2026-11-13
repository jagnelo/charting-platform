<template>
  <section class="rotation-tool" role="region" tabindex="0" :aria-label="`Relative rotation vs ${rotationBenchmark}`" :aria-busy="loading && !rows.length">
    <header class="rotation-tool__header">
      <div class="rotation-tool__header-main"><strong>Relative Rotation · {{ rotationBenchmark }}</strong>
        <details class="rotation-tool__settings"><summary>Settings</summary><div class="rotation-tool__settings-panel"><div class="rotation-tool__controls"><label>Universe <select v-model="groupKey" aria-label="Rotation universe"><option value="sp500-sectors">S&amp;P 500 sectors</option><option value="us-benchmarks">US benchmarks</option><option v-for="family in familyKeys" :key="family.key" :value="family.key">{{ family.label }}</option></select></label><label>Benchmark <input v-model.trim="benchmark" aria-label="Rotation benchmark" :disabled="isFamily" /></label><label>Timeframe <select v-model="timeframe" aria-label="Rotation timeframe"><option value="D1">Daily</option><option value="W1">Weekly</option><option value="MN">Monthly</option></select></label><label>Sampling <input v-model.number="sampling" aria-label="Rotation sampling" type="number" min="1" max="30" /></label><label>Lookback <input v-model.number="lookback" aria-label="Rotation lookback" type="number" min="2" max="252" /></label><label>Tail <input v-model.number="tailLength" aria-label="Rotation tail length" type="number" min="1" max="100" /></label><label>History <input v-model.number="historyLength" aria-label="Rotation history length" type="number" min="0" max="5000" /></label><label>As of <input v-model="asOf" aria-label="Rotation as of" type="date" /></label><label class="rotation-tool__adjusted"><input v-model="adjusted" aria-label="Rotation split adjusted" type="checkbox" /> Adjusted</label></div><small>Trend: ratio return over {{ lookback }} sampled observations · Momentum: change in that trend{{ historyLength ? ` · ${historyLength} history points` : '' }}{{ asOf ? ` · As of ${asOf}` : '' }}{{ freshness ? ` · ${formatWorkstationFreshness(freshness)}` : '' }}</small></div></details>
        <details v-if="rows.length" class="rotation-tool__rows-disclosure"><summary>Rows · {{ rows.length }}</summary><div class="rotation-tool__table" role="region" aria-label="Relative rotation rows"><div class="rotation-tool__head" role="group" aria-label="Sort relative rotation rows"><button type="button" :aria-label="sortLabel('symbol')" @click="setSort('symbol')">{{ isFamily ? 'Leg' : 'Sector' }}{{ sortMark('symbol') }}</button><button type="button" :aria-label="sortLabel('state')" @click="setSort('state')">State{{ sortMark('state') }}</button><span class="rotation-tool__warning-heading">Warnings</span><button type="button" :aria-label="sortLabel('trend')" @click="setSort('trend')">Trend{{ sortMark('trend') }}</button><button type="button" :aria-label="sortLabel('momentum')" @click="setSort('momentum')">Momentum{{ sortMark('momentum') }}</button><button type="button" :aria-label="sortLabel('heading')" @click="setSort('heading')">Heading{{ sortMark('heading') }}</button><button type="button" :aria-label="sortLabel('distance')" @click="setSort('distance')">Distance{{ sortMark('distance') }}</button><button type="button" :aria-label="sortLabel('velocity')" @click="setSort('velocity')">Velocity{{ sortMark('velocity') }}</button><button type="button" :aria-label="sortLabel('transition')" @click="setSort('transition')">Transition{{ sortMark('transition') }}</button><button type="button" :aria-label="sortLabel('time_in_state')" @click="setSort('time_in_state')">Time{{ sortMark('time_in_state') }}</button><button type="button" :aria-label="sortLabel('coverage')" @click="setSort('coverage')">Coverage{{ sortMark('coverage') }}</button><button type="button" :aria-label="sortLabel('tail')" @click="setSort('tail')">Tail{{ sortMark('tail') }}</button></div><button v-for="row in sortedRows" :key="row.role ?? row.instrument_id ?? row.symbol" type="button" class="rotation-tool__row" :aria-label="rotationRowLabel(row)" @click="emit('select', row.symbol, row.instrument_id)"><strong>{{ row.symbol }}</strong><span :class="`rotation-tool__state-${row.state}`">{{ row.state ?? 'Unavailable' }}</span><span v-if="row.warnings?.length" class="rotation-tool__warning" :title="row.warnings.map(warning => warning.message).join('\n')"><WorkstationGlyph kind="warning" /> {{ row.warnings.length }}</span><span v-else class="rotation-tool__warning-placeholder" aria-hidden="true" /><span>{{ percent(row.trend) }}</span><span>{{ percent(row.momentum) }}</span><span>{{ row.heading == null ? '—' : `${row.heading.toFixed(0)}°` }}</span><span>{{ percent(row.distance) }}</span><span>{{ percent(row.velocity) }}</span><span>{{ row.transition ?? '—' }}</span><span>{{ row.time_in_state ?? '—' }}</span><span>{{ percent(row.coverage) }}</span><span>{{ row.tail.length }}</span></button></div></details>
      </div>
      <CompactStatusNotice v-if="rotationStatusDetail" class="rotation-tool__status" :kind="error ? 'alert' : 'status'" :summary="rotationStatusSummary" :detail="rotationStatusDetail" />
    </header>
    <p v-if="loading && !rows.length" class="rotation-tool__state">{{ rotationStatusSummary }}</p>
    <p v-else-if="error" class="rotation-tool__state rotation-tool__state--error">{{ rotationStatusSummary }}</p>
    <p v-else-if="!rows.length" class="rotation-tool__state">{{ rotationStatusSummary }}</p>
    <template v-else>
      <div class="rotation-tool__plot-shell" @mousemove="onPlotMove" @mouseleave="hovered = null" @click="selectHovered">
        <div
          ref="plotHost"
          class="rotation-tool__plot"
          role="group"
          tabindex="0"
          aria-label="Relative rotation trend and momentum plane"
          :aria-describedby="plotInstructionsId"
          aria-keyshortcuts="ArrowUp ArrowDown ArrowLeft ArrowRight Home End Enter Space"
          @keydown="handlePlotKeydown"
          @focus="handlePlotFocus"
          @blur="handlePlotBlur"
        />
        <p :id="plotInstructionsId" class="rotation-tool__sr-only">Use the arrow keys to inspect each symbol's latest plotted point. Home and End move to the first and last points. Press Enter or Space to select the symbol in the linked chart.</p>
        <div v-if="hovered" class="rotation-tool__tooltip" :style="tooltipStyle" role="status" aria-live="polite" aria-atomic="true">
          <strong>{{ hovered.symbol }}</strong><span>{{ hovered.point.timestamp }}</span><span>Trend {{ percent(hovered.point.trend) }} · Momentum {{ percent(hovered.point.momentum) }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.rotation-tool__head,
.rotation-tool__row { grid-template-columns: 54px 78px 58px 68px 76px 66px 76px 76px 104px 58px 72px 42px; }
.rotation-tool__head button,
.rotation-tool__row > * { white-space: nowrap; }
.rotation-tool__warning-heading { box-sizing: border-box; min-width: 0; padding: 0 8px 0 3px; color: #9baab5; font-weight: 600; text-align: left; text-transform: uppercase; }
.rotation-tool__warning { color: #e7bc68; }
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { api } from '@/lib/api'
import { dataPreparationCoordinator, PreparationProgressRefreshQueue, preparationMessageSummary, preparationStatusMessage, shouldRefreshAnalysisProgress } from '@/lib/dataPreparation'
import { formatWorkstationFreshness } from '@/lib/workstation/freshness'
import WorkstationGlyph from './WorkstationGlyph.vue'
import CompactStatusNotice from '@/components/common/CompactStatusNotice.vue'

interface Tail { timestamp: string; trend: number; momentum: number }
interface Row { role?: string; label?: string; instrument_id?: number | null; symbol: string; state: string | null; trend: number | null; momentum: number | null; heading?: number | null; distance?: number | null; velocity?: number | null; transition?: string | null; time_in_state?: number | null; coverage: number; tail: Tail[]; history: Tail[]; warnings?: Array<{ code: string; message: string }> }
interface PlotPoint extends Tail { symbol: string; color: string; last: boolean }
type SortKey = 'symbol' | 'state' | 'trend' | 'momentum' | 'heading' | 'distance' | 'velocity' | 'transition' | 'time_in_state' | 'coverage' | 'tail'
const props = defineProps<{ configuration?: Record<string, unknown> }>()
const queryClient = useQueryClient()
const emit = defineEmits<{ select: [symbol: string, instrumentId?: number | null]; configuration: [configuration: Record<string, unknown>] }>()
const rows = ref<Row[]>([]), loading = ref(true), error = ref(''), freshness = ref(''), preparationMessage = ref('')
const configString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const groupKey = ref(configString('group_key', 'sp500-sectors'))
const benchmark = ref(configString('benchmark', 'SPY').toUpperCase())
const rotationBenchmark = ref(benchmark.value)
const familyKeys = [
  { key: 'sp500', label: 'S&P 500 legs' }, { key: 'sp400', label: 'S&P 400 legs' },
  { key: 'sp600', label: 'S&P 600 legs' }, { key: 'sp1500', label: 'S&P 1500 legs' },
  { key: 'russell1000', label: 'Russell 1000 legs' }, { key: 'russell2000', label: 'Russell 2000 legs' },
  { key: 'russell3000', label: 'Russell 3000 legs' }, { key: 'nasdaq100', label: 'Nasdaq 100 legs' },
]
const isFamily = computed(() => familyKeys.some(family => family.key === groupKey.value))
const timeframe = ref(['D1', 'W1', 'MN'].includes(configString('timeframe', 'D1')) ? configString('timeframe', 'D1') : 'D1')
const lookback = ref(Math.min(252, Math.max(2, Number(props.configuration?.lookback ?? 20) || 20)))
const tailLength = ref(Math.min(100, Math.max(1, Number(props.configuration?.tail_length ?? 10) || 10)))
const historyLength = ref(Math.min(5000, Math.max(0, Number(props.configuration?.history_length ?? 0) || 0)))
const sampling = ref(Math.min(30, Math.max(1, Number(props.configuration?.sampling ?? 1) || 1)))
const asOf = ref(configString('as_of', ''))
const adjusted = ref(props.configuration?.adjusted !== false)
const rotationStatusDetail = computed(() => error.value || preparationMessage.value || (loading.value
  ? rows.value.length ? 'Updating ratios…' : 'Calculating aligned local ratios…'
  : !rows.value.length ? `No ${isFamily.value ? 'family-leg' : 'sector'} rotation rows are available.` : ''))
// A failed preparation over a loaded rotation is a non-blocking notice; only a
// failed rotation request is an "update failed" state.
const rotationPreparationFailed = computed(() => /could not be completed|refresh failed/i.test(preparationMessage.value))
const rotationStatusSummary = computed(() => !error.value && rows.value.length && rotationPreparationFailed.value
  ? 'RRG local results'
  : preparationMessageSummary(rotationStatusDetail.value, 'RRG'))
const plotInstructionsId = `relative-rotation-plot-help-${useId()}`
const plotHost = ref<HTMLElement | null>(null)
const hovered = ref<{ symbol: string; point: PlotPoint; left: number; top: number } | null>(null)
const keyboardPointIndex = ref(-1)
const sortKey = ref<SortKey>('distance')
const sortDirection = ref<-1 | 1>(-1)
const sortedRows = computed(() => [...rows.value].sort((left, right) => {
  const a = sortValue(left, sortKey.value), b = sortValue(right, sortKey.value)
  if (a == null && b == null) return left.symbol.localeCompare(right.symbol)
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'string' && typeof b === 'string') return sortDirection.value * a.localeCompare(b)
  return sortDirection.value * (Number(a) - Number(b)) || left.symbol.localeCompare(right.symbol)
}))
const tooltipStyle = computed(() => hovered.value ? { left: `${hovered.value.left}px`, top: `${hovered.value.top}px` } : {})
let plot: uPlot | null = null
let observer: ResizeObserver | null = null
let observedPlotHost: HTMLElement | null = null
let points: PlotPoint[] = []
let loadGeneration = 0
let renderedAnalysisContext = ''
let renderedAnalysisLabel = ''
let mounted = false
let activeLoadController: AbortController | null = null
function percent(value: number | null | undefined) { return value == null ? '—' : `${(value * 100).toFixed(2)}%` }
function sortValue(row: Row, key: SortKey): string | number | null {
  if (key === 'symbol' || key === 'state' || key === 'transition') return row[key] ?? null
  if (key === 'tail') return row.tail.length
  return row[key] ?? null
}
function setSort(key: SortKey) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 1 ? -1 : 1
  else { sortKey.value = key; sortDirection.value = key === 'symbol' || key === 'state' || key === 'transition' ? 1 : -1 }
}
function sortMark(key: SortKey) { return sortKey.value === key ? (sortDirection.value === 1 ? ' ▲' : ' ▼') : '' }
function sortLabel(key: SortKey) {
  const labels: Record<SortKey, string> = {
    symbol: isFamily.value ? 'leg' : 'sector',
    state: 'state',
    trend: 'trend',
    momentum: 'momentum',
    heading: 'heading',
    distance: 'distance',
    velocity: 'velocity',
    transition: 'transition',
    time_in_state: 'time in state',
    coverage: 'coverage',
    tail: 'tail length',
  }
  if (sortKey.value !== key) return `Sort by ${labels[key]}`
  return `Sort by ${labels[key]}, currently ${sortDirection.value === 1 ? 'ascending' : 'descending'}`
}
function rotationRowLabel(row: Row) {
  const warning = row.warnings?.length ? `, ${row.warnings.length} warning${row.warnings.length === 1 ? '' : 's'}` : ''
  return `${row.symbol}, ${row.state ?? 'unavailable'}, trend ${percent(row.trend)}, momentum ${percent(row.momentum)}, coverage ${percent(row.coverage)}${warning}. Select row for details.`
}
function onPlotMove(event: MouseEvent) {
  if (!plot || !plotHost.value || !points.length) return
  plot.syncRect()
  const hostBounds = plotHost.value.getBoundingClientRect()
  const plotBounds = plot.rect
  const x = event.clientX - plotBounds.left
  const y = event.clientY - plotBounds.top
  let nearest: { point: PlotPoint; distance: number } | null = null
  for (const point of points) {
    const pointX = plot.valToPos(point.trend, 'x')
    const pointY = plot.valToPos(point.momentum, 'y')
    const distance = Math.hypot(pointX - x, pointY - y)
    if (!nearest || distance < nearest.distance) nearest = { point, distance }
  }
  if (!nearest || nearest.distance > 28) {
    hovered.value = null
    return
  }
  hovered.value = {
    symbol: nearest.point.symbol,
    point: nearest.point,
    left: Math.min(Math.max(8, plotBounds.left - hostBounds.left + x + 10), Math.max(8, hostBounds.width - 210)),
    top: Math.min(Math.max(8, plotBounds.top - hostBounds.top + y + 10), Math.max(8, hostBounds.height - 58)),
  }
}
function selectHovered() {
  if (hovered.value) emit('select', hovered.value.symbol, rows.value.find(row => row.symbol === hovered.value?.symbol)?.instrument_id)
}
function latestPlotPoints() { return points.filter(point => point.last) }
function showKeyboardPoint(index: number) {
  const available = latestPlotPoints()
  const host = plotHost.value
  if (!plot || !host || available.length === 0) return
  plot.syncRect()
  const nextIndex = Math.min(available.length - 1, Math.max(0, index))
  const point = available[nextIndex]
  const bounds = host.getBoundingClientRect()
  const plotBounds = plot.rect
  const x = plot.valToPos(point.trend, 'x'), y = plot.valToPos(point.momentum, 'y')
  keyboardPointIndex.value = nextIndex
  hovered.value = {
    symbol: point.symbol,
    point,
    left: Math.min(Math.max(8, plotBounds.left - bounds.left + x + 10), Math.max(8, bounds.width - 210)),
    top: Math.min(Math.max(8, plotBounds.top - bounds.top + y + 10), Math.max(8, bounds.height - 58)),
  }
}
function handlePlotFocus() {
  // Clicking a hovered point focuses the keyboard surface before the click
  // handler runs; keep that deliberate pointer target instead of replacing it
  // with the first keyboard point.
  if (keyboardPointIndex.value < 0 && !hovered.value) showKeyboardPoint(0)
}
function handlePlotBlur() {
  keyboardPointIndex.value = -1
  hovered.value = null
}
function handlePlotKeydown(event: KeyboardEvent) {
  const available = latestPlotPoints()
  if (available.length === 0) return
  const currentIndex = Math.min(available.length - 1, Math.max(0, keyboardPointIndex.value))
  let nextIndex: number
  switch (event.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      nextIndex = Math.min(available.length - 1, currentIndex + 1)
      break
    case 'ArrowLeft':
    case 'ArrowUp':
      nextIndex = Math.max(0, currentIndex - 1)
      break
    case 'Home':
      nextIndex = 0
      break
    case 'End':
      nextIndex = available.length - 1
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      emit('select', available[currentIndex].symbol, rows.value.find(row => row.symbol === available[currentIndex].symbol)?.instrument_id)
      return
    default:
      return
  }
  event.preventDefault()
  showKeyboardPoint(nextIndex)
}
function syncPlotObserver() {
  const host = plotHost.value
  if (host === observedPlotHost) return
  observer?.disconnect()
  observedPlotHost = host
  if (host) observer?.observe(host)
}
const colors: Record<string, string> = { leading: '#61c58c', weakening: '#e7bc68', improving: '#6dbbe6', lagging: '#df8181' }
function numericRange(values: number[]): [number, number] {
  let min = 0, max = 0
  for (const value of values) {
    if (!Number.isFinite(value)) continue
    min = Math.min(min, value)
    max = Math.max(max, value)
  }
  const padding = Math.max((max - min) * 0.08, 0.005)
  return [min - padding, max + padding]
}
function drawPlot() {
  syncPlotObserver()
  if (!plotHost.value) return
  points = rows.value.flatMap(row => {
    const curve = row.history.length ? row.history : row.tail
    return curve.map((tail, index) => ({ ...tail, symbol: row.symbol, color: colors[row.state ?? ''] ?? '#8796a1', last: index === curve.length - 1 }))
  }).filter(point => Number.isFinite(point.trend) && Number.isFinite(point.momentum))
  hovered.value = null
  const width = Math.max(160, plotHost.value.clientWidth), height = Math.max(64, plotHost.value.clientHeight)
  const compactPlot = height < 160
  // uPlot's aligned-data x array must be ascending even though this tool draws
  // the ratio points itself as an XY scatter plot. Keep the hidden y-series
  // paired with its x value, and use the same full finite domain for the
  // custom-drawn points below.
  const sortedCoordinates = [...points].sort((left, right) => left.trend - right.trend)
  const data: uPlot.AlignedData = [sortedCoordinates.map(point => point.trend), sortedCoordinates.map(point => point.momentum)]
  if (plot) {
    // Keep the current scales while replacing aligned data, then explicitly
    // set both numeric domains. The y series is hidden because this is an XY
    // scatter plot drawn by the plugin, so uPlot cannot infer its new bounds.
    plot.setData(data, false)
    const trendRange = numericRange(points.map(point => point.trend))
    const momentumRange = numericRange(points.map(point => point.momentum))
    plot.setScale('x', { min: trendRange[0], max: trendRange[1] })
    plot.setScale('y', { min: momentumRange[0], max: momentumRange[1] })
    plot.setSize({ width, height })
    plot.syncRect()
    return
  }
  const markerPlugin: uPlot.Plugin = { hooks: { draw: [(chart) => {
    const ctx = chart.ctx
    const { left, top, width: plotWidth, height: plotHeight } = chart.bbox
    const pixelRatio = chart.ctx.canvas.width / chart.width || 1
    const zeroX = chart.valToPos(0, 'x', true)
    const zeroY = chart.valToPos(0, 'y', true)
    const compactDataPlane = plotHeight / pixelRatio < 72
    ctx.save()
    ctx.strokeStyle = '#53636e'
    ctx.lineWidth = pixelRatio
    ctx.setLineDash([3 * pixelRatio, 3 * pixelRatio])
    if (Number.isFinite(zeroX)) { ctx.beginPath(); ctx.moveTo(zeroX, top); ctx.lineTo(zeroX, top + plotHeight); ctx.stroke() }
    if (Number.isFinite(zeroY)) { ctx.beginPath(); ctx.moveTo(left, zeroY); ctx.lineTo(left + plotWidth, zeroY); ctx.stroke() }
    ctx.font = `${(compactDataPlane ? 8 : 10) * pixelRatio}px Segoe UI`
    ctx.fillStyle = '#7fca9e'
    if (Number.isFinite(zeroX) && Number.isFinite(zeroY)) {
      ctx.fillText('Leading', Math.min(left + plotWidth - 54 * pixelRatio, zeroX + 6 * pixelRatio), Math.max(top + 10 * pixelRatio, zeroY - 8 * pixelRatio))
      ctx.fillStyle = '#d2b675'
      ctx.fillText('Weakening', Math.min(left + plotWidth - 66 * pixelRatio, zeroX + 6 * pixelRatio), Math.min(top + plotHeight - 6 * pixelRatio, zeroY + 18 * pixelRatio))
      ctx.fillStyle = '#83bce0'
      ctx.fillText('Improving', Math.max(left + 4 * pixelRatio, zeroX - 64 * pixelRatio), Math.max(top + 12 * pixelRatio, zeroY - 8 * pixelRatio))
      ctx.fillStyle = '#d88b8b'
      ctx.fillText('Lagging', Math.max(left + 4 * pixelRatio, zeroX - 52 * pixelRatio), Math.min(top + plotHeight - 6 * pixelRatio, zeroY + 18 * pixelRatio))
    }
    ctx.restore()
    for (const row of rows.value) {
      const curve = row.history.length ? row.history : row.tail
      if (curve.length < 2) continue
      ctx.save()
      ctx.strokeStyle = colors[row.state ?? ''] ?? '#8796a1'
      ctx.globalAlpha = 0.72
      ctx.lineWidth = 1
      ctx.beginPath()
      curve.forEach((tail, index) => {
        const x = chart.valToPos(tail.trend, 'x', true)
        const y = chart.valToPos(tail.momentum, 'y', true)
        if (!Number.isFinite(x) || !Number.isFinite(y)) return
        if (index === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
      ctx.restore()
    }
    const latestLabels = points.filter(point => point.last)
      .map(point => ({ point, x: chart.valToPos(point.trend, 'x', true), y: chart.valToPos(point.momentum, 'y', true) }))
      .filter(entry => Number.isFinite(entry.x) && Number.isFinite(entry.y))
      .sort((left, right) => left.y - right.y)
    const labelRects: Array<{ left: number; top: number; right: number; bottom: number }> = []
    const labelFontSize = (compactDataPlane ? 8 : 9) * pixelRatio
    const labelPadding = 2 * pixelRatio
    const labelGap = 4 * pixelRatio
    ctx.font = `${labelFontSize}px Segoe UI`
    for (const { point, x, y } of latestLabels) {
      const labelWidth = Math.max(24 * pixelRatio, ctx.measureText?.(point.symbol).width ?? point.symbol.length * labelFontSize * 0.66)
      const minLabelLeft = left + labelPadding
      const maxLabelLeft = Math.max(minLabelLeft, left + plotWidth - labelWidth - labelPadding)
      const minBaseline = top + labelFontSize + labelPadding
      const maxBaseline = Math.max(minBaseline, top + plotHeight - labelPadding)
      const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
      const candidates = [
        { left: x + labelGap, baseline: y - labelGap },
        { left: x + labelGap, baseline: y + labelFontSize + labelGap },
        { left: x - labelWidth - labelGap, baseline: y - labelGap },
        { left: x - labelWidth - labelGap, baseline: y + labelFontSize + labelGap },
        { left: x - labelWidth / 2, baseline: y - labelFontSize - labelGap },
        { left: x - labelWidth / 2, baseline: y + labelFontSize + labelGap },
      ].map(candidate => {
        const labelLeft = clamp(candidate.left, minLabelLeft, maxLabelLeft)
        const labelBaseline = clamp(candidate.baseline, minBaseline, maxBaseline)
        return {
          left: labelLeft,
          baseline: labelBaseline,
          rect: {
            left: labelLeft - labelPadding,
            top: labelBaseline - labelFontSize - labelPadding,
            right: labelLeft + labelWidth + labelPadding,
            bottom: labelBaseline + labelPadding,
          },
        }
      })
      const markerRadius = 4.5 * pixelRatio
      const placed = candidates.map(candidate => {
        const overlapArea = labelRects.reduce((area, previous) => {
          const overlapWidth = Math.max(0, Math.min(candidate.rect.right, previous.right) - Math.max(candidate.rect.left, previous.left))
          const overlapHeight = Math.max(0, Math.min(candidate.rect.bottom, previous.bottom) - Math.max(candidate.rect.top, previous.top))
          return area + overlapWidth * overlapHeight
        }, 0)
        const markerOverlap = latestLabels.reduce((count, marker) => {
          if (marker.point === point) return count
          const markerRect = { left: marker.x - markerRadius, top: marker.y - markerRadius, right: marker.x + markerRadius, bottom: marker.y + markerRadius }
          return count + Number(candidate.rect.left < markerRect.right && candidate.rect.right > markerRect.left
            && candidate.rect.top < markerRect.bottom && candidate.rect.bottom > markerRect.top)
        }, 0)
        const distance = Math.hypot(candidate.left - x, candidate.baseline - y)
        return { ...candidate, cost: overlapArea * 100 + markerOverlap * 200 + distance * 0.01 }
      }).sort((first, second) => first.cost - second.cost)[0]
      const { left: labelX, baseline: labelY, rect: labelRect } = placed
      labelRects.push(labelRect)
      ctx.fillStyle = '#0d1318'
      ctx.fillRect(labelRect.left, labelRect.top, labelRect.right - labelRect.left, labelRect.bottom - labelRect.top)
      ctx.fillStyle = point.color
      ctx.fillText(point.symbol, labelX, labelY)
    }
    // Paint every older point first. If markers are drawn row-by-row, a later
    // row's historical point can cover an earlier row's latest marker. Keep
    // all current centers above the complete history layer and label backdrops.
    for (const point of points.filter(candidate => !candidate.last)) {
      const x = chart.valToPos(point.trend, 'x', true), y = chart.valToPos(point.momentum, 'y', true)
      ctx.fillStyle = point.color; ctx.beginPath(); ctx.arc(x, y, 2 * pixelRatio, 0, Math.PI * 2); ctx.fill()
    }
    for (const point of points.filter(candidate => candidate.last)) {
      const x = chart.valToPos(point.trend, 'x', true), y = chart.valToPos(point.momentum, 'y', true)
      ctx.fillStyle = point.color; ctx.beginPath(); ctx.arc(x, y, 3.5 * pixelRatio, 0, Math.PI * 2); ctx.fill()
    }
  }] } }
  plot = new uPlot({
    width,
    height,
    // The tool has its own Settings, Rows, and status controls. Do not spend
    // part of a compact dock's height on uPlot's second legend row.
    legend: { show: false },
    // Keep the full axis labels while using measured tick-value widths and
    // compact reservations so short panes retain a useful XY data plane.
    padding: compactPlot ? [2, 4, 2, 4] : [4, 8, 4, 8],
    cursor: { drag: { x: true, y: true } },
    scales: {
      x: { time: false, auto: true, range: () => numericRange(points.map(point => point.trend)) },
      y: { auto: true, range: () => numericRange(points.map(point => point.momentum)) },
    },
    axes: [
      {
        label: 'Relative trend',
        stroke: '#9aabb6',
        size: compactPlot ? 14 : 18,
        gap: compactPlot ? 1 : 2,
        labelSize: compactPlot ? 10 : 16,
        labelGap: compactPlot ? 1 : 2,
        grid: { stroke: '#26313a', width: 1 },
        ticks: { stroke: '#40505a', width: 1, size: compactPlot ? 2 : 3 },
        values: (_u, values) => values.map(value => `${(value * 100).toFixed(1)}%`),
        font: compactPlot ? '9px Segoe UI' : '10px Segoe UI',
        labelFont: compactPlot ? '9px Segoe UI' : '10px Segoe UI',
      },
      {
        label: 'Relative momentum',
        stroke: '#9aabb6',
        size: (_u, values) => Math.ceil(Math.max(0, ...(values ?? []).map(value => _u.ctx.measureText(value).width)) + (compactPlot ? 6 : 8)),
        gap: 2,
        labelSize: compactPlot ? 10 : 16,
        labelGap: compactPlot ? 1 : 2,
        grid: { stroke: '#26313a', width: 1 },
        ticks: { stroke: '#40505a', width: 1, size: compactPlot ? 2 : 3 },
        values: (_u, values) => values.map(value => `${(value * 100).toFixed(1)}%`),
        font: compactPlot ? '9px Segoe UI' : '10px Segoe UI',
        labelFont: compactPlot ? '9px Segoe UI' : '10px Segoe UI',
      },
    ],
    series: [{}, { show: false }],
    plugins: [markerPlugin],
  }, data, plotHost.value)
}
function publishConfiguration() {
  emit('configuration', { ...(props.configuration ?? {}), group_key: groupKey.value, benchmark: benchmark.value.toUpperCase(), timeframe: timeframe.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, history_length: historyLength.value, as_of: asOf.value || null, adjusted: adjusted.value })
}
function asOfTimestamp() { return asOf.value ? `${asOf.value}T23:59:59Z` : undefined }
async function load() {
  activeLoadController?.abort()
  const generation = ++loadGeneration
  const controller = new AbortController()
  activeLoadController = controller
  loading.value = true
  error.value = ''
  preparationMessage.value = ''
  const params = { ...(isFamily.value ? {} : { benchmark: benchmark.value.toUpperCase() }), timeframe: timeframe.value, adjusted: adjusted.value, sampling: sampling.value, lookback: lookback.value, tail_length: tailLength.value, history_length: historyLength.value, as_of: asOfTimestamp() }
  const selectedGroup = groupKey.value
  const family = isFamily.value
  const path = family
    ? `/analysis/benchmark-families/${encodeURIComponent(selectedGroup)}/relative-rotation`
    : `/analysis/groups/${encodeURIComponent(selectedGroup)}/relative-rotation`
  const target = family
    ? { kind: 'family' as const, family_key: selectedGroup }
    : { kind: 'market_group' as const, group_key: selectedGroup }
  const queryKey = ['workstation', 'relative-rotation', selectedGroup, params]
  const contextKey = JSON.stringify(queryKey)
  const contextLabel = `${selectedGroup} · ${params.timeframe}${params.benchmark ? ` vs ${params.benchmark}` : ''} · lookback ${params.lookback} · sample ${params.sampling}${params.as_of ? ` · as of ${params.as_of.slice(0, 10)}` : ''}`
  const showingPriorContext = () => Boolean(rows.value.length && renderedAnalysisContext && renderedAnalysisContext !== contextKey)
  const contextualize = (message: string) => showingPriorContext()
    ? `${message} Showing ${renderedAnalysisLabel} results while ${contextLabel} loads.`
    : message
  let currentPreparationText = showingPriorContext() ? `Updating ${contextLabel}.` : ''
  preparationMessage.value = contextualize(currentPreparationText)
  const isCurrent = () => mounted && generation === loadGeneration && !controller.signal.aborted
  const readAnalysis = async (fresh = false) => {
    if (fresh) await queryClient.invalidateQueries({ queryKey, exact: true, refetchType: 'none' })
    return queryClient.fetchQuery<{ rows?: Row[]; roles?: Row[]; benchmark?: string; freshness?: string }>({
      queryKey,
      // The query is shared by every tool with this key, so its cancellation must
      // belong to the query, not to whichever instance started it.
      queryFn: ({ signal }) => api.get<{ rows?: Row[]; roles?: Row[]; benchmark?: string; freshness?: string }>(path, params, { signal }),
      staleTime: fresh ? 0 : 30_000,
    })
  }
  const applyAnalysis = async (payload: { rows?: Row[]; roles?: Row[]; benchmark?: string; freshness?: string }) => {
    if (!isCurrent()) return
    rows.value = (payload.roles ?? payload.rows ?? []).map(row => ({ ...row, tail: row.tail ?? [], history: row.history ?? [], symbol: row.symbol ?? row.label ?? row.role ?? 'Unavailable' }))
    rotationBenchmark.value = payload.benchmark ?? (family ? rotationBenchmark.value : benchmark.value.toUpperCase())
    freshness.value = payload.freshness ?? ''
    renderedAnalysisContext = contextKey
    renderedAnalysisLabel = contextLabel
    if (currentPreparationText.startsWith('Updating ')) currentPreparationText = ''
    preparationMessage.value = contextualize(currentPreparationText)
    error.value = ''
    await nextTick()
    if (isCurrent()) drawPlot()
  }
  const reportAnalysisFailure = () => {
    if (!isCurrent()) return
    if (!rows.value.length) error.value = 'Relative rotation data could not be loaded.'
    else {
      currentPreparationText = 'The latest local refresh failed; showing the available results.'
      preparationMessage.value = contextualize(currentPreparationText)
    }
  }

  // Read the local analysis immediately. An admitted backfill can take much
  // longer, but it must not hide a useful cached plot or erase it on a hold.
  const initialAnalysis = readAnalysis().then(applyAnalysis).catch(cause => {
    if (cause?.name !== 'AbortError') reportAnalysisFailure()
  })
  const progressRefreshQueue = new PreparationProgressRefreshQueue()
  const refreshForProgress = (response: import('@/lib/dataPreparation').DataEnsureResponse) => progressRefreshQueue.request(response, async () => {
      await initialAnalysis
      if (!isCurrent() || !progressRefreshQueue.isLatest(response)) return
      try { await applyAnalysis(await readAnalysis(true)) } catch (cause: any) {
        if (cause?.name !== 'AbortError') reportAnalysisFailure()
      }
    })
  const preparation = dataPreparationCoordinator.ensure({
    target,
    datasets: ['identity', 'history'],
    timeframe: params.timeframe as import('@/lib/dataPreparation').PreparationTimeframe,
    adjusted: params.adjusted,
    end_at: params.as_of ?? null,
    analysis: {
      kind: 'rrg', lookback: params.lookback, sampling: params.sampling,
      tail_length: params.tail_length, history_length: params.history_length,
      ...(family ? {} : { benchmark_symbol: params.benchmark }),
    },
  }, {
    signal: controller.signal,
    onProgress: progress => {
      if (!isCurrent()) return
      const status = progress.response.status
      currentPreparationText = ['queued', 'running', 'partial'].includes(status)
        ? `Preparing ratio inputs (${progress.completed}/${progress.total} dependencies)…`
        : preparationStatusMessage(progress.response)
      preparationMessage.value = contextualize(currentPreparationText)
      if (shouldRefreshAnalysisProgress(progress.response)) {
        void refreshForProgress(progress.response).catch(reportAnalysisFailure)
      }
    },
  }).then(async result => {
    if (!isCurrent()) return
    currentPreparationText = result.status === 'ready' ? '' : preparationStatusMessage(result)
    preparationMessage.value = contextualize(currentPreparationText)
    // A terminal held/partial outcome can still have produced independently
    // useful inputs, so reread this exact analysis context without discarding
    // the last successful result.
    await refreshForProgress(result).catch(reportAnalysisFailure)
  }).catch(cause => {
    if (isCurrent() && cause?.name !== 'AbortError') {
      currentPreparationText = 'Data preparation could not be completed; showing available local results.'
      preparationMessage.value = contextualize(currentPreparationText)
    }
  })

  try {
    await Promise.all([initialAnalysis, preparation])
  } finally {
    if (isCurrent()) loading.value = false
    if (generation === loadGeneration && activeLoadController === controller) activeLoadController = null
  }
}
onMounted(async () => {
  mounted = true
  observer = new ResizeObserver(drawPlot)
  syncPlotObserver()
  await load()
})
watch([groupKey, benchmark, timeframe, sampling, lookback, tailLength, historyLength, asOf, adjusted], () => { publishConfiguration(); if (sampling.value >= 1 && lookback.value >= 2 && tailLength.value >= 1 && historyLength.value >= 0) void load() })
watch(plotHost, syncPlotObserver, { flush: 'post' })
watch(() => props.configuration, configuration => {
  if (typeof configuration?.group_key === 'string') groupKey.value = configuration.group_key
  if (typeof configuration?.benchmark === 'string') benchmark.value = configuration.benchmark.toUpperCase()
  if (typeof configuration?.timeframe === 'string' && ['D1', 'W1', 'MN'].includes(configuration.timeframe)) timeframe.value = configuration.timeframe
  if (Number.isFinite(Number(configuration?.lookback))) lookback.value = Math.min(252, Math.max(2, Number(configuration?.lookback)))
  if (Number.isFinite(Number(configuration?.tail_length))) tailLength.value = Math.min(100, Math.max(1, Number(configuration?.tail_length)))
  if (Number.isFinite(Number(configuration?.history_length))) historyLength.value = Math.min(5000, Math.max(0, Number(configuration?.history_length)))
  if (Number.isFinite(Number(configuration?.sampling))) sampling.value = Math.min(30, Math.max(1, Number(configuration?.sampling)))
  if (typeof configuration?.as_of === 'string') asOf.value = configuration.as_of
  if (configuration?.as_of === null) asOf.value = ''
  if (typeof configuration?.adjusted === 'boolean') adjusted.value = configuration.adjusted
}, { deep: true })
onBeforeUnmount(() => {
  mounted = false
  loadGeneration += 1
  activeLoadController?.abort(); activeLoadController = null
  observer?.disconnect(); observedPlotHost = null; plot?.destroy(); plot = null
})
</script>

<style scoped>
.rotation-tool{position:relative;display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden;background:#11161b;color:#cad4db;font:10px "Segoe UI",Arial,sans-serif}
.rotation-tool__header{position:static;display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:5px;min-width:0;padding:3px 6px;border-bottom:1px solid #2d3841}
.rotation-tool__header-main{display:flex;align-items:center;gap:5px;min-width:0}
.rotation-tool__header strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rotation-tool__status{flex:0 1 auto;min-width:0;max-width:58%}
.rotation-tool__settings,.rotation-tool__rows-disclosure{position:static;flex:0 0 auto}
.rotation-tool__settings>summary,.rotation-tool__rows-disclosure>summary{padding:3px 5px;border:1px solid #394750;border-radius:2px;background:#172027;color:#c8d4dc;cursor:pointer;white-space:nowrap;list-style:none}
.rotation-tool__settings>summary::-webkit-details-marker,.rotation-tool__rows-disclosure>summary::-webkit-details-marker{display:none}
.rotation-tool__settings>summary::before{content:'▸';margin-right:4px}.rotation-tool__settings[open]>summary::before{content:'▾'}
.rotation-tool__settings-panel{position:absolute;top:38px;left:6px;z-index:5;box-sizing:border-box;width:min(340px,calc(100vw - 24px),calc(100% - 12px));max-height:calc(100% - 44px);overflow:auto;padding:8px;border:1px solid #526674;background:#172027;box-shadow:0 4px 12px #000b}
.rotation-tool__settings-panel small{display:block;margin-top:6px;color:#82929d}
.rotation-tool__controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;align-items:center}
.rotation-tool__controls label{display:flex;align-items:center;gap:3px;min-width:0;color:#9aabb6}
.rotation-tool__controls input,.rotation-tool__controls select{box-sizing:border-box;min-width:0;width:auto;flex:0 1 78px;max-width:100%;border:1px solid #3a4954;background:#172027;color:#dce6ed;font:inherit;padding:2px 3px}
.rotation-tool__controls label:first-child{grid-column:1/-1}.rotation-tool__controls label:first-child select{flex-basis:150px}.rotation-tool__controls label:nth-child(7) input{flex-basis:100px}.rotation-tool__adjusted input{flex:0 0 auto}
.rotation-tool__rows-disclosure{position:static}
.rotation-tool__rows-disclosure[open]>.rotation-tool__table{position:absolute;z-index:6;right:0;bottom:6px;width:min(100%,900px);height:min(52vh,280px);max-height:calc(100% - 48px);min-height:64px;overflow:auto;border:1px solid #526674;background:#172027;box-shadow:0 4px 14px #000b}
.rotation-tool__plot-shell{position:relative;flex:1 1 auto;min-height:64px;background:#101419;overflow:hidden}
.rotation-tool__plot{width:100%;height:100%}.rotation-tool__plot:focus-visible{outline:2px solid #eef3fb;outline-offset:-2px}
.rotation-tool__state{display:grid;flex:1 1 auto;min-height:48px;place-items:center;margin:0;color:#8596a1;text-align:center;padding:8px}.rotation-tool__state--error{color:#e28c8c}
.rotation-tool__sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.rotation-tool__tooltip{position:absolute;z-index:2;display:grid;gap:2px;min-width:190px;padding:5px 7px;border:1px solid #526674;background:#172027;color:#dce6ed;box-shadow:0 3px 12px #0008;pointer-events:none}.rotation-tool__tooltip span{color:#9aabb6}
.rotation-tool__table{height:100%;overflow:auto;overscroll-behavior:contain}.rotation-tool__head,.rotation-tool__row{display:grid;grid-template-columns:54px 78px 58px 68px 76px 66px 76px 76px 104px 58px 72px 42px;align-items:center;gap:5px;padding:5px 7px;min-width:720px}.rotation-tool__head{position:sticky;top:0;background:#20282f;color:#9baab5;font-weight:600;text-transform:uppercase}.rotation-tool__head button{border:0;background:transparent;color:inherit;font:inherit;text-align:left;padding:0;cursor:pointer}.rotation-tool__head button:hover{color:#e4eef3}.rotation-tool__row{width:100%;border:0;border-bottom:1px solid #20282f;background:transparent;color:inherit;text-align:left;cursor:pointer}.rotation-tool__row:hover{background:#1d4057}.rotation-tool__state-leading{color:#61c58c}.rotation-tool__state-weakening{color:#e7bc68}.rotation-tool__state-improving{color:#6dbbe6}.rotation-tool__state-lagging{color:#df8181}
@media (max-height: 680px) {
  .rotation-tool__header { padding-block: 0; }
  .rotation-tool__settings>summary,.rotation-tool__rows-disclosure>summary { padding-block: 1px; }
  .rotation-tool__status :deep(summary) { padding-block: 1px; }
}
</style>
