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
            >
              <span class="color-dot" :style="{ background: ind.style.color }" />
              <span class="row-name">{{ displayName(ind) }}</span>
              <button class="row-btn" @click="openIndEditor(i)" title="Settings">⚙</button>
              <button class="row-btn danger" @click="chartStore.removeIndicator(i)" title="Remove">✕</button>
            </div>
            <div v-if="!chartStore.indicators.length" class="empty-hint">None active</div>
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
          </div>
          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyIndEdit">Apply</button>
            <button class="ed-btn" @click="closeIndEditor">Cancel</button>
          </div>
        </div>
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
import { ref, reactive } from 'vue'
import { useChartStore }   from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { usePresetsStore }  from '@/stores/presets'
import type { ChartDrawing, IndicatorConfig, IndicatorType } from '@/types'

const chartStore   = useChartStore()
const drawStore    = useDrawingsStore()
const presetsStore = usePresetsStore()

// ── Section collapse state ────────────────────────────────────────────────────
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
const indFields  = reactive({ color: '#fff', lineWidth: 1.5, pane: 'main' as 'main'|'separate', params: {} as Record<string, unknown> })

function openIndEditor(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  editingIndIdx = i
  editingInd.value = ind
  indFields.color     = ind.style.color
  indFields.lineWidth = ind.style.lineWidth ?? 1.5
  indFields.pane      = (ind.pane ?? 'main') as 'main'|'separate'
  indFields.params    = { ...ind.params }
  indEditorOpen.value = true
}

function closeIndEditor() { indEditorOpen.value = false; editingInd.value = null; editingIndIdx = -1 }

function applyIndEdit() {
  if (editingIndIdx < 0) return
  chartStore.updateIndicator(editingIndIdx, {
    ...chartStore.indicators[editingIndIdx],
    style:  { ...chartStore.indicators[editingIndIdx].style, color: indFields.color, lineWidth: indFields.lineWidth },
    pane:   indFields.pane,
    params: { ...indFields.params },
  })
  closeIndEditor()
}

// ── Drawing editor ────────────────────────────────────────────────────────────
const drawEditorOpen = ref(false)
const editingDraw    = ref<ChartDrawing | null>(null)
const drawFields     = reactive({ color: '#fff', lineWidth: 1.5, label: '', notes: '' })

function openDrawEditor(d: ChartDrawing) {
  editingDraw.value    = d
  drawFields.color     = d.style?.color ?? '#ffffff'
  drawFields.lineWidth = d.style?.lineWidth ?? 1.5
  drawFields.label     = d.label ?? ''
  drawFields.notes     = d.notes ?? ''
  drawEditorOpen.value = true
}

function closeDrawEditor() { drawEditorOpen.value = false; editingDraw.value = null }

async function applyDrawEdit() {
  if (!editingDraw.value) return
  await drawStore.updateDrawing(editingDraw.value.id, {
    style: { ...editingDraw.value.style, color: drawFields.color, lineWidth: drawFields.lineWidth },
    label: drawFields.label || undefined,
    notes: drawFields.notes || undefined,
  } as any)
  closeDrawEditor()
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
.ed-num { max-width: 70px; }
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