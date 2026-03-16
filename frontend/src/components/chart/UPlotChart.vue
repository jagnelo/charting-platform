<template>
  <div class="chart-root" ref="rootRef">

    <!-- Main price chart -->
    <div class="uplot-wrapper" ref="wrapperRef">
      <canvas ref="drawingCanvasRef" class="drawing-canvas"
              :class="{ 'cursor-crosshair': !!drawStore.activeToolType }" />
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

      <!-- Log scale indicator -->
      <div class="scale-badge" v-if="isLogScale">LOG</div>

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
      ↓ Latest
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
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed, reactive } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useChartStore }    from '@/stores/chart'
import { useDrawingsStore }  from '@/stores/drawings'
import { useAlertsStore }    from '@/stores/alerts'
import { candlestickPlugin } from '@/lib/uplot/plugins/candlestick'
import { volumePlugin }      from '@/lib/uplot/plugins/volume'
import { alertLinesPlugin }  from '@/lib/uplot/plugins/alert-lines'
import { DrawingRenderer }   from '@/lib/drawings/renderer'
import { computeSMA }  from '@/lib/uplot/indicators/sma'
import { computeEMA }  from '@/lib/uplot/indicators/ema'
import { computeRSI }  from '@/lib/uplot/indicators/rsi'
import { computeVWAP } from '@/lib/uplot/indicators/vwap'
import { api }         from '@/lib/api'
import type { DrawingPoint }   from '@/lib/drawings/types'
import type { DrawingType, IndicatorConfig, Timeframe } from '@/types'
import type { AnyDrawing }     from '@/lib/drawings/types'

// ── Constants ─────────────────────────────────────────────────────────────────
const DEFAULT_BARS_VISIBLE = 150
const ZOOM_FACTOR          = 1.08
const PRICE_DRAG_EXPO      = 0.004
const LIVE_POLL_MULTIPLIER = 1.0   // poll every 1× bar duration

// ── Stores & DOM refs ─────────────────────────────────────────────────────────
const chartStore  = useChartStore()
const drawStore   = useDrawingsStore()
const alertsStore = useAlertsStore()

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
  const ts = d[0]?.[idx]
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
const isAtLatest    = ref(true)
const showShortcuts = ref(false)
const isLogScale    = ref(false)
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
      const raw = await api.get<any[]>(`/ohlcv/${chartStore.symbol}/${chartStore.timeframe}`)
      const mapped = raw.map((b: any) => ({
        ...b,
        open: Number(b.open), high: Number(b.high),
        low:  Number(b.low),  close: Number(b.close),
        volume: b.volume != null ? Number(b.volume) : undefined,
      }))
      // Compare latest timestamp numerically (both end up as ISO strings from API)
      const existingTs = chartStore.bars[chartStore.bars.length - 1]?.ts ?? ''
      const newTs      = mapped[mapped.length - 1]?.ts ?? ''
      if (newTs !== existingTs) {
        const wasAtLatest = isAtLatest.value
        chartStore.bars = mapped
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
  chartStore.indicators
    .filter(i => i.pane === 'separate')
    .map(i => ({
      key:    `${i.type}_${JSON.stringify(i.params)}`,
      label:  `${i.type.toUpperCase()}(${Object.values(i.params).join(',')})`,
      config: i,
    }))
)

const hasVolumeIndicator = computed(() =>
  chartStore.indicators.some(i => i.type === 'volume' && i.pane !== 'separate')
)

// ── Y-scale range ─────────────────────────────────────────────────────────────
function yRangeFn(u: uPlot): [number, number] {
  if (manualYMin !== null && manualYMax !== null) return [manualYMin, manualYMax]
  const [ts, , highs, lows] = u.data as number[][]
  if (!ts?.length) return [0, 1]
  const xMin = u.scales.x?.min ?? -Infinity
  const xMax = u.scales.x?.max ?? Infinity
  let lo = Infinity, hi = -Infinity
  for (let i = 0; i < ts.length; i++) {
    if (ts[i] >= xMin && ts[i] <= xMax) {
      if (highs[i] != null && highs[i] > hi) hi = highs[i]
      if (lows[i]  != null && lows[i]  < lo) lo = lows[i]
    }
  }
  if (lo === Infinity) return [0, 1]
  const pad = (hi - lo) * 0.08
  const yMin = lo - pad
  const yMax = hi + pad
  // Log scale requires strictly positive values
  if (isLogScale.value) return [Math.max(yMin, yMax * 0.0001), yMax]
  return [yMin, yMax]
}

// ── Log scale toggle ──────────────────────────────────────────────────────────
function toggleLogScale() {
  ctxMenu.visible = false
  isLogScale.value = !isLogScale.value
  manualYMin = null; manualYMax = null
  initChart()
}

function resetPriceScale() {
  ctxMenu.visible = false
  manualYMin = null; manualYMax = null
  if (uplot) uplot.setData(uplot.data as uPlot.AlignedData)
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
    default:       return new Array(closes.length).fill(null)
  }
}

// ── Build data ────────────────────────────────────────────────────────────────
function buildData(): uPlot.AlignedData {
  const d = chartStore.uplotData as number[][]
  const [ts, opens, highs, lows, closes, vols] = d
  const extra = chartStore.indicators
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')
    .map(i => computeIndicatorSeries(closes, highs, lows, vols, ts, i))
  return [ts, opens, highs, lows, closes, vols, ...extra] as uPlot.AlignedData
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
  for (const ind of chartStore.indicators.filter(i => i.pane !== 'separate' && i.type !== 'volume')) {
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

// ── Init chart ────────────────────────────────────────────────────────────────
async function initChart() {
  if (!chartRef.value || !wrapperRef.value) return
  destroyAll()
  manualYMin = null; manualYMax = null

  const data = chartStore.uplotData as number[][]
  if (!data[0]?.length) return

  const w = wrapperRef.value.clientWidth || 900
  const h = Math.max(380, (rootRef.value?.clientHeight ?? 600) - subPanes.value.length * 120 - 20)
  const series = buildSeries()
  lastSeriesCount = series.length

  const plugins: uPlot.Plugin[] = [
    candlestickPlugin({ upColor: '#26a69a', downColor: '#ef5350' }),
    alertLinesPlugin(() =>
      alertsStore.alerts
        .filter(a => a.status === 'active' || a.status === 'triggered')
        .map(a => ({
          price:     Number(a.threshold_price),
          label:     a.notes ?? undefined,
          triggered: a.status === 'triggered',
        }))
    ),
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
      x: { time: true },
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
        scale: 'x', stroke: '#555',
        ticks: { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
      },
      {
        scale:  'y', side: 1, size: 65, stroke: '#888',
        ticks:  { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
        values: (_u, ticks) => ticks.map(t => t >= 1000 ? t.toFixed(0) : t.toFixed(2)),
      },
    ],

    series,
    plugins,

    hooks: {
      setCursor: [(u) => {
        updateTooltip(u, u.cursor.idx)
        // Snap crosshair to nearest bar centre — guard against re-entrancy
        if (snapGuard) return
        const idx = u.cursor.idx
        if (idx != null && u.cursor.left != null) {
          const [ts] = u.data as number[][]
          if (ts?.length > 1) {
            const snapX = u.valToPos(ts[idx], 'x')
            const barPx = Math.abs(u.valToPos(ts[1], 'x') - u.valToPos(ts[0], 'x'))
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
        setInitialView(u)
        updateTooltip(u, null)
      }],
    },
  }

  uplot = new uPlot(opts, buildData(), chartRef.value)
  syncCanvasSize(w, h)
  await buildSubPanes()
  startLivePolling()
}

// ── Initial view: last DEFAULT_BARS_VISIBLE bars ──────────────────────────────
function setInitialView(u: uPlot) {
  const [ts] = u.data as number[][]
  if (!ts?.length) return
  const barDur = ts.length > 1 ? ts[1] - ts[0] : 86400
  const latest = ts[ts.length - 1]
  u.setScale('x', { min: latest - DEFAULT_BARS_VISIBLE * barDur, max: latest + barDur * 5 })
  isAtLatest.value = true
}

function goToLatest() {
  if (!uplot) return
  const [ts] = uplot.data as number[][]
  if (!ts?.length) return
  const barDur = ts.length > 1 ? ts[1] - ts[0] : 86400
  const span   = uplot.scales.x.max! - uplot.scales.x.min!
  const latest = ts[ts.length - 1]
  uplot.setScale('x', { min: latest - span + barDur * 5, max: latest + barDur * 5 })
  isAtLatest.value = true
}

// ── setData fast path ─────────────────────────────────────────────────────────
function updateData() {
  if (!uplot) return
  const newData = buildData()
  const currentCount = buildSeries().length
  if (currentCount !== lastSeriesCount) { initChart(); return }

  const xMin = uplot.scales.x.min
  const xMax = uplot.scales.x.max
  uplot.setData(newData)
  lastSeriesCount = currentCount
  if (xMin != null && xMax != null) uplot.setScale('x', { min: xMin, max: xMax })
  drawingRenderer?.renderAll(drawStore.renderableDrawings)
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
    const [ts] = u.data as number[][]
    if (!ts?.length) { isAtLatest.value = true; return }
    const span = u.scales.x.max! - u.scales.x.min!
    isAtLatest.value = u.scales.x.max! >= ts[ts.length - 1] - span * 0.08
  }

  const setXRange = (min: number, max: number) => {
    const [ts] = u.data as number[][]
    if (!ts?.length) return
    const span   = max - min
    const lBound = ts[0]              - span * 0.5
    const rBound = ts[ts.length - 1] + span * 0.15
    if (min < lBound) { min = lBound; max = min + span }
    if (max > rBound) { max = rBound; min = max - span }
    u.setScale('x', { min, max })
    updateAtLatest()
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
      manualYMin = mid - half * f
      manualYMax = mid + half * f
      u.setScale('y', { min: manualYMin, max: manualYMax })
      return
    }

    // Horizontal trackpad swipe — pan
    if (!isPinch && Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      const span    = xMax - xMin
      const pxWidth = getRect().width || 1
      setXRange(xMin + (e.deltaX / pxWidth) * span, xMax + (e.deltaX / pxWidth) * span)
      return
    }

    // Vertical scroll / pinch — zoom on cursor
    const rect       = liveRect()
    const cursorPx   = Math.max(0, e.clientX - rect.left)
    const cursorTime = u.posToVal(cursorPx, 'x')
    const mag        = isPinch ? Math.abs(e.deltaY) * 0.01 : 1
    const f          = e.deltaY > 0
      ? 1 + (ZOOM_FACTOR - 1) * Math.min(mag, 3)
      : 1 / (1 + (ZOOM_FACTOR - 1) * Math.min(mag, 3))
    setXRange(
      cursorTime - (cursorTime - xMin) * f,
      cursorTime + (xMax - cursorTime) * f,
    )
  }

  const onMouseDown = (e: MouseEvent) => {
    if (e.button !== 0) return
    if (drawStore.activeToolType) return
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
      manualYMin = mid - half
      manualYMax = mid + half
      u.setScale('y', { min: manualYMin, max: manualYMax })
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
    if (panActive || priceActive || xAxisActive || drawStore.activeToolType) return
    if (isOnYAxis(e.clientX))   { wrapper.style.cursor = 'ns-resize'; return }
    if (isOnXAxis(e.clientY))   { wrapper.style.cursor = 'ew-resize'; return }
    wrapper.style.cursor = ''
  }

  const onDblClick = (e: MouseEvent) => {
    // Prevent uPlot's own dblclick-to-reset on the plot area
    e.preventDefault()
    e.stopPropagation()
    if (isOnYAxis(e.clientX)) {
      // Reset manual Y lock only — TradingView behaviour
      manualYMin = null; manualYMax = null
      u.setData(u.data as uPlot.AlignedData)
    }
    // Dblclick on plot area: no action (TradingView doesn't reset X on dblclick)
  }

  // Also intercept uPlot's own dblclick on u.over with capture to be sure
  const onOverDblClick = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }
  u.over.addEventListener('dblclick', onOverDblClick, { capture: true })
  const origCleanup = interactionCleanup
  interactionCleanup = () => {
    origCleanup?.()
    u.over.removeEventListener('dblclick', onOverDblClick, true)
  }

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
        drawingPoints = []
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
    wrapper.style.cursor = ''
  }
}

// ── Sub-panes ─────────────────────────────────────────────────────────────────
async function buildSubPanes() {
  await nextTick()
  const data = chartStore.uplotData as number[][]
  if (!data[0]?.length) return
  const [ts, , highs, lows, closes, vols] = data

  for (const pane of subPanes.value) {
    const el = subPaneRefs[pane.key]
    if (!el) continue
    const values = computeSubPaneSeries(pane.config, closes, highs, lows, vols, ts)
    const w = wrapperRef.value?.clientWidth || 900

    const subOpts: uPlot.Options = {
      width: w, height: 110,
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, sync: { key: 'chart' }, lock: false },
      scales: { x: { time: true }, y: { auto: true } },
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

    const sp = new uPlot(subOpts, [ts, values] as uPlot.AlignedData, el)
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
  const data = chartStore.uplotData as number[][]
  if (!data[0]?.length) return
  const [ts, , highs, lows, closes, vols] = data
  for (const pane of subPanes.value) {
    const sp = subPlotsMap[pane.key]
    if (!sp) continue
    sp.setData([ts, computeSubPaneSeries(pane.config, closes, highs, lows, vols, ts)] as uPlot.AlignedData)
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
    for (const line of lines) {
      const y = u.valToPos(line.value, 'y')
      ctx.strokeStyle = line.color; ctx.lineWidth = 1; ctx.setLineDash([4, 3])
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(u.width, y); ctx.stroke()
      if (line.label) {
        ctx.fillStyle = line.color; ctx.font = '10px monospace'; ctx.setLineDash([])
        ctx.fillText(line.label, 4, y - 3)
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
  alignDrawingCanvas(u)
  drawingRenderer.renderAll(drawStore.renderableDrawings)
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

function setupDrawingInteraction(u: uPlot) {
  const canvas = drawingCanvasRef.value; if (!canvas) return
  canvas.addEventListener('pointerdown', (e) => {
    if (!drawStore.activeToolType) return; e.preventDefault()
    const rect = canvas.getBoundingClientRect()
    const pt = { time: u.posToVal(e.clientX - rect.left, 'x'), price: u.posToVal(e.clientY - rect.top, 'y') }
    if (drawStore.activeToolType === 'horizontal_line' || drawStore.activeToolType === 'vertical_line') {
      finishDrawing([pt], drawStore.activeToolType); return
    }
    drawingPoints.push(pt)
    if (drawingPoints.length >= 2) {
      finishDrawing([...drawingPoints], drawStore.activeToolType); drawingPoints = []
    }
  })
  canvas.addEventListener('pointermove', (e) => {
    if (!drawStore.activeToolType || drawingPoints.length === 0) return
    const rect = canvas.getBoundingClientRect()
    const cur = { time: u.posToVal(e.clientX - rect.left, 'x'), price: u.posToVal(e.clientY - rect.top, 'y') }
    drawingRenderer?.renderAll([
      ...drawStore.renderableDrawings,
      { type: drawStore.activeToolType as DrawingType, points: [drawingPoints[0], cur],
        style: { color: '#ffffff88', lineWidth: 1 }, isVisible: true } as any,
    ])
  })
  canvas.addEventListener('contextmenu', (e) => {
    e.preventDefault(); drawingPoints = []; drawStore.setActiveTool(null)
  })
}

function setupHitDetection(u: uPlot) {
  // Attach to u.over (not the drawing canvas) so selection always works,
  // even when drawing canvas has pointer-events:none.
  // u.over is the transparent element uPlot uses for mouse tracking.
  const over = u.over
  if (!over) return

  over.addEventListener('pointerdown', (e) => {
    if (drawStore.activeToolType) return  // drawing tool handles its own events
    drawCtxMenu.visible = false
    const rect = over.getBoundingClientRect()
    const hit  = findHitDrawing(u, e.clientX - rect.left, e.clientY - rect.top)
    if (hit) {
      // Consume the event so pan/interaction doesn't also fire
      e.stopPropagation()
    }
    drawStore.selectDrawing(hit ? hit.id ?? null : null)
    drawingRenderer?.renderAll(drawStore.renderableDrawings)
  }, { capture: true })  // capture: true to fire before uPlot's own handlers

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

function findHitDrawing(u: uPlot, mx: number, my: number): AnyDrawing | null {
  const HIT = 8
  for (const d of [...drawStore.renderableDrawings].reverse()) {
    if (!d.points?.length) continue
    if (d.type === 'horizontal_line' && Math.abs(my - u.valToPos(d.points[0].price, 'y')) < HIT) return d
    if (d.type === 'vertical_line'   && Math.abs(mx - u.valToPos(d.points[0].time, 'x'))  < HIT) return d
    if (d.points.length >= 2) {
      const [p0, p1] = [d.points[0]!, d.points[1]!]
      const [x1, y1] = [u.valToPos(p0.time, 'x'), u.valToPos(p0.price, 'y')]
      const [x2, y2] = [u.valToPos(p1.time, 'x'), u.valToPos(p1.price, 'y')]
      if (distToSeg(mx, my, x1, y1, x2, y2) < HIT) return d
    }
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
  }
  await drawStore.saveDrawing({ type, points, style: { color: colors[type] ?? '#fff', lineWidth: 1.5 } } as any)
  drawingRenderer?.renderAll(drawStore.renderableDrawings)
}

// ── Resize ────────────────────────────────────────────────────────────────────
function handleResize() {
  if (!uplot || !wrapperRef.value) return
  const w = wrapperRef.value.clientWidth
  const h = Math.max(380, (rootRef.value?.clientHeight ?? 600) - subPanes.value.length * 120 - 20)
  uplot.setSize({ width: w, height: h }); syncCanvasSize(w, h)
  drawingRenderer?.resize(); drawingRenderer?.renderAll(drawStore.renderableDrawings)
  for (const sp of Object.values(subPlotsMap)) sp.setSize({ width: w, height: 110 })
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────
function destroyAll() {
  stopLivePolling()
  if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
  uplot?.destroy(); uplot = null
  for (const sp of Object.values(subPlotsMap)) sp.destroy()
  subPlotsMap = {}
}

onMounted(async () => {
  await nextTick(); await initChart()
  resizeObserver = new ResizeObserver(handleResize)
  if (rootRef.value) resizeObserver.observe(rootRef.value)
})

onUnmounted(() => { destroyAll(); resizeObserver?.disconnect() })

watch(() => chartStore.bars, () => { if (uplot) updateData(); else initChart() }, { deep: false })
watch(() => chartStore.indicators, async () => { await nextTick(); initChart() }, { deep: true })
watch(() => drawStore.renderableDrawings, () => {
  drawingRenderer?.renderAll(drawStore.renderableDrawings)
}, { deep: true })
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
.drawing-canvas.cursor-crosshair { pointer-events: all; cursor: crosshair; }

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

/* Go to latest */
.go-to-latest {
  position: absolute; bottom: 20px; right: 80px; z-index: 30;
  background: rgba(20,20,20,0.92); border: 1px solid #333; border-radius: 4px;
  color: #64b5f6; font-family: monospace; font-size: 11px;
  padding: 4px 10px; cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.go-to-latest:hover { background: rgba(40,40,40,0.96); border-color: #64b5f6; }

/* Help button */
.help-btn {
  position: absolute; bottom: 20px; left: 12px; z-index: 30;
  width: 22px; height: 22px;
  background: rgba(20,20,20,0.7); border: 1px solid #2a2a2a; border-radius: 50%;
  color: #555; font-size: 12px; cursor: pointer; line-height: 1;
  transition: color 0.15s, border-color 0.15s;
}
.help-btn:hover { color: #aaa; border-color: #555; }

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