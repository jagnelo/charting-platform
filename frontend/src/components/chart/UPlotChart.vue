<template>
  <div class="chart-root" ref="rootRef">

    <!-- Main price chart -->
    <div class="uplot-wrapper" ref="wrapperRef"
          :class="{ 'cursor-crosshair-wrapper': !!drawStore.activeToolType || drawStore.avwapDropActive }">
      <canvas ref="drawingCanvasRef" class="drawing-canvas"
              :class="{ 'cursor-crosshair': !!drawStore.activeToolType || drawStore.avwapDropActive }" />
      <div ref="chartRef" />

      <!-- TradingView-style OHLCV info — fixed top-left, not cursor-following -->
      <div class="ohlcv-info" v-if="tooltip.hasData">
        <span class="tt-date">{{ tooltip.date }}</span>
        <span class="tt-item">O <b>{{ fmt(tooltip.o) }}</b></span>
        <span class="tt-item">H <b>{{ fmt(tooltip.h) }}</b></span>
        <span class="tt-item">L <b>{{ fmt(tooltip.l) }}</b></span>
        <span class="tt-item">C <b :class="tooltip.c >= tooltip.o ? 'up' : 'dn'">{{ fmt(tooltip.c) }}</b></span>
        <span class="tt-item tt-vol" v-if="tooltip.v">V <b>{{ fmtVol(tooltip.v) }}</b></span>
        <span class="tt-chg" :class="tooltip.chg >= 0 ? 'up' : 'dn'" v-if="tooltip.chg != null">
          {{ tooltip.chg >= 0 ? '+' : '' }}{{ tooltip.chg.toFixed(2) }}%
        </span>
      </div>

      <!-- TradingView-style A (auto) + L (log) buttons on Y axis -->
      <div class="yaxis-btns">
        <button
          class="yaxis-btn"
          :class="{ active: autoY }"
          @click="toggleAutoY"
          title="Auto scale (A)"
        >A</button>
        <button
          class="yaxis-btn"
          :class="{ active: isLogScale }"
          @click="toggleLogScale"
          title="Log scale (L)"
        >L</button>
      </div>

      <!-- Right-click context menu on price axis -->
      <div class="ctx-menu" v-if="ctxMenu.visible"
           :style="{ top: ctxMenu.y + 'px', right: '8px' }"
           @mouseleave="ctxMenu.visible = false">
        <button @click="toggleLogScale">{{ isLogScale ? '✓ ' : '' }}Log Scale</button>
        <button @click="resetPriceScale">Reset Price Scale</button>
      </div>

      <!-- Drawing context menu (right-click on selected drawing) -->
      <div class="ctx-menu" v-if="drawCtxMenu.visible"
           :style="{ top: drawCtxMenu.y + 'px', left: drawCtxMenu.x + 'px' }"
           @mouseleave="drawCtxMenu.visible = false">
        <button @click="deleteSelectedDrawing">🗑 Delete Drawing</button>
        <button @click="drawCtxMenu.visible = false; drawStore.selectDrawing(null)">Deselect</button>
      </div>
    </div>

    <!-- Sub-panes: one per separate-pane indicator -->
    <div
      v-for="pane in subPanes"
      :key="pane.key"
      class="sub-pane"
      :ref="el => subPaneRefs[pane.key] = el as HTMLElement"
    >
      <div class="sub-pane-label">{{ pane.label }}</div>
    </div>

    <!-- Go to latest button -->
    <button v-if="!isAtLatest" class="go-to-latest" @click="goToLatest">
      → Latest
    </button>

    <!-- Keyboard shortcuts overlay -->
    <Transition name="fade">
      <div class="shortcuts-overlay" v-if="showShortcuts" @click="showShortcuts = false">
        <div class="shortcuts-box" @click.stop>
          <div class="sc-title">Keyboard Shortcuts</div>
          <div class="sc-row"><kbd>+</kbd><kbd>-</kbd> Zoom in / out</div>
          <div class="sc-row"><kbd>←</kbd><kbd>→</kbd> Pan 5 bars</div>
          <div class="sc-row"><kbd>Alt</kbd><kbd>R</kbd> Go to latest</div>
          <div class="sc-row"><kbd>L</kbd> Toggle log scale</div>
          <div class="sc-row"><kbd>?</kbd> This help</div>
          <div class="sc-row"><kbd>Del</kbd> Delete selected drawing</div>
          <div class="sc-row"><kbd>Esc</kbd> Deselect / cancel tool</div>
          <div class="sc-row sc-mouse"><b>Scroll</b> Zoom on cursor</div>
          <div class="sc-row sc-mouse"><b>Shift+Scroll</b> Pan</div>
          <div class="sc-row sc-mouse"><b>Shift+Click</b> Measure</div>
          <div class="sc-row sc-mouse"><b>Drag</b> Pan</div>
          <div class="sc-row sc-mouse"><b>Price axis drag</b> Zoom Y</div>
          <div class="sc-row sc-mouse"><b>Price axis dblclick</b> Reset Y</div>
          <div class="sc-row sc-mouse"><b>Price axis right-click</b> Menu</div>
          <button class="sc-close" @click="showShortcuts = false">✕ Close</button>
        </div>
      </div>
    </Transition>

    <!-- Help button -->
    <button class="help-btn" @click="showShortcuts = !showShortcuts" title="Keyboard shortcuts">?</button>

    <!-- Chart settings button (cog) -->
    <button class="settings-btn" @click="showChartSettings = !showChartSettings" title="Chart settings">⚙</button>
  </div>

  <!-- Chart settings popup -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="showChartSettings" @click.self="showChartSettings = false">
        <div class="editor-box">
          <div class="ed-header">
            <span>Chart Settings</span>
            <button class="ed-close" @click="showChartSettings = false">✕</button>
          </div>
          <div class="ed-body">
            <div class="ed-section-title">Y-Axis Projections</div>
            <label class="ed-checkbox-row">
              <input type="checkbox" v-model="userSettingsStore.showCurrentPriceProjection" class="ed-checkbox" />
              Show current price on Y axis
            </label>
            <label class="ed-checkbox-row">
              <input type="checkbox" v-model="userSettingsStore.showHighLowProjection" class="ed-checkbox" />
              Show visible high / low on Y axis
            </label>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed, reactive, inject } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { usePanelStore }        from '@/stores/chart'
import { useLayoutStore }       from '@/stores/layout'
import { useDrawingsStore }     from '@/stores/drawings'
import { useAlertsStore }       from '@/stores/alerts'
import { useUserSettingsStore } from '@/stores/userSettings'
import { candlestickPlugin }       from '@/lib/uplot/plugins/candlestick'
import { volumePlugin }            from '@/lib/uplot/plugins/volume'
import { alertLinesPlugin }        from '@/lib/uplot/plugins/alert-lines'
import { yAxisProjectionsPlugin }  from '@/lib/uplot/plugins/y-axis-projections'
import type { ProjectionItem }     from '@/lib/uplot/plugins/y-axis-projections'
import { DrawingRenderer }   from '@/lib/drawings/renderer'
import type { MeasurementOverlay } from '@/lib/drawings/renderer'
import { computeSMA }  from '@/lib/uplot/indicators/sma'
import { computeEMA }  from '@/lib/uplot/indicators/ema'
import { computeRSI }  from '@/lib/uplot/indicators/rsi'
import { computeVWAP, computeAVWAP } from '@/lib/uplot/indicators/vwap'
import { api }         from '@/lib/api'
import type { DrawingPoint }   from '@/lib/drawings/types'
import type { DrawingType, IndicatorConfig, Timeframe } from '@/types'
import type { AnyDrawing }     from '@/lib/drawings/types'

// ── Constants ─────────────────────────────────────────────────────────────────
const DEFAULT_BARS_VISIBLE  = 150
const ZOOM_FACTOR           = 1.08
const PRICE_DRAG_EXPO       = 0.004
const WHEEL_AXIS_DOMINANCE  = 1.25
const WHEEL_PAN_SENSITIVITY = 0.65
const LIVE_POLL_MULTIPLIER  = 1.0   // poll every 1× bar duration

const PREFETCH_THRESHOLD = 80  // bar indices from left edge before prefetch fires

// ── Stores & DOM refs ─────────────────────────────────────────────────────────
const panelId            = inject<string>('panelId', 'main')
const chartStore         = usePanelStore(panelId)
const layoutStore        = useLayoutStore()
const drawStore          = useDrawingsStore()
const alertsStore        = useAlertsStore()
const userSettingsStore  = useUserSettingsStore()

const rootRef          = ref<HTMLDivElement | null>(null)
const wrapperRef       = ref<HTMLDivElement | null>(null)
const chartRef         = ref<HTMLDivElement | null>(null)
const drawingCanvasRef = ref<HTMLCanvasElement | null>(null)
const subPaneRefs: Record<string, HTMLElement | null> = reactive({})

// ── uPlot instances ───────────────────────────────────────────────────────────
let uplot: uPlot | null = null
let subPlotsMap: Record<string, uPlot> = {}
let drawingRenderer: DrawingRenderer | null = null
let resizeObserver: ResizeObserver | null = null
let lastSeriesCount = 0
let firstRenderedBarTs: string | null = null

interface MeasurementPoint {
  index: number
  time: number
  price: number
}

const measurement = reactive<{
  active: boolean
  frozen: boolean
  start: MeasurementPoint | null
  end: MeasurementPoint | null
}>({
  active: false,
  frozen: false,
  start: null,
  end: null,
})

// ── OHLCV tooltip (top-left, TradingView style) ────────────────────────────
interface TooltipState {
  hasData: boolean
  date: string
  o: number; h: number; l: number; c: number; v: number
  chg: number | null
}
const tooltip = ref<TooltipState>({
  hasData: false, date: '', o: 0, h: 0, l: 0, c: 0, v: 0, chg: null,
})

const fmt    = (v: number) => v != null ? v.toFixed(4) : '—'
const fmtVol = (v: number) => v >= 1e9 ? `${(v/1e9).toFixed(1)}B` : v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : String(Math.round(v))
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function formatDate(ts: number, tf: Timeframe): string {
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
  if (['D1','W1','MN'].includes(tf)) return date
  return `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function updateTooltip(u: uPlot, idx: number | null | undefined) {
  if (idx == null) {
    // Show latest bar when no hover
    const d = u.data as number[][]
    const i = (d[0]?.length ?? 0) - 1
    if (i < 0) { tooltip.value.hasData = false; return }
    idx = i
  }
  const d = u.data as number[][]
  const ts = barIndexToTime(idx)
  if (ts == null) { tooltip.value.hasData = false; return }
  const o = d[1]?.[idx] ?? 0
  const h = d[2]?.[idx] ?? 0
  const l = d[3]?.[idx] ?? 0
  const c = d[4]?.[idx] ?? 0
  const v = d[5]?.[idx] ?? 0
  const prevClose = idx > 0 ? d[4]?.[idx - 1] ?? null : null
  const chg = prevClose != null && prevClose !== 0 ? ((c - prevClose) / prevClose) * 100 : null
  tooltip.value = {
    hasData: true,
    date: formatDate(ts, chartStore.timeframe),
    o, h, l, c, v, chg,
  }
}

// ── UI state ──────────────────────────────────────────────────────────────────
const isAtLatest        = ref(true)
const showShortcuts     = ref(false)
const showChartSettings = ref(false)
const isLogScale        = ref(false)
const autoY             = ref(true)   // true = auto-fit Y to visible bars; false = manual lock
const showCurrentPriceProjection = computed(() => userSettingsStore.showCurrentPriceProjection)
const showHighLowProjection = computed(() => userSettingsStore.showHighLowProjection)

const barTimestamps = computed(() =>
  chartStore.bars.map(b => new Date(b.ts).getTime() / 1000)
)

function barIndexToTime(idx: number): number | null {
  const i = Math.round(idx)
  return barTimestamps.value[i] ?? null
}

function timeToBarIndex(ts: number): number {
  const times = barTimestamps.value
  if (!times.length) return 0

  let lo = 0
  let hi = times.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const v = times[mid]
    if (v === ts) return mid
    if (v < ts) lo = mid + 1
    else hi = mid - 1
  }

  return Math.max(0, Math.min(times.length - 1, lo))
}

function formatXAxisTicks(u: uPlot, ticks: (number | null)[]): string[] {
  const visibleBars = u.scales.x.min != null && u.scales.x.max != null
    ? Math.max(1, u.scales.x.max - u.scales.x.min)
    : DEFAULT_BARS_VISIBLE
  const intraday = !['D1', 'W1', 'MN'].includes(chartStore.timeframe)
  const pad = (n: number) => String(n).padStart(2, '0')

  // Determine display granularity based on zoom level
  // 'year'  — only show year label when year changes
  // 'month' — show month (+ year when year changes)
  // 'day'   — show day (+ month/year when they change)
  // 'time'  — show H:MM (+ date components when they change)
  type Gran = 'year' | 'month' | 'day' | 'time'
  let gran: Gran
  if (visibleBars > 1100)     gran = 'year'
  else if (visibleBars > 260) gran = 'month'
  else if (visibleBars > 80 || !intraday) gran = 'day'
  else                        gran = 'time'

  // Collect valid ticks with their parsed dates, filtering by pixel spacing
  let lastPx = -Infinity
  const valid: Array<{ idx: number; px: number; d: Date }> = []
  for (const t of ticks) {
    if (t == null) continue
    const idx = Math.round(t)
    const ts = barIndexToTime(idx)
    if (ts == null) continue
    const px = u.valToPos(idx, 'x')
    // Minimum gap: at least 44px between tick labels
    if (px - lastPx < 44) continue
    lastPx = px
    valid.push({ idx, px, d: new Date(ts * 1000) })
  }

  // Build label per valid tick — only emit a component if it changed from the previous tick
  const labelMap = new Map<number, string>()
  let prevYear = -1, prevMonth = -1, prevDay = -1

  for (let vi = 0; vi < valid.length; vi++) {
    const { idx, d } = valid[vi]
    const year  = d.getFullYear()
    const month = d.getMonth()
    const day   = d.getDate()
    const mon   = MONTHS[month]
    const shortY = `'${String(year).slice(-2)}`

    let label = ''
    if (gran === 'year') {
      // Only show the year label when it changes
      label = year !== prevYear ? String(year) : ''
    } else if (gran === 'month') {
      if (year !== prevYear) {
        label = `${mon} ${String(year)}`
      } else if (month !== prevMonth) {
        label = mon
      }
      // else suppress — same month
    } else if (gran === 'day') {
      if (year !== prevYear) {
        label = `${mon} ${day}, ${shortY}`
      } else if (month !== prevMonth) {
        label = `${mon} ${day}`
      } else if (day !== prevDay) {
        label = `${day}`
      }
      // else suppress — same day
    } else {
      // 'time' granularity — intraday
      const hhmm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
      if (year !== prevYear) {
        label = `${mon} ${day}, ${shortY} ${hhmm}`
      } else if (month !== prevMonth || day !== prevDay) {
        label = `${mon} ${day} ${hhmm}`
      } else {
        label = hhmm
      }
    }

    labelMap.set(idx, label)
    prevYear  = year
    prevMonth = month
    prevDay   = day
  }

  // Map back to full ticks array (return '' for suppressed/spaced-out ticks)
  return ticks.map(t => {
    if (t == null) return ''
    return labelMap.get(Math.round(t)) ?? ''
  })
}

function formatProjectionDate(ts: number): string {
  const d = new Date(ts * 1000)
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, '${String(d.getFullYear()).slice(-2)}`
}

function toggleAutoY() {
  if (autoY.value) {
    // Lock to current range
    autoY.value = false
  } else {
    // Reset to auto-fit
    autoY.value   = true
    manualYMin    = null
    manualYMax    = null
    refreshScalesPreservingX()
  }
}
const ctxMenu        = reactive({ visible: false, y: 0 })
const drawCtxMenu    = reactive({ visible: false, x: 0, y: 0 })

function deleteSelectedDrawing() {
  drawCtxMenu.visible = false
  if (drawStore.selectedId != null) drawStore.deleteDrawing(drawStore.selectedId)
}

// Y scale — null = auto-fit; set = manual lock
let manualYMin: number | null = null
let manualYMax: number | null = null
let interactionCleanup: (() => void) | null = null
let snapGuard = false
let syncGuard = false
let suppressNextMouseDown = false

interface ViewSnapshot {
  xMin?: number
  xMax?: number
  yMin?: number
  yMax?: number
}

function captureView(): ViewSnapshot | null {
  if (!uplot) return null
  return {
    xMin: uplot.scales.x.min,
    xMax: uplot.scales.x.max,
    yMin: uplot.scales.y.min,
    yMax: uplot.scales.y.max,
  }
}

function restoreView(view: ViewSnapshot | null, xOffset = 0) {
  if (!uplot || !view) return
  if (view.xMin != null && view.xMax != null) {
    uplot.setScale('x', { min: view.xMin + xOffset, max: view.xMax + xOffset })
  }
  if (!autoY.value && view.yMin != null && view.yMax != null) {
    manualYMin = view.yMin
    manualYMax = view.yMax
    uplot.setScale('y', { min: view.yMin, max: view.yMax })
  }
}

function refreshScalesPreservingX() {
  if (!uplot) return
  const view = captureView()
  uplot.setData(uplot.data as uPlot.AlignedData)
  restoreView(view)
}

function redrawVisuals() {
  renderVisualOverlays()
  const redraw = (uplot as any)?.redraw
  if (typeof redraw === 'function') redraw.call(uplot)
}

function renderVisualOverlays(drawings: AnyDrawing[] = drawingOverlayList()) {
  drawingRenderer?.renderAll(drawings, measurementOverlay())
}

function drawingOverlayList(base: AnyDrawing[] = drawStore.renderableDrawings): AnyDrawing[] {
  if (!drawStore.activeToolType || drawingPoints.length === 0 || !drawingPreviewPoint) return base
  return [
    ...base,
    {
      type: drawStore.activeToolType as DrawingType,
      points: [drawingPoints[0], drawingPreviewPoint],
      style: { color: '#ffffff88', lineWidth: 1 },
      isVisible: true,
    } as any,
  ]
}

function measurementOverlay(): MeasurementOverlay | null {
  if (!uplot || !measurement.start || !measurement.end) return null
  const start = measurement.start
  const end = measurement.end
  const x1 = uplot.valToPos(start.index, 'x')
  const x2 = uplot.valToPos(end.index, 'x')
  const y1 = uplot.valToPos(start.price, 'y')
  const y2 = uplot.valToPos(end.price, 'y')
  const priceDiff = end.price - start.price
  const pctDiff = start.price !== 0 ? (priceDiff / start.price) * 100 : 0
  const bars = end.index - start.index
  return {
    x1, y1, x2, y2,
    label: [
      `${priceDiff >= 0 ? '+' : ''}${priceDiff.toFixed(4)} (${pctDiff >= 0 ? '+' : ''}${pctDiff.toFixed(2)}%)`,
      `${bars >= 0 ? '+' : ''}${bars} bars`,
      formatElapsed(Math.abs(end.time - start.time)),
    ],
  }
}

function formatElapsed(seconds: number): string {
  const minute = 60
  const hour = minute * 60
  const day = hour * 24
  const year = day * 365
  if (seconds >= year) return `${(seconds / year).toFixed(1)}y`
  if (seconds >= day) return `${Math.round(seconds / day)}d`
  if (seconds >= hour) return `${Math.round(seconds / hour)}h`
  return `${Math.round(seconds / minute)}m`
}

// ── Live polling ───────────────────────────────────────────────────────────────
// Minimum poll intervals by timeframe — daily+ bars don't change intraday
const TF_POLL_MS: Record<string, number> = {
  M1: 15_000, M5: 30_000, M15: 60_000, M30: 120_000,
  H1: 300_000, H2: 600_000, H4: 900_000, H12: 1_800_000,
  D1: 3_600_000,    // 1 hour — once a day is enough but 1h is safe
  W1: 86_400_000,   // 24 hours
  MN: 86_400_000,   // 24 hours
}
let livePollTimer: ReturnType<typeof setTimeout> | null = null

function startLivePolling() {
  stopLivePolling()
  const tf = chartStore.timeframe as string
  const interval = TF_POLL_MS[tf] ?? 60_000

  const poll = async () => {
    if (!chartStore.symbol || !chartStore.timeframe) return
    try {
      // Only fetch the latest page; merge any genuinely new bars at the tail
      const raw = await api.get<any[]>(`/ohlcv/${encodeURIComponent(chartStore.symbol)}/${chartStore.timeframe}`)
      const mapped = raw.map((b: any) => ({
        ...b,
        open: Number(b.open), high: Number(b.high),
        low:  Number(b.low),  close: Number(b.close),
        volume: b.volume != null ? Number(b.volume) : undefined,
      }))
      const existingLatestTs = chartStore.bars[chartStore.bars.length - 1]?.ts ?? ''
      const newLatestTs      = mapped[mapped.length - 1]?.ts ?? ''
      if (newLatestTs !== existingLatestTs) {
        const wasAtLatest = isAtLatest.value
        // Splice only the tail: keep all bars before the overlap, append new ones
        const overlapIdx = chartStore.bars.findIndex(b => b.ts === mapped[0]?.ts)
        if (overlapIdx >= 0) {
          chartStore.bars = [...chartStore.bars.slice(0, overlapIdx), ...mapped]
        } else {
          // No overlap — just append (shouldn't normally happen)
          chartStore.bars = [...chartStore.bars, ...mapped]
        }
        if (wasAtLatest && uplot) {
          const [tArr] = uplot.data as number[][]
          if (tArr?.length) {
            const barD   = tArr.length > 1 ? tArr[1] - tArr[0] : 86400
            const latest = tArr[tArr.length - 1]
            const span   = uplot.scales.x.max! - uplot.scales.x.min!
            uplot.setScale('x', { min: latest - span + barD, max: latest + barD * 5 })
          }
        }
      }
    } catch { /* silent */ }
    livePollTimer = setTimeout(poll, interval)
  }

  livePollTimer = setTimeout(poll, interval)
}

function stopLivePolling() {
  if (livePollTimer != null) { clearTimeout(livePollTimer); livePollTimer = null }
}

// ── Sub-panes ─────────────────────────────────────────────────────────────────
const subPanes = computed(() =>
  chartStore.activeIndicators
    .filter(i => i.pane === 'separate')
    .map(i => ({
      key:    `${i.type}_${JSON.stringify(i.params)}`,
      label:  `${i.type.toUpperCase()}(${Object.values(i.params).join(',')})`,
      config: i,
    }))
)

const hasVolumeIndicator = computed(() =>
  chartStore.activeIndicators.some(i => i.type === 'volume' && i.pane !== 'separate')
)

// ── Y-scale range ─────────────────────────────────────────────────────────────
function yRangeFn(u: uPlot): [number, number] {
  // Manual lock: user has dragged/scrolled the Y axis
  if (!autoY.value && manualYMin !== null && manualYMax !== null) {
    // Log scale: clamp to strictly positive
    if (isLogScale.value) {
      const safeMin = Math.max(manualYMin, manualYMax * 1e-6)
      return [safeMin, manualYMax]
    }
    return [manualYMin, manualYMax]
  }
  // Auto-fit to visible bars
  const [x, , highs, lows] = u.data as number[][]
  if (!x?.length) return [1, 2]
  const xMin = u.scales.x?.min ?? -Infinity
  const xMax = u.scales.x?.max ?? Infinity
  let lo = Infinity, hi = -Infinity
  for (let i = 0; i < x.length; i++) {
    if (i >= xMin && i <= xMax) {
      if (highs[i] != null && highs[i] > hi) hi = highs[i]
      if (lows[i]  != null && lows[i]  < lo) lo = lows[i]
    }
  }
  if (lo === Infinity || lo <= 0) return [1, 2]
  const pad  = (hi - lo) * 0.08
  const yMin = lo - pad
  const yMax = hi + pad
  // Log scale: floor must be strictly positive — use actual data min, not zero
  if (isLogScale.value) return [Math.max(yMin, lo * 0.92), yMax]
  return [yMin, yMax]
}

// ── Log scale toggle ──────────────────────────────────────────────────────────
function toggleLogScale() {
  ctxMenu.visible = false
  isLogScale.value = !isLogScale.value
  initChart()
}

function resetPriceScale() {
  ctxMenu.visible = false
  manualYMin  = null; manualYMax = null
  autoY.value = true
  refreshScalesPreservingX()
}

// ── Indicator computation ─────────────────────────────────────────────────────
function computeIndicatorSeries(
  closes: number[], highs: number[], lows: number[],
  vols: number[], ts: number[], ind: IndicatorConfig,
): (number | null)[] {
  switch (ind.type) {
    case 'sma':    return computeSMA(closes, (ind.params.period as number) ?? 20)
    case 'ema':    return computeEMA(closes, (ind.params.period as number) ?? 20)
    case 'vwap':   return computeVWAP(ts, highs, lows, closes, vols)
    case 'avwap':  return computeAVWAP(ts, highs, lows, closes, vols, (ind.params.anchorTime as number) ?? ts[0] ?? 0)
    default:       return new Array(closes.length).fill(null)
  }
}

// ── Build data ────────────────────────────────────────────────────────────────
function buildData(): uPlot.AlignedData {
  const barIdx = chartStore.bars.map((_, i) => i)
  const ts = barTimestamps.value
  const opens  = chartStore.bars.map(b => b.open)
  const highs  = chartStore.bars.map(b => b.high)
  const lows   = chartStore.bars.map(b => b.low)
  const closes = chartStore.bars.map(b => b.close)
  const vols   = chartStore.bars.map(b => b.volume ?? 0)
  // Reversed: index 0 (top of UI list) → last series → highest z-index (drawn on top)
  const mainInds = [...chartStore.activeIndicators]
    .reverse()
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')
  const extra = mainInds.map(i => computeIndicatorSeries(closes, highs, lows, vols, ts, i))
  return [barIdx, opens, highs, lows, closes, vols, ...extra] as uPlot.AlignedData
}

// ── Indicator selection highlight plugin ──────────────────────────────────────
function indicatorHighlightPlugin(): uPlot.Plugin {
  return {
    hooks: {
      draw: [(u: uPlot) => {
        const selIdx = chartStore.selectedIndicatorIndex
        if (selIdx == null) return

        const mainInds = [...chartStore.activeIndicators]
          .reverse()
          .filter(i => i.pane !== 'separate' && i.type !== 'volume')

        const mi = mainInds.findIndex(ind => chartStore.indicators.indexOf(ind) === selIdx)
        if (mi < 0) return

        const ind = mainInds[mi]
        const seriesData = (u.data as number[][])[6 + mi]
        if (!seriesData) return

        const dpr = devicePixelRatio || 1
        const { ctx } = u

        ctx.save()
        ctx.beginPath()
        ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height)
        ctx.clip()

        ctx.strokeStyle = ind.style.color
        ctx.lineWidth   = ((ind.style.lineWidth ?? 1.5) + 1.5) * dpr
        ctx.shadowColor = ind.style.color
        ctx.shadowBlur  = 8
        ctx.setLineDash([])
        ctx.beginPath()

        let started = false
        for (let i = 0; i < seriesData.length; i++) {
          const val = seriesData[i]
          if (val == null || isNaN(val)) { started = false; continue }
          const x = u.valToPos((u.data[0] as number[])[i], 'x', true)
          const y = u.valToPos(val, 'y', true)
          if (!started) { ctx.moveTo(x, y); started = true }
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
        ctx.restore()
      }],
    },
  }
}

// ── Build series ──────────────────────────────────────────────────────────────
function buildSeries(): uPlot.Series[] {
  const base: uPlot.Series[] = [
    {},
    { label: 'Open',   scale: 'y',   show: false },
    { label: 'High',   scale: 'y',   show: false },
    { label: 'Low',    scale: 'y',   show: false },
    { label: 'Close',  scale: 'y',   show: false },
    { label: 'Volume', scale: 'vol', show: false },
  ]
  // Reversed: index 0 (top of UI list) → last series → highest z-index (drawn on top)
  const mainInds = [...chartStore.activeIndicators]
    .reverse()
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')
  for (const ind of mainInds) {
    base.push({
      label:  `${ind.type.toUpperCase()}(${Object.values(ind.params).join(',')})`,
      scale:  'y',
      stroke: ind.style.color,
      width:  ind.style.lineWidth ?? 1.5,
      points: { show: false },
    })
  }
  return base
}

// ── Y-axis projection items ───────────────────────────────────────────────────
const FIBO_TYPES = new Set(['fibonacci_retracement', 'fibonacci_extension'])

const DRAWING_CHIP: Record<string, string> = {
  horizontal_line: 'H Line',
  trendline:       'TL',
  ray:             'Ray',
  arrow:           'Arrow',
  rectangle:       'Rect',
  circle:          'Circle',
  half_circle:     'HCirc',
  triangle:        'Tri',
}

function getProjectionItems(): ProjectionItem[] {
  if (!uplot) return []
  const u      = uplot
  const xMin   = u.scales.x?.min ?? 0
  const xMax   = u.scales.x?.max ?? 0
  const items: ProjectionItem[] = []

  // ── Main-pane indicators with showYProjection ────────────────────────────
  const mainInds = [...chartStore.activeIndicators]
    .reverse()
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')

  for (let mi = 0; mi < mainInds.length; mi++) {
    const ind = mainInds[mi]
    if (!ind.showYProjection) continue
    const seriesData = (u.data as number[][])[6 + mi]
    if (!seriesData) continue
    // Walk back from the rightmost visible bar to find the last non-null value
    const rightIdx = Math.min(Math.floor(xMax), seriesData.length - 1)
    let lastVal: number | null = null
    let lastIdx = -1
    for (let i = rightIdx; i >= 0; i--) {
      if (seriesData[i] != null && !isNaN(seriesData[i])) {
        lastVal = seriesData[i]; lastIdx = i; break
      }
    }
    if (lastVal == null) continue
    let label: string
    if (ind.type === 'avwap') {
      const anchorTime = Number(ind.params.anchorTime)
      if (anchorTime) {
        label = `AVWAP\n${formatProjectionDate(anchorTime)}`
      } else {
        label = 'AVWAP'
      }
    } else {
      label = `${ind.type.toUpperCase()}(${Object.values(ind.params).join(',')})`
    }
    items.push({ price: lastVal, color: ind.style.color, chipLabel: label, originX: lastIdx })
  }

  // ── Price alerts with projection toggled on ──────────────────────────────
  for (const alert of alertsStore.alerts) {
    if (alert.status !== 'active' && alert.status !== 'triggered') continue
    if (!alertsStore.getAlertProjection(alert.id)) continue
    const color = alert.status === 'triggered' ? '#888888' : '#ffb74d'
    items.push({ price: Number(alert.threshold_price), color, chipLabel: 'Alert' })
  }

  // ── Drawings (non-fib) with projection toggled on ────────────────────────
  for (const d of drawStore.renderableDrawings) {
    if (!d.id || FIBO_TYPES.has(d.type)) continue
    if (!drawStore.getDrawingProjection(d.id)) continue
    if (!d.points?.length) continue
    if (d.type === 'vertical_line') continue  // no meaningful single price level
    const color = d.style?.color ?? '#ffffff'
    if (d.type === 'horizontal_line') {
      // Full-width — the line is already infinite, projection just adds the chip
      items.push({ price: d.points[0].price, color, chipLabel: 'H Line' })
    } else {
      // Use the rightmost point's price (last defined point)
      const rightPt = d.points.length > 1 ? d.points[d.points.length - 1] : d.points[0]
      const originX = timeToBarIndex(rightPt.time)
      items.push({
        price: rightPt.price,
        color,
        chipLabel: DRAWING_CHIP[d.type] ?? 'Draw',
        originX,
      })
    }
  }

  // ── Current price (last close) ────────────────────────────────────────────
  if (showCurrentPriceProjection.value) {
    const closes = (u.data as number[][])[4]
    if (closes?.length) {
      const lastClose = closes[closes.length - 1]
      if (lastClose != null && !isNaN(lastClose)) {
        items.push({ price: lastClose, color: '#26a69a', chipLabel: 'Last' })
      }
    }
  }

  // ── Visible high / low ────────────────────────────────────────────────────
  if (showHighLowProjection.value) {
    const xArr  = (u.data as number[][])[0]
    const highs = (u.data as number[][])[2]
    const lows  = (u.data as number[][])[3]
    if (xArr && highs && lows) {
      let visHigh = -Infinity, visLow = Infinity
      let highIdx = -1, lowIdx = -1
      for (let i = 0; i < xArr.length; i++) {
        if (i < xMin - 0.5 || i > xMax + 0.5) continue
        if (highs[i] != null && highs[i] > visHigh) { visHigh = highs[i]; highIdx = i }
        if (lows[i]  != null && lows[i]  < visLow)  { visLow  = lows[i];  lowIdx  = i }
      }
      if (highIdx >= 0) items.push({ price: visHigh, color: '#26a69a', chipLabel: 'High', originX: highIdx })
      if (lowIdx  >= 0) items.push({ price: visLow,  color: '#ef5350', chipLabel: 'Low',  originX: lowIdx  })
    }
  }

  return items
}

// ── Init chart ────────────────────────────────────────────────────────────────
async function initChart() {
  if (!chartRef.value || !wrapperRef.value) return

  // Snapshot the current viewport before destroying so we can restore it after
  // a rebuild (e.g. adding/modifying an indicator). Only falls back to
  // setInitialView on the very first render when uplot doesn't exist yet.
  const savedView = captureView()

  destroyAll()
  drawingPoints = []
  drawingPreviewPoint = null
  // Do NOT reset manualYMin/Max or autoY here — they survive rebuilds
  // (log toggle, indicator changes). Only explicit user actions reset them.

  const data = chartStore.uplotData as number[][]
  if (!data[0]?.length) return

  const w = wrapperRef.value.clientWidth || 900
  const h = Math.max(80, (rootRef.value?.clientHeight ?? 600) - subPanes.value.length * 120 - 20)
  const series = buildSeries()
  lastSeriesCount = series.length

  const plugins: uPlot.Plugin[] = [
    candlestickPlugin({ upColor: '#26a69a', downColor: '#ef5350' }),
    alertLinesPlugin(
      () => alertsStore.alerts
        .filter(a => a.status === 'active' || a.status === 'triggered')
        .map(a => ({
          id:        a.id,
          price:     Number(a.threshold_price),
          label:     a.notes ?? undefined,
          triggered: a.status === 'triggered',
        })),
      () => alertsStore.selectedAlertId,
    ),
    indicatorHighlightPlugin(),
    yAxisProjectionsPlugin(() => getProjectionItems()),
  ]

  // Add volume bars plugin if volume indicator is active
  if (hasVolumeIndicator.value) {
    plugins.push(volumePlugin({
      upColor: 'rgba(38,166,154,0.35)',
      downColor: 'rgba(239,83,80,0.35)',
      heightRatio: 0.18,
    }))
  }

  const opts: uPlot.Options = {
    width: w, height: h,

    // Disable uPlot's built-in legend and all drag behaviour
    legend: { show: false },
    cursor: {
      drag:  { x: false, y: false, uni: undefined, dist: 0 },
      sync:  { key: 'chart' },
      lock:  false,
    },

    scales: {
      x: {
        time: false,
        min: savedView?.xMin,
        max: savedView?.xMax,
      },
      y: {
        auto:  true,
        dir:   1,
        distr: isLogScale.value ? 3 : 1,
        range: (_u) => yRangeFn(_u),
      },
      vol: { auto: true, ori: 1, range: (_u, _min, max) => [0, max * 4] },
    },

    axes: [
      {
        scale: 'x', size: 30, gap: 4, stroke: '#555', font: '10px monospace',
        ticks: { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
        values: (_u, ticks) => formatXAxisTicks(_u, ticks),
      },
      {
        scale:  'y', side: 1, size: 65, gap: 6, stroke: '#888', font: '10px monospace',
        ticks:  { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
        values: (_u, ticks) => ticks.map(t => t == null ? '' : t >= 1000 ? t.toFixed(0) : t.toFixed(2)),
      },
    ],

    series,
    plugins,

    hooks: {
      draw: [(u) => {
        renderVisualOverlays()
      }],
      setCursor: [(u) => {
        updateTooltip(u, u.cursor.idx)
        // Broadcast cursor timestamp for cross-panel sync
        if (u.cursor.idx != null && layoutStore.panelCount > 1 && !syncGuard) {
          const ts = chartStore.bars[u.cursor.idx]?.ts
          if (ts) layoutStore.setSyncedTs(ts, panelId)
        }
        // Snap crosshair to nearest bar centre — guard against re-entrancy
        if (snapGuard) return
        const idx = u.cursor.idx
        if (idx != null && u.cursor.left != null) {
          const [x] = u.data as number[][]
          if (x?.length > 1) {
            const snapX = u.valToPos(idx, 'x')
            const barPx = Math.abs(u.valToPos(1, 'x') - u.valToPos(0, 'x'))
            if (Math.abs((u.cursor.left ?? snapX) - snapX) < barPx * 0.7) {
              snapGuard = true
              u.setCursor({ left: snapX, top: u.cursor.top ?? 0 })
              snapGuard = false
            }
          }
        }
      }],
      ready: [(u) => {
        setupDrawingCanvas(u)
        setupDrawingInteraction(u)
        setupHitDetection(u)
        setupInteraction(u)
        updateTooltip(u, null)
      }],
    },
  }

  uplot = new uPlot(opts, buildData(), chartRef.value)
  firstRenderedBarTs = chartStore.bars[0]?.ts ?? null
  if (savedView?.xMin != null && savedView?.xMax != null) {
    restoreView(savedView)
    // Force an immediate, synchronous Y recompute against the restored X window.
    // Without this, uPlot batches Y recalculation to the next RAF, leaving the
    // internal Y scale state from the full-data initial render.  The result is
    // a visible Y snap (or flash) on the very first user interaction after any
    // rebuild — adding an indicator, toggling log scale, etc.
    // This mirrors what setInitialView() does for the first-render path.
    uplot.setData(uplot.data as uPlot.AlignedData)
    restoreView(savedView)
    // Keep isAtLatest in sync with the restored viewport
    const [xArr] = uplot.data as number[][]
    if (xArr?.length) {
      const span = savedView.xMax - savedView.xMin
      isAtLatest.value = savedView.xMax >= xArr[xArr.length - 1] - span * 0.08
    }
  } else {
    setInitialView(uplot)
  }
  syncCanvasSize(w, h)
  await buildSubPanes()
  startLivePolling()
}

// ── Initial view: last DEFAULT_BARS_VISIBLE bars ──────────────────────────────
function setInitialView(u: uPlot) {
  const [x] = u.data as number[][]
  if (!x?.length) return
  const latest = x[x.length - 1]
  u.setScale('x', {
    min: Math.max(-0.5, latest - DEFAULT_BARS_VISIBLE + 0.5),
    max: latest + 0.5,
  })
  // Recompute the auto Y range against the initial X window so the first
  // user interaction does not snap to a different vertical scale.
  u.setData(u.data as uPlot.AlignedData)
  isAtLatest.value = true
}

function goToLatest() {
  if (!uplot) return
  const [x] = uplot.data as number[][]
  if (!x?.length) return
  const span   = uplot.scales.x.max! - uplot.scales.x.min!
  const latest = x[x.length - 1]
  uplot.setScale('x', { min: latest - span + 0.5, max: latest + 0.5 })
  isAtLatest.value = true
  renderVisualOverlays()
}

// ── setData fast path ─────────────────────────────────────────────────────────
function updateData() {
  if (!uplot) return
  const newData = buildData()
  const currentCount = buildSeries().length
  if (currentCount !== lastSeriesCount) { initChart(); return }

  // When bars are prepended (loadMoreBars), the existing visible bars shift
  // right by the number of new bars. Preserve the viewport by offsetting.
  const prevLen = (uplot.data[0] as number[]).length
  const newLen  = (newData[0] as number[]).length
  const newFirstBarTs = chartStore.bars[0]?.ts ?? null
  const prepended = firstRenderedBarTs && newFirstBarTs !== firstRenderedBarTs
    ? Math.max(0, newLen - prevLen)
    : 0

  const view = captureView()
  uplot.setData(newData)
  firstRenderedBarTs = newFirstBarTs
  lastSeriesCount = currentCount
  restoreView(view, prepended)
  renderVisualOverlays()
  updateSubPaneData()
  updateTooltip(uplot, uplot.cursor.idx)
}

// ── Interaction ────────────────────────────────────────────────────────────────
function setupInteraction(u: uPlot) {
  if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
  const wrapper = wrapperRef.value!
  let cachedRect: DOMRect | null = null

  const liveRect    = () => u.over.getBoundingClientRect()
  const getRect     = () => cachedRect ?? liveRect()
  const isOnYAxis   = (cx: number) => cx > getRect().right
  const isOnXAxis   = (cy: number) => cy > getRect().bottom

  const updateAtLatest = () => {
    const [x] = u.data as number[][]
    if (!x?.length) { isAtLatest.value = true; return }
    const span = u.scales.x.max! - u.scales.x.min!
    isAtLatest.value = u.scales.x.max! >= x[x.length - 1] - span * 0.08
  }

  const setXRange = (min: number, max: number) => {
    const [x] = u.data as number[][]
    if (!x?.length) return
    const span   = max - min
    const lBound = -0.5
    const rBound = x[x.length - 1] + 0.5
    if (min < lBound) { min = lBound; max = min + span }
    if (max > rBound) { max = rBound; min = max - span }
    u.setScale('x', { min, max })
    updateAtLatest()
    renderVisualOverlays()
    // Trigger older-page load when viewport approaches the left edge of loaded data
    if (min < PREFETCH_THRESHOLD && !chartStore.hasReachedStart && !chartStore.isLoadingMore) {
      chartStore.loadMoreBars()
    }
  }

  // Drag state
  let panActive     = false, panStartX = 0, panStartMin = 0, panStartMax = 0
  let priceActive   = false, priceStartY = 0, priceStartMin = 0, priceStartMax = 0
  let xAxisActive   = false, xAxisStartX = 0, xAxisStartMin = 0, xAxisStartMax = 0

  const onWheel = (e: WheelEvent) => {
    e.preventDefault(); e.stopPropagation()
    const xMin = u.scales.x.min!
    const xMax = u.scales.x.max!
    const isPinch = e.ctrlKey

    // Price axis — zoom Y
    if (isOnYAxis(e.clientX)) {
      const yMin = u.scales.y.min!, yMax = u.scales.y.max!
      const mid  = (yMin + yMax) / 2
      const half = (yMax - yMin) / 2
      const f    = e.deltaY > 0 ? 1.08 : 1 / 1.08
      autoY.value = false
      manualYMin  = isLogScale.value ? Math.max(mid - half * f, yMax * 1e-6) : mid - half * f
      manualYMax  = mid + half * f
      u.setScale('y', { min: manualYMin, max: manualYMax })
      renderVisualOverlays()
      return
    }

    const absX = Math.abs(e.deltaX)
    const absY = Math.abs(e.deltaY)

    // Horizontal trackpad swipe — pan
    if (!isPinch && absX > absY * WHEEL_AXIS_DOMINANCE) {
      const span    = xMax - xMin
      const pxWidth = getRect().width || 1
      const panDelta = e.deltaX * WHEEL_PAN_SENSITIVITY
      setXRange(
        xMin + (panDelta / pxWidth) * span,
        xMax + (panDelta / pxWidth) * span,
      )
      return
    }

    // Vertical scroll / pinch — zoom on cursor
    if (!isPinch && absY <= absX * WHEEL_AXIS_DOMINANCE) return
    const rect       = liveRect()
    const cursorPx   = Math.max(0, e.clientX - rect.left)
    const cursorIdx  = u.posToVal(cursorPx, 'x')
    const mag        = isPinch ? Math.abs(e.deltaY) * 0.01 : 1
    const f          = e.deltaY > 0
      ? 1 + (ZOOM_FACTOR - 1) * Math.min(mag, 3)
      : 1 / (1 + (ZOOM_FACTOR - 1) * Math.min(mag, 3))
    setXRange(
      cursorIdx - (cursorIdx - xMin) * f,
      cursorIdx + (xMax - cursorIdx) * f,
    )
  }

  const onMouseDown = (e: MouseEvent) => {
    if (e.button !== 0) return
    if (suppressNextMouseDown) {
      suppressNextMouseDown = false
      return
    }
    if (drawStore.activeToolType || drawStore.avwapDropActive) return
    cachedRect = liveRect()

    if (isOnYAxis(e.clientX)) {
      priceActive   = true
      priceStartY   = e.clientY
      priceStartMin = u.scales.y.min!
      priceStartMax = u.scales.y.max!
      wrapper.style.cursor = 'ns-resize'
      return
    }

    if (isOnXAxis(e.clientY)) {
      xAxisActive   = true
      xAxisStartX   = e.clientX
      xAxisStartMin = u.scales.x.min!
      xAxisStartMax = u.scales.x.max!
      wrapper.style.cursor = 'ew-resize'
      return
    }

    panActive   = true
    panStartX   = e.clientX
    panStartMin = u.scales.x.min!
    panStartMax = u.scales.x.max!
    wrapper.style.cursor = 'grabbing'
  }

  const onMouseMove = (e: MouseEvent) => {
    if (panActive) {
      const span    = panStartMax - panStartMin
      const pxWidth = getRect().width || 1
      const dt      = -((e.clientX - panStartX) / pxWidth) * span
      setXRange(panStartMin + dt, panStartMax + dt)
      return
    }
    if (priceActive) {
      const dy   = e.clientY - priceStartY
      const f    = Math.exp(dy * PRICE_DRAG_EXPO)
      const mid  = (priceStartMin + priceStartMax) / 2
      const half = (priceStartMax - priceStartMin) / 2 * f
      autoY.value = false
      manualYMin  = isLogScale.value ? Math.max(mid - half, mid * 1e-6) : mid - half
      manualYMax  = mid + half
      u.setScale('y', { min: manualYMin, max: manualYMax })
      renderVisualOverlays()
      return
    }
    if (xAxisActive) {
      // Drag right = compress time (fewer bars, zoom in)
      // Drag left  = expand time (more bars, zoom out) — same as TradingView
      const dx       = e.clientX - xAxisStartX
      const span     = xAxisStartMax - xAxisStartMin
      const pxWidth  = getRect().width || 1
      const mid      = (xAxisStartMin + xAxisStartMax) / 2
      // Exponential feel: each pixel stretches/shrinks symmetrically around midpoint
      const f        = Math.exp(-dx / pxWidth * 3)
      setXRange(mid - span / 2 * f, mid + span / 2 * f)
    }
  }

  const onMouseUp = () => {
    panActive = false; priceActive = false; xAxisActive = false
    cachedRect = null; wrapper.style.cursor = ''
  }

  const onHoverMove = (e: MouseEvent) => {
    if (panActive || priceActive || xAxisActive || drawStore.activeToolType || drawStore.avwapDropActive) return
    if (isOnYAxis(e.clientX))   { wrapper.style.cursor = 'ns-resize'; return }
    if (isOnXAxis(e.clientY))   { wrapper.style.cursor = 'ew-resize'; return }
    const rect = liveRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const hit = findHitDrawing(u, mx, my)
    if (hit && !hit.isLocked) {
      wrapper.style.cursor = hitDrawingHandle(u, hit, mx, my) == null ? 'move' : 'grab'
      return
    }
    wrapper.style.cursor = ''
  }

  const onDblClick = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (isOnYAxis(e.clientX)) {
      manualYMin  = null; manualYMax = null
      autoY.value = true
      refreshScalesPreservingX()
    }
  }

  // Also intercept uPlot's own dblclick on u.over with capture to be sure
  const onOverDblClick = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }
  u.over.addEventListener('dblclick', onOverDblClick, { capture: true })
  // Will be cleaned up below alongside other listeners
  const _overDblClickCleanup = () => u.over.removeEventListener('dblclick', onOverDblClick, true)

  const onContextMenu = (e: MouseEvent) => {
    if (isOnYAxis(e.clientX)) {
      e.preventDefault()
      ctxMenu.visible = true
      ctxMenu.y = e.clientY - (wrapperRef.value?.getBoundingClientRect().top ?? 0)
    } else {
      ctxMenu.visible = false
    }
  }

  const onKeyDown = (e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    const [ts] = u.data as number[][]
    if (!ts?.length) return
    const xMin   = u.scales.x.min!
    const xMax   = u.scales.x.max!
    const span   = xMax - xMin
    const mid    = (xMin + xMax) / 2
    const barDur = ts.length > 1 ? ts[1] - ts[0] : 86400
    switch (e.key) {
      case '=': case '+': e.preventDefault(); setXRange(mid - span/2/ZOOM_FACTOR, mid + span/2/ZOOM_FACTOR); break
      case '-':           e.preventDefault(); setXRange(mid - span/2*ZOOM_FACTOR, mid + span/2*ZOOM_FACTOR); break
      case 'ArrowLeft':   e.preventDefault(); setXRange(xMin - barDur*5, xMax - barDur*5); break
      case 'ArrowRight':  e.preventDefault(); setXRange(xMin + barDur*5, xMax + barDur*5); break
      case 'r': case 'R': if (e.altKey) { e.preventDefault(); goToLatest() } break
      case 'l': case 'L': toggleLogScale(); break
      case 'a': case 'A': toggleAutoY(); break
      case '?':           showShortcuts.value = !showShortcuts.value; break
      case 'Delete': case 'Backspace':
        if (drawStore.selectedId != null) {
          e.preventDefault()
          drawStore.deleteDrawing(drawStore.selectedId)
        }
        break
      case 'Escape':
        drawStore.selectDrawing(null)
        drawStore.setActiveTool(null)
        clearMeasurement()
        drawingPoints = []
        drawingPreviewPoint = null
        break
    }
  }

  wrapper.addEventListener('wheel',       onWheel,       { passive: false, capture: true })
  wrapper.addEventListener('mousedown',   onMouseDown)
  wrapper.addEventListener('mousemove',   onHoverMove)
  wrapper.addEventListener('dblclick',    onDblClick)
  wrapper.addEventListener('contextmenu', onContextMenu)
  window.addEventListener('mousemove',    onMouseMove)
  window.addEventListener('mouseup',      onMouseUp)
  window.addEventListener('keydown',      onKeyDown)

  interactionCleanup = () => {
    wrapper.removeEventListener('wheel',       onWheel,       true)
    wrapper.removeEventListener('mousedown',   onMouseDown)
    wrapper.removeEventListener('mousemove',   onHoverMove)
    wrapper.removeEventListener('dblclick',    onDblClick)
    wrapper.removeEventListener('contextmenu', onContextMenu)
    window.removeEventListener('mousemove',    onMouseMove)
    window.removeEventListener('mouseup',      onMouseUp)
    window.removeEventListener('keydown',      onKeyDown)
    _overDblClickCleanup()
    wrapper.style.cursor = ''
  }
}

// ── Sub-panes ─────────────────────────────────────────────────────────────────
async function buildSubPanes() {
  await nextTick()
  const x = chartStore.bars.map((_, i) => i)
  const ts = barTimestamps.value
  if (!x?.length) return
  const highs  = chartStore.bars.map(b => b.high)
  const lows   = chartStore.bars.map(b => b.low)
  const closes = chartStore.bars.map(b => b.close)
  const vols   = chartStore.bars.map(b => b.volume ?? 0)

  for (const pane of subPanes.value) {
    const el = subPaneRefs[pane.key]
    if (!el) continue
    const values = computeSubPaneSeries(pane.config, closes, highs, lows, vols, ts)
    const w = wrapperRef.value?.clientWidth || 900

    const subOpts: uPlot.Options = {
      width: w, height: 110,
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, sync: { key: 'chart' }, lock: false },
      scales: { x: { time: false }, y: { auto: true } },
      axes: [
        { scale: 'x', show: false },
        { scale: 'y', side: 1, stroke: '#888', size: 65,
          ticks: { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
          values: (_u, ticks) => ticks.map(t => t.toFixed(1)) },
      ],
      series: [
        {},
        { label: pane.label, stroke: pane.config.style.color, width: pane.config.style.lineWidth ?? 1.5, points: { show: false } },
      ],
      plugins: getSubPaneRefLines(pane.config.type).length
        ? [refLinesPlugin(getSubPaneRefLines(pane.config.type))] : [],
    }

    const sp = new uPlot(subOpts, [x, values] as uPlot.AlignedData, el)
    subPlotsMap[pane.key] = sp

    el.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault(); e.stopPropagation()
      wrapperRef.value?.dispatchEvent(new WheelEvent('wheel', {
        deltaX: e.deltaX, deltaY: e.deltaY,
        ctrlKey: e.ctrlKey, bubbles: true, cancelable: true,
      }))
    }, { passive: false, capture: true })
  }
}

function computeSubPaneSeries(ind: IndicatorConfig, closes: number[], highs: number[], lows: number[], vols: number[], ts: number[]): (number | null)[] {
  switch (ind.type) {
    case 'rsi': return computeRSI(closes, (ind.params.period as number) ?? 14)
    default:    return new Array(closes.length).fill(null)
  }
}

function updateSubPaneData() {
  const x = chartStore.bars.map((_, i) => i)
  const ts = barTimestamps.value
  if (!x?.length) return
  const highs  = chartStore.bars.map(b => b.high)
  const lows   = chartStore.bars.map(b => b.low)
  const closes = chartStore.bars.map(b => b.close)
  const vols   = chartStore.bars.map(b => b.volume ?? 0)
  for (const pane of subPanes.value) {
    const sp = subPlotsMap[pane.key]
    if (!sp) continue
    sp.setData([x, computeSubPaneSeries(pane.config, closes, highs, lows, vols, ts)] as uPlot.AlignedData)
  }
}

function getSubPaneRefLines(type: string): { value: number; color: string; label?: string }[] {
  if (type === 'rsi') return [
    { value: 70, color: '#ef535066', label: 'OB 70' },
    { value: 30, color: '#26a69a66', label: 'OS 30' },
    { value: 50, color: '#44444488' },
  ]
  return []
}

function refLinesPlugin(lines: { value: number; color: string; label?: string }[]): uPlot.Plugin {
  return { hooks: { draw: [(u) => {
    const ctx = u.ctx; ctx.save()
    const dpr = devicePixelRatio || 1
    for (const line of lines) {
      const y = u.valToPos(line.value, 'y', true)
      ctx.strokeStyle = line.color; ctx.lineWidth = dpr; ctx.setLineDash([4 * dpr, 3 * dpr])
      ctx.beginPath(); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke()
      if (line.label) {
        ctx.fillStyle = line.color; ctx.font = `${dpr * 10}px monospace`; ctx.setLineDash([])
        ctx.fillText(line.label, u.bbox.left + dpr * 4, y - dpr * 3)
      }
    }
    ctx.restore()
  }] } }
}

// ── Drawing canvas ────────────────────────────────────────────────────────────
function setupDrawingCanvas(u: uPlot) {
  if (!drawingCanvasRef.value) return
  drawingRenderer = new DrawingRenderer(drawingCanvasRef.value)
  drawingRenderer.attach(u)
  drawingRenderer.setTimeToXMapper((time: number) => u.valToPos(timeToBarIndex(time), 'x'))
  alignDrawingCanvas(u)
  renderVisualOverlays()
}

// Position the drawing canvas to exactly cover u.over (the inner plot area),
// so that u.valToPos() coordinates map 1:1 to canvas coordinates.
function alignDrawingCanvas(u: uPlot) {
  const canvas  = drawingCanvasRef.value
  const wrapper = wrapperRef.value
  if (!canvas || !wrapper || !u.over) return
  const overRect     = u.over.getBoundingClientRect()
  const wrapperRect  = wrapper.getBoundingClientRect()
  const x = overRect.left - wrapperRect.left
  const y = overRect.top  - wrapperRect.top
  const w = overRect.width
  const h = overRect.height
  canvas.style.left   = `${x}px`
  canvas.style.top    = `${y}px`
  canvas.style.width  = `${w}px`
  canvas.style.height = `${h}px`
  canvas.width  = Math.round(w)
  canvas.height = Math.round(h)
}

function syncCanvasSize(_w: number, _h: number) {
  // Sizing is handled by alignDrawingCanvas; this is kept for the resize call chain
  if (uplot) alignDrawingCanvas(uplot)
}

let drawingPoints: DrawingPoint[] = []
let drawingPreviewPoint: DrawingPoint | null = null

type DrawingDragMode = 'move' | 'point'
interface DrawingDragState {
  id: number
  mode: DrawingDragMode
  pointIndex: number | null
  startPoints: DrawingPoint[]
  startPointer: DrawingPoint
}
let drawingDrag: DrawingDragState | null = null

function pointerToDrawingPoint(u: uPlot, e: PointerEvent): DrawingPoint {
  const rect = u.over.getBoundingClientRect()
  const idx = u.posToVal(e.clientX - rect.left, 'x')
  const times = barTimestamps.value
  if (!times.length) return { time: 0, price: u.posToVal(e.clientY - rect.top, 'y') }
  const clampedIdx = Math.max(0, Math.min(times.length - 1, Math.round(idx)))
  return {
    time: times[clampedIdx] ?? 0,
    price: u.posToVal(e.clientY - rect.top, 'y'),
  }
}

function pointerToMeasurementPoint(u: uPlot, e: PointerEvent): MeasurementPoint {
  const rect = u.over.getBoundingClientRect()
  const idx = u.posToVal(e.clientX - rect.left, 'x')
  const times = barTimestamps.value
  if (!times.length) return { index: 0, time: 0, price: u.posToVal(e.clientY - rect.top, 'y') }
  const clampedIdx = Math.max(0, Math.min(times.length - 1, Math.round(idx)))
  return {
    index: clampedIdx,
    time: times[clampedIdx] ?? 0,
    price: u.posToVal(e.clientY - rect.top, 'y'),
  }
}

function clearMeasurement() {
  measurement.active = false
  measurement.frozen = false
  measurement.start = null
  measurement.end = null
  renderVisualOverlays()
}

function patchDrawingPoints(id: number, points: DrawingPoint[], persist = false) {
  const d = drawStore.drawings.find(x => x.id === id)
  if (!d) return
  const data = { ...(d.data as any), points }
  if (persist) drawStore.updateDrawing(id, { data } as any)
  else drawStore.localUpdateDrawing(id, { data } as any)
}

function hitDrawingHandle(u: uPlot, d: AnyDrawing, mx: number, my: number): number | null {
  const HIT = 9
  if (!d.points?.length) return null
  const toX = (time: number) => u.valToPos(timeToBarIndex(time), 'x')
  if ((d.type === 'circle' || d.type === 'half_circle') && d.points.length >= 2) {
    const p0 = d.points[0]!
    const p1 = d.points[1]!
    const x1 = toX(p0.time), y1 = u.valToPos(p0.price, 'y')
    const x2 = toX(p1.time), y2 = u.valToPos(p1.price, 'y')
    const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2
    const rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2
    const handles = d.type === 'half_circle'
      ? [
          [cx - rx, cy],
          [cx + rx, cy],
          [cx, y2 <= y1 ? cy - ry : cy + ry],
        ]
      : [
          [cx - rx, cy],
          [cx, cy - ry],
          [cx + rx, cy],
          [cx, cy + ry],
        ]
    for (let i = 0; i < handles.length; i++) {
      const [x, y] = handles[i]!
      if (Math.hypot(mx - x, my - y) <= HIT) return i
    }
    return null
  }
  const handleCount = d.points.length === 1 ? 1 : 2
  for (let i = 0; i < handleCount; i++) {
    const p = d.points[i]
    if (!p) continue
    const x = toX(p.time)
    const y = u.valToPos(p.price, 'y')
    if (Math.hypot(mx - x, my - y) <= HIT) return i
  }
  return null
}

function updateDrawingDrag(u: uPlot, e: PointerEvent, persist = false) {
  if (!drawingDrag) return
  const cur = pointerToDrawingPoint(u, e)
  let points: DrawingPoint[]
  const drawing = drawStore.renderableDrawings.find(d => d.id === drawingDrag?.id)
  if (
    drawingDrag.mode === 'point'
    && drawingDrag.pointIndex != null
    && (drawing?.type === 'circle' || drawing?.type === 'half_circle')
    && drawingDrag.startPoints.length >= 2
  ) {
    const [p0, p1] = drawingDrag.startPoints
    points = [{ ...p0! }, { ...p1! }]
    const left = Math.min(p0!.time, p1!.time)
    const right = Math.max(p0!.time, p1!.time)
    const top = Math.max(p0!.price, p1!.price)
    const bottom = Math.min(p0!.price, p1!.price)
    if (drawing?.type === 'half_circle') {
      if (drawingDrag.pointIndex === 0) points = [{ time: cur.time, price: top }, { time: right, price: bottom }]
      else if (drawingDrag.pointIndex === 1) points = [{ time: left, price: top }, { time: cur.time, price: bottom }]
      else points = [{ time: left, price: cur.price }, { time: right, price: bottom }]
    } else if (drawingDrag.pointIndex === 0) {
      points = [{ time: cur.time, price: top }, { time: right, price: bottom }]
    } else if (drawingDrag.pointIndex === 1) {
      points = [{ time: left, price: cur.price }, { time: right, price: bottom }]
    } else if (drawingDrag.pointIndex === 2) {
      points = [{ time: left, price: top }, { time: cur.time, price: bottom }]
    } else {
      points = [{ time: left, price: top }, { time: right, price: cur.price }]
    }
  } else if (drawingDrag.mode === 'point' && drawingDrag.pointIndex != null) {
    points = drawingDrag.startPoints.map((p, i) =>
      i === drawingDrag!.pointIndex ? cur : { ...p }
    )
  } else {
    const dt = cur.time - drawingDrag.startPointer.time
    const dp = cur.price - drawingDrag.startPointer.price
    points = drawingDrag.startPoints.map(p => ({ time: p.time + dt, price: p.price + dp }))
  }
  patchDrawingPoints(drawingDrag.id, points, persist)
  renderVisualOverlays()
}

function setupDrawingInteraction(u: uPlot) {
  // Use u.over so events fire regardless of drawing canvas pointer-events state
  const over = u.over; if (!over) return

  over.addEventListener('pointerdown', (e) => {
    const rect = over.getBoundingClientRect()
    const idx  = u.posToVal(e.clientX - rect.left, 'x')

    // ── AVWAP click-to-drop ──────────────────────────────────────────────
    if (drawStore.avwapDropActive && e.button === 0) {
      e.stopPropagation()
      const anchorTime = barIndexToTime(idx) ?? 0
      chartStore.addIndicator({
        type: 'avwap',
        params: { anchorTime },
        style: { color: '#80cbc4', lineWidth: 2 },
        pane: 'main',
      })
      drawStore.setAvwapDrop(false)
      return
    }

    if (!drawStore.activeToolType || e.button !== 0) return
    e.stopPropagation()  // prevent pan from also firing
    const pt = { time: barIndexToTime(idx) ?? 0, price: u.posToVal(e.clientY - rect.top, 'y') }
    if (drawStore.activeToolType === 'horizontal_line' || drawStore.activeToolType === 'vertical_line') {
      finishDrawing([pt], drawStore.activeToolType); return
    }
    drawingPoints.push(pt)
    drawingPreviewPoint = pt
    if (drawingPoints.length >= 2) {
      finishDrawing([...drawingPoints], drawStore.activeToolType)
      drawingPoints = []
      drawingPreviewPoint = null
    }
  }, { capture: true })

  over.addEventListener('pointermove', (e) => {
    if (!drawStore.activeToolType || drawingPoints.length === 0) return
    const rect = over.getBoundingClientRect()
    const idx = u.posToVal(e.clientX - rect.left, 'x')
    const cur = { time: barIndexToTime(idx) ?? 0, price: u.posToVal(e.clientY - rect.top, 'y') }
    drawingPreviewPoint = cur
    renderVisualOverlays()
  })

  over.addEventListener('contextmenu', (e) => {
    if (drawStore.activeToolType || drawStore.avwapDropActive) {
      e.preventDefault(); e.stopPropagation()
      drawingPoints = []
      drawingPreviewPoint = null
      drawStore.setActiveTool(null)
      drawStore.setAvwapDrop(false)
    }
  })
}

function setupHitDetection(u: uPlot) {
  // Attach to u.over (not the drawing canvas) so selection always works,
  // even when drawing canvas has pointer-events:none.
  // u.over is the transparent element uPlot uses for mouse tracking.
  const over = u.over
  if (!over) return

  over.addEventListener('pointerdown', (e) => {
    if (measurement.active && e.button === 0) {
      e.preventDefault()
      e.stopPropagation()
      measurement.active = false
      measurement.frozen = true
      measurement.end = pointerToMeasurementPoint(u, e)
      suppressNextMouseDown = true
      renderVisualOverlays()
      return
    }
    if (measurement.frozen && e.button === 0) {
      e.preventDefault()
      e.stopPropagation()
      suppressNextMouseDown = true
      clearMeasurement()
      return
    }
    if (e.shiftKey && e.button === 0 && !drawStore.activeToolType && !drawStore.avwapDropActive) {
      e.preventDefault()
      e.stopPropagation()
      const start = pointerToMeasurementPoint(u, e)
      measurement.active = true
      measurement.frozen = false
      measurement.start = start
      measurement.end = start
      drawStore.selectDrawing(null)
      alertsStore.selectAlert(null)
      chartStore.selectIndicator(null)
      suppressNextMouseDown = true
      renderVisualOverlays()
      return
    }
    if (drawStore.activeToolType) return  // drawing tool handles its own events
    drawCtxMenu.visible = false
    const rect   = over.getBoundingClientRect()
    const mx     = e.clientX - rect.left
    const my     = e.clientY - rect.top
    const hitDraw = findHitDrawing(u, mx, my)
    if (hitDraw) {
      e.preventDefault()
      e.stopPropagation()
      drawStore.selectDrawing(hitDraw.id ?? null)
      alertsStore.selectAlert(null)
      chartStore.selectIndicator(null)
      if (e.button === 0 && hitDraw.id != null && !hitDraw.isLocked) {
        suppressNextMouseDown = true
        const handleIndex = hitDrawingHandle(u, hitDraw, mx, my)
        drawingDrag = {
          id: hitDraw.id,
          mode: handleIndex == null ? 'move' : 'point',
          pointIndex: handleIndex,
          startPoints: hitDraw.points.map(p => ({ ...p })),
          startPointer: pointerToDrawingPoint(u, e),
        }
        try { over.setPointerCapture?.(e.pointerId) } catch { /* pointer already released */ }
        const onPointerMove = (moveEvent: PointerEvent) => {
          moveEvent.preventDefault()
          updateDrawingDrag(u, moveEvent)
        }
        const onPointerUp = (upEvent: PointerEvent) => {
          updateDrawingDrag(u, upEvent, true)
          drawingDrag = null
          try { over.releasePointerCapture?.(e.pointerId) } catch { /* pointer already released */ }
          window.removeEventListener('pointermove', onPointerMove)
          window.removeEventListener('pointerup', onPointerUp)
          window.removeEventListener('pointercancel', onPointerUp)
        }
        window.addEventListener('pointermove', onPointerMove)
        window.addEventListener('pointerup', onPointerUp)
        window.addEventListener('pointercancel', onPointerUp)
      }
    } else {
      drawStore.selectDrawing(null)
      const alertId = findHitAlert(u, my)
      if (alertId !== null) {
        e.stopPropagation()
        alertsStore.selectAlert(alertId)
        chartStore.selectIndicator(null)
      } else {
        alertsStore.selectAlert(null)
        const barIdx = Math.round(u.posToVal(mx, 'x'))
        const indIdx = findHitIndicator(u, my, barIdx)
        if (indIdx !== null) {
          e.stopPropagation()
          chartStore.selectIndicator(indIdx)
        } else {
          chartStore.selectIndicator(null)
        }
      }
    }
    renderVisualOverlays()
  }, { capture: true })  // capture: true to fire before uPlot's own handlers

  over.addEventListener('pointermove', (e) => {
    if (!measurement.active) return
    measurement.end = pointerToMeasurementPoint(u, e)
    renderVisualOverlays()
  })

  over.addEventListener('dblclick', (e) => {
    if (drawStore.activeToolType || drawStore.avwapDropActive) return
    const rect = over.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top

    const hitDraw = findHitDrawing(u, mx, my)
    if (hitDraw?.id != null) {
      e.stopPropagation()
      drawStore.requestEditDrawing(hitDraw.id)
      return
    }

    const alertId = findHitAlert(u, my)
    if (alertId !== null) {
      e.stopPropagation()
      alertsStore.requestEditAlert(alertId)
      return
    }

    const barIdx = Math.round(u.posToVal(mx, 'x'))
    const indIdx = findHitIndicator(u, my, barIdx)
    if (indIdx !== null) {
      e.stopPropagation()
      chartStore.requestEditIndicator(indIdx)
    }
  }, { capture: true })

  over.addEventListener('contextmenu', (e) => {
    const rect = over.getBoundingClientRect()
    const hit  = findHitDrawing(u, e.clientX - rect.left, e.clientY - rect.top)
    if (hit) {
      e.preventDefault()
      e.stopPropagation()
      drawStore.selectDrawing(hit.id ?? null)
      drawCtxMenu.visible = true
      drawCtxMenu.x = e.clientX - (wrapperRef.value?.getBoundingClientRect().left ?? 0)
      drawCtxMenu.y = e.clientY - (wrapperRef.value?.getBoundingClientRect().top  ?? 0)
    }
  })
}

function findHitAlert(u: uPlot, my: number): number | null {
  const HIT = 8
  for (const alert of alertsStore.alerts) {
    if (alert.status !== 'active' && alert.status !== 'triggered') continue
    const py = u.valToPos(Number(alert.threshold_price), 'y')
    if (Math.abs(my - py) < HIT) return alert.id
  }
  return null
}

function findHitIndicator(u: uPlot, my: number, barIdx: number): number | null {
  const HIT = 8
  // Main-pane, non-volume indicators in the same order they appear in uplot.data (series 6+)
  const mainInds = [...chartStore.activeIndicators]
    .reverse()
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')
  for (let mi = 0; mi < mainInds.length; mi++) {
    const val = (u.data as number[][])[6 + mi]?.[barIdx]
    if (val == null || isNaN(val)) continue
    const py = u.valToPos(val, 'y')
    if (Math.abs(my - py) < HIT) {
      return chartStore.indicators.indexOf(mainInds[mi])
    }
  }
  return null
}

function findHitDrawing(u: uPlot, mx: number, my: number): AnyDrawing | null {
  const HIT = 8
  for (const d of [...drawStore.renderableDrawings].reverse()) {
    if (!d.points?.length) continue
    const toX = (time: number) => u.valToPos(timeToBarIndex(time), 'x')
    if (d.type === 'horizontal_line') {
      if (Math.abs(my - u.valToPos(d.points[0].price, 'y')) < HIT) return d
      continue
    }
    if (d.type === 'vertical_line') {
      if (Math.abs(mx - toX(d.points[0].time)) < HIT) return d
      continue
    }
    if (d.points.length < 2) continue
    const [p0, p1] = [d.points[0]!, d.points[1]!]
    const [x1, y1] = [toX(p0.time), u.valToPos(p0.price, 'y')]
    const [x2, y2] = [toX(p1.time), u.valToPos(p1.price, 'y')]

    if (d.type === 'rectangle') {
      const minX = Math.min(x1, x2), maxX = Math.max(x1, x2)
      const minY = Math.min(y1, y2), maxY = Math.max(y1, y2)
      const onLeft   = Math.abs(mx - minX) < HIT && my >= minY - HIT && my <= maxY + HIT
      const onRight  = Math.abs(mx - maxX) < HIT && my >= minY - HIT && my <= maxY + HIT
      const onTop    = Math.abs(my - minY) < HIT && mx >= minX - HIT && mx <= maxX + HIT
      const onBottom = Math.abs(my - maxY) < HIT && mx >= minX - HIT && mx <= maxX + HIT
      const inside = mx >= minX && mx <= maxX && my >= minY && my <= maxY
      if (onLeft || onRight || onTop || onBottom || inside) return d
      continue
    }
    if (d.type === 'circle' || d.type === 'half_circle') {
      const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2
      const rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2
      if (rx < 1 || ry < 1) continue
      const nx = (mx - cx) / rx, ny = (my - cy) / ry
      const dist = Math.sqrt(nx * nx + ny * ny)
      const tol  = HIT / Math.min(rx, ry)
      if (d.type === 'half_circle') {
        const topHalf = y2 <= y1
        const onVisibleHalf = topHalf ? my <= cy + HIT : my >= cy - HIT
        const nearArc = Math.abs(dist - 1) < tol && onVisibleHalf
        const nearDiameter = Math.abs(my - cy) < HIT && mx >= cx - rx - HIT && mx <= cx + rx + HIT
        if (nearArc || nearDiameter) return d
      } else if (Math.abs(dist - 1) < tol || dist < 1) return d
      continue
    }
    if (d.type === 'text_box') {
      const text = (d as any).text ?? d.label ?? ''
      const w = Math.max(40, String(text).length * 8)
      const h = 18
      if (mx >= x1 - HIT && mx <= x1 + w + HIT && my >= y1 - h - HIT && my <= y1 + HIT) {
        return d
      }
      continue
    }
    if (d.type === 'fibonacci_retracement' || d.type === 'fibonacci_extension') {
      const levels = (d as any).levels ?? [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
      const priceRange = p1.price - p0.price
      const left = Math.min(x1, x2) - HIT, right = Math.max(x1, x2) + HIT
      if (mx < left || mx > right) continue
      for (const lvl of levels) {
        const price = p0.price + priceRange * lvl
        if (Math.abs(my - u.valToPos(price, 'y')) < HIT) return d
      }
      continue
    }
    // trendline, ray, arrow, and any other line-type drawings
    if (distToSeg(mx, my, x1, y1, x2, y2) < HIT) return d
  }
  return null
}

function distToSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay, lenSq = dx*dx + dy*dy
  if (lenSq === 0) return Math.hypot(px-ax, py-ay)
  const t = Math.max(0, Math.min(1, ((px-ax)*dx + (py-ay)*dy) / lenSq))
  return Math.hypot(px-(ax+t*dx), py-(ay+t*dy))
}

async function finishDrawing(points: DrawingPoint[], type: DrawingType) {
  const colors: Record<string, string> = {
    trendline: '#64b5f6', horizontal_line: '#ffb74d',
    fibonacci_retracement: '#81c784', rectangle: '#ba68c8',
    text_box: '#ffffff', circle: '#f06292', arrow: '#a5d6a7',
    half_circle: '#f06292',
  }
  await drawStore.saveDrawing({ type, points, style: { color: colors[type] ?? '#fff', lineWidth: 1.5 } } as any)
  renderVisualOverlays()
}

// ── Resize ────────────────────────────────────────────────────────────────────
function handleResize() {
  if (!uplot || !wrapperRef.value) return
  const w = wrapperRef.value.clientWidth
  const h = Math.max(80, (rootRef.value?.clientHeight ?? 600) - subPanes.value.length * 120 - 20)
  uplot.setSize({ width: w, height: h }); syncCanvasSize(w, h)
  drawingRenderer?.resize(); renderVisualOverlays()
  for (const sp of Object.values(subPlotsMap)) sp.setSize({ width: w, height: 110 })
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────
function destroyAll() {
  stopLivePolling()
  if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
  uplot?.destroy(); uplot = null
  firstRenderedBarTs = null
  for (const sp of Object.values(subPlotsMap)) sp.destroy()
  subPlotsMap = {}
}

onMounted(async () => {
  userSettingsStore.loadSettings().catch(console.error)
  await nextTick(); await initChart()
  resizeObserver = new ResizeObserver(handleResize)
  if (rootRef.value) resizeObserver.observe(rootRef.value)
})

onUnmounted(() => { destroyAll(); resizeObserver?.disconnect() })

watch(() => chartStore.bars, () => { if (uplot) updateData(); else initChart() }, { deep: false })
watch(() => chartStore.activeIndicators, async () => { await nextTick(); initChart() }, { deep: true })
watch(() => drawStore.renderableDrawings, () => {
  renderVisualOverlays()
}, { deep: true })

// Reset in-progress drawing points whenever the active tool changes
watch(() => drawStore.activeToolType, () => {
  drawingPoints = []
  drawingPreviewPoint = null
})
watch(() => drawStore.avwapDropActive, () => {
  drawingPoints = []
  drawingPreviewPoint = null
})

// Trigger a uPlot redraw when indicator/alert selection changes (so highlight plugin runs)
watch(() => chartStore.selectedIndicatorIndex, () => {
  redrawVisuals()
})
watch(() => alertsStore.selectedAlertId, () => {
  redrawVisuals()
})
watch(() => alertsStore.alerts, () => {
  redrawVisuals()
}, { deep: true })

// Redraw when any Y-projection toggle changes
watch(() => chartStore.indicators.map(i => i.showYProjection), () => { redrawVisuals() })
watch(() => alertsStore.alerts.map(a => `${a.id}:${a.show_projection}`).join('|'), () => { redrawVisuals() })
watch(() => drawStore.drawingProjections,  () => { redrawVisuals() })
watch(showCurrentPriceProjection, () => { redrawVisuals() })
watch(showHighLowProjection,      () => { redrawVisuals() })

/** Move the cursor to the bar closest to the given ISO timestamp (cross-panel sync). */
function jumpToTs(isoTs: string) {
  if (!uplot) return
  const bars = chartStore.bars
  if (!bars.length) return
  // Find last bar whose timestamp is <= target
  let idx = bars.findIndex(b => b.ts > isoTs)
  if (idx === -1) idx = bars.length - 1
  else if (idx > 0) idx -= 1
  const left = uplot.valToPos(idx, 'x')
  syncGuard = true
  uplot.setCursor({ left, top: uplot.cursor.top ?? 0 })
  syncGuard = false
  // Update tooltip with the correct idx directly — setCursor may clamp idx
  // if the bar is scrolled off-screen, which would show the wrong OHLCV data.
  updateTooltip(uplot, idx)
}

defineExpose({ jumpToTs })
</script>

<style scoped>
.chart-root {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%; height: 100%;
  background: #080808;
  overflow: hidden;
  overscroll-behavior: none;
  user-select: none;
  -webkit-user-select: none;
}

.uplot-wrapper {
  position: relative;
  flex: 1;
  overflow: hidden;
  touch-action: none;
  overscroll-behavior: none;
}

.drawing-canvas {
  position: absolute; top: 0; left: 0;
  z-index: 10; pointer-events: none;
}
.drawing-canvas.cursor-crosshair { pointer-events: none; cursor: crosshair; }

.cursor-crosshair-wrapper { cursor: crosshair; }

/* TradingView-style OHLCV overlay — top-left, small, semi-transparent */
.ohlcv-info {
  position: absolute;
  top: 6px; left: 8px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  color: #666;
  pointer-events: none;
  white-space: nowrap;
}
.tt-date { color: #444; margin-right: 2px; }
.tt-item b  { color: #bbb; }
.tt-item b.up { color: #26a69a; }
.tt-item b.dn { color: #ef5350; }
.tt-vol   { color: #555; }
.tt-chg   { font-weight: 600; }
.tt-chg.up { color: #26a69a; }
.tt-chg.dn { color: #ef5350; }

/* Log scale badge */
.scale-badge {
  position: absolute;
  top: 6px; right: 72px;
  z-index: 20;
  font-family: monospace; font-size: 10px;
  color: #555; background: rgba(20,20,20,0.8);
  border: 1px solid #2a2a2a; border-radius: 3px;
  padding: 1px 5px; pointer-events: none;
}

/* Context menu */
.ctx-menu {
  position: absolute;
  right: 0; z-index: 50;
  background: #1a1a1a;
  border: 1px solid #333; border-radius: 4px;
  overflow: hidden; min-width: 160px;
}
.ctx-menu button {
  display: block; width: 100%;
  background: none; border: none;
  color: #ccc; font-size: 12px; font-family: monospace;
  padding: 8px 14px; text-align: left; cursor: pointer;
}
.ctx-menu button:hover { background: #2a2a2a; color: #fff; }

.sub-pane {
  position: relative; height: 120px;
  background: #080808; border-top: 1px solid #1a1a1a;
  flex-shrink: 0; touch-action: none; overscroll-behavior: none;
}
.sub-pane-label {
  position: absolute; top: 4px; left: 8px;
  font-size: 10px; color: #555; z-index: 5;
  pointer-events: none; font-family: monospace;
}

/* Y axis A/L buttons — TradingView style, pinned to bottom of Y axis */
.yaxis-btns {
  position: absolute;
  bottom: 5px;
  right: 0;
  width: 65px; /* matches axis size */
  display: flex;
  justify-content: center;
  gap: 4px;
  z-index: 25;
  pointer-events: all;
}

.yaxis-btn {
  width: 22px; height: 18px;
  background: rgba(20,20,20,0.85);
  border: 1px solid #2a2a2a;
  border-radius: 3px;
  color: #555;
  font-family: monospace;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  line-height: 1;
  transition: color 0.1s, border-color 0.1s, background 0.1s;
}
.yaxis-btn:hover { color: #aaa; border-color: #555; }
.yaxis-btn.active {
  color: #64b5f6;
  border-color: #64b5f6;
  background: rgba(100,181,246,0.08);
}

/* Go to latest */
.go-to-latest {
  position: absolute; bottom: 26px; right: 80px; z-index: 30;
  background: rgba(20,20,20,0.92); border: 1px solid #333; border-radius: 4px;
  color: #64b5f6; font-family: monospace; font-size: 11px;
  padding: 4px 10px; cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.go-to-latest:hover { background: rgba(40,40,40,0.96); border-color: #64b5f6; }

/* Help button */
.help-btn {
  position: absolute; bottom: 26px; left: 12px; z-index: 30;
  width: 22px; height: 22px;
  background: rgba(20,20,20,0.7); border: 1px solid #2a2a2a; border-radius: 50%;
  color: #555; font-size: 12px; cursor: pointer; line-height: 1;
  transition: color 0.15s, border-color 0.15s;
}
.help-btn:hover { color: #aaa; border-color: #555; }

.settings-btn {
  position: absolute; bottom: 26px; left: 42px; z-index: 30;
  width: 22px; height: 22px;
  background: rgba(20,20,20,0.7); border: 1px solid #2a2a2a; border-radius: 4px;
  color: #555; font-size: 12px; cursor: pointer; line-height: 1;
  transition: color 0.15s, border-color 0.15s;
}
.settings-btn:hover { color: #aaa; border-color: #555; }

.editor-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.55);
}
.editor-box {
  width: min(360px, calc(100vw - 32px));
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  box-shadow: 0 12px 30px rgba(0,0,0,0.55);
  color: #aaa;
  font-family: monospace;
}
.ed-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #222;
  color: #ddd;
  font-size: 12px;
  font-weight: 700;
}
.ed-close {
  background: none; border: none; color: #666; cursor: pointer;
  font-size: 12px; padding: 2px 4px;
}
.ed-close:hover { color: #ddd; }
.ed-body { padding: 12px; }
.ed-section-title {
  color: #777;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 10px;
}
.ed-checkbox-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 0;
  font-size: 12px;
  color: #bbb;
}
.ed-checkbox { accent-color: #64b5f6; }

/* Shortcuts overlay */
.shortcuts-overlay {
  position: absolute; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.6);
}
.shortcuts-box {
  background: #141414; border: 1px solid #2a2a2a; border-radius: 6px;
  padding: 20px 24px; min-width: 240px;
  font-family: monospace; font-size: 12px; color: #888;
}
.sc-title { font-size: 13px; color: #bbb; font-weight: 600; margin-bottom: 14px; }
.sc-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #777; }
.sc-row b { color: #aaa; min-width: 120px; }
.sc-mouse { color: #555; font-size: 11px; }
kbd {
  background: #222; border: 1px solid #333; border-radius: 3px;
  padding: 1px 6px; font-size: 11px; color: #aaa;
}
.sc-close {
  display: block; width: 100%; margin-top: 16px;
  background: none; border: 1px solid #2a2a2a; border-radius: 4px;
  color: #555; font-family: monospace; font-size: 11px;
  padding: 6px; cursor: pointer;
}
.sc-close:hover { color: #aaa; border-color: #444; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
