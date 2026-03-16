<template>
  <div class="indicator-panel">
    <div class="panel-header">
      <span>Indicators</span>
      <button class="add-btn" @click="showPicker = !showPicker">+ Add</button>
    </div>

    <!-- Active indicators list -->
    <div class="indicator-list">
      <div v-for="(ind, i) in chartStore.indicators" :key="i" class="indicator-row">
        <span class="ind-dot" :style="{ background: ind.style.color }" />
        <span class="ind-name">{{ displayName(ind) }}</span>
        <button class="ind-btn" @click="openEditor(i)" title="Settings">⚙</button>
        <button class="ind-btn danger" @click="chartStore.removeIndicator(i)" title="Remove">✕</button>
      </div>
      <div v-if="!chartStore.indicators.length" class="no-indicators">None active</div>
    </div>

    <!-- Indicator picker -->
    <div v-if="showPicker" class="picker-dropdown">
      <button v-for="t in availableTypes" :key="t.type" class="picker-item" @click="addIndicator(t.type)">
        {{ t.label }}
      </button>
    </div>

    <!-- Preset section -->
    <div class="preset-section">
      <select v-model="selectedPresetId" class="preset-select">
        <option value="">— Apply preset —</option>
        <option v-for="p in presetsStore.presets" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <button class="preset-btn" @click="applyPreset">Apply</button>
      <button class="preset-btn" @click="saveAsPreset">Save as preset</button>
    </div>
  </div>

  <!-- Indicator settings popup — rendered outside panel so it can overlap chart -->
  <Teleport to="body">
    <Transition name="fade">
      <div class="ind-editor-backdrop" v-if="editorOpen" @click.self="closeEditor">
        <div class="ind-editor">
          <div class="ed-header">
            <span>{{ editingIndicator?.type.toUpperCase() }} Settings</span>
            <button class="ed-close" @click="closeEditor">✕</button>
          </div>

          <div class="ed-body" v-if="editingIndicator">

            <!-- Colour -->
            <div class="ed-row">
              <label>Colour</label>
              <input type="color" v-model="editFields.color" class="ed-color" />
            </div>

            <!-- Line width -->
            <div class="ed-row">
              <label>Line width</label>
              <input type="range" min="0.5" max="4" step="0.5" v-model.number="editFields.lineWidth" class="ed-range" />
              <span class="ed-val">{{ editFields.lineWidth }}px</span>
            </div>

            <!-- Dynamic params (period, fast, slow, signal, stdDev, etc.) -->
            <div
              class="ed-row"
              v-for="(val, key) in editingIndicator.params"
              :key="key"
            >
              <label>{{ paramLabel(key as string) }}</label>
              <template v-if="key === 'anchorTime'">
                <!-- AVWAP anchor: shows a date picker -->
                <input
                  type="datetime-local"
                  :value="anchorToDateInput(editFields.params.anchorTime as number)"
                  @input="e => editFields.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                  class="ed-input ed-datetime"
                />
                <span class="ed-hint">Anchor point for AVWAP</span>
              </template>
              <template v-else>
                <input
                  type="number"
                  v-model.number="editFields.params[key as string]"
                  class="ed-input ed-num"
                  :min="1"
                />
              </template>
            </div>

            <!-- AVWAP: if no anchorTime param, let user pick one -->
            <div class="ed-row" v-if="editingIndicator.type === 'avwap' && !('anchorTime' in editingIndicator.params)">
              <label>Anchor date</label>
              <input
                type="datetime-local"
                :value="anchorToDateInput(editFields.params.anchorTime as number)"
                @input="e => editFields.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                class="ed-input ed-datetime"
              />
              <span class="ed-hint">VWAP resets from this point</span>
            </div>

            <!-- Pane selection for applicable indicators -->
            <div class="ed-row" v-if="['rsi','macd'].includes(editingIndicator.type)">
              <label>Pane</label>
              <select v-model="editFields.pane" class="ed-select">
                <option value="main">Main chart</option>
                <option value="separate">Separate subplot</option>
              </select>
            </div>

          </div>

          <div class="ed-footer">
            <button class="ed-btn ed-apply" @click="applyEdit">Apply</button>
            <button class="ed-btn ed-cancel" @click="closeEditor">Cancel</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useChartStore } from '@/stores/chart'
import { usePresetsStore } from '@/stores/presets'
import type { IndicatorConfig, IndicatorType } from '@/types'

const chartStore   = useChartStore()
const presetsStore = usePresetsStore()

const showPicker       = ref(false)
const selectedPresetId = ref<number | ''>('')

// ── Indicator picker ──────────────────────────────────────────────────────────
const availableTypes: Array<{ type: IndicatorType; label: string }> = [
  { type: 'sma',    label: 'SMA — Simple Moving Average'        },
  { type: 'ema',    label: 'EMA — Exponential Moving Average'   },
  { type: 'vwap',   label: 'VWAP — Volume Weighted Avg Price'   },
  { type: 'avwap',  label: 'AVWAP — Anchored VWAP'              },
  { type: 'rsi',    label: 'RSI — Relative Strength Index'      },
  { type: 'bb',     label: 'BB — Bollinger Bands'               },
  { type: 'macd',   label: 'MACD — Moving Avg Convergence Div'  },
  { type: 'volume', label: 'Volume bars'                        },
]

const DEFAULTS: Record<IndicatorType, IndicatorConfig> = {
  sma:    { type: 'sma',    params: { period: 20  }, style: { color: '#ffb74d', lineWidth: 1.5 }, pane: 'main'     },
  ema:    { type: 'ema',    params: { period: 50  }, style: { color: '#64b5f6', lineWidth: 1.5 }, pane: 'main'     },
  vwap:   { type: 'vwap',   params: {},              style: { color: '#ce93d8', lineWidth: 2   }, pane: 'main'     },
  avwap:  { type: 'avwap',  params: { anchorTime: Math.floor(Date.now() / 1000) - 86400 * 30 },
                                                     style: { color: '#80cbc4', lineWidth: 2   }, pane: 'main'     },
  rsi:    { type: 'rsi',    params: { period: 14  }, style: { color: '#ef9a9a', lineWidth: 1.5 }, pane: 'separate' },
  bb:     { type: 'bb',     params: { period: 20, stdDev: 2 }, style: { color: '#a5d6a7', lineWidth: 1 }, pane: 'main' },
  macd:   { type: 'macd',   params: { fast: 12, slow: 26, signal: 9 }, style: { color: '#ef5350', lineWidth: 1.5 }, pane: 'separate' },
  volume: { type: 'volume', params: {},              style: { color: '#4db6ac', lineWidth: 1   }, pane: 'main'     },
}

function displayName(ind: IndicatorConfig) {
  const params = Object.values(ind.params).join(',')
  return params ? `${ind.type.toUpperCase()}(${params})` : ind.type.toUpperCase()
}

function addIndicator(type: IndicatorType) {
  chartStore.addIndicator({ ...DEFAULTS[type], params: { ...DEFAULTS[type].params } })
  showPicker.value = false
}

// ── Editor ────────────────────────────────────────────────────────────────────
const editorOpen = ref(false)
let editingIndex = -1
const editingIndicator = ref<IndicatorConfig | null>(null)
const editFields = reactive<{
  color: string
  lineWidth: number
  pane: 'main' | 'separate'
  params: Record<string, unknown>
}>({
  color: '#ffffff',
  lineWidth: 1.5,
  pane: 'main',
  params: {},
})

function openEditor(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  editingIndex = i
  editingIndicator.value = ind
  editFields.color     = ind.style.color
  editFields.lineWidth = ind.style.lineWidth ?? 1.5
  editFields.pane      = (ind.pane ?? 'main') as 'main' | 'separate'
  editFields.params    = { ...ind.params }
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editingIndicator.value = null
  editingIndex = -1
}

function applyEdit() {
  if (editingIndex < 0) return
  chartStore.updateIndicator(editingIndex, {
    ...chartStore.indicators[editingIndex],
    style: {
      ...chartStore.indicators[editingIndex].style,
      color:     editFields.color,
      lineWidth: editFields.lineWidth,
    },
    pane:   editFields.pane,
    params: { ...editFields.params },
  })
  closeEditor()
}

function paramLabel(key: string): string {
  const labels: Record<string, string> = {
    period: 'Period', fast: 'Fast period', slow: 'Slow period',
    signal: 'Signal period', stdDev: 'Std deviation',
    anchorTime: 'Anchor time',
  }
  return labels[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

// AVWAP anchor time helpers
function anchorToDateInput(ts: number | undefined): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function dateInputToTs(val: string): number {
  return Math.floor(new Date(val).getTime() / 1000)
}

// ── Presets ───────────────────────────────────────────────────────────────────
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
</script>

<style scoped>
.indicator-panel {
  background: #111;
  border-left: 1px solid #222;
  width: 220px;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: #aaa;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid #222;
  color: #ccc;
  font-weight: 600;
}

.add-btn {
  background: #1a3a5c;
  border: none;
  color: #64b5f6;
  border-radius: 3px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11px;
}

.indicator-list {
  flex: 1;
  padding: 4px 0;
  overflow-y: auto;
}

.indicator-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
}
.indicator-row:hover { background: #1a1a1a; }

.ind-dot {
  width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0;
}
.ind-name { flex: 1; font-family: monospace; }

.ind-btn {
  background: none; border: none;
  color: #555; cursor: pointer;
  padding: 2px; font-size: 11px; border-radius: 2px;
}
.ind-btn:hover { color: #aaa; background: #222; }
.ind-btn.danger:hover { color: #ef5350; }

.no-indicators { padding: 8px 10px; color: #444; font-style: italic; }

.picker-dropdown {
  border-top: 1px solid #222;
  background: #0d0d0d;
  max-height: 200px;
  overflow-y: auto;
}

.picker-item {
  display: block; width: 100%;
  background: none; border: none;
  color: #aaa; text-align: left;
  padding: 6px 10px; cursor: pointer; font-size: 11px;
}
.picker-item:hover { background: #1a1a1a; color: #fff; }

.preset-section {
  padding: 8px 10px;
  border-top: 1px solid #222;
  display: flex; flex-direction: column; gap: 4px;
}

.preset-select {
  background: #1a1a1a; border: 1px solid #333;
  color: #aaa; border-radius: 3px;
  padding: 3px 6px; font-size: 11px; width: 100%;
}

.preset-btn {
  background: #1a1a1a; border: 1px solid #333;
  color: #aaa; border-radius: 3px;
  padding: 3px 8px; cursor: pointer; font-size: 11px; text-align: left;
}
.preset-btn:hover { border-color: #555; color: #ccc; }

/* ── Editor backdrop & popup ─────────────────────────────────────────────── */
.ind-editor-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}

.ind-editor {
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  min-width: 300px; max-width: 380px; width: 100%;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}

.ed-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #222;
  color: #ccc; font-weight: 600; font-size: 13px;
}

.ed-close {
  background: none; border: none;
  color: #555; cursor: pointer; font-size: 14px;
}
.ed-close:hover { color: #aaa; }

.ed-body {
  padding: 12px 16px;
  display: flex; flex-direction: column; gap: 12px;
}

.ed-row {
  display: flex; align-items: center; gap: 10px;
}

.ed-row label {
  color: #666; min-width: 100px; font-size: 11px;
}

.ed-color {
  width: 32px; height: 22px;
  border: 1px solid #333; border-radius: 3px;
  background: none; cursor: pointer; padding: 0;
}

.ed-range {
  flex: 1; accent-color: #64b5f6;
}

.ed-val {
  color: #888; font-size: 11px; min-width: 28px; text-align: right;
}

.ed-input {
  flex: 1;
  background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
  color: #ccc; padding: 4px 8px; font-size: 11px; font-family: monospace;
}
.ed-input:focus { outline: none; border-color: #64b5f6; }
.ed-num { max-width: 80px; }
.ed-datetime { font-size: 10px; }
.ed-hint { color: #444; font-size: 10px; }

.ed-select {
  flex: 1;
  background: #1a1a1a; border: 1px solid #333; border-radius: 3px;
  color: #ccc; padding: 4px 8px; font-size: 11px;
}

.ed-footer {
  display: flex; gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid #1a1a1a;
}

.ed-btn {
  flex: 1; padding: 6px;
  border-radius: 4px; border: 1px solid #333;
  font-family: monospace; font-size: 11px; cursor: pointer;
}
.ed-apply  { background: #1a3a5c; color: #64b5f6; border-color: #1a3a5c; }
.ed-apply:hover { background: #1f4a7a; }
.ed-cancel { background: #1a1a1a; color: #777; }
.ed-cancel:hover { color: #aaa; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>