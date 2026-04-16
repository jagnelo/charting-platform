<template>
  <div class="dashboard-view">
    <header class="dashboard-header">
      <div class="header-left">
        <div>
          <h1>{{ dashboardStore.activeDashboard?.name ?? 'Dashboard' }}</h1>
          <p>Build the market workspace you want to land on.</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="dash-btn" @click="reload">Refresh</button>
        <button class="dash-btn primary" :class="{ active: dashboardStore.editMode }" @click="toggleEdit">
          {{ dashboardStore.editMode ? 'Done' : 'Edit' }}
        </button>
      </div>
    </header>

    <div class="tab-bar" v-if="dashboardStore.activeDashboard">
      <button
        v-for="tab in dashboardStore.activeDashboard.tabs"
        :key="tab.id"
        class="tab-btn"
        :class="{ active: dashboardStore.activeTabId === tab.id }"
        @click="dashboardStore.setActiveTab(tab.id)"
      >
        <input
          v-if="renamingTabId === tab.id"
          v-model="tabRenameDraft"
          class="tab-input"
          @click.stop
          @keydown.enter="commitTabRename(tab)"
          @keydown.escape="renamingTabId = null"
          @blur="commitTabRename(tab)"
        />
        <span v-else @dblclick.stop="startTabRename(tab)">{{ tab.name }}</span>
      </button>
      <button v-if="dashboardStore.editMode" class="tab-add" @click="dashboardStore.createTab()">+ Tab</button>
      <button
        v-if="dashboardStore.editMode && dashboardStore.activeDashboard.tabs.length > 1 && dashboardStore.activeTab"
        class="tab-add danger"
        @click="dashboardStore.deleteTab(dashboardStore.activeTab.id)"
      >
        Delete Tab
      </button>
    </div>

    <div v-if="dashboardStore.isLoading" class="dashboard-state">Loading dashboard...</div>
    <div v-else-if="dashboardStore.error" class="dashboard-state error">{{ dashboardStore.error }}</div>
    <div v-else-if="!dashboardStore.activeTab" class="dashboard-state">No dashboard tab available.</div>

    <div v-else class="dashboard-body">
      <aside v-if="dashboardStore.editMode" class="widget-catalog">
        <div class="catalog-title">Add Widget</div>
        <button
          v-for="item in widgetCatalog"
          :key="item.type"
          class="catalog-item"
          @click="addWidget(item.type)"
        >
          <span>{{ item.title }}</span>
          <small>{{ item.description }}</small>
        </button>
      </aside>

      <div class="dashboard-scroll">
        <div class="dashboard-canvas" :style="canvasStyle">
          <div v-if="!widgets.length" class="canvas-empty">
            <div>
              <strong>Your dashboard is empty.</strong>
              <span>Enter edit mode and add the first widget.</span>
            </div>
            <button class="dash-btn primary" @click="dashboardStore.setEditMode(true)">Edit Dashboard</button>
          </div>
          <section
            v-for="widget in widgets"
            :key="widget.id"
            class="dashboard-widget"
            :class="{ editing: dashboardStore.editMode }"
            :style="widgetStyle(widget)"
          >
            <div class="widget-header" @pointerdown="startMove($event, widget)">
              <div class="widget-title">{{ widget.title || widgetTitle(widget.widget_type) }}</div>
              <div class="widget-tools" v-if="dashboardStore.editMode">
                <button @click.stop="configWidget = widget">Configure</button>
                <button @click.stop="duplicateWidget(widget)">Copy</button>
                <button class="danger" @click.stop="dashboardStore.deleteWidget(widget.id)">Delete</button>
              </div>
            </div>

            <div class="widget-body">
              <DashboardNotesWidget
                v-if="['notes', 'checklist'].includes(widget.widget_type)"
                :config="widget.config"
                @patch-config="patchConfig(widget, $event)"
              />
              <DashboardQuoteWidget
                v-else-if="widget.widget_type === 'quote'"
                :config="widget.config"
              />
              <DashboardLineChartWidget
                v-else-if="['simple_chart', 'comparison_chart', 'ratio_chart'].includes(widget.widget_type)"
                :type="widget.widget_type"
                :config="widget.config"
              />
              <DashboardAdvancedChartWidget
                v-else-if="widget.widget_type === 'advanced_chart'"
                :widget-id="widget.id"
                :config="widget.config"
              />
              <DashboardInstrumentDetailsWidget
                v-else-if="widget.widget_type === 'instrument_details'"
                :config="widget.config"
              />
              <DashboardWatchlistWidget
                v-else-if="widget.widget_type === 'watchlist'"
                :config="widget.config"
                @patch-config="patchConfig(widget, $event)"
              />
              <DashboardAlertsWidget v-else-if="widget.widget_type === 'alerts'" />
              <DashboardScreenerWidget
                v-else-if="widget.widget_type === 'screener'"
                :config="widget.config"
                @patch-config="patchConfig(widget, $event)"
              />
              <DashboardEconomicCalendarWidget
                v-else-if="widget.widget_type === 'economic_calendar'"
                :config="widget.config"
              />
              <DashboardHeatMapWidget
                v-else-if="widget.widget_type === 'heat_map'"
                :config="widget.config"
              />
              <div v-else class="empty-small">Unsupported widget.</div>
            </div>

            <button
              v-if="dashboardStore.editMode"
              class="resize-handle"
              title="Resize"
              @pointerdown.stop="startResize($event, widget)"
            />
          </section>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="configWidget" class="config-backdrop" @click.self="configWidget = null">
        <div class="config-modal">
          <div class="config-header">
            <div>
              <strong>Configure {{ configWidget.title || widgetTitle(configWidget.widget_type) }}</strong>
              <span>{{ widgetTitle(configWidget.widget_type) }}</span>
            </div>
            <button @click="configWidget = null">x</button>
          </div>

          <div class="config-body">
            <label class="config-field">
              <span>Title</span>
              <input
                :value="configWidget.title || ''"
                placeholder="Widget title"
                @change="patchWidget(configWidget, { title: inputValue($event) || null })"
              />
            </label>

            <label
              v-if="['quote', 'simple_chart', 'advanced_chart', 'instrument_details', 'economic_calendar', 'ratio_chart'].includes(configWidget.widget_type)"
              class="config-field"
            >
              <span>Instrument or expression</span>
              <DashboardInstrumentSearch
                :model-value="configWidget.config.symbol || configWidget.config.expression || ''"
                @select="patchConfig(configWidget, { symbol: $event })"
                @update:model-value="patchConfigLocal(configWidget, { symbol: $event })"
              />
            </label>

            <template v-if="configWidget.widget_type === 'comparison_chart'">
              <div class="config-field">
                <span>Compared instruments</span>
                <div
                  v-for="(target, index) in comparisonTargets(configWidget)"
                  :key="index"
                  class="comparison-config-row"
                >
                  <DashboardInstrumentSearch
                    :model-value="target.symbol"
                    @select="patchComparisonTarget(configWidget, index, { symbol: $event, label: $event })"
                    @update:model-value="patchComparisonTargetLocal(configWidget, index, { symbol: $event, label: $event })"
                  />
                  <input
                    type="color"
                    :value="target.color"
                    @input="patchComparisonTarget(configWidget, index, { color: inputValue($event) })"
                  />
                  <button @click="removeComparisonTarget(configWidget, index)">Remove</button>
                </div>
                <button class="config-add" @click="addComparisonTarget(configWidget)">+ Add comparison</button>
              </div>
            </template>

            <label v-if="chartWidgetTypes.includes(configWidget.widget_type)" class="config-field">
              <span>Timeframe</span>
              <select
                :value="configWidget.config.timeframe || 'D1'"
                @change="patchConfig(configWidget, { timeframe: inputValue($event) })"
              >
                <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
              </select>
            </label>

            <label v-if="configWidget.widget_type === 'advanced_chart'" class="config-field">
              <span>Chart style</span>
              <select
                :value="configWidget.config.chartType || 'candles'"
                @change="patchConfig(configWidget, { chartType: inputValue($event) })"
              >
                <option v-for="bt in CHART_BAR_TYPES" :key="bt.value" :value="bt.value">{{ bt.label }}</option>
              </select>
            </label>

            <template v-if="configWidget.widget_type === 'advanced_chart'">
              <label class="config-check">
                <input
                  type="checkbox"
                  :checked="configWidget.config.showIndicators !== false"
                  @change="patchConfig(configWidget, { showIndicators: checkboxValue($event) })"
                />
                <span>Show instrument indicators</span>
              </label>
              <label class="config-check">
                <input
                  type="checkbox"
                  :checked="configWidget.config.showDrawings !== false"
                  @change="patchConfig(configWidget, { showDrawings: checkboxValue($event) })"
                />
                <span>Show instrument drawings</span>
              </label>
              <label class="config-check">
                <input
                  type="checkbox"
                  :checked="configWidget.config.showAlerts !== false"
                  @change="patchConfig(configWidget, { showAlerts: checkboxValue($event) })"
                />
                <span>Show price alert levels</span>
              </label>
            </template>

            <label v-if="['simple_chart', 'comparison_chart'].includes(configWidget.widget_type)" class="config-check">
              <input
                type="checkbox"
                :checked="configWidget.widget_type === 'comparison_chart' ? configWidget.config.normalize !== false : configWidget.config.normalize === true"
                @change="patchConfig(configWidget, { normalize: checkboxValue($event) })"
              />
              <span>Show performance from first visible bar</span>
            </label>

            <template v-if="configWidget.widget_type === 'watchlist'">
              <label class="config-field">
                <span>Watchlist</span>
                <select
                  :value="configWidget.config.watchlistId || ''"
                  @change="patchConfig(configWidget, { watchlistId: Number(inputValue($event)) || null })"
                >
                  <option value="">First watchlist</option>
                  <option v-for="wl in watchlistStore.watchlists" :key="wl.id" :value="wl.id">{{ wl.name }}</option>
                </select>
              </label>
              <label class="config-check">
                <input
                  type="checkbox"
                  :checked="configWidget.config.showSparklines !== false"
                  @change="patchConfig(configWidget, { showSparklines: checkboxValue($event) })"
                />
                <span>Show line charts for rows</span>
              </label>
            </template>

            <label v-if="configWidget.widget_type === 'screener'" class="config-field">
              <span>Screener</span>
              <select
                :value="configWidget.config.screenerId || ''"
                @change="patchConfig(configWidget, { screenerId: Number(inputValue($event)) || null })"
              >
                <option value="">First screener</option>
                <option v-for="s in screeners" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </label>

            <label v-if="configWidget.widget_type === 'heat_map'" class="config-field">
              <span>Watchlist</span>
              <select
                :value="configWidget.config.watchlistId || ''"
                @change="patchConfig(configWidget, { watchlistId: Number(inputValue($event)) || null })"
              >
                <option value="">First watchlist</option>
                <option v-for="wl in watchlistStore.watchlists" :key="wl.id" :value="wl.id">{{ wl.name }}</option>
              </select>
            </label>

            <label v-if="['notes', 'checklist'].includes(configWidget.widget_type)" class="config-field">
              <span>Mode</span>
              <select
                :value="configWidget.config.mode || (configWidget.widget_type === 'checklist' ? 'checklist' : 'notes')"
                @change="patchConfig(configWidget, { mode: inputValue($event) })"
              >
                <option value="notes">Notes</option>
                <option value="checklist">Checklist</option>
              </select>
            </label>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import DashboardAlertsWidget from '@/components/dashboard/DashboardAlertsWidget.vue'
import DashboardAdvancedChartWidget from '@/components/dashboard/DashboardAdvancedChartWidget.vue'
import DashboardEconomicCalendarWidget from '@/components/dashboard/DashboardEconomicCalendarWidget.vue'
import DashboardHeatMapWidget from '@/components/dashboard/DashboardHeatMapWidget.vue'
import DashboardInstrumentSearch from '@/components/dashboard/DashboardInstrumentSearch.vue'
import DashboardInstrumentDetailsWidget from '@/components/dashboard/DashboardInstrumentDetailsWidget.vue'
import DashboardLineChartWidget from '@/components/dashboard/DashboardLineChartWidget.vue'
import DashboardNotesWidget from '@/components/dashboard/DashboardNotesWidget.vue'
import DashboardQuoteWidget from '@/components/dashboard/DashboardQuoteWidget.vue'
import DashboardScreenerWidget from '@/components/dashboard/DashboardScreenerWidget.vue'
import DashboardWatchlistWidget from '@/components/dashboard/DashboardWatchlistWidget.vue'
import { api } from '@/lib/api'
import { useAlertsStore } from '@/stores/alerts'
import { useDashboardStore } from '@/stores/dashboard'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'
import { useWatchlistStore } from '@/stores/watchlist'
import { CHART_BAR_TYPES } from '@/types'
import type {
  DashboardTab,
  DashboardWidget,
  DashboardWidgetLayout,
  DashboardWidgetType,
  Timeframe,
} from '@/types'

const COL = 56
const ROW = 34
const GAP = 6
const MIN_W = 4
const MIN_H = 4

interface ScreenerOut {
  id: number
  name: string
  timeframe: string
}

const dashboardStore = useDashboardStore()
const watchlistStore = useWatchlistStore()
const alertsStore = useAlertsStore()
const screenerAlertsStore = useScreenerAlertsStore()
const screeners = ref<ScreenerOut[]>([])
const renamingTabId = ref<number | null>(null)
const tabRenameDraft = ref('')
const configWidget = ref<DashboardWidget | null>(null)

const timeframes: Timeframe[] = ['M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'MN']
const chartWidgetTypes = ['simple_chart', 'advanced_chart', 'comparison_chart', 'ratio_chart']

const widgetCatalog: Array<{
  type: DashboardWidgetType
  title: string
  description: string
}> = [
  { type: 'quote', title: 'Quote Card', description: 'Last price and daily change' },
  { type: 'simple_chart', title: 'Simple Chart', description: 'Line chart with axes' },
  { type: 'advanced_chart', title: 'Advanced Chart', description: 'Full chart engine' },
  { type: 'comparison_chart', title: 'Comparison Chart', description: 'Normalize several symbols' },
  { type: 'watchlist', title: 'Watchlist', description: 'Saved symbols' },
  { type: 'alerts', title: 'Alerts', description: 'Price and indicator alerts' },
  { type: 'screener', title: 'Screener Results', description: 'Latest run output' },
  { type: 'economic_calendar', title: 'Economic Calendar', description: 'Earnings, dividends, splits' },
  { type: 'heat_map', title: 'Heat Map', description: 'Watchlist sector performance' },
  { type: 'instrument_details', title: 'Instrument Details', description: 'Metadata and stats' },
  { type: 'notes', title: 'Notes', description: 'Freeform text' },
  { type: 'checklist', title: 'Checklist', description: 'Reusable task list' },
]

const widgets = computed(() =>
  [...(dashboardStore.activeTab?.widgets ?? [])].sort((a, b) => a.position - b.position || a.id - b.id)
)

const canvasStyle = computed(() => {
  const bounds = widgets.value.reduce(
    (acc, widget) => {
      const layout = normalizedLayout(widget.layout)
      acc.w = Math.max(acc.w, layout.x + layout.w)
      acc.h = Math.max(acc.h, layout.y + layout.h)
      return acc
    },
    { w: 0, h: 0 },
  )
  return {
    width: bounds.w > 0 ? `${bounds.w * (COL + GAP) + GAP}px` : '100%',
    height: bounds.h > 0 ? `${bounds.h * (ROW + GAP) + GAP}px` : '100%',
  }
})

let activeDrag:
  | {
      mode: 'move' | 'resize'
      widget: DashboardWidget
      startX: number
      startY: number
      startLayout: DashboardWidgetLayout
    }
  | null = null

async function reload() {
  try {
    await dashboardStore.loadDefaultDashboard()
  } catch {
    return
  }
  await Promise.allSettled([
    watchlistStore.loadWatchlists(),
    alertsStore.loadAlerts(),
    screenerAlertsStore.loadAlerts(),
    loadScreeners(),
  ])
}

function toggleEdit() {
  dashboardStore.setEditMode(!dashboardStore.editMode)
}

async function loadScreeners() {
  try {
    screeners.value = await api.get<ScreenerOut[]>('/screeners')
  } catch {
    screeners.value = []
  }
}

function widgetTitle(type: string) {
  return widgetCatalog.find(item => item.type === type)?.title ?? type
}

function finiteNumber(value: unknown, fallback: number) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function normalizedLayout(layout: Partial<DashboardWidgetLayout> = {}) {
  return {
    x: Math.max(0, Math.round(finiteNumber(layout.x, 0))),
    y: Math.max(0, Math.round(finiteNumber(layout.y, 0))),
    w: Math.max(MIN_W, Math.round(finiteNumber(layout.w, MIN_W))),
    h: Math.max(MIN_H, Math.round(finiteNumber(layout.h, MIN_H))),
  }
}

function widgetStyle(widget: DashboardWidget) {
  const layout = normalizedLayout(widget.layout)
  return {
    left: `${layout.x * (COL + GAP) + GAP}px`,
    top: `${layout.y * (ROW + GAP) + GAP}px`,
    width: `${layout.w * COL + (layout.w - 1) * GAP}px`,
    height: `${layout.h * ROW + (layout.h - 1) * GAP}px`,
  }
}

function inputValue(event: Event) {
  return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value
}

function startTabRename(tab: DashboardTab) {
  if (!dashboardStore.editMode) return
  renamingTabId.value = tab.id
  tabRenameDraft.value = tab.name
  nextTick(() => document.querySelector<HTMLInputElement>('.tab-input')?.select())
}

async function commitTabRename(tab: DashboardTab) {
  if (renamingTabId.value !== tab.id) return
  const name = tabRenameDraft.value.trim()
  renamingTabId.value = null
  if (name && name !== tab.name) await dashboardStore.renameTab(tab.id, name)
}

async function addWidget(type: DashboardWidgetType) {
  const spot = nextWidgetSpot()
  const widget = await dashboardStore.addWidget({
    widget_type: type,
    title: null,
    layout: defaultLayout(type, spot),
    config: defaultConfig(type),
    style: {},
  })
  if (widget) configWidget.value = widget
}

function nextWidgetSpot() {
  const maxBottom = widgets.value.reduce((max, widget) => {
    const layout = normalizedLayout(widget.layout)
    return Math.max(max, layout.y + layout.h)
  }, 0)
  return { x: 0, y: maxBottom }
}

function defaultLayout(type: DashboardWidgetType, spot: { x: number; y: number }) {
  const sizes: Record<string, { w: number; h: number }> = {
    quote: { w: 6, h: 6 },
    simple_chart: { w: 10, h: 8 },
    advanced_chart: { w: 16, h: 12 },
    comparison_chart: { w: 12, h: 8 },
    ratio_chart: { w: 10, h: 8 },
    watchlist: { w: 9, h: 10 },
    alerts: { w: 8, h: 8 },
    screener: { w: 10, h: 8 },
    economic_calendar: { w: 10, h: 8 },
    heat_map: { w: 12, h: 9 },
    instrument_details: { w: 8, h: 8 },
    notes: { w: 8, h: 6 },
    checklist: { w: 8, h: 7 },
  }
  return { x: spot.x, y: spot.y, ...(sizes[type] ?? { w: 8, h: 6 }) }
}

function defaultConfig(type: DashboardWidgetType) {
  if (type === 'comparison_chart') {
    return {
      targets: [
        { symbol: 'SPY', label: 'SPY', color: '#64b5f6' },
        { symbol: 'QQQ', label: 'QQQ', color: '#81c784' },
        { symbol: 'DIA', label: 'DIA', color: '#ffb74d' },
      ],
      timeframe: 'D1',
      normalize: true,
    }
  }
  if (type === 'ratio_chart') return { expression: 'SPY/GLD', timeframe: 'D1' }
  if (type === 'watchlist') return { watchlistId: null, showSparklines: true }
  if (type === 'heat_map') return { watchlistId: null }
  if (type === 'screener') return { screenerId: null }
  if (type === 'economic_calendar') return { symbol: 'SPY' }
  if (type === 'alerts') return {}
  if (type === 'notes') return { text: '' }
  if (type === 'checklist') {
    return {
      mode: 'checklist',
      items: [
        { id: 'macro', text: 'Review macro calendar', done: false },
        { id: 'alerts', text: 'Check active alerts', done: false },
      ],
    }
  }
  if (type === 'advanced_chart') {
    return {
      symbol: 'SPY',
      timeframe: 'D1',
      chartType: 'candles',
      showIndicators: true,
      showDrawings: true,
      showAlerts: true,
    }
  }
  return { symbol: 'SPY', timeframe: 'D1', chartType: 'line' }
}

async function duplicateWidget(widget: DashboardWidget) {
  const layout = normalizedLayout(widget.layout)
  await dashboardStore.addWidget({
    widget_type: widget.widget_type as DashboardWidgetType,
    title: widget.title,
    layout: { ...layout, x: layout.x + 1, y: layout.y + 1 },
    config: { ...widget.config },
    style: { ...widget.style },
  })
}

async function patchWidget(widget: DashboardWidget, patch: Partial<DashboardWidget>) {
  await dashboardStore.updateWidget(widget.id, patch)
}

async function patchConfig(widget: DashboardWidget, patch: Record<string, any>) {
  await dashboardStore.updateWidget(widget.id, {
    config: { ...widget.config, ...patch },
  })
}

function patchConfigLocal(widget: DashboardWidget, patch: Record<string, any>) {
  widget.config = { ...widget.config, ...patch }
}

function checkboxValue(event: Event) {
  return (event.target as HTMLInputElement).checked
}

function comparisonTargets(widget: DashboardWidget) {
  if (Array.isArray(widget.config.targets) && widget.config.targets.length) {
    return widget.config.targets.map((target: any, index: number) => ({
      symbol: String(target.symbol ?? ''),
      label: String(target.label ?? target.symbol ?? ''),
      color: String(target.color ?? defaultColor(index)),
    }))
  }
  return String(widget.config.symbols ?? 'SPY,QQQ,DIA')
    .split(',')
    .map((symbol, index) => ({
      symbol: symbol.trim(),
      label: symbol.trim(),
      color: defaultColor(index),
    }))
    .filter(target => target.symbol)
}

function defaultColor(index: number) {
  return ['#64b5f6', '#81c784', '#ffb74d', '#ba68c8', '#f06292', '#4dd0e1'][index % 6]
}

function patchComparisonTargetLocal(widget: DashboardWidget, index: number, patch: Record<string, any>) {
  const targets = comparisonTargets(widget)
  targets[index] = { ...targets[index], ...patch }
  widget.config = { ...widget.config, targets }
}

async function patchComparisonTarget(widget: DashboardWidget, index: number, patch: Record<string, any>) {
  patchComparisonTargetLocal(widget, index, patch)
  await dashboardStore.updateWidget(widget.id, { config: widget.config })
}

async function addComparisonTarget(widget: DashboardWidget) {
  const targets = comparisonTargets(widget)
  targets.push({ symbol: 'IWM', label: 'IWM', color: defaultColor(targets.length) })
  await patchConfig(widget, { targets })
}

async function removeComparisonTarget(widget: DashboardWidget, index: number) {
  const targets = comparisonTargets(widget).filter((_, i) => i !== index)
  await patchConfig(widget, { targets })
}

function startMove(event: PointerEvent, widget: DashboardWidget) {
  if (!dashboardStore.editMode) return
  if ((event.target as HTMLElement).closest('button,input,select,textarea,a')) return
  beginDrag(event, widget, 'move')
}

function startResize(event: PointerEvent, widget: DashboardWidget) {
  beginDrag(event, widget, 'resize')
}

function beginDrag(event: PointerEvent, widget: DashboardWidget, mode: 'move' | 'resize') {
  activeDrag = {
    mode,
    widget,
    startX: event.clientX,
    startY: event.clientY,
    startLayout: normalizedLayout(widget.layout),
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp, { once: true })
}

function onPointerMove(event: PointerEvent) {
  if (!activeDrag) return
  const dx = Math.round((event.clientX - activeDrag.startX) / (COL + GAP))
  const dy = Math.round((event.clientY - activeDrag.startY) / (ROW + GAP))
  const next =
    activeDrag.mode === 'move'
      ? {
          ...activeDrag.startLayout,
          x: Math.max(0, activeDrag.startLayout.x + dx),
          y: Math.max(0, activeDrag.startLayout.y + dy),
        }
      : {
          ...activeDrag.startLayout,
          w: Math.max(MIN_W, activeDrag.startLayout.w + dx),
          h: Math.max(MIN_H, activeDrag.startLayout.h + dy),
        }
  activeDrag.widget.layout = next
}

async function onPointerUp() {
  if (!activeDrag) return
  const { widget } = activeDrag
  activeDrag = null
  window.removeEventListener('pointermove', onPointerMove)
  try {
    await dashboardStore.saveWidgetLayout(widget.id, normalizedLayout(widget.layout))
  } catch (e) {
    console.error('Failed to save dashboard widget layout', e)
  }
}

onMounted(reload)
onUnmounted(() => {
  window.removeEventListener('pointermove', onPointerMove)
})
</script>

<style scoped>
.dashboard-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #080808;
  color: #ccc;
  min-width: 0;
}
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px 10px;
  border-bottom: 1px solid #181818;
  background: #0b0b0b;
  flex-shrink: 0;
}
.dashboard-header h1 {
  font-size: 18px;
  color: #f2f2f2;
  margin: 0 0 4px;
}
.dashboard-header p {
  color: #666;
  font-size: 11px;
}
.header-actions { display: flex; gap: 8px; align-items: center; }
.dash-btn,
.tab-add,
.catalog-item,
.widget-tools button {
  background: #151515;
  color: #bbb;
  border: 1px solid #282828;
  border-radius: 6px;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}
.dash-btn {
  padding: 7px 11px;
}
.dash-btn:hover,
.tab-add:hover,
.catalog-item:hover,
.widget-tools button:hover { border-color: #3a3a3a; background: #1b1b1b; }
.dash-btn.primary.active,
.dash-btn.primary:hover {
  color: #64b5f6;
  border-color: #245177;
  background: #0e1a24;
}
.tab-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 18px;
  border-bottom: 1px solid #171717;
  background: #0a0a0a;
  flex-shrink: 0;
}
.tab-btn {
  height: 28px;
  min-width: 84px;
  padding: 0 12px;
  border: 1px solid #222;
  border-radius: 6px;
  background: #111;
  color: #777;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
}
.tab-btn.active {
  color: #eee;
  border-color: #345;
  background: #121a20;
}
.tab-input {
  width: 90px;
  background: #050505;
  color: #eee;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 3px 5px;
  font-family: inherit;
  font-size: 11px;
}
.tab-add {
  padding: 6px 9px;
}
.tab-add.danger,
.widget-tools .danger { color: #ef5350; }
.dashboard-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 13px;
}
.dashboard-state.error { color: #ef5350; }
.dashboard-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.widget-catalog {
  width: 216px;
  padding: 10px;
  border-right: 1px solid #181818;
  background: #0a0a0a;
  overflow-y: auto;
  flex-shrink: 0;
}
.catalog-title {
  color: #777;
  font-size: 10px;
  text-transform: uppercase;
  margin: 2px 2px 8px;
}
.catalog-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  padding: 9px;
  margin-bottom: 7px;
}
.catalog-item span { color: #ddd; font-size: 12px; }
.catalog-item small { color: #666; font-size: 10px; line-height: 1.35; }
.dashboard-scroll {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  background-color: #080808;
  background-image:
    linear-gradient(#101010 1px, transparent 1px),
    linear-gradient(90deg, #101010 1px, transparent 1px);
  background-size: 62px 40px;
}
.dashboard-canvas {
  position: relative;
  min-width: 100%;
  min-height: 100%;
}
.canvas-empty {
  position: absolute;
  inset: 0;
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 14px;
  color: #666;
  text-align: center;
  font-size: 12px;
}
.canvas-empty strong {
  display: block;
  color: #ddd;
  font-size: 15px;
  margin-bottom: 6px;
}
.canvas-empty span { display: block; }
.dashboard-widget {
  position: absolute;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #222;
  border-radius: 6px;
  background: #0d0d0d;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
}
.dashboard-widget.editing {
  border-color: #2f4d62;
}
.widget-header {
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 9px;
  border-bottom: 1px solid #1c1c1c;
  background: #111;
  flex-shrink: 0;
}
.editing .widget-header { cursor: move; }
.widget-title {
  color: #ddd;
  font-size: 11px;
  font-weight: 700;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.widget-tools {
  display: flex;
  gap: 5px;
  flex-shrink: 0;
}
.widget-tools button {
  padding: 3px 6px;
  font-size: 10px;
}
.widget-body {
  flex: 1;
  min-height: 0;
  padding: 9px;
  overflow: hidden;
}
.list-widget {
  height: 100%;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.list-row {
  display: grid;
  grid-template-columns: 76px 1fr auto;
  gap: 8px;
  align-items: center;
  min-height: 28px;
  padding: 5px 0;
  border-bottom: 1px solid #181818;
  font-size: 11px;
}
.list-row a {
  color: #64b5f6;
  text-decoration: none;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}
.list-row span {
  color: #888;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.list-row b {
  font-size: 9px;
  color: #777;
  font-weight: 500;
}
.list-row b.active { color: #81c784; }
.list-row b.triggered { color: #ffb74d; }
.empty-small {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
}
.resize-handle {
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 14px;
  height: 14px;
  border: 1px solid #37627e;
  border-radius: 3px;
  background: #0f1f2e;
  cursor: nwse-resize;
}
.config-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.62);
}
.config-modal {
  width: min(680px, calc(100vw - 72px));
  max-height: min(720px, calc(100vh - 72px));
  display: flex;
  flex-direction: column;
  border: 1px solid #2c2c2c;
  border-radius: 6px;
  background: #101010;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.55);
}
.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid #1f1f1f;
}
.config-header strong {
  display: block;
  color: #eee;
  font-size: 13px;
}
.config-header span {
  display: block;
  color: #666;
  font-size: 10px;
  margin-top: 3px;
}
.config-header button,
.config-add,
.comparison-config-row button {
  background: #151515;
  color: #aaa;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 5px 8px;
  font-family: inherit;
  font-size: 10px;
  cursor: pointer;
}
.config-body {
  padding: 14px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 13px;
}
.config-field {
  display: grid;
  gap: 6px;
  color: #777;
  font-size: 10px;
}
.config-field > input,
.config-field > select {
  width: 100%;
  background: #050505;
  color: #ccc;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 7px 8px;
  font-family: inherit;
  font-size: 11px;
}
.config-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #aaa;
  font-size: 11px;
}
.comparison-config-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 42px auto;
  gap: 7px;
  align-items: center;
  margin-bottom: 7px;
}
.comparison-config-row input[type='color'] {
  width: 42px;
  height: 30px;
  padding: 2px;
  background: #050505;
  border: 1px solid #282828;
  border-radius: 4px;
}
</style>
