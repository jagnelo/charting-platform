<template>
  <div class="side-panel">

    <!-- ── Indicators section ──────────────────────────────────────────── -->
    <div class="section" :class="{ collapsed: !indicatorsOpen }">
      <div class="section-header" @click="indicatorsOpen = !indicatorsOpen">
        <span class="section-title">Indicators</span>
        <span class="section-count">{{ chartStore.indicators.length }}</span>
        <span class="section-chevron">{{ indicatorsOpen ? '▴' : '▾' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-body" v-if="indicatorsOpen">
          <div class="ind-list">
            <div
              v-for="(ind, i) in chartStore.indicators"
              :key="i"
              class="list-row"
              :class="{ 'row--tf-inactive': !isActiveOnCurrentTf(ind) }"
              :title="isActiveOnCurrentTf(ind) ? undefined : `Locked to: ${(ind.lockedTimeframes ?? []).join(', ')}`"
            >
              <span class="color-dot" :style="{ background: ind.style.color }" />
              <span class="row-name">{{ displayName(ind) }}</span>
              <span v-if="ind.lockedTimeframes?.length" class="tf-lock-badge" title="Timeframe locked">🔒</span>
              <button class="row-btn" @click="alertForIndicator(i)" title="Create alert">🔔</button>
              <button class="row-btn" @click="openIndEditor(i)" title="Settings">⚙</button>
              <button class="row-btn danger" @click="chartStore.removeIndicator(i)" title="Remove">✕</button>
            </div>
            <div v-if="!chartStore.indicators.length" class="empty-hint">
              No indicators for this ticker
              <button v-if="presetsStore.getDefault()" class="hint-btn" @click="applyDefault">Apply default preset</button>
            </div>
          </div>

          <!-- Picker -->
          <div class="add-bar">
            <button class="add-btn" @click="showPicker = !showPicker">+ Add</button>
          </div>
          <div v-if="showPicker" class="picker-dropdown">
            <button
              v-for="t in availableTypes"
              :key="t.type"
              class="picker-item"
              @click="addIndicator(t.type)"
            >{{ t.label }}</button>
          </div>

          <!-- Presets -->
          <div class="preset-bar">
            <select v-model="selectedPresetId" class="preset-select">
              <option value="">— Preset —</option>
              <option v-for="p in presetsStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <button class="preset-btn" @click="applyPreset" title="Apply preset">↓</button>
            <button class="preset-btn" @click="saveAsPreset" title="Save as preset">✎</button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Drawings section ────────────────────────────────────────────── -->
    <div class="section section--drawings" :class="{ collapsed: !drawingsOpen }">
      <div class="section-header" @click="drawingsOpen = !drawingsOpen">
        <span class="section-title">Drawings</span>
        <span class="section-count">{{ drawStore.drawings.length }}</span>
        <span class="section-chevron">{{ drawingsOpen ? '▴' : '▾' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-body" v-if="drawingsOpen">
          <div class="ind-list">
            <div
              v-for="d in drawStore.drawings"
              :key="d.id"
              class="list-row"
              :class="{ 'row--selected': d.id === drawStore.selectedId, 'row--hidden': !d.is_visible }"
              @click="drawStore.selectDrawing(d.id)"
            >
              <span class="draw-icon">{{ drawingIcon(d.drawing_type) }}</span>
              <span class="row-name">{{ drawingLabel(d) }}</span>
              <!-- Visibility toggle -->
              <button
                class="row-btn"
                :class="{ 'btn--dim': !d.is_visible }"
                @click.stop="toggleVisible(d)"
                :title="d.is_visible ? 'Hide' : 'Show'"
              >{{ d.is_visible ? '👁' : '🚫' }}</button>
              <!-- Lock toggle -->
              <button
                class="row-btn"
                :class="{ 'btn--active': d.is_locked }"
                @click.stop="toggleLock(d)"
                :title="d.is_locked ? 'Unlock' : 'Lock'"
              >{{ d.is_locked ? '🔒' : '🔓' }}</button>
              <!-- Edit -->
              <button class="row-btn" @click.stop="openDrawEditor(d)" title="Edit">⚙</button>
              <!-- Delete -->
              <button class="row-btn danger" @click.stop="drawStore.deleteDrawing(d.id)" title="Delete">✕</button>
            </div>
            <div v-if="!drawStore.drawings.length" class="empty-hint">No drawings</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Alerts section ──────────────────────────────────────────── -->
    <div class="section section--alerts" :class="{ collapsed: !alertsOpen }">
      <div class="section-header" @click="alertsOpen = !alertsOpen">
        <span class="section-title">Alerts</span>
        <span class="section-count">{{ instrumentAlerts.length }}</span>
        <span class="section-chevron">{{ alertsOpen ? '▴' : '▾' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-body" v-if="alertsOpen">
          <div class="ind-list">
            <!-- Price alerts -->
            <div
              v-for="a in instrumentPriceAlerts"
              :key="'p'+a.id"
              class="list-row alert-row"
              :class="`alert-row--${a.status}`"
            >
              <span class="alert-icon">¤</span>
              <span class="row-name">{{ a.condition.replace(/_/g,' ') }} {{ formatMoney(Number(a.threshold_price), a.instrument_currency) }}</span>
              <button class="row-btn" @click.stop="openAlertEditor(a, null)" title="Edit">⚙</button>
              <button class="row-btn" :class="{ 'btn--active': a.repeat }"
                      @click.stop="alertsStore.updateAlert(a.id, { repeat: !a.repeat })" title="Toggle repeat">↺</button>
              <button class="row-btn" v-if="a.status==='active'"
                      @click.stop="alertsStore.updateAlert(a.id, { status: 'paused' })" title="Pause">⏸</button>
              <button class="row-btn" v-if="a.status==='paused'"
                      @click.stop="alertsStore.updateAlert(a.id, { status: 'active' })" title="Resume">▶</button>
              <button class="row-btn" v-if="a.status==='triggered'"
                      @click.stop="alertsStore.rearmAlert(a.id)" title="Rearm">↺</button>
              <button class="row-btn danger" @click.stop="alertsStore.deleteAlert(a.id)" title="Delete">✕</button>
            </div>
            <!-- Indicator alerts -->
            <div
              v-for="a in instrumentIndicatorAlerts"
              :key="'i'+a.id"
              class="list-row alert-row"
              :class="`alert-row--${a.status}`"
              :title="indAlertLabel(a)"
            >
              <span class="alert-icon">≈</span>
              <span class="row-name">{{ indAlertLabel(a) }}</span>
              <button class="row-btn" @click.stop="openAlertEditor(null, a)" title="Edit">⚙</button>
              <button class="row-btn" :class="{ 'btn--active': a.repeat }"
                      @click.stop="alertsStore.updateIndicatorAlert(a.id, { repeat: !a.repeat })" title="Toggle repeat">↺</button>
              <button class="row-btn" v-if="a.status==='active'"
                      @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'paused' })" title="Pause">⏸</button>
              <button class="row-btn" v-if="a.status==='paused'"
                      @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'active' })" title="Resume">▶</button>
              <button class="row-btn" v-if="a.status==='triggered'"
                      @click.stop="alertsStore.rearmIndicatorAlert(a.id)" title="Rearm">↺</button>
              <button class="row-btn danger" @click.stop="alertsStore.deleteIndicatorAlert(a.id)" title="Delete">✕</button>
            </div>
            <div v-if="!instrumentAlerts.length" class="empty-hint">No alerts for this ticker</div>
          </div>
          <div class="add-bar">
            <button class="add-btn" @click="openAlertEditor(null, null)">+ Add Alert</button>
          </div>
        </div>
      </Transition>
    </div>

  </div>

  <!-- ── Indicator editor popup ──────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="indEditorOpen" @click.self="closeIndEditor">
        <div class="editor-box">
          <div class="ed-header">
            <span>{{ editingInd?.type.toUpperCase() }} Settings</span>
            <button class="ed-close" @click="closeIndEditor">✕</button>
          </div>
          <div class="ed-body" v-if="editingInd">
            <div class="ed-row">
              <label>Colour</label>
              <input type="color" v-model="indFields.color" class="ed-color" />
            </div>
            <div class="ed-row">
              <label>Line width</label>
              <input type="range" min="0.5" max="4" step="0.5" v-model.number="indFields.lineWidth" class="ed-range" />
              <span class="ed-val">{{ indFields.lineWidth }}px</span>
            </div>
            <template v-for="(_, key) in editingInd.params" :key="key">
              <div class="ed-row">
                <label>{{ paramLabel(key as string) }}</label>
                <template v-if="key === 'anchorTime'">
                  <input
                    type="datetime-local"
                    :value="tsToDateInput(indFields.params.anchorTime as number)"
                    @input="e => indFields.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                    class="ed-input"
                  />
                </template>
                <template v-else>
                  <input type="number" v-model.number="indFields.params[key as string]" min="1" class="ed-input ed-num" />
                </template>
              </div>
            </template>
            <!-- AVWAP without anchorTime yet -->
            <div class="ed-row" v-if="editingInd.type === 'avwap' && !('anchorTime' in editingInd.params)">
              <label>Anchor date</label>
              <input
                type="datetime-local"
                :value="tsToDateInput(indFields.params.anchorTime as number)"
                @input="e => indFields.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                class="ed-input"
              />
            </div>
            <div class="ed-row" v-if="['rsi','macd'].includes(editingInd.type)">
              <label>Pane</label>
              <select v-model="indFields.pane" class="ed-input">
                <option value="main">Main chart</option>
                <option value="separate">Separate subplot</option>
              </select>
            </div>
            <div class="ed-sep" />
            <div class="ed-row">
              <label>Timeframes</label>
              <select v-model="indFields.tfMode" class="ed-input">
                <option value="all">All timeframes</option>
                <option value="locked">Selected only</option>
              </select>
            </div>
            <div v-if="indFields.tfMode === 'locked'" class="ed-tf-grid">
              <label
                v-for="tf in allTimeframes"
                :key="tf"
                class="ed-tf-chip"
                :class="{ 'ed-tf-chip--on': indFields.lockedTimeframes.includes(tf) }"
              >
                <input type="checkbox" :value="tf" v-model="indFields.lockedTimeframes" class="ed-tf-check" />
                {{ tf }}
              </label>
            </div>
          </div>
          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyIndEdit">Apply</button>
            <button class="ed-btn" @click="closeIndEditor">Cancel</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- ── Alert editor popup ────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="alertEditorOpen && chartStore.instrument" @click.self="closeAlertEditor">
        <AlertForm
          :instrument-id="chartStore.instrument.id"
          :symbol="chartStore.symbol"
          :current-tf="chartStore.timeframe"
          :seed-indicator="alertSeedIndicator"
          :edit-price-alert="editingPriceAlertData"
          :edit-indicator-alert="editingIndicatorAlertData"
          @close="closeAlertEditor"
        />
      </div>
    </Transition>
  </Teleport>

  <!-- ── Drawing editor popup ────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="editor-backdrop" v-if="drawEditorOpen" @click.self="closeDrawEditor">
        <div class="editor-box">
          <div class="ed-header">
            <span>{{ editingDraw ? drawingLabel(editingDraw) : '' }} Settings</span>
            <button class="ed-close" @click="closeDrawEditor">✕</button>
          </div>
          <div class="ed-body" v-if="editingDraw">
            <div class="ed-row">
              <label>Colour</label>
              <input type="color" v-model="drawFields.color" class="ed-color" />
            </div>
            <div class="ed-row">
              <label>Line width</label>
              <input type="range" min="0.5" max="4" step="0.5" v-model.number="drawFields.lineWidth" class="ed-range" />
              <span class="ed-val">{{ drawFields.lineWidth }}px</span>
            </div>
            <div class="ed-row">
              <label>Label</label>
              <input type="text" v-model="drawFields.label" placeholder="Optional label" class="ed-input" />
            </div>
            <div class="ed-row">
              <label>Notes</label>
              <input type="text" v-model="drawFields.notes" placeholder="Optional notes" class="ed-input" />
            </div>

            <!-- Coordinate editing -->
            <template v-if="drawPoints.length">
              <div class="ed-sep" />
              <template v-for="(pt, i) in drawPoints" :key="i">
                <div class="ed-point-title">{{ drawPointLabel(editingDraw.drawing_type, i, drawPoints.length) }}</div>
                <div class="ed-row" v-if="editingDraw.drawing_type !== 'horizontal_line'">
                  <label>Date / Time</label>
                  <input type="datetime-local" :value="tsToDateInput(pt.time)"
                         @change="onDrawPointTime(i, ($event.target as HTMLInputElement).value)"
                         class="ed-input" />
                </div>
                <div class="ed-row" v-if="editingDraw.drawing_type !== 'vertical_line'">
                  <label>Price</label>
                  <input type="number" step="any" :value="pt.price"
                         @change="onDrawPointPrice(i, Number(($event.target as HTMLInputElement).value))"
                         class="ed-input ed-num" />
                </div>
              </template>
            </template>
          </div>
          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyDrawEdit">Apply</button>
            <button class="ed-btn" @click="closeDrawEditor">Cancel</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import { formatMoney } from '@/lib/format'
import { useChartStore }   from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { usePresetsStore }  from '@/stores/presets'
import AlertForm from '@/components/alerts/AlertForm.vue'
import type { ChartDrawing, IndicatorAlert, PriceAlert, IndicatorConfig, IndicatorType } from '@/types'


const alertsStore  = useAlertsStore()
const chartStore   = useChartStore()
const drawStore    = useDrawingsStore()
const presetsStore = usePresetsStore()

// ── Section collapse state ────────────────────────────────────────────────────
const alertsOpen     = ref(true)
const indicatorsOpen = ref(true)
const drawingsOpen   = ref(true)

// ── Indicators ─────────────────────────────────────────────────────────────────
const showPicker       = ref(false)
const selectedPresetId = ref<number | ''>('')

const availableTypes: Array<{ type: IndicatorType; label: string }> = [
  { type: 'sma',    label: 'SMA — Simple Moving Average'       },
  { type: 'ema',    label: 'EMA — Exponential Moving Average'  },
  { type: 'vwap',   label: 'VWAP — Volume Weighted Avg Price'  },
  { type: 'avwap',  label: 'AVWAP — Anchored VWAP'             },
  { type: 'rsi',    label: 'RSI — Relative Strength Index'     },
  { type: 'bb',     label: 'BB — Bollinger Bands'              },
  { type: 'macd',   label: 'MACD — Moving Avg Convergence Div' },
  { type: 'volume', label: 'Volume bars'                       },
]

const DEFAULTS: Record<IndicatorType, IndicatorConfig> = {
  sma:    { type: 'sma',    params: { period: 20 }, style: { color: '#ffb74d', lineWidth: 1.5 }, pane: 'main'     },
  ema:    { type: 'ema',    params: { period: 50 }, style: { color: '#64b5f6', lineWidth: 1.5 }, pane: 'main'     },
  vwap:   { type: 'vwap',   params: {},             style: { color: '#ce93d8', lineWidth: 2   }, pane: 'main'     },
  avwap:  { type: 'avwap',  params: { anchorTime: Math.floor(Date.now() / 1000) - 86400 * 30 },
                                                    style: { color: '#80cbc4', lineWidth: 2   }, pane: 'main'     },
  rsi:    { type: 'rsi',    params: { period: 14 }, style: { color: '#ef9a9a', lineWidth: 1.5 }, pane: 'separate' },
  bb:     { type: 'bb',     params: { period: 20, stdDev: 2 }, style: { color: '#a5d6a7', lineWidth: 1 }, pane: 'main' },
  macd:   { type: 'macd',   params: { fast: 12, slow: 26, signal: 9 }, style: { color: '#ef5350', lineWidth: 1.5 }, pane: 'separate' },
  volume: { type: 'volume', params: {},             style: { color: '#4db6ac', lineWidth: 1   }, pane: 'main'     },
}

function isActiveOnCurrentTf(ind: IndicatorConfig): boolean {
  return !ind.lockedTimeframes?.length || ind.lockedTimeframes.includes(chartStore.timeframe)
}

function displayName(ind: IndicatorConfig): string {
  if (ind.type === 'avwap' && ind.params.anchorTime) {
    const d = new Date((ind.params.anchorTime as number) * 1000)
    const label = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
    return `AVWAP(${label})`
  }
  const params = Object.values(ind.params).join(',')
  return params ? `${ind.type.toUpperCase()}(${params})` : ind.type.toUpperCase()
}

function addIndicator(type: IndicatorType) {
  chartStore.addIndicator({ ...DEFAULTS[type], params: { ...DEFAULTS[type].params } })
  showPicker.value = false
}

function applyPreset() {
  if (!selectedPresetId.value) return
  const preset = presetsStore.presets.find(p => p.id === selectedPresetId.value)
  if (preset) chartStore.setIndicators([...preset.indicators])
}

function applyDefault() {
  const def = presetsStore.getDefault()
  if (def) chartStore.setIndicators([...def.indicators])
}

async function saveAsPreset() {
  const name = prompt('Preset name:')
  if (!name) return
  await presetsStore.savePreset(name, [...chartStore.indicators])
}

// ── Drawings helpers ──────────────────────────────────────────────────────────
const DRAW_ICONS: Record<string, string> = {
  trendline: '╱', ray: '→', horizontal_line: '─', vertical_line: '│',
  rectangle: '▭', circle: '○', fibonacci_retracement: 'φ',
  fibonacci_extension: 'φ+', arrow: '↗', text_box: 'T',
}

function drawingIcon(type: string): string {
  return DRAW_ICONS[type] ?? '✎'
}

function drawingLabel(d: ChartDrawing): string {
  if (d.label) return d.label
  const name = d.drawing_type.replace(/_/g, ' ')
  // If it has points with a price, show it
  const pts = (d.data as any)?.points
  if (pts?.length) {
    const price = pts[0]?.price
    if (price != null) return `${name} @ ${Number(price).toFixed(2)}`
  }
  return name
}

async function toggleVisible(d: ChartDrawing) {
  await drawStore.updateDrawing(d.id, { is_visible: !d.is_visible })
}

async function toggleLock(d: ChartDrawing) {
  await drawStore.updateDrawing(d.id, { is_locked: !d.is_locked })
}

// ── Indicator editor ──────────────────────────────────────────────────────────
const indEditorOpen = ref(false)
let   editingIndIdx = -1
const editingInd = ref<IndicatorConfig | null>(null)
const allTimeframes = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN'] as const
const indFields  = reactive({
  color: '#fff',
  lineWidth: 1.5,
  pane: 'main' as 'main'|'separate',
  params: {} as Record<string, unknown>,
  tfMode: 'all' as 'all'|'locked',
  lockedTimeframes: [] as string[],
})

function openIndEditor(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  editingIndIdx = i
  editingInd.value = ind
  indFields.color            = ind.style.color
  indFields.lineWidth        = ind.style.lineWidth ?? 1.5
  indFields.pane             = (ind.pane ?? 'main') as 'main'|'separate'
  indFields.params           = { ...ind.params }
  indFields.lockedTimeframes = ind.lockedTimeframes ? [...ind.lockedTimeframes] : []
  indFields.tfMode           = indFields.lockedTimeframes.length ? 'locked' : 'all'
  indEditorOpen.value = true
}

function alertForIndicator(i: number) {
  openAlertEditor(null, null, chartStore.indicators[i])
}

function closeIndEditor() { indEditorOpen.value = false; editingInd.value = null; editingIndIdx = -1 }

function applyIndEdit() {
  if (editingIndIdx < 0) return
  chartStore.updateIndicator(editingIndIdx, {
    ...chartStore.indicators[editingIndIdx],
    style:            { ...chartStore.indicators[editingIndIdx].style, color: indFields.color, lineWidth: indFields.lineWidth },
    pane:             indFields.pane,
    params:           { ...indFields.params },
    lockedTimeframes: indFields.tfMode === 'locked' && indFields.lockedTimeframes.length
      ? [...indFields.lockedTimeframes] as import('@/types').Timeframe[]
      : null,
  })
  closeIndEditor()
}

const instrumentPriceAlerts = computed(() =>
  alertsStore.alerts.filter(a => a.instrument_id === chartStore.instrument?.id)
)
const instrumentIndicatorAlerts = computed(() =>
  alertsStore.indicatorAlerts.filter(a => a.instrument_id === chartStore.instrument?.id)
)
const instrumentAlerts = computed(() =>
  [...instrumentPriceAlerts.value, ...instrumentIndicatorAlerts.value]
)

// ── Alert editor ──────────────────────────────────────────────────────────────
const alertEditorOpen           = ref(false)
const editingPriceAlertData     = ref<PriceAlert | null>(null)
const editingIndicatorAlertData = ref<IndicatorAlert | null>(null)
const alertSeedIndicator        = ref<IndicatorConfig | null>(null)

function openAlertEditor(price: PriceAlert | null, indicator: IndicatorAlert | null, seed: IndicatorConfig | null = null) {
  editingPriceAlertData.value     = price
  editingIndicatorAlertData.value = indicator
  alertSeedIndicator.value        = seed
  alertEditorOpen.value = true
}

function closeAlertEditor() {
  alertEditorOpen.value = false
  editingPriceAlertData.value     = null
  editingIndicatorAlertData.value = null
  alertSeedIndicator.value        = null
}

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`
}

function fmtIndParams(type: string, params: Record<string, unknown>): string {
  if (!params || !Object.keys(params).length) return type.toUpperCase()
  if (type === 'avwap' && params.anchorTime) return `AVWAP(${fmtTs(params.anchorTime as number)})`
  return `${type.toUpperCase()}(${Object.values(params).join(',')})`
}

function indAlertLabel(a: IndicatorAlert): string {
  const indA = fmtIndParams(a.indicator_a_type, a.indicator_a_params ?? {})
  const cond = a.condition.replace(/_/g, ' ')
  const expr = a.indicator_b_type
    ? `${indA} ${cond} ${fmtIndParams(a.indicator_b_type, a.indicator_b_params ?? {})}`
    : `${indA} ${cond} ${a.threshold_value ?? ''}`
  return `${expr} · ${a.timeframe}`
}

// ── Drawing editor ────────────────────────────────────────────────────────────
const drawEditorOpen = ref(false)
const editingDraw    = ref<ChartDrawing | null>(null)
const drawFields     = reactive({ color: '#fff', lineWidth: 1.5, label: '', notes: '' })
const drawPoints     = ref<Array<{ time: number; price: number }>>([])
let   drawOriginalPoints: Array<{ time: number; price: number }> = []

function openDrawEditor(d: ChartDrawing) {
  editingDraw.value    = d
  drawFields.color     = d.style?.color ?? '#ffffff'
  drawFields.lineWidth = d.style?.lineWidth ?? 1.5
  drawFields.label     = d.label ?? ''
  drawFields.notes     = d.notes ?? ''
  const pts = ((d.data as any)?.points ?? []) as Array<{ time: number; price: number }>
  drawOriginalPoints   = pts.map(p => ({ ...p }))
  drawPoints.value     = pts.map(p => ({ ...p }))
  drawEditorOpen.value = true
}

function closeDrawEditor() {
  // Revert any live coordinate preview changes if user cancels
  if (editingDraw.value) {
    drawStore.localUpdateDrawing(editingDraw.value.id, {
      data: { ...(editingDraw.value.data as any), points: drawOriginalPoints },
    } as any)
  }
  drawEditorOpen.value = false
  editingDraw.value    = null
  drawPoints.value     = []
}

function onDrawPointTime(idx: number, val: string) {
  if (!editingDraw.value) return
  const ts = dateInputToTs(val)
  if (!isFinite(ts)) return
  drawPoints.value[idx] = { ...drawPoints.value[idx], time: ts }
  _livePreviewPoints()
}

function onDrawPointPrice(idx: number, price: number) {
  if (!editingDraw.value || !isFinite(price)) return
  drawPoints.value[idx] = { ...drawPoints.value[idx], price }
  _livePreviewPoints()
}

function _livePreviewPoints() {
  if (!editingDraw.value) return
  drawStore.localUpdateDrawing(editingDraw.value.id, {
    data: { ...(editingDraw.value.data as any), points: drawPoints.value.map(p => ({ ...p })) },
  } as any)
}

function drawPointLabel(type: string, idx: number, total: number): string {
  if (total === 1) return 'Point'
  const labels: Record<string, string[]> = {
    rectangle: ['Top-left', 'Bottom-right'],
    fibonacci_retracement: ['Start', 'End'],
    fibonacci_extension: ['Start', 'End'],
    circle: ['Top-left', 'Bottom-right'],
  }
  return labels[type]?.[idx] ?? `Point ${idx + 1}`
}

async function applyDrawEdit() {
  if (!editingDraw.value) return
  await drawStore.updateDrawing(editingDraw.value.id, {
    data:  { ...(editingDraw.value.data as any), points: drawPoints.value.map(p => ({ ...p })) },
    style: { ...editingDraw.value.style, color: drawFields.color, lineWidth: drawFields.lineWidth },
    label: drawFields.label || undefined,
    notes: drawFields.notes || undefined,
  } as any)
  drawEditorOpen.value = false
  editingDraw.value    = null
  drawPoints.value     = []
}

// ── Shared helpers ────────────────────────────────────────────────────────────
function paramLabel(key: string): string {
  const m: Record<string, string> = {
    period: 'Period', fast: 'Fast', slow: 'Slow',
    signal: 'Signal', stdDev: 'Std dev', anchorTime: 'Anchor time',
  }
  return m[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

function tsToDateInput(ts: number | undefined): string {
  if (!ts) return ''
  const d   = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function dateInputToTs(val: string): number {
  return Math.floor(new Date(val).getTime() / 1000)
}
</script>

<style scoped>
.side-panel {
  background: #111;
  border-left: 1px solid #222;
  width: 220px;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: #aaa;
  overflow: hidden;
}

/* ── Section chrome ────────────────────────────────────────────────────── */
.section {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  border-bottom: 1px solid #1a1a1a;
  transition: flex 0.2s ease;
}
.section.collapsed { flex: 0 0 auto; }

.section-header {
  display: flex;
  align-items: center;
  padding: 7px 10px;
  background: #141414;
  cursor: pointer;
  gap: 6px;
  flex-shrink: 0;
  user-select: none;
}
.section-header:hover { background: #1a1a1a; }

.section-title { flex: 1; font-weight: 600; color: #ccc; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
.section-count { background: #2a2a2a; color: #666; border-radius: 8px; padding: 0 5px; font-size: 10px; }
.section-chevron { color: #444; font-size: 9px; }

.section-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}

.alert-row { cursor: default; }
.alert-icon { width: 14px; text-align: center; font-size: 10px; color: #f59e0b; flex-shrink: 0; }
.alert-row--active .alert-icon { color: #f59e0b; }
.alert-row--triggered .alert-icon { color: #555; }
.alert-row--paused .alert-icon { color: #ffd54f; opacity: 0.5; }

/* ── List ──────────────────────────────────────────────────────────────── */
.ind-list {
  flex: 1;
  overflow-y: auto;
  padding: 2px 0;
}

.list-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  cursor: pointer;
  transition: background 0.1s;
}
.list-row:hover { background: #1a1a1a; }
.list-row.row--selected { background: #1a2a3a; }
.list-row.row--hidden { opacity: 0.45; }
.list-row.row--tf-inactive { opacity: 0.35; }
.list-row.row--tf-inactive .color-dot { filter: grayscale(1); }

.tf-lock-badge { font-size: 9px; opacity: 0.6; flex-shrink: 0; }

.color-dot {
  width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0;
}

.draw-icon {
  width: 14px; text-align: center;
  font-size: 11px; color: #555; flex-shrink: 0;
}

.row-name {
  flex: 1;
  font-family: monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-btn {
  background: none; border: none;
  color: #444; cursor: pointer;
  padding: 1px 3px; font-size: 11px; border-radius: 2px;
  flex-shrink: 0;
}
.row-btn:hover { color: #aaa; background: #222; }
.row-btn.danger:hover { color: #ef5350; }
.row-btn.btn--dim  { opacity: 0.35; }
.row-btn.btn--active { color: #64b5f6; }

.empty-hint { padding: 8px 10px; color: #333; font-style: italic; font-size: 11px; }

.hint-btn {
  display: block;
  margin-top: 6px;
  background: #1a3a5c;
  border: none;
  color: #64b5f6;
  border-radius: 3px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 11px;
  font-style: normal;
}
.hint-btn:hover { background: #1f4a7a; }

/* ── Add / preset bars ─────────────────────────────────────────────────── */
.add-bar {
  padding: 4px 8px;
  border-top: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.add-btn {
  background: #1a3a5c; border: none;
  color: #64b5f6; border-radius: 3px;
  padding: 3px 10px; cursor: pointer; font-size: 11px; width: 100%;
}
.add-btn:hover { background: #1f4a7a; }

.picker-dropdown {
  border-top: 1px solid #222;
  background: #0d0d0d;
  max-height: 180px;
  overflow-y: auto;
  flex-shrink: 0;
}
.picker-item {
  display: block; width: 100%;
  background: none; border: none;
  color: #aaa; text-align: left;
  padding: 5px 10px; cursor: pointer; font-size: 11px;
}
.picker-item:hover { background: #1a1a1a; color: #fff; }

.preset-bar {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 8px;
  border-top: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.preset-select {
  flex: 1;
  background: #1a1a1a; border: 1px solid #2a2a2a;
  color: #888; border-radius: 3px;
  padding: 2px 4px; font-size: 10px;
}
.preset-btn {
  background: #1a1a1a; border: 1px solid #2a2a2a;
  color: #666; border-radius: 3px;
  padding: 2px 6px; cursor: pointer; font-size: 11px;
}
.preset-btn:hover { color: #ccc; border-color: #444; }

/* ── Shared editor styles ─────────────────────────────────────────────── */
.editor-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.editor-box {
  background: #141414; border: 1px solid #2a2a2a; border-radius: 6px;
  min-width: 300px; max-width: 360px; width: 100%;
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
.ed-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 11px 14px; border-bottom: 1px solid #1f1f1f;
  color: #ccc; font-weight: 600; font-size: 12px;
}
.ed-close { background: none; border: none; color: #555; cursor: pointer; font-size: 14px; }
.ed-close:hover { color: #aaa; }
.ed-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.ed-row { display: flex; align-items: center; gap: 10px; }
.ed-row label { color: #666; min-width: 90px; font-size: 11px; }
.ed-color { width: 30px; height: 22px; border: 1px solid #333; border-radius: 3px; background: none; cursor: pointer; padding: 0; }
.ed-range { flex: 1; accent-color: #64b5f6; }
.ed-val   { color: #888; font-size: 11px; min-width: 28px; text-align: right; }
.ed-input {
  flex: 1; background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
  color: #ccc; padding: 3px 7px; font-size: 11px; font-family: monospace;
}
.ed-input:focus { outline: none; border-color: #64b5f6; }
.ed-num { max-width: 120px; }
.ed-sep { height: 1px; background: #1a1a1a; margin: 6px 0; }
.ed-tf-grid {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 0 6px;
}
.ed-tf-chip {
  display: flex; align-items: center; gap: 3px;
  padding: 2px 7px; border-radius: 10px; font-size: 10px;
  border: 1px solid #2a2a2a; background: #1a1a1a; color: #555;
  cursor: pointer; user-select: none; transition: background 0.1s, color 0.1s;
}
.ed-tf-chip--on { background: #1a3a5c; color: #64b5f6; border-color: #1a4a7c; }
.ed-tf-check { display: none; }
.ed-point-title { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 0 2px; }
.ed-footer { display: flex; gap: 8px; padding: 9px 14px; border-top: 1px solid #1a1a1a; }
.ed-btn {
  flex: 1; padding: 5px; border-radius: 4px; border: 1px solid #2a2a2a;
  font-family: monospace; font-size: 11px; cursor: pointer;
  background: #1a1a1a; color: #777;
}
.ed-btn:hover { color: #aaa; }
.ed-apply { background: #1a3a5c; color: #64b5f6; border-color: #1a3a5c; }
.ed-apply:hover { background: #1f4a7a; }

/* ── Transitions ──────────────────────────────────────────────────────── */
.slide-enter-active, .slide-leave-active { transition: all 0.18s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; }
.slide-enter-to, .slide-leave-from { opacity: 1; max-height: 600px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>