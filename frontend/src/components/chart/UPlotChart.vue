<template>
  <div class="chart-root" ref="rootRef">

    <!-- Main price chart -->
    <div class="uplot-wrapper" ref="wrapperRef"
          :class="{ 'cursor-crosshair-wrapper': overlayInteractionsEnabled && (!!drawStore.activeToolType || drawStore.avwapDropActive) }">
      <canvas ref="drawingCanvasRef" class="drawing-canvas"
              :class="{ 'cursor-crosshair': overlayInteractionsEnabled && (!!drawStore.activeToolType || drawStore.avwapDropActive) }" />
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


      <div
        v-if="eventPopover"
        class="event-popover"
        :style="{ left: eventPopover.x + 'px', top: eventPopover.y + 'px' }"
      >
        <div class="event-popover-head">
          <strong>{{ eventPopover.event.symbol }} {{ eventLabel(eventPopover.event) }}</strong>
          <button @click="eventPopover = null">x</button>
        </div>
        <div class="event-popover-date">{{ formatEventTime(eventPopover.event) }}</div>
        <div class="event-popover-grid">
          <template v-for="row in eventRows(eventPopover.event)" :key="row.label">
            <span>{{ row.label }}</span>
            <b>{{ row.value }}</b>
          </template>
        </div>
      </div>
    </div>

    <!-- Drawing context menu (right-click on any drawing, main or sub-pane) -->
    <div class="ctx-menu" v-if="overlayInteractionsEnabled && drawCtxMenu.visible"
         :style="{ top: drawCtxMenu.y + 'px', left: drawCtxMenu.x + 'px' }"
         @mouseleave="drawCtxMenu.visible = false">
      <button @click="deleteSelectedDrawing">🗑 Delete Drawing</button>
      <button @click="drawCtxMenu.visible = false; drawStore.selectDrawing(null)">Deselect</button>
    </div>

    <!-- Sub-panes: one per separate-pane indicator -->
    <template v-for="pane in subPanes" :key="pane.key">
      <ResizeHandle
        direction="vertical"
        inverted
        :value="subPaneHeights[pane.key] ?? SUB_PANE_DEFAULT_H"
        :min="SUB_PANE_MIN_H"
        :max="SUB_PANE_MAX_H"
        @change="v => { subPaneHeights[pane.key] = v; handleResize() }"
      />
      <div
        class="sub-pane"
        :class="{ 'cursor-crosshair-wrapper': overlayInteractionsEnabled && !!drawStore.activeToolType }"
        :ref="el => subPaneRefs[pane.key] = el as HTMLElement"
        :style="{ height: `${subPaneHeights[pane.key] ?? SUB_PANE_DEFAULT_H}px` }"
      >
        <div class="sub-pane-label">{{ pane.label }}</div>
        <canvas :ref="el => subPaneCanvasRefs[pane.key] = el as HTMLCanvasElement" class="drawing-canvas" />
      </div>
    </template>

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
    <button v-if="controlsEnabled" class="help-btn" @click="showShortcuts = !showShortcuts" title="Keyboard shortcuts">?</button>

    <!-- Chart settings button (cog) -->
    <button v-if="controlsEnabled" class="settings-btn" @click="showChartSettings = !showChartSettings" title="Chart settings">⚙</button>
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
            <div class="ed-section-title">Chart Type</div>
            <label class="ed-field-row">
              <span>Primary rendering</span>
              <select :value="effectiveChartType" class="ed-select" @change="setChartType(($event.target as HTMLSelectElement).value)">
                <option v-for="bt in CHART_BAR_TYPES" :key="bt.value" :value="bt.value">{{ bt.label }}</option>
              </select>
            </label>
            <div class="ed-section-title">Y-Axis Projections</div>
            <label class="ed-checkbox-row">
              <input type="checkbox" :checked="showCurrentPriceProjection" class="ed-checkbox" @change="setBooleanChartSetting('current_price_projection', ($event.target as HTMLInputElement).checked)" />
              Show current price on Y axis
            </label>
            <label class="ed-checkbox-row">
              <input type="checkbox" :checked="showHighLowProjection" class="ed-checkbox" @change="setBooleanChartSetting('high_low_projection', ($event.target as HTMLInputElement).checked)" />
              Show visible high / low on Y axis
            </label>
            <label class="ed-checkbox-row">
              <input type="checkbox" :checked="showApproxVolumeProfile" class="ed-checkbox" @change="setBooleanChartSetting('volume_profile', ($event.target as HTMLInputElement).checked)" />
              Show approximate volume profile
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
import { api } from '@/lib/api'
import { usePanelStore }        from '@/stores/chart'
import { useLayoutStore }       from '@/stores/layout'
import { useDrawingsStore }     from '@/stores/drawings'
import { useAlertsStore }       from '@/stores/alerts'
import { useUserSettingsStore } from '@/stores/userSettings'
import { useOptionsExposureStore } from '@/stores/optionsExposure'
import { useWorkspaceStore } from '@/stores/workspace'
import { isEditorTarget } from '@/lib/workstation/keyboard'
import { candlestickPlugin }       from '@/lib/uplot/plugins/candlestick'
import { ohlcBarsPlugin }          from '@/lib/uplot/plugins/ohlc-bars'
import { baselinePlugin }          from '@/lib/uplot/plugins/baseline'
import { approxVolumeProfilePlugin } from '@/lib/uplot/plugins/approx-volume-profile'
import { volumePlugin }            from '@/lib/uplot/plugins/volume'
import { alertLinesPlugin }        from '@/lib/uplot/plugins/alert-lines'
import { alertEventsPlugin }       from '@/lib/uplot/plugins/alert-events'
import type { AlertEventMarker }   from '@/lib/uplot/plugins/alert-events'
import { optionsLevelsPlugin }    from '@/lib/uplot/plugins/options-levels'
import { yAxisProjectionsPlugin }  from '@/lib/uplot/plugins/y-axis-projections'
import type { ProjectionItem }     from '@/lib/uplot/plugins/y-axis-projections'
import ResizeHandle          from '@/components/common/ResizeHandle.vue'
import { DrawingRenderer }   from '@/lib/drawings/renderer'
import { estimatedBarStep as _estimatedBarStep, drawingTimeToBarIndex as _drawingTimeToBarIndex, barIndexToDrawingTime as _barIndexToDrawingTime } from '@/lib/drawings/coords'
import type { MeasurementOverlay } from '@/lib/drawings/renderer'
import { computeSMA }  from '@/lib/uplot/indicators/sma'
import { computeEMA }  from '@/lib/uplot/indicators/ema'
import { computeRSI }  from '@/lib/uplot/indicators/rsi'
import { computeVWAP, computeAVWAP } from '@/lib/uplot/indicators/vwap'
import { computeMACD } from '@/lib/uplot/indicators/macd'
import {
  computeWMA, computeHMA, computeDEMA, computeTEMA,
  computeATR, computeOBV, computeCCI, computeWilliamsR,
  computeMFI, computeROC, computeMomentum, computeStdDev,
  computeCMF, computePSAR, computeTRIX, computePPO, computeVolumeRatio,
  computeBB, computeKeltner, computeDonchian,
  computeADX, computeStoch, computeAroon,
  computeIchimoku, computePivotPoints,
} from '@/lib/uplot/indicators/all'
import {
  getParamNumber,
  getParamString,
  indicatorDisplayName,
  normalizeIndicatorParams,
} from '@/lib/indicators/catalog'
import {
  mergeChartIndicatorsWithRadar,
  radarIndicatorSignature,
} from '@/lib/radar/visuals'
import type { DrawingPoint }   from '@/lib/drawings/types'
import type { ChartComparisonSeries, ChartDrawing, ChartPythonSeries, DrawingType, IndicatorConfig, PriceAlert, Timeframe, ChartBarType } from '@/types'
import { CHART_BAR_TYPES } from '@/types'
import type { AnyDrawing }     from '@/lib/drawings/types'

const props = withDefaults(defineProps<{
  chartType?: ChartBarType
  overlayDrawings?: ChartDrawing[]
  overlayIndicators?: IndicatorConfig[]
  overlayAlerts?: PriceAlert[]
  showIndicators?: boolean
  showOverlays?: boolean
  enableOverlayInteractions?: boolean
  enableKeyboard?: boolean
  showControls?: boolean
  chartSettings?: Record<string, unknown>
  comparisonSeries?: ChartComparisonSeries[]
  pythonSeries?: ChartPythonSeries[]
  workspaceLinkGroup?: import('@/stores/workspace').LinkGroup
  linkedTimestamp?: string | null
}>(), {
  showIndicators: true,
  showOverlays: true,
  enableOverlayInteractions: true,
  enableKeyboard: true,
  showControls: true,
  workspaceLinkGroup: 'blue',
  linkedTimestamp: null,
})
const emit = defineEmits<{ configuration: [changes: Record<string, unknown>] }>()

// ── Constants ─────────────────────────────────────────────────────────────────
const DEFAULT_BARS_VISIBLE  = 150
const ZOOM_FACTOR           = 1.08
const PRICE_DRAG_EXPO       = 0.004
const WHEEL_AXIS_DOMINANCE  = 1.25
const WHEEL_PAN_SENSITIVITY = 0.65
const LIVE_POLL_MULTIPLIER  = 1.0   // poll every 1× bar duration
const LATEST_RIGHT_MARGIN_MIN = 36
const LATEST_RIGHT_MARGIN_MAX = 180
const LATEST_RIGHT_MARGIN_RATIO = 0.3
const RIGHT_OVERSCROLL_RATIO = 0.85

const PREFETCH_THRESHOLD = 80  // bar indices from left edge before prefetch fires

// ── Stores & DOM refs ─────────────────────────────────────────────────────────
const panelId            = inject<string>('panelId', 'main')
const chartStore         = usePanelStore(panelId)
const layoutStore        = useLayoutStore()
const drawStore          = useDrawingsStore()
const alertsStore        = useAlertsStore()
const userSettingsStore  = useUserSettingsStore()
const optionsExposureStore = useOptionsExposureStore()
const workspaceStore = useWorkspaceStore()
const effectiveChartType = computed(() => props.chartType ?? userSettingsStore.chartType)
function configuredBoolean(key: string, fallback: boolean) {
  const value = props.chartSettings?.[key]
  return typeof value === 'boolean' ? value : fallback
}
function setChartType(value: string) {
  if (!CHART_BAR_TYPES.some(type => type.value === value)) return
  if (props.chartType) emit('configuration', { bar_type: value })
  else userSettingsStore.chartType = value as ChartBarType
}
function setBooleanChartSetting(key: 'current_price_projection' | 'high_low_projection' | 'volume_profile', value: boolean) {
  if (props.chartSettings) {
    emit('configuration', { [key]: value })
    return
  }
  if (key === 'current_price_projection') userSettingsStore.showCurrentPriceProjection = value
  if (key === 'high_low_projection') userSettingsStore.showHighLowProjection = value
  if (key === 'volume_profile') userSettingsStore.showApproxVolumeProfile = value
}
const overlaysEnabled    = computed(() => props.showOverlays)
const overlayInteractionsEnabled = computed(() => overlaysEnabled.value && props.enableOverlayInteractions)
const keyboardEnabled    = computed(() => props.enableKeyboard)
const controlsEnabled    = computed(() => props.showControls)
const baseVisibleIndicators = computed(() =>
  props.showIndicators ? chartStore.activeIndicators : []
)
const visibleActiveIndicators = computed(() =>
  mergeChartIndicatorsWithRadar(baseVisibleIndicators.value, props.overlayIndicators ?? [])
)
const visibleComparisonSeries = computed(() =>
  (props.comparisonSeries ?? []).filter(series => series.values.some(v => v != null && Number.isFinite(v)))
)
const visiblePythonSeries = computed(() =>
  (props.pythonSeries ?? []).filter(series => series.timestamps.length === series.values.length && series.values.some(v => v != null && Number.isFinite(v)))
)
const visibleAlerts = computed(() => props.overlayAlerts ?? alertsStore.alerts)
function chartDrawingToRenderable(d: ChartDrawing): AnyDrawing {
  return {
    id: d.id,
    type: d.drawing_type as DrawingType,
    points: (d.data as any).points ?? [],
    style: d.style,
    label: d.label,
    isSelected: d.id === drawStore.selectedId,
    isLocked: d.is_locked,
    isVisible: d.is_visible,
    sourceTag: (d as any).sourceTag ?? (d as any).__radarSourceTag ?? null,
    radarLinked: (d as any).radarLinked ?? !!(d as any).__radarSource,
    radarHighlightOpacity: (d as any).radarHighlightOpacity ?? (d as any).__radarHighlightOpacity,
    radarRoles: (d as any).radarRoles ?? (d as any).__radarRoles,
    indicatorKey: d.indicator_key ?? null,
    ...(d.data as any),
  }
}
const renderableDrawings = computed<AnyDrawing[]>(() => {
  if (!props.overlayDrawings) return drawStore.renderableDrawings
  return [...props.overlayDrawings].reverse()
    .filter(d => d.is_visible && (d.indicator_key ?? null) === null)
    .map(chartDrawingToRenderable)
})

const rootRef          = ref<HTMLDivElement | null>(null)
const wrapperRef       = ref<HTMLDivElement | null>(null)
const chartRef         = ref<HTMLDivElement | null>(null)
const drawingCanvasRef = ref<HTMLCanvasElement | null>(null)
const subPaneRefs: Record<string, HTMLElement | null> = reactive({})
const subPaneCanvasRefs: Record<string, HTMLCanvasElement | null> = reactive({})
const SUB_PANE_DEFAULT_H = 120
const SUB_PANE_MIN_H     = 60
const SUB_PANE_MAX_H     = 400
const subPaneHeights     = reactive<Record<string, number>>({})

// ── uPlot instances ───────────────────────────────────────────────────────────
let uplot: uPlot | null = null
let subPlotsMap: Record<string, uPlot> = {}
let drawingRenderer: DrawingRenderer | null = null
let subDrawingRenderers: Record<string, DrawingRenderer> = {}
let activeDrawingPaneKey: string | null = null  // null = main chart; indicator type = sub-pane
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

interface InstrumentEvent {
  id: number
  date: string
  event_time: string
  fetched_at: string
  event_type: string
  symbol: string
  title: string
  value?: number | null
  actual?: number | null
  eps_estimate?: number | null
  eps_actual?: number | null
  eps_surprise?: number | null
  eps_surprise_pct?: number | null
  dividend_amount?: number | null
  split_ratio?: number | null
  time_hint: string
  source: string
  is_estimate: boolean
}

const instrumentEvents = ref<InstrumentEvent[]>([])
const alertFiringMarkers = ref<AlertEventMarker[]>([])
const EVENT_POPOVER_WIDTH = 238
const EVENT_POPOVER_HEIGHT = 178
const eventPopover = ref<{ event: InstrumentEvent; x: number; y: number } | null>(null)
let eventMarkers: Array<{ event: InstrumentEvent; x: number; y: number; r: number }> = []
let eventLoadSeq = 0
let eventRangeKey = ''

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
const isLogScale        = ref(configuredBoolean('log_scale', false))
const autoY             = ref(true)   // true = auto-fit Y to visible bars; false = manual lock
const showCurrentPriceProjection = computed(() => configuredBoolean('current_price_projection', userSettingsStore.showCurrentPriceProjection))
const showHighLowProjection = computed(() => configuredBoolean('high_low_projection', userSettingsStore.showHighLowProjection))
const showApproxVolumeProfile = computed(() => configuredBoolean('volume_profile', userSettingsStore.showApproxVolumeProfile))

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

function estimatedBarStepSeconds(): number {
  return _estimatedBarStep(barTimestamps.value)
}

function drawingTimeToBarIndex(ts: number): number {
  return _drawingTimeToBarIndex(ts, barTimestamps.value)
}

function barIndexToDrawingTime(idx: number): number {
  return _barIndexToDrawingTime(idx, barTimestamps.value)
}

function eventTimeToChartIndex(ts: number): number {
  const times = barTimestamps.value
  if (!times.length) return 0
  const first = times[0]
  const last = times[times.length - 1]
  if (ts <= last) return timeToBarIndex(ts)
  return times.length - 1 + (ts - last) / estimatedBarStepSeconds()
}

// ── Y-axis dynamic width ───────────────────────────────────────────────────────
let _yMeasureCtx: CanvasRenderingContext2D | null = null
function getYMeasureCtx(): CanvasRenderingContext2D {
  if (!_yMeasureCtx) {
    const canvas = document.createElement('canvas')
    _yMeasureCtx = canvas.getContext('2d')!
    _yMeasureCtx.font = '10px monospace'
  }
  return _yMeasureCtx
}

function yAxisSize(_u: uPlot, values: string[] | null | undefined): number {
  if (!values?.length) return 52
  const ctx = getYMeasureCtx()
  let maxW = 0
  for (const v of values) {
    if (v) {
      const w = ctx.measureText(v).width
      if (w > maxW) maxW = w
    }
  }
  return Math.max(52, Math.ceil(maxW) + 14)
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

function eventLabel(event: InstrumentEvent): string {
  if (event.event_type.startsWith('earnings')) return 'Earnings'
  if (event.event_type === 'dividend' || event.event_type === 'ex_dividend') return 'Dividend'
  if (event.event_type === 'split') return 'Split'
  return event.event_type.replace(/_/g, ' ')
}

function eventGlyph(event: InstrumentEvent): string {
  if (event.event_type.startsWith('earnings')) return 'E'
  if (event.event_type === 'dividend' || event.event_type === 'ex_dividend') return 'D'
  if (event.event_type === 'split') return 'S'
  return '•'
}

function eventColor(event: InstrumentEvent): string {
  if (event.event_type.startsWith('earnings')) return '#ffb74d'
  if (event.event_type === 'dividend' || event.event_type === 'ex_dividend') return '#26a69a'
  if (event.event_type === 'split') return '#64b5f6'
  return '#aaa'
}

function formatEventTime(event: InstrumentEvent): string {
  const hint = event.time_hint && event.time_hint !== 'unknown'
    ? ` · ${event.time_hint.replace(/_/g, ' ')}`
    : ''
  return `${new Date(event.event_time).toLocaleString()}${hint}`
}

function eventRows(event: InstrumentEvent) {
  const rows: Array<{ label: string; value: string }> = []
  const pct = (v?: number | null) => v == null ? '' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
  const num = (v?: number | null) => v == null ? '' : v.toFixed(4)
  if (event.eps_estimate != null) rows.push({ label: 'EPS estimate', value: num(event.eps_estimate) })
  if (event.eps_actual != null) rows.push({ label: 'EPS actual', value: num(event.eps_actual) })
  if (event.eps_surprise != null) rows.push({ label: 'EPS surprise', value: num(event.eps_surprise) })
  if (event.eps_surprise_pct != null) rows.push({ label: 'Surprise %', value: pct(event.eps_surprise_pct) })
  if (event.dividend_amount != null) rows.push({ label: 'Dividend', value: num(event.dividend_amount) })
  if (event.split_ratio != null) rows.push({ label: 'Split ratio', value: num(event.split_ratio) })
  rows.push({ label: 'Source', value: event.source })
  rows.push({ label: 'Fetched', value: new Date(event.fetched_at).toLocaleString() })
  return rows
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
  if (!overlayInteractionsEnabled.value) return
  if (drawStore.selectedId != null) drawStore.deleteDrawing(drawStore.selectedId)
}

// Y scale — null = auto-fit; set = manual lock
let manualYMin: number | null = null
let manualYMax: number | null = null
let interactionCleanup: (() => void) | null = null
let snapGuard = false
let syncGuard = false
let lastPublishedWorkspaceCursor: string | null = null
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

function latestRightMargin(span: number): number {
  return Math.max(
    LATEST_RIGHT_MARGIN_MIN,
    Math.min(LATEST_RIGHT_MARGIN_MAX, span * LATEST_RIGHT_MARGIN_RATIO),
  )
}

function rightOverscroll(span: number): number {
  return Math.max(latestRightMargin(span), span * RIGHT_OVERSCROLL_RATIO)
}

function latestXRange(latest: number, span: number): { min: number; max: number } {
  const margin = latestRightMargin(span)
  return { min: latest - span + margin, max: latest + margin }
}

function redrawVisuals() {
  renderVisualOverlays()
  const redraw = (uplot as any)?.redraw
  if (typeof redraw === 'function') redraw.call(uplot)
}

async function loadAlertFiringEvents() {
  const instrument = chartStore.instrument
  if (!instrument) { alertFiringMarkers.value = []; return }
  try {
    const events = await alertsStore.loadInstrumentHistory(instrument.id)
    alertFiringMarkers.value = events.map(e => ({
      ts:        new Date(e.fired_at).getTime() / 1000,
      alertType: e.alert_type,
      label:     e.instrument_symbol ?? undefined,
    }))
    redrawVisuals()
  } catch {
    alertFiringMarkers.value = []
  }
}

async function loadInstrumentEvents() {
  const symbol = chartStore.symbol
  const bars = chartStore.bars
  const instrument = chartStore.instrument
  if (!symbol || !bars.length || !instrument || instrument.symbol !== symbol) {
    instrumentEvents.value = []
    eventRangeKey = ''
    return
  }
  const start = bars[0].ts
  const lastTs = new Date(bars[bars.length - 1].ts).getTime()
  const end = Number.isFinite(lastTs)
    ? new Date(lastTs + 370 * 86_400_000).toISOString()
    : bars[bars.length - 1].ts
  const key = `${symbol}:${start}:${end}`
  if (key === eventRangeKey) return
  eventRangeKey = key
  const seq = ++eventLoadSeq
  try {
    const loaded = await api.get<InstrumentEvent[]>(
      `/calendar/instruments/${encodeURIComponent(symbol)}/calendar`,
      { start, end },
    )
    if (seq === eventLoadSeq && symbol === chartStore.symbol) {
      instrumentEvents.value = loaded
      redrawVisuals()
    }
  } catch {
    if (seq === eventLoadSeq && symbol === chartStore.symbol) instrumentEvents.value = []
  }
}

function renderEventMarkers(u: uPlot) {
  eventMarkers = []
  if (!instrumentEvents.value.length) return
  const { ctx, bbox } = u
  const dpr = devicePixelRatio || 1
  const baseY = bbox.top + bbox.height - dpr * 11

  ctx.save()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = `bold ${Math.round(9 * dpr)}px monospace`

  for (const event of instrumentEvents.value) {
    const ts = new Date(event.event_time).getTime() / 1000
    if (!Number.isFinite(ts)) continue
    const idx = eventTimeToChartIndex(ts)
    const x = u.valToPos(idx, 'x', true)
    if (x < bbox.left || x > bbox.left + bbox.width) continue
    const r = dpr * 8
    const color = eventColor(event)
    ctx.beginPath()
    ctx.fillStyle = '#0b0b0b'
    ctx.strokeStyle = color
    ctx.lineWidth = dpr * 1.5
    ctx.arc(x, baseY, r, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = color
    ctx.fillText(eventGlyph(event), x, baseY + dpr * 0.5)
    eventMarkers.push({ event, x: x / dpr, y: baseY / dpr, r: r / dpr + 3 })
  }

  ctx.restore()
}

function eventAt(mx: number, my: number): InstrumentEvent | null {
  for (const marker of eventMarkers) {
    if (Math.hypot(mx - marker.x, my - marker.y) <= marker.r) return marker.event
  }
  return null
}

function positionEventPopover(clientX: number, clientY: number): { x: number; y: number } {
  const wrapper = wrapperRef.value
  if (!wrapper) return { x: 8, y: 8 }
  const rect = wrapper.getBoundingClientRect()
  const margin = 8
  const clickX = clientX - rect.left
  const clickY = clientY - rect.top
  const maxX = Math.max(margin, wrapper.clientWidth - EVENT_POPOVER_WIDTH - margin)
  const maxY = Math.max(margin, wrapper.clientHeight - EVENT_POPOVER_HEIGHT - margin)
  const x = Math.max(margin, Math.min(clickX + 12, maxX))
  const preferredAbove = clickY - EVENT_POPOVER_HEIGHT - 12
  const preferredBelow = clickY + 12
  const y = preferredAbove >= margin
    ? preferredAbove
    : Math.min(Math.max(margin, preferredBelow), maxY)
  return { x, y }
}

function renderVisualOverlays() {
  drawingRenderer?.renderAll(drawingOverlayList(null), measurementOverlay())
  for (const pane of subPanes.value) {
    const renderer = subDrawingRenderers[pane.key]
    if (renderer) renderer.renderAll(drawingOverlayList(pane.config.type))
  }
}

function drawingOverlayList(indicatorKey: string | null): AnyDrawing[] {
  if (!overlaysEnabled.value) return []
  const base: AnyDrawing[] = props.overlayDrawings
    ? [...props.overlayDrawings].reverse()
        .filter(d => d.is_visible && (d.indicator_key ?? null) === indicatorKey)
        .map(chartDrawingToRenderable)
    : drawStore.renderableDrawingsFor(indicatorKey)
  if (!overlayInteractionsEnabled.value) return base
  // Show live preview only in the pane currently being drawn on
  if (activeDrawingPaneKey !== indicatorKey) return base
  if (!drawStore.activeToolType || drawingPoints.length === 0 || !drawingPreviewPoint) return base
  const previewPoints = drawStore.activeToolType === 'freehand'
    ? [...drawingPoints]
    : [drawingPoints[0], drawingPreviewPoint]
  return [
    ...base,
    {
      type: drawStore.activeToolType as DrawingType,
      points: previewPoints,
      style: { color: '#ffffff88', lineWidth: 0.75 },
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
      const mapped = await chartStore.fetchLatestBars()
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
            const latest = tArr[tArr.length - 1]
            const span   = uplot.scales.x.max! - uplot.scales.x.min!
            uplot.setScale('x', latestXRange(latest, span))
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
  visibleActiveIndicators.value
    .filter(i => i.pane === 'separate')
    .map(i => ({
      key:    `${i.type}_${JSON.stringify(i.params)}`,
      label:  indicatorDisplayName(i),
      config: i,
    }))
)

const hasVolumeIndicator = computed(() =>
  visibleActiveIndicators.value.some(i => i.type === 'volume' && i.pane !== 'separate')
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
  for (const series of visibleComparisonSeries.value) {
    for (let i = 0; i < series.values.length; i++) {
      if (i < xMin || i > xMax) continue
      const v = series.values[i]
      if (v == null || !Number.isFinite(v)) continue
      if (v > hi) hi = v
      if (v < lo) lo = v
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
  if (props.chartSettings) emit('configuration', { log_scale: isLogScale.value })
  initChart()
}

function resetPriceScale() {
  ctxMenu.visible = false
  manualYMin  = null; manualYMax = null
  autoY.value = true
  refreshScalesPreservingX()
}

// ── Indicator output key helpers ──────────────────────────────────────────────

/** Returns the canonical output keys for a given indicator type. Single-output → ['_']. */
function getIndicatorOutputKeys(type: string): string[] {
  switch (type) {
    case 'bb': case 'keltner': case 'donchian':
      return ['upper', 'mid', 'lower']
    case 'ichimoku':
      return ['tenkanLine', 'kijunLine', 'senkouALine', 'senkouBLine', 'chikouLine']
    case 'pivot_points':
      return ['pp', 'r1', 'r2', 'r3', 's1', 's2', 's3']
    default:
      return ['_']
  }
}

/** Derives a per-output colour based on the indicator's base colour. */
function getOutputColor(ind: IndicatorConfig, key: string): string {
  const base = ind.style.color
  switch (key) {
    case '_':         return base
    case 'upper':     return base
    case 'mid':       return base + '99'
    case 'lower':     return base
    case 'tenkanLine':  return '#ef5350'
    case 'kijunLine':   return '#2196f3'
    case 'senkouALine': return '#26a69a88'
    case 'senkouBLine': return '#ef535088'
    case 'chikouLine':  return '#ab47bc'
    case 'pp': return base
    case 'r1': return '#ef535088'
    case 'r2': return '#ef5350bb'
    case 'r3': return '#ef5350'
    case 's1': return '#26a69a88'
    case 's2': return '#26a69abb'
    case 's3': return '#26a69a'
    default:   return base
  }
}

/** Builds a human-readable series label for a given indicator + output key. */
function getSeriesLabel(ind: IndicatorConfig, key: string): string {
  const base = indicatorDisplayName(ind)
  if (key === '_') return base
  const suffix: Record<string, string> = {
    upper: 'U', mid: 'M', lower: 'L',
    tenkanLine: 'Tenkan', kijunLine: 'Kijun',
    senkouALine: 'Span A', senkouBLine: 'Span B', chikouLine: 'Chikou',
    pp: 'PP', r1: 'R1', r2: 'R2', r3: 'R3', s1: 'S1', s2: 'S2', s3: 'S3',
  }
  return `${base} ${suffix[key] ?? key}`
}

/** One entry in the flattened (expanded) list of main-pane series. */
interface MainSeriesMeta {
  ind: IndicatorConfig
  outputKey: string
  color: string
  label: string
}

/**
 * Returns the flat expanded list of main-pane indicator series metadata.
 * Multi-output indicators (BB → upper/mid/lower) produce multiple entries.
 * Ordering matches buildData() and buildSeries(): reversed indicator list.
 */
function buildExpandedMainIndList(): MainSeriesMeta[] {
  const mainInds = [...visibleActiveIndicators.value]
    .reverse()
    .filter(i => i.pane !== 'separate' && i.type !== 'volume')

  const result: MainSeriesMeta[] = []
  for (const ind of mainInds) {
    for (const key of getIndicatorOutputKeys(ind.type)) {
      result.push({
        ind,
        outputKey: key,
        color: getOutputColor(ind, key),
        label: getSeriesLabel(ind, key),
      })
    }
  }
  return result
}

// ── Indicator computation ─────────────────────────────────────────────────────

/** Computes ALL outputs for a single indicator. Returns a Record keyed by output key. */
function computeAllIndicatorOutputs(
  closes: number[], highs: number[], lows: number[],
  vols: number[], ts: number[], ind: IndicatorConfig,
): Record<string, (number | null)[]> {
  const p = normalizeIndicatorParams(ind.type, ind.params)
  const nil = () => new Array(closes.length).fill(null)
  switch (ind.type) {
    case 'sma':      return { '_': computeSMA(closes, getParamNumber(p, 'period', 20)) }
    case 'ema':      return { '_': computeEMA(closes, getParamNumber(p, 'period', 20)) }
    case 'wma':      return { '_': computeWMA(closes, getParamNumber(p, 'period', 20)) }
    case 'hma':      return { '_': computeHMA(closes, getParamNumber(p, 'period', 20)) }
    case 'dema':     return { '_': computeDEMA(closes, getParamNumber(p, 'period', 20)) }
    case 'tema':     return { '_': computeTEMA(closes, getParamNumber(p, 'period', 20)) }
    case 'vwap':     return { '_': computeVWAP(ts, highs, lows, closes, vols) }
    case 'avwap':    return { '_': computeAVWAP(ts, highs, lows, closes, vols, getParamNumber(p, 'anchor_timestamp', ts[0] ?? 0)) }
    case 'volume_ratio': return { '_': computeVolumeRatio(vols, getParamNumber(p, 'period', 20)) }
    case 'psar':     return { '_': computePSAR(highs, lows, getParamNumber(p, 'af_start', 0.02), getParamNumber(p, 'af_step', 0.02), getParamNumber(p, 'af_max', 0.2)) }
    case 'bb': {
      const r = computeBB(closes, getParamNumber(p, 'period', 20), getParamNumber(p, 'std_dev', 2))
      return { upper: r.upper, mid: r.mid, lower: r.lower }
    }
    case 'keltner': {
      const r = computeKeltner(highs, lows, closes, getParamNumber(p, 'period', 20), getParamNumber(p, 'atr_period', 10), getParamNumber(p, 'multiplier', 2))
      return { upper: r.upper, mid: r.mid, lower: r.lower }
    }
    case 'donchian': {
      const r = computeDonchian(highs, lows, getParamNumber(p, 'period', 20))
      return { upper: r.upper, mid: r.mid, lower: r.lower }
    }
    case 'ichimoku': {
      const r = computeIchimoku(highs, lows, closes, getParamNumber(p, 'tenkan', 9), getParamNumber(p, 'kijun', 26), getParamNumber(p, 'senkou_b', 52), getParamNumber(p, 'displacement', 26))
      return { tenkanLine: r.tenkanLine, kijunLine: r.kijunLine, senkouALine: r.senkouALine, senkouBLine: r.senkouBLine, chikouLine: r.chikouLine }
    }
    case 'pivot_points': {
      const r = computePivotPoints(highs, lows, closes, getParamString(p, 'method', 'classic') as 'classic' | 'fibonacci' | 'camarilla')
      return { pp: r.pp, r1: r.r1, r2: r.r2, r3: r.r3, s1: r.s1, s2: r.s2, s3: r.s3 }
    }
    default: return { '_': nil() }
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

  // Build expanded flat list of main-pane series (multi-output indicators produce multiple entries)
  const expandedList = buildExpandedMainIndList()
  // Cache per-indicator computation to avoid redundant work for multi-output types
  const outputCache = new Map<IndicatorConfig, Record<string, (number | null)[]>>()
  const extraData = expandedList.map(meta => {
    if (!outputCache.has(meta.ind)) {
      outputCache.set(meta.ind, computeAllIndicatorOutputs(closes, highs, lows, vols, ts, meta.ind))
    }
    const outputs = outputCache.get(meta.ind)!
    return (outputs[meta.outputKey] ?? new Array(closes.length).fill(null)) as (number | null)[]
  })
  const comparisonData = visibleComparisonSeries.value.map(series =>
    series.values.slice(0, closes.length).concat(new Array(Math.max(0, closes.length - series.values.length)).fill(null))
  )
  const timestampIndexes = new Map<number, number>()
  ts.forEach((timestamp, index) => timestampIndexes.set(timestamp, index))
  const pythonData = visiblePythonSeries.value.map(series => {
    const aligned = new Array<number | null>(closes.length).fill(null)
    series.timestamps.forEach((timestamp, index) => {
      const parsed = Number(timestamp)
      const seconds = Number.isFinite(parsed) ? (parsed > 10_000_000_000 ? parsed / 1000 : parsed) : Date.parse(timestamp) / 1000
      const target = timestampIndexes.get(seconds)
      if (target != null) aligned[target] = series.values[index] == null ? null : Number(series.values[index])
    })
    return aligned
  })

  return [barIdx, opens, highs, lows, closes, vols, ...extraData, ...comparisonData, ...pythonData] as uPlot.AlignedData
}

// ── Indicator selection highlight plugin ──────────────────────────────────────
function indicatorHighlightPlugin(): uPlot.Plugin {
  return {
    hooks: {
      draw: [(u: uPlot) => {
        const selIdx = chartStore.selectedIndicatorIndex
        if (selIdx == null) return
        const selInd = chartStore.indicators[selIdx]
        if (!selInd) return
        const selectedSignature = radarIndicatorSignature(selInd)

        const expandedList = buildExpandedMainIndList()
        const dpr = devicePixelRatio || 1
        const { ctx } = u

        ctx.save()
        ctx.beginPath()
        ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height)
        ctx.clip()

        for (let ei = 0; ei < expandedList.length; ei++) {
          const meta = expandedList[ei]
          if (radarIndicatorSignature(meta.ind) !== selectedSignature) continue

          const seriesData = (u.data as number[][])[6 + ei]
          if (!seriesData) continue

          ctx.strokeStyle = meta.color
          ctx.lineWidth   = ((meta.ind.style.lineWidth ?? 0.75) + 1.1) * dpr
          ctx.shadowColor = meta.color
          ctx.shadowBlur  = 5
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
        }
        ctx.restore()
      }],
    },
  }
}

function radarIndicatorHighlightPlugin(): uPlot.Plugin {
  return {
    hooks: {
      draw: [(u: uPlot) => {
        const expandedList = buildExpandedMainIndList()
        const dpr = devicePixelRatio || 1
        const { ctx } = u

        ctx.save()
        ctx.beginPath()
        ctx.rect(u.bbox.left, u.bbox.top, u.bbox.width, u.bbox.height)
        ctx.clip()

        for (let ei = 0; ei < expandedList.length; ei++) {
          const meta = expandedList[ei]
          const radarOpacity = (meta.ind as any).__radarHighlightOpacity as number | undefined
          const radarSource = (meta.ind as any).__radarSource as 'overlay' | 'reuse' | undefined
          if (!radarSource || !radarOpacity) continue

          const seriesData = (u.data as number[][])[6 + ei]
          if (!seriesData) continue

          ctx.strokeStyle = meta.color
          ctx.lineWidth = ((meta.ind.style.lineWidth ?? 0.75) + (radarSource === 'reuse' ? 0.45 : 0.18)) * dpr
          ctx.shadowColor = meta.color
          ctx.shadowBlur = (radarSource === 'reuse' ? 4.5 : 2.8) * Math.max(0.2, radarOpacity)
          ctx.globalAlpha = Math.min(0.78, 0.36 + radarOpacity * 0.28)
          ctx.setLineDash([])
          ctx.beginPath()

          let started = false
          for (let i = 0; i < seriesData.length; i++) {
            const val = seriesData[i]
            if (val == null || isNaN(val)) { started = false; continue }
            const x = u.valToPos((u.data[0] as number[])[i], 'x', true)
            const y = u.valToPos(val, 'y', true)
            if (!started) {
              ctx.moveTo(x, y)
              started = true
            } else {
              ctx.lineTo(x, y)
            }
          }
          ctx.stroke()
        }

        ctx.restore()
      }],
    },
  }
}

// ── Build series ──────────────────────────────────────────────────────────────
function buildSeries(): uPlot.Series[] {
  // area/baseline render as a visible close line; candlestick types hide it
  const isLineBased = effectiveChartType.value === 'line' || effectiveChartType.value === 'area' || effectiveChartType.value === 'baseline'
  const closeSeries: uPlot.Series = isLineBased
    ? {
        label: 'Close',
        scale: 'y',
        stroke: '#64b5f6',
        width: 1.6,
        fill: effectiveChartType.value === 'area' ? 'rgba(100,181,246,0.12)' : undefined,
        points: { show: false },
      }
    : { label: 'Close', scale: 'y', show: false }
  const base: uPlot.Series[] = [
    {},
    { label: 'Open',   scale: 'y',   show: false },
    { label: 'High',   scale: 'y',   show: false },
    { label: 'Low',    scale: 'y',   show: false },
    closeSeries,
    { label: 'Volume', scale: 'vol', show: false },
  ]
  // Expanded flat list: multi-output indicators (BB, etc.) produce multiple series
  for (const meta of buildExpandedMainIndList()) {
    base.push({
      label:  meta.label,
      scale:  'y',
      stroke: meta.color,
      width:  meta.ind.style.lineWidth ?? 0.75,
      points: { show: false },
    })
  }
  for (const series of visibleComparisonSeries.value) {
    base.push({
      label: series.label || series.symbol,
      scale: 'y',
      stroke: series.color,
      width: 1.4,
      points: { show: false },
    })
  }
  for (const series of visiblePythonSeries.value) {
    base.push({
      label: series.label,
      scale: 'y',
      stroke: series.color,
      width: 1.35,
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
  // Use expanded list; project only the first output of each indicator to avoid duplicates.
  const expandedList = buildExpandedMainIndList()
  const projectedInds = new Set<IndicatorConfig>()

  for (let ei = 0; ei < expandedList.length; ei++) {
    const meta = expandedList[ei]
    const ind = meta.ind
    if (!ind.showYProjection) continue
    if (projectedInds.has(ind)) continue  // already emitted a chip for this indicator
    projectedInds.add(ind)

    const seriesData = (u.data as number[][])[6 + ei]
    if (!seriesData) continue
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
      const anchorTime = getParamNumber(ind.params, 'anchor_timestamp', 0)
      label = anchorTime ? `AVWAP\n${formatProjectionDate(anchorTime)}` : 'AVWAP'
    } else {
      label = indicatorDisplayName(ind)
    }
    items.push({ price: lastVal, color: ind.style.color, chipLabel: label, originX: lastIdx })
  }

  if (overlaysEnabled.value) {
    // ── Price alerts with projection toggled on ────────────────────────────
    for (const alert of visibleAlerts.value) {
      if (alert.status !== 'active' && alert.status !== 'triggered') continue
      if (!getAlertProjection(alert)) continue
      const color = alert.status === 'triggered' ? '#888888' : '#ffb74d'
      items.push({ price: Number(alert.threshold_price), color, chipLabel: 'Alert' })
    }

    // ── Drawings (non-fib) with projection toggled on ──────────────────────
    for (const d of renderableDrawings.value) {
      if (!d.id || FIBO_TYPES.has(d.type)) continue
      if (!getDrawingProjection(d)) continue
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
  }

  // ── Current price (last close) ────────────────────────────────────────────
  if (showCurrentPriceProjection.value) {
    const closes = (u.data as number[][])[4]
    if (closes?.length) {
      const lastClose = closes[closes.length - 1]
      if (lastClose != null && !isNaN(lastClose)) {
        items.push({ price: lastClose, color: '#26a69a', chipLabel: 'Last', originX: closes.length - 1 })
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

function getAlertProjection(alert: PriceAlert): boolean {
  return props.overlayAlerts ? !!alert.show_projection : alertsStore.getAlertProjection(alert.id)
}

function getDrawingProjection(drawing: AnyDrawing): boolean {
  if (props.overlayDrawings) return !!(drawing as any).showProjection
  return drawing.id != null ? drawStore.getDrawingProjection(drawing.id) : false
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
  const totalSubPaneH = subPanes.value.reduce((sum, p) => sum + (subPaneHeights[p.key] ?? SUB_PANE_DEFAULT_H), 0)
  const h = Math.max(80, (rootRef.value?.clientHeight ?? 600) - totalSubPaneH - subPanes.value.length * 4 - 20)
  const series = buildSeries()
  lastSeriesCount = series.length

  const plugins: uPlot.Plugin[] = [
    alertLinesPlugin(
      () => overlaysEnabled.value
        ? visibleAlerts.value
          .filter(a => a.status === 'active' || a.status === 'triggered')
          .map(a => ({
            id:        a.id,
            price:     Number(a.threshold_price),
            label:     a.notes ?? undefined,
            triggered: a.status === 'triggered',
          }))
        : [],
      () => overlayInteractionsEnabled.value ? alertsStore.selectedAlertId : null,
    ),
    alertEventsPlugin(() => alertFiringMarkers.value),
    indicatorHighlightPlugin(),
    radarIndicatorHighlightPlugin(),
    yAxisProjectionsPlugin(() => getProjectionItems()),
    optionsLevelsPlugin(() => optionsExposureStore.data?.key_levels ?? null),
  ]

  if (effectiveChartType.value === 'ohlc') {
    plugins.unshift(ohlcBarsPlugin({ upColor: '#26a69a', downColor: '#ef5350' }))
  } else if (effectiveChartType.value === 'baseline') {
    plugins.unshift(baselinePlugin())
  } else if (
    effectiveChartType.value === 'candles'
    || effectiveChartType.value === 'heikin_ashi'
    || effectiveChartType.value === 'renko'
    || effectiveChartType.value === 'kagi'
    || effectiveChartType.value === 'point_figure'
  ) {
    plugins.unshift(candlestickPlugin({ upColor: '#26a69a', downColor: '#ef5350' }))
  }

  // Add volume bars plugin if volume indicator is active
  if (hasVolumeIndicator.value) {
    plugins.push(volumePlugin({
      upColor: 'rgba(38,166,154,0.35)',
      downColor: 'rgba(239,83,80,0.35)',
      heightRatio: 0.18,
    }))
  }

  if (showApproxVolumeProfile.value) {
    plugins.push(approxVolumeProfilePlugin())
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
        scale:  'y', side: 1, size: yAxisSize, gap: 6, stroke: '#888', font: '10px monospace',
        ticks:  { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
        values: (_u, ticks) => ticks.map(t => t == null ? '' : t >= 1000 ? t.toFixed(0) : t.toFixed(2)),
      },
    ],

    series,
    plugins,

    hooks: {
      setScale: [(u, scaleKey) => {
        if (scaleKey !== 'x') return
        const min = u.scales.x.min!
        const max = u.scales.x.max!
        for (const sp of Object.values(subPlotsMap)) {
          if (sp.scales.x.min !== min || sp.scales.x.max !== max) {
            sp.setScale('x', { min, max })
          }
        }
      }],
      draw: [(u) => {
        renderVisualOverlays()
        renderEventMarkers(u)
      }],
      setCursor: [(u) => {
        updateTooltip(u, u.cursor.idx)
        // Broadcast cursor timestamp for cross-panel sync
        // Snap crosshair to nearest bar centre — guard against re-entrancy
        if (snapGuard) return
        if (u.cursor.idx != null && layoutStore.panelCount > 1 && !syncGuard) {
          const ts = chartStore.bars[u.cursor.idx]?.ts
          if (ts) layoutStore.setSyncedTs(ts, panelId)
        }
        if (u.cursor.idx != null && !syncGuard) {
          const ts = chartStore.bars[u.cursor.idx]?.ts
          if (ts && ts !== lastPublishedWorkspaceCursor) {
            // The workstation bus carries cursor positions across docked windows and
            // browser pop-outs. Grey charts stay deliberately isolated.
            workspaceStore.publishTimestamp(ts, props.workspaceLinkGroup, panelId)
            lastPublishedWorkspaceCursor = ts
          }
        }
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
        if (!chartStore.instrument?.is_synthetic) {
          loadInstrumentEvents()
          loadAlertFiringEvents()
        }
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
  applyLinkedTimestamp(props.linkedTimestamp)
  startLivePolling()
}

// ── Initial view: last DEFAULT_BARS_VISIBLE bars ──────────────────────────────
function setInitialView(u: uPlot) {
  const [x] = u.data as number[][]
  if (!x?.length) return
  const latest = x[x.length - 1]
  const span = Math.min(DEFAULT_BARS_VISIBLE, Math.max(1, x.length))
  u.setScale('x', {
    min: Math.max(-0.5, latestXRange(latest, span).min),
    max: latestXRange(latest, span).max,
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
  uplot.setScale('x', latestXRange(latest, span))
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
  if (!chartStore.instrument?.is_synthetic) {
    loadInstrumentEvents()
    loadAlertFiringEvents()
  }
}

// ── Interaction ────────────────────────────────────────────────────────────────
function setupInteraction(u: uPlot) {
  if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
  const wrapper = wrapperRef.value!
  let cachedRect: DOMRect | null = null

  const liveRect    = () => u.over.getBoundingClientRect()
  const rootRect    = () => ((u.root as HTMLElement | undefined)?.getBoundingClientRect?.() ?? liveRect())
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
    const rBound = x[x.length - 1] + rightOverscroll(span)
    if (min < lBound) { min = lBound; max = min + span }
    if (max > rBound) { max = rBound; min = max - span }
    u.setScale('x', { min, max })
    updateAtLatest()
    // Note: drawings are re-rendered via the draw hook after uPlot commits the canvas.
    // An explicit renderVisualOverlays() here would draw at the new scale while the chart
    // canvas is still at the old scale (uPlot batches canvas updates), causing drawings to float.
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

  const onClick = (e: MouseEvent) => {
    const rect = rootRect()
    const event = eventAt(e.clientX - rect.left, e.clientY - rect.top)
    if (!event) {
      eventPopover.value = null
      return
    }
    e.preventDefault()
    e.stopPropagation()
    const pos = positionEventPopover(e.clientX, e.clientY)
    eventPopover.value = {
      event,
      x: pos.x,
      y: pos.y,
    }
  }

  const onHoverMove = (e: MouseEvent) => {
    if (panActive || priceActive || xAxisActive || drawStore.activeToolType || drawStore.avwapDropActive) return
    if (isOnYAxis(e.clientX))   { wrapper.style.cursor = 'ns-resize'; return }
    if (isOnXAxis(e.clientY))   { wrapper.style.cursor = 'ew-resize'; return }
    const chartRect = rootRect()
    if (eventAt(e.clientX - chartRect.left, e.clientY - chartRect.top)) {
      wrapper.style.cursor = 'pointer'
      return
    }
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
    if (isEditorTarget(e.target)) return
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
        if (overlayInteractionsEnabled.value && drawStore.selectedId != null) {
          e.preventDefault()
          drawStore.deleteDrawing(drawStore.selectedId)
        }
        break
      case 'Escape':
        if (overlayInteractionsEnabled.value) {
          drawStore.selectDrawing(null)
          drawStore.setActiveTool(null)
        }
        clearMeasurement()
        drawingPoints = []
        drawingPreviewPoint = null
        break
    }
  }

  wrapper.addEventListener('wheel',       onWheel,       { passive: false, capture: true })
  wrapper.addEventListener('mousedown',   onMouseDown)
  wrapper.addEventListener('mousemove',   onHoverMove)
  wrapper.addEventListener('click',       onClick)
  wrapper.addEventListener('dblclick',    onDblClick)
  wrapper.addEventListener('contextmenu', onContextMenu)
  window.addEventListener('mousemove',    onMouseMove)
  window.addEventListener('mouseup',      onMouseUp)
  if (keyboardEnabled.value) window.addEventListener('keydown', onKeyDown)

  interactionCleanup = () => {
    wrapper.removeEventListener('wheel',       onWheel,       true)
    wrapper.removeEventListener('mousedown',   onMouseDown)
    wrapper.removeEventListener('mousemove',   onHoverMove)
    wrapper.removeEventListener('click',       onClick)
    wrapper.removeEventListener('dblclick',    onDblClick)
    wrapper.removeEventListener('contextmenu', onContextMenu)
    window.removeEventListener('mousemove',    onMouseMove)
    window.removeEventListener('mouseup',      onMouseUp)
    if (keyboardEnabled.value) window.removeEventListener('keydown', onKeyDown)
    _overDblClickCleanup()
    wrapper.style.cursor = ''
  }
}

// ── Sub-panes ─────────────────────────────────────────────────────────────────

interface SubPaneOutput {
  key: string
  values: (number | null)[]
  color: string
  label: string
}

/** Compute all output series for a sub-pane indicator. Multi-output types return multiple entries. */
function computeSubPaneOutputs(
  ind: IndicatorConfig,
  closes: number[], highs: number[], lows: number[],
  vols: number[], ts: number[],
): SubPaneOutput[] {
  const p = normalizeIndicatorParams(ind.type, ind.params)
  const n = closes.length
  const nil = (): (number | null)[] => new Array(n).fill(null)

  switch (ind.type) {
    case 'rsi':
      return [{ key: '_', values: computeRSI(closes, getParamNumber(p, 'period', 14)), color: ind.style.color, label: `RSI(${getParamNumber(p, 'period', 14)})` }]
    case 'macd': {
      const r = computeMACD(closes, getParamNumber(p, 'fast', 12), getParamNumber(p, 'slow', 26), getParamNumber(p, 'signal', 9))
      return [
        { key: 'macd',      values: r.macd,      color: ind.style.color, label: 'MACD' },
        { key: 'signal',    values: r.signal,    color: '#ffb74d',       label: 'Signal' },
        { key: 'histogram', values: r.histogram, color: '#26a69a66',     label: 'Hist' },
      ]
    }
    case 'adx': {
      const r = computeADX(highs, lows, closes, getParamNumber(p, 'period', 14))
      return [
        { key: 'adx',      values: r.adx,      color: ind.style.color, label: 'ADX' },
        { key: 'plus_di',  values: r.plus_di,  color: '#26a69a',       label: '+DI' },
        { key: 'minus_di', values: r.minus_di, color: '#ef5350',       label: '-DI' },
      ]
    }
    case 'stoch': {
      const r = computeStoch(highs, lows, closes, getParamNumber(p, 'k_period', 14), getParamNumber(p, 'smooth_k', 3), getParamNumber(p, 'd_period', 3))
      return [
        { key: 'k', values: r.k, color: ind.style.color, label: '%K' },
        { key: 'd', values: r.d, color: '#ffb74d',       label: '%D' },
      ]
    }
    case 'aroon': {
      const r = computeAroon(highs, lows, getParamNumber(p, 'period', 25))
      return [
        { key: 'up',   values: r.up,   color: '#26a69a', label: 'Aroon Up' },
        { key: 'down', values: r.down, color: '#ef5350', label: 'Aroon Down' },
      ]
    }
    case 'cci':
      return [{ key: '_', values: computeCCI(highs, lows, closes, getParamNumber(p, 'period', 20)), color: ind.style.color, label: `CCI(${getParamNumber(p, 'period', 20)})` }]
    case 'williams_r':
      return [{ key: '_', values: computeWilliamsR(highs, lows, closes, getParamNumber(p, 'period', 14)), color: ind.style.color, label: `%R(${getParamNumber(p, 'period', 14)})` }]
    case 'roc':
      return [{ key: '_', values: computeROC(closes, getParamNumber(p, 'period', 10)), color: ind.style.color, label: `ROC(${getParamNumber(p, 'period', 10)})` }]
    case 'momentum':
      return [{ key: '_', values: computeMomentum(closes, getParamNumber(p, 'period', 10)), color: ind.style.color, label: `MOM(${getParamNumber(p, 'period', 10)})` }]
    case 'mfi':
      return [{ key: '_', values: computeMFI(highs, lows, closes, vols, getParamNumber(p, 'period', 14)), color: ind.style.color, label: `MFI(${getParamNumber(p, 'period', 14)})` }]
    case 'cmf':
      return [{ key: '_', values: computeCMF(highs, lows, closes, vols, getParamNumber(p, 'period', 20)), color: ind.style.color, label: `CMF(${getParamNumber(p, 'period', 20)})` }]
    case 'obv':
      return [{ key: '_', values: computeOBV(closes, vols), color: ind.style.color, label: 'OBV' }]
    case 'volume_ratio':
      return [{ key: '_', values: computeVolumeRatio(vols, getParamNumber(p, 'period', 20)), color: ind.style.color, label: `VolRatio(${getParamNumber(p, 'period', 20)})` }]
    case 'atr':
      return [{ key: '_', values: computeATR(highs, lows, closes, getParamNumber(p, 'period', 14)), color: ind.style.color, label: `ATR(${getParamNumber(p, 'period', 14)})` }]
    case 'stddev':
      return [{ key: '_', values: computeStdDev(closes, getParamNumber(p, 'period', 20)), color: ind.style.color, label: `StdDev(${getParamNumber(p, 'period', 20)})` }]
    case 'trix':
      return [{ key: '_', values: computeTRIX(closes, getParamNumber(p, 'period', 15)), color: ind.style.color, label: `TRIX(${getParamNumber(p, 'period', 15)})` }]
    case 'ppo':
      return [{ key: '_', values: computePPO(closes, getParamNumber(p, 'fast', 12), getParamNumber(p, 'slow', 26)), color: ind.style.color, label: `PPO(${getParamNumber(p, 'fast', 12)},${getParamNumber(p, 'slow', 26)})` }]
    default:
      return [{ key: '_', values: nil(), color: ind.style.color, label: ind.type.toUpperCase() }]
  }
}

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

    const outputs = computeSubPaneOutputs(pane.config, closes, highs, lows, vols, ts)
    const w = wrapperRef.value?.clientWidth || 900

    const subOpts: uPlot.Options = {
      width: w, height: 110,
      legend: { show: false },
      cursor: { drag: { x: false, y: false }, sync: { key: 'chart' }, lock: true },
      scales: { x: { time: false }, y: { auto: true } },
      axes: [
        { scale: 'x', show: false },
        { scale: 'y', side: 1, stroke: '#888', size: yAxisSize,
          ticks: { stroke: '#2a2a2a' }, grid: { stroke: '#1a1a1a', width: 1 },
          values: (_u, ticks) => ticks.map(t => t.toFixed(1)) },
      ],
      series: [
        {},
        ...outputs.map(o => ({
          label:  o.label,
          stroke: o.color,
      width:  pane.config.style.lineWidth ?? 0.75,
          points: { show: false },
        })),
      ],
      plugins: getSubPaneRefLines(pane.config.type).length
        ? [refLinesPlugin(getSubPaneRefLines(pane.config.type))] : [],
    }

    const alignedData: uPlot.AlignedData = [x, ...outputs.map(o => o.values)] as uPlot.AlignedData
    const sp = new uPlot(subOpts, alignedData, el)
    subPlotsMap[pane.key] = sp

    el.addEventListener('wheel', (e: WheelEvent) => {
      e.preventDefault(); e.stopPropagation()
      wrapperRef.value?.dispatchEvent(new WheelEvent('wheel', {
        deltaX: e.deltaX, deltaY: e.deltaY,
        ctrlKey: e.ctrlKey,
        clientX: e.clientX, clientY: e.clientY,
        bubbles: true, cancelable: true,
      }))
    }, { passive: false, capture: true })

    el.addEventListener('mousedown', (e: MouseEvent) => {
      if (e.button !== 0) return
      const wrapper = wrapperRef.value
      if (!wrapper) return
      // Remap clientY into the main chart's plot area so pan mode activates
      // (not X-axis drag mode, which triggers when clientY > u.over.bottom)
      const overRect = uplot?.over?.getBoundingClientRect()
      if (!overRect) return
      wrapper.dispatchEvent(new MouseEvent('mousedown', {
        button: 0, buttons: 1,
        clientX: e.clientX,
        clientY: overRect.top + overRect.height / 2,
        bubbles: true, cancelable: true,
      }))
    })

    if (overlayInteractionsEnabled.value) {
      await nextTick()
      const canvas = subPaneCanvasRefs[pane.key]
      if (canvas) {
        const renderer = new DrawingRenderer(canvas)
        renderer.attach(sp)
        renderer.setTimeToXMapper((time: number) => sp.valToPos(drawingTimeToBarIndex(time), 'x'))
        subDrawingRenderers[pane.key] = renderer
        alignSubPaneCanvas(canvas, el, sp)
        setupSubPaneDrawingInteraction(sp, pane.key, pane.config.type)
        setupSubPaneHitDetection(sp, pane.config.type)
        renderer.renderAll(drawingOverlayList(pane.config.type))
      }
    }
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
    const outputs = computeSubPaneOutputs(pane.config, closes, highs, lows, vols, ts)
    sp.setData([x, ...outputs.map(o => o.values)] as uPlot.AlignedData)
  }
}

function getSubPaneRefLines(type: string): { value: number; color: string; label?: string }[] {
  switch (type) {
    case 'rsi':
      return [
        { value: 70, color: '#ef535066', label: 'OB 70' },
        { value: 30, color: '#26a69a66', label: 'OS 30' },
        { value: 50, color: '#44444488' },
      ]
    case 'stoch': case 'mfi':
      return [
        { value: 80, color: '#ef535066', label: '80' },
        { value: 20, color: '#26a69a66', label: '20' },
        { value: 50, color: '#44444488' },
      ]
    case 'adx':
      return [{ value: 25, color: '#ffb74d88', label: '25' }]
    case 'cci':
      return [
        { value:  100, color: '#ef535066', label: '100' },
        { value: -100, color: '#26a69a66', label: '-100' },
        { value:    0, color: '#44444488' },
      ]
    case 'williams_r':
      return [
        { value: -20, color: '#ef535066', label: 'OB -20' },
        { value: -80, color: '#26a69a66', label: 'OS -80' },
        { value: -50, color: '#44444488' },
      ]
    case 'aroon':
      return [
        { value: 70, color: '#26a69a66' },
        { value: 30, color: '#ef535066' },
        { value: 50, color: '#44444488' },
      ]
    case 'macd': case 'cmf': case 'trix': case 'ppo': case 'roc': case 'momentum':
      return [{ value: 0, color: '#44444488' }]
    case 'volume_ratio':
      return [
        { value: 1, color: '#44444488', label: 'Avg' },
        { value: 2, color: '#ffb74d88', label: '2x' },
      ]
    default:
      return []
  }
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
  drawingRenderer.setTimeToXMapper((time: number) => u.valToPos(drawingTimeToBarIndex(time), 'x'))
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

function alignSubPaneCanvas(canvas: HTMLCanvasElement, parentEl: HTMLElement, u: uPlot) {
  if (!u.over) return
  const overRect   = u.over.getBoundingClientRect()
  const parentRect = parentEl.getBoundingClientRect()
  const x = overRect.left - parentRect.left
  const y = overRect.top  - parentRect.top
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
  const roundedIdx = Math.round(idx)
  const step = estimatedBarStepSeconds()
  let time: number
  if (roundedIdx < 0) {
    time = (times[0] ?? 0) + roundedIdx * step
  } else if (roundedIdx >= times.length) {
    time = (times[times.length - 1] ?? 0) + (roundedIdx - (times.length - 1)) * step
  } else {
    time = times[roundedIdx] ?? 0
  }
  return { time, price: u.posToVal(e.clientY - rect.top, 'y') }
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
  if (d.type === 'freehand') return null  // freehand has no handles — always move
  const toX = (time: number) => u.valToPos(drawingTimeToBarIndex(time), 'x')
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
  const drawing = drawStore.drawings.find(d => d.id === drawingDrag?.id)
  if (
    drawingDrag.mode === 'point'
    && drawingDrag.pointIndex != null
    && (drawing?.drawing_type === 'circle' || drawing?.drawing_type === 'half_circle')
    && drawingDrag.startPoints.length >= 2
  ) {
    const [p0, p1] = drawingDrag.startPoints
    points = [{ ...p0! }, { ...p1! }]
    const left = Math.min(p0!.time, p1!.time)
    const right = Math.max(p0!.time, p1!.time)
    const top = Math.max(p0!.price, p1!.price)
    const bottom = Math.min(p0!.price, p1!.price)
    if (drawing?.drawing_type === 'half_circle') {
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
    const startIdx = drawingTimeToBarIndex(drawingDrag.startPointer.time)
    const curIdx   = drawingTimeToBarIndex(cur.time)
    const dIdx     = curIdx - startIdx
    const dp       = cur.price - drawingDrag.startPointer.price
    points = drawingDrag.startPoints.map(p => ({
      time:  barIndexToDrawingTime(drawingTimeToBarIndex(p.time) + dIdx),
      price: p.price + dp,
    }))
  }
  patchDrawingPoints(drawingDrag.id, points, persist)
  renderVisualOverlays()
}

function setupDrawingInteraction(u: uPlot) {
  if (!overlayInteractionsEnabled.value) return
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
        params: { anchor_timestamp: anchorTime },
        style: { color: '#80cbc4', lineWidth: 0.75 },
        pane: 'main',
      })
      drawStore.setAvwapDrop(false)
      return
    }

    if (!drawStore.activeToolType || e.button !== 0) return
    e.stopPropagation()  // prevent pan from also firing
    const pt = pointerToDrawingPoint(u, e)

    // Freehand: start on pointerdown, collect points on move, finish on pointerup
    if (drawStore.activeToolType === 'freehand') {
      drawingPoints = [pt]
      drawingPreviewPoint = pt
      activeDrawingPaneKey = null
      const onMove = (ev: PointerEvent) => {
        drawingPoints.push(pointerToDrawingPoint(u, ev))
        renderVisualOverlays()
      }
      const onUp = () => {
        if (drawingPoints.length >= 2) {
          finishDrawing([...drawingPoints], 'freehand')
        }
        drawingPoints = []
        drawingPreviewPoint = null
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
      return
    }

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
    if (drawStore.activeToolType === 'freehand') return  // handled separately above
    const cur = pointerToDrawingPoint(u, e)
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
    if (e.shiftKey && e.button === 0 && (!overlayInteractionsEnabled.value || (!drawStore.activeToolType && !drawStore.avwapDropActive))) {
      e.preventDefault()
      e.stopPropagation()
      const start = pointerToMeasurementPoint(u, e)
      measurement.active = true
      measurement.frozen = false
      measurement.start = start
      measurement.end = start
      if (overlayInteractionsEnabled.value) {
        drawStore.selectDrawing(null)
        alertsStore.selectAlert(null)
      }
      chartStore.selectIndicator(null)
      suppressNextMouseDown = true
      renderVisualOverlays()
      return
    }
    if (overlayInteractionsEnabled.value && drawStore.activeToolType) return  // drawing tool handles its own events
    drawCtxMenu.visible = false
    const rect   = over.getBoundingClientRect()
    const mx     = e.clientX - rect.left
    const my     = e.clientY - rect.top
    const hitDraw = overlayInteractionsEnabled.value ? findHitDrawing(u, mx, my) : null
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
      if (overlayInteractionsEnabled.value) drawStore.selectDrawing(null)
      const alertId = findHitAlert(u, my)
      if (alertId !== null) {
        e.stopPropagation()
        alertsStore.selectAlert(alertId)
        chartStore.selectIndicator(null)
      } else {
        if (overlayInteractionsEnabled.value) alertsStore.selectAlert(null)
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
    if (overlayInteractionsEnabled.value && (drawStore.activeToolType || drawStore.avwapDropActive)) return
    const rect = over.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top

    const hitDraw = overlayInteractionsEnabled.value ? findHitDrawing(u, mx, my) : null
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
    if (!overlayInteractionsEnabled.value) return
    const rect = over.getBoundingClientRect()
    const hit  = findHitDrawing(u, e.clientX - rect.left, e.clientY - rect.top)
    if (hit) {
      e.preventDefault()
      e.stopPropagation()
      drawStore.selectDrawing(hit.id ?? null)
      drawCtxMenu.visible = true
      drawCtxMenu.x = e.clientX - (rootRef.value?.getBoundingClientRect().left ?? 0)
      drawCtxMenu.y = e.clientY - (rootRef.value?.getBoundingClientRect().top  ?? 0)
    }
  })
}

function setupSubPaneDrawingInteraction(sp: uPlot, paneKey: string, indicatorKey: string) {
  const over = sp.over; if (!over) return

  over.addEventListener('pointerdown', (e) => {
    if (!drawStore.activeToolType || e.button !== 0) return
    e.stopPropagation()
    const rect = over.getBoundingClientRect()
    const idx  = sp.posToVal(e.clientX - rect.left, 'x')
    const pt = { time: barIndexToTime(idx) ?? 0, price: sp.posToVal(e.clientY - rect.top, 'y') }
    activeDrawingPaneKey = indicatorKey

    if (drawStore.activeToolType === 'freehand') {
      drawingPoints = [pt]
      drawingPreviewPoint = pt
      const onMove = (ev: PointerEvent) => {
        const r = over.getBoundingClientRect()
        const i = sp.posToVal(ev.clientX - r.left, 'x')
        drawingPoints.push({ time: barIndexToTime(i) ?? 0, price: sp.posToVal(ev.clientY - r.top, 'y') })
        renderVisualOverlays()
      }
      const onUp = () => {
        if (drawingPoints.length >= 2) finishDrawing([...drawingPoints], 'freehand', indicatorKey)
        drawingPoints = []; drawingPreviewPoint = null
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
      return
    }

    if (drawStore.activeToolType === 'horizontal_line' || drawStore.activeToolType === 'vertical_line') {
      finishDrawing([pt], drawStore.activeToolType, indicatorKey); return
    }
    drawingPoints.push(pt)
    drawingPreviewPoint = pt
    if (drawingPoints.length >= 2) {
      finishDrawing([...drawingPoints], drawStore.activeToolType, indicatorKey)
      drawingPoints = []
      drawingPreviewPoint = null
    }
  }, { capture: true })

  over.addEventListener('pointermove', (e) => {
    if (!drawStore.activeToolType || drawingPoints.length === 0 || activeDrawingPaneKey !== indicatorKey) return
    if (drawStore.activeToolType === 'freehand') return
    const rect = over.getBoundingClientRect()
    const idx  = sp.posToVal(e.clientX - rect.left, 'x')
    drawingPreviewPoint = { time: barIndexToTime(idx) ?? 0, price: sp.posToVal(e.clientY - rect.top, 'y') }
    renderVisualOverlays()
  })

  over.addEventListener('contextmenu', (e) => {
    if (drawStore.activeToolType) {
      e.preventDefault(); e.stopPropagation()
      drawingPoints = []
      drawingPreviewPoint = null
      activeDrawingPaneKey = null
      drawStore.setActiveTool(null)
    }
  })
}

function setupSubPaneHitDetection(sp: uPlot, indicatorKey: string) {
  const over = sp.over; if (!over) return

  over.addEventListener('pointerdown', (e) => {
    if (drawStore.activeToolType) return  // drawing tool handles its own events
    drawCtxMenu.visible = false
    const rect = over.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top
    const paneDrawings = drawStore.renderableDrawingsFor(indicatorKey)
    const hitDraw = findHitDrawingInList(sp, paneDrawings, mx, my)
    if (hitDraw) {
      e.preventDefault(); e.stopPropagation()
      drawStore.selectDrawing(hitDraw.id ?? null)
      if (e.button === 0 && hitDraw.id != null && !hitDraw.isLocked) {
        const handleIndex = hitDrawingHandle(sp, hitDraw, mx, my)
        drawingDrag = {
          id: hitDraw.id,
          mode: handleIndex == null ? 'move' : 'point',
          pointIndex: handleIndex,
          startPoints: hitDraw.points.map(p => ({ ...p })),
          startPointer: pointerToDrawingPoint(sp, e),
        }
        try { over.setPointerCapture?.(e.pointerId) } catch { /* pointer already released */ }
        const onPointerMove = (moveEvent: PointerEvent) => {
          moveEvent.preventDefault()
          updateDrawingDrag(sp, moveEvent)
        }
        const onPointerUp = (upEvent: PointerEvent) => {
          updateDrawingDrag(sp, upEvent, true)
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
    }
    renderVisualOverlays()
  }, { capture: true })

  over.addEventListener('dblclick', (e) => {
    if (drawStore.activeToolType) return
    const rect = over.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top
    const paneDrawings = drawStore.renderableDrawingsFor(indicatorKey)
    const hitDraw = findHitDrawingInList(sp, paneDrawings, mx, my)
    if (hitDraw?.id != null) {
      e.stopPropagation()
      drawStore.requestEditDrawing(hitDraw.id)
    }
  }, { capture: true })

  over.addEventListener('contextmenu', (e) => {
    if (drawStore.activeToolType) return
    const rect = over.getBoundingClientRect()
    const mx   = e.clientX - rect.left
    const my   = e.clientY - rect.top
    const paneDrawings = drawStore.renderableDrawingsFor(indicatorKey)
    const hit = findHitDrawingInList(sp, paneDrawings, mx, my)
    if (hit) {
      e.preventDefault(); e.stopPropagation()
      drawStore.selectDrawing(hit.id ?? null)
      drawCtxMenu.visible = true
      drawCtxMenu.x = e.clientX - (rootRef.value?.getBoundingClientRect().left ?? 0)
      drawCtxMenu.y = e.clientY - (rootRef.value?.getBoundingClientRect().top  ?? 0)
    }
  })
}

function findHitAlert(u: uPlot, my: number): number | null {
  if (!overlayInteractionsEnabled.value) return null
  const HIT = 8
  for (const alert of visibleAlerts.value) {
    if (alert.status !== 'active' && alert.status !== 'triggered') continue
    const py = u.valToPos(Number(alert.threshold_price), 'y')
    if (Math.abs(my - py) < HIT) return alert.id
  }
  return null
}

function findHitIndicator(u: uPlot, my: number, barIdx: number): number | null {
  const HIT = 8
  // Use expanded list — multi-output indicators occupy consecutive slots in u.data[6+]
  const expandedList = buildExpandedMainIndList()
  for (let ei = 0; ei < expandedList.length; ei++) {
    const val = (u.data as number[][])[6 + ei]?.[barIdx]
    if (val == null || isNaN(val)) continue
    const py = u.valToPos(val, 'y')
    if (Math.abs(my - py) < HIT) {
      const signature = radarIndicatorSignature(expandedList[ei].ind)
      const storeIndex = chartStore.indicators.findIndex(indicator =>
        radarIndicatorSignature(indicator) === signature
      )
      if (storeIndex >= 0) return storeIndex
    }
  }
  return null
}

function findHitDrawing(u: uPlot, mx: number, my: number): AnyDrawing | null {
  if (!overlayInteractionsEnabled.value) return null
  return findHitDrawingInList(u, [...renderableDrawings.value].reverse(), mx, my)
}

function findHitDrawingInList(u: uPlot, drawings: AnyDrawing[], mx: number, my: number): AnyDrawing | null {
  const HIT = 8
  for (const d of drawings) {
    if ((d.id ?? 0) < 0) continue
    if (!d.points?.length) continue
    const toX = (time: number) => u.valToPos(drawingTimeToBarIndex(time), 'x')
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
    if (d.type === 'freehand') {
      for (let i = 1; i < d.points.length; i++) {
        const ax = toX(d.points[i - 1].time), ay = u.valToPos(d.points[i - 1].price, 'y')
        const bx = toX(d.points[i].time),     by = u.valToPos(d.points[i].price, 'y')
        if (distToSeg(mx, my, ax, ay, bx, by) < HIT) return d
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

async function finishDrawing(points: DrawingPoint[], type: DrawingType, indicatorKey: string | null = null) {
  const colors: Record<string, string> = {
    trendline: '#64b5f6', horizontal_line: '#ffb74d',
    fibonacci_retracement: '#81c784', rectangle: '#ba68c8',
    text_box: '#ffffff', circle: '#f06292', arrow: '#a5d6a7',
    half_circle: '#f06292',
  }
  activeDrawingPaneKey = null
  await drawStore.saveDrawing({ type, points, style: { color: colors[type] ?? '#fff', lineWidth: 0.75 } } as any, false, indicatorKey)
  renderVisualOverlays()
}

// ── Resize ────────────────────────────────────────────────────────────────────
function handleResize() {
  if (!uplot || !wrapperRef.value) return
  const w = wrapperRef.value.clientWidth
  const totalSubPaneH = subPanes.value.reduce((sum, p) => sum + (subPaneHeights[p.key] ?? SUB_PANE_DEFAULT_H), 0)
  const h = Math.max(80, (rootRef.value?.clientHeight ?? 600) - totalSubPaneH - subPanes.value.length * 4 - 20)
  uplot.setSize({ width: w, height: h }); syncCanvasSize(w, h)
  drawingRenderer?.resize(); renderVisualOverlays()
  for (const pane of subPanes.value) {
    const sp = subPlotsMap[pane.key]
    const paneH = (subPaneHeights[pane.key] ?? SUB_PANE_DEFAULT_H) - 10
    if (sp) sp.setSize({ width: w, height: Math.max(50, paneH) })
    const canvas = subPaneCanvasRefs[pane.key]
    const el = subPaneRefs[pane.key]
    if (canvas && el && sp) alignSubPaneCanvas(canvas, el, sp)
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────
function destroyAll() {
  stopLivePolling()
  if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
  uplot?.destroy(); uplot = null
  firstRenderedBarTs = null
  for (const sp of Object.values(subPlotsMap)) sp.destroy()
  subPlotsMap = {}
  subDrawingRenderers = {}
  activeDrawingPaneKey = null
}

onMounted(async () => {
  try { await userSettingsStore.loadSettings() } catch {}
  const initialType = effectiveChartType.value
  if (chartStore.symbol && chartStore.barType !== initialType) {
    await chartStore.loadBars(chartStore.symbol, chartStore.timeframe, initialType)
  } else {
    chartStore.setBarType(initialType)
  }
  await nextTick(); await initChart()
  resizeObserver = new ResizeObserver(handleResize)
  if (rootRef.value) {
    resizeObserver.observe(rootRef.value)
    // Prevent browser back/forward navigation gestures when over the chart
    rootRef.value.addEventListener('wheel', (e) => e.preventDefault(), { passive: false, capture: true })
  }
})

onUnmounted(() => { destroyAll(); resizeObserver?.disconnect() })

watch(() => chartStore.bars, () => {
  if (uplot) updateData(); else void initChart()
  applyLinkedTimestamp(props.linkedTimestamp)
}, { deep: false })
watch(() => chartStore.instrument?.id, () => { if (!chartStore.instrument?.is_synthetic) loadInstrumentEvents() })
watch(() => chartStore.instrument?.id, () => { if (!chartStore.instrument?.is_synthetic) loadAlertFiringEvents() })
watch([visibleComparisonSeries, visiblePythonSeries], () => { if (uplot) updateData(); else initChart() }, { deep: true })
watch(visibleActiveIndicators, async () => { await nextTick(); initChart() }, { deep: true })
watch(effectiveChartType, async (type) => {
  if (chartStore.symbol && chartStore.barType !== type) {
    await chartStore.loadBars(chartStore.symbol, chartStore.timeframe, type)
  } else {
    chartStore.setBarType(type)
  }
  await nextTick()
  initChart()
})
watch(() => props.chartSettings?.log_scale, value => {
  if (typeof value !== 'boolean' || value === isLogScale.value) return
  isLogScale.value = value
  if (uplot) void initChart()
})
watch(() => drawStore.drawings, () => {
  renderVisualOverlays()
}, { deep: true })

// Reset in-progress drawing points whenever the active tool changes
watch(() => drawStore.activeToolType, () => {
  drawingPoints = []
  drawingPreviewPoint = null
  activeDrawingPaneKey = null
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
watch(visibleAlerts, () => {
  redrawVisuals()
}, { deep: true })

// Redraw when any Y-projection toggle changes
watch(() => chartStore.indicators.map(i => i.showYProjection), () => { redrawVisuals() })
watch(() => visibleAlerts.value.map(a => `${a.id}:${a.show_projection}`).join('|'), () => { redrawVisuals() })
watch(() => drawStore.drawingProjections,  () => { redrawVisuals() })
watch(() => props.overlayDrawings, () => { redrawVisuals() }, { deep: true })
watch(() => props.overlayIndicators, async () => { await nextTick(); initChart() }, { deep: true })
watch(showCurrentPriceProjection, () => { redrawVisuals() })
watch(showHighLowProjection,      () => { redrawVisuals() })
watch(showApproxVolumeProfile,    () => { initChart() })

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

/** Publish Study Lab occurrences into every linked chart without treating them as a new data request. */
function applyLinkedTimestamp(timestamp: string | null) {
  if (timestamp) jumpToTs(timestamp)
}

watch(() => props.linkedTimestamp, applyLinkedTimestamp)

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

.event-popover {
  position: absolute;
  z-index: 80;
  width: 238px;
  max-width: calc(100% - 16px);
  max-height: calc(100% - 16px);
  overflow: auto;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  background: rgba(12, 12, 12, 0.96);
  box-shadow: 0 10px 28px rgba(0,0,0,0.45);
  color: #bbb;
  font-size: 10px;
  pointer-events: auto;
}
.event-popover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 8px;
  border-bottom: 1px solid #1f1f1f;
}
.event-popover-head strong { color: #eee; font-size: 11px; }
.event-popover-head button {
  background: transparent;
  border: 0;
  color: #666;
  cursor: pointer;
  font-family: inherit;
}
.event-popover-date {
  padding: 6px 8px 2px;
  color: #777;
  text-transform: capitalize;
}
.event-popover-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  padding: 7px 8px 9px;
}
.event-popover-grid span { color: #666; }
.event-popover-grid b {
  color: #ddd;
  font-weight: 600;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
}

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
.ed-section-sep {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #1a1a1a;
}
.ed-hint {
  font-size: 10px;
  color: #3a3a3a;
  padding-bottom: 4px;
}
.ed-checkbox-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 0;
  font-size: 12px;
  color: #bbb;
}
.ed-checkbox { accent-color: #64b5f6; }
.ed-field-row {
  display: grid;
  gap: 6px;
  padding: 0 0 12px;
  color: #bbb;
  font-size: 12px;
}
.ed-select {
  background: #0a0a0a;
  color: #ccc;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: monospace;
  font-size: 12px;
}

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
