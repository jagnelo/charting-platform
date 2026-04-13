<template>
  <div :class="['side-panel', { 'side-panel--collapsed': !isPanelOpen }]">
    <!-- Collapse toggle strip -->
    <button
      class="panel-toggle"
      :title="isPanelOpen ? 'Hide panel' : 'Show panel'"
      @click="isPanelOpen = !isPanelOpen"
    >{{ isPanelOpen ? '›' : '‹' }}</button>

    <div v-show="isPanelOpen" class="panel-body">

    <!-- ── Instrument info ───────────────────────────────────────────────── -->
    <InstrumentInfoPanel
      :instrument="chartStore.instrument ?? null"
      :current-price="chartStore.bars.length ? chartStore.bars[chartStore.bars.length - 1].close : null"
      @select="symbol => emit('selectSymbol', symbol)"
    />

    <!-- ── Watchlists membership ─────────────────────────────────────────── -->
    <div v-if="membership !== null" class="section" :class="{ collapsed: !watchlistsOpen }">
      <div class="section-header" @click="watchlistsOpen = !watchlistsOpen">
        <span class="section-title">Watchlists</span>
        <span class="section-count">{{ membership!.watchlists.length }}</span>
        <span class="section-chevron">{{ watchlistsOpen ? '▾' : '▸' }}</span>
      </div>
      <Transition name="slide">
        <div class="section-content" v-if="watchlistsOpen">
          <div class="section-body">
            <div
              v-for="wl in membership!.watchlists"
              :key="wl.id"
              class="list-row membership-row"
              @click="onWatchlistClick(wl.id)"
            >
              <span class="mem-icon">☰</span>
              <span class="row-name">{{ wl.name }}</span>
              <span v-if="wl.is_managed" class="mem-badge">managed</span>
            </div>
            <div v-if="!membership!.watchlists.length" class="empty-hint">Not in any watchlist</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Screeners membership ───────────────────────────────────────────── -->
    <div v-if="membership !== null" class="section" :class="{ collapsed: !screenersOpen }">
      <div class="section-header" @click="screenersOpen = !screenersOpen">
        <span class="section-title">Screeners</span>
        <span class="section-count">{{ activeScreeners.length }}</span>
        <span class="section-chevron">{{ screenersOpen ? '▾' : '▸' }}</span>
      </div>
      <Transition name="slide">
        <div class="section-content" v-if="screenersOpen">
          <div class="section-body">
            <div
              v-for="sc in activeScreeners"
              :key="sc.id"
              class="list-row membership-row"
              @click="onScreenerClick(sc.id)"
            >
              <span class="mem-icon">⊞</span>
              <span class="row-name">{{ sc.name }}</span>
            </div>
            <div v-if="!activeScreeners.length" class="empty-hint">No active screener matches</div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Indicators section ──────────────────────────────────────────── -->
    <div class="section" :class="{ collapsed: !indicatorsOpen }">
      <div class="section-header" @click="indicatorsOpen = !indicatorsOpen">
        <span class="section-title">Indicators</span>
        <span class="section-count">{{ chartStore.indicators.length }}</span>
        <span class="section-chevron">{{ indicatorsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="indicatorsOpen">
          <div class="section-body">
            <div class="ind-list">
              <VueDraggable
                v-model="draggableIndicators"
                handle=".ind-drag-handle"
                animation="150"
              >
                <div
                  v-for="(ind, i) in draggableIndicators"
                  :key="displayName(ind) + i"
                  class="list-row"
                  :class="{ 'row--selected': i === chartStore.selectedIndicatorIndex, 'row--tf-inactive': !isActiveOnCurrentTf(ind) }"
                  :title="isActiveOnCurrentTf(ind) ? undefined : `Locked to: ${(ind.lockedTimeframes ?? []).join(', ')}`"
                  @click.stop="chartStore.selectIndicator(i)"
                  @dblclick.stop="openIndEditor(i)"
                >
                  <span class="ind-drag-handle" title="Drag to reorder">⠿</span>
                  <span class="color-dot" :style="{ background: ind.style.color }" />
                  <span class="row-name">{{ displayName(ind) }}</span>
                  <span v-if="ind.lockedTimeframes?.length" class="tf-lock-badge" title="Timeframe locked">🔒</span>
                  <div class="row-menu-wrap">
                    <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`ind-${i}`, $event)" title="More">⋯</button>
                    <Teleport to="body">
                      <div v-if="menuOpenId === `ind-${i}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                        <button class="dd-item" @click.stop="openIndEditor(i); closeMenu()">⚙ Settings</button>
                        <button class="dd-item" @click.stop="alertForIndicator(i); closeMenu()">🔔 Create alert</button>
                        <button class="dd-item" @click.stop="toggleIndProjection(i); closeMenu()">
                          {{ ind.showYProjection ? '◉' : '○' }} Y projection
                        </button>
                        <div class="dd-sep" />
                        <button class="dd-item dd-item--danger" @click.stop="chartStore.removeIndicator(i); closeMenu()">✕ Remove</button>
                      </div>
                    </Teleport>
                  </div>
                </div>
              </VueDraggable>
              <div v-if="!chartStore.indicators.length" class="empty-hint">
                No indicators for this symbol
                <button v-if="presetsStore.getDefault()" class="hint-btn" @click="applyDefault">Apply default preset</button>
              </div>
            </div>
          </div>

          <!-- Footer: add button + picker + presets (outside scrollable area) -->
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
        <span class="section-chevron">{{ drawingsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="drawingsOpen">
          <div class="section-body">
          <div class="ind-list">
            <VueDraggable
              v-model="draggableDrawings"
              handle=".draw-drag-handle"
              animation="150"
              @end="onDrawingsReorder"
            >
              <div
                v-for="d in draggableDrawings"
                :key="d.id"
                class="list-row"
                :class="{ 'row--selected': d.id === drawStore.selectedId, 'row--hidden': !d.is_visible }"
                @click="drawStore.selectDrawing(d.id)"
                @dblclick.stop="openDrawEditor(d)"
              >
                <span class="draw-drag-handle" title="Drag to reorder">⠿</span>
                <span class="draw-icon">{{ drawingIcon(d.drawing_type) }}</span>
                <span class="row-name">{{ drawingLabel(d) }}</span>
                <div class="row-menu-wrap">
                  <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`draw-${d.id}`, $event)" title="More">⋯</button>
                  <Teleport to="body">
                    <div v-if="menuOpenId === `draw-${d.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                      <button class="dd-item" @click.stop="toggleVisible(d); closeMenu()">
                        {{ d.is_visible ? '👁 Hide' : '🚫 Show' }}
                      </button>
                      <button class="dd-item" @click.stop="toggleLock(d); closeMenu()">
                        {{ d.is_locked ? '🔓 Unlock' : '🔒 Lock' }}
                      </button>
                      <button class="dd-item" @click.stop="openDrawEditor(d); closeMenu()">⚙ Edit</button>
                      <template v-if="!['fibonacci_retracement','fibonacci_extension'].includes(d.drawing_type)">
                        <button class="dd-item" @click.stop="drawStore.toggleDrawingProjection(d.id); closeMenu()">
                          {{ drawStore.getDrawingProjection(d.id) ? '◉' : '○' }} Y projection
                        </button>
                      </template>
                      <div class="dd-sep" />
                      <button class="dd-item dd-item--danger" @click.stop="drawStore.deleteDrawing(d.id); closeMenu()">✕ Delete</button>
                    </div>
                  </Teleport>
                </div>
              </div>
            </VueDraggable>
            <div v-if="!drawStore.drawings.length" class="empty-hint">No drawings</div>
          </div>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Alerts section ──────────────────────────────────────────── -->
    <div class="section section--alerts" :class="{ collapsed: !alertsOpen }">
      <div class="section-header" @click="alertsOpen = !alertsOpen">
        <span class="section-title">Alerts</span>
        <span class="section-count">{{ instrumentAlerts.length }}</span>
        <span class="section-chevron">{{ alertsOpen ? '▾' : '▸' }}</span>
      </div>

      <Transition name="slide">
        <div class="section-content" v-if="alertsOpen">
          <div class="section-body">
          <div class="ind-list">
            <!-- Price alerts -->
            <div
              v-for="a in instrumentPriceAlerts"
              :key="'p'+a.id"
              class="list-row alert-row"
              :class="[`alert-row--${a.status}`, { 'row--selected': a.id === alertsStore.selectedAlertId }]"
              @click.stop="alertsStore.selectAlert(a.id)"
              @dblclick.stop="openAlertEditor(a, null)"
            >
              <span class="alert-icon">¤</span>
              <span class="row-name">{{ a.condition.replace(/_/g,' ') }} {{ formatMoney(Number(a.threshold_price), a.instrument_currency) }}</span>
              <div class="row-menu-wrap">
                <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`palert-${a.id}`, $event)" title="More">⋯</button>
                <Teleport to="body">
                  <div v-if="menuOpenId === `palert-${a.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                    <button class="dd-item" @click.stop="openAlertEditor(a, null); closeMenu()">⚙ Edit</button>
                    <button class="dd-item" @click.stop="alertsStore.updateAlert(a.id, { repeat: !a.repeat }); closeMenu()">
                      {{ a.repeat ? '◉' : '○' }} Repeat
                    </button>
                    <button class="dd-item" v-if="a.status === 'active'"
                            @click.stop="alertsStore.updateAlert(a.id, { status: 'paused' }); closeMenu()">⏸ Pause</button>
                    <button class="dd-item" v-if="a.status === 'paused'"
                            @click.stop="alertsStore.updateAlert(a.id, { status: 'active' }); closeMenu()">▶ Resume</button>
                    <button class="dd-item" v-if="a.status === 'triggered'"
                            @click.stop="alertsStore.rearmAlert(a.id); closeMenu()">↺ Rearm</button>
                    <button class="dd-item" @click.stop="alertsStore.toggleAlertProjection(a.id); closeMenu()">
                      {{ alertsStore.getAlertProjection(a.id) ? '◉' : '○' }} Y projection
                    </button>
                    <div class="dd-sep" />
                    <button class="dd-item dd-item--danger" @click.stop="alertsStore.deleteAlert(a.id); closeMenu()">✕ Delete</button>
                  </div>
                </Teleport>
              </div>
            </div>
            <!-- Indicator alerts -->
            <div
              v-for="a in instrumentIndicatorAlerts"
              :key="'i'+a.id"
              class="list-row alert-row"
              :class="[`alert-row--${a.status}`, { 'row--selected': a.id === alertsStore.selectedAlertId }]"
              :title="indAlertLabel(a)"
              @click.stop="alertsStore.selectAlert(a.id)"
              @dblclick.stop="openAlertEditor(null, a)"
            >
              <span class="alert-icon">≈</span>
              <span class="row-name">{{ indAlertLabel(a) }}</span>
              <div class="row-menu-wrap">
                <button class="row-btn row-menu-btn" @click.stop="toggleMenu(`ialert-${a.id}`, $event)" title="More">⋯</button>
                <Teleport to="body">
                  <div v-if="menuOpenId === `ialert-${a.id}`" class="row-dropdown row-dropdown--fixed" :style="rowMenuStyle" @click.stop>
                    <button class="dd-item" @click.stop="openAlertEditor(null, a); closeMenu()">⚙ Edit</button>
                    <button class="dd-item" @click.stop="alertsStore.updateIndicatorAlert(a.id, { repeat: !a.repeat }); closeMenu()">
                      {{ a.repeat ? '◉' : '○' }} Repeat
                    </button>
                    <button class="dd-item" v-if="a.status === 'active'"
                            @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'paused' }); closeMenu()">⏸ Pause</button>
                    <button class="dd-item" v-if="a.status === 'paused'"
                            @click.stop="alertsStore.updateIndicatorAlert(a.id, { status: 'active' }); closeMenu()">▶ Resume</button>
                    <button class="dd-item" v-if="a.status === 'triggered'"
                            @click.stop="alertsStore.rearmIndicatorAlert(a.id); closeMenu()">↺ Rearm</button>
                    <div class="dd-sep" />
                    <button class="dd-item dd-item--danger" @click.stop="alertsStore.deleteIndicatorAlert(a.id); closeMenu()">✕ Delete</button>
                  </div>
                </Teleport>
              </div>
            </div>
            <div v-if="!instrumentAlerts.length" class="empty-hint">No alerts for this symbol</div>
          </div>
          </div>
          <div class="add-bar">
            <button class="add-btn" @click="openAlertEditor(null, null)">+ Add Alert</button>
          </div>
        </div>
      </Transition>
    </div>

    </div><!-- /panel-body -->
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
                  <!-- Date-only input for non-intraday timeframes -->
                  <input
                    v-if="isNonIntradayTf"
                    type="date"
                    :value="tsToDateOnlyInput(indFields.params.anchorTime as number)"
                    @input="e => indFields.params.anchorTime = dateOnlyInputToTs((e.target as HTMLInputElement).value)"
                    class="ed-input"
                  />
                  <input
                    v-else
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
            <!-- AVWAP without anchorTime yet (newly added via picker) -->
            <div class="ed-row" v-if="editingInd.type === 'avwap' && !('anchorTime' in editingInd.params)">
              <label>Anchor date</label>
              <input
                v-if="isNonIntradayTf"
                type="date"
                :value="tsToDateOnlyInput(indFields.params.anchorTime as number)"
                @input="e => indFields.params.anchorTime = dateOnlyInputToTs((e.target as HTMLInputElement).value)"
                class="ed-input"
              />
              <input
                v-else
                type="datetime-local"
                :value="tsToDateInput(indFields.params.anchorTime as number)"
                @input="e => indFields.params.anchorTime = dateInputToTs((e.target as HTMLInputElement).value)"
                class="ed-input"
              />
            </div>
            <!-- AVWAP preset shortcuts -->
            <div class="ed-row" v-if="editingInd.type === 'avwap'">
              <label>Presets</label>
              <div class="avwap-presets">
                <button class="preset-chip" @click="setAvwapPreset('yesterday')" title="Start of yesterday">Yesterday</button>
                <button class="preset-chip" @click="setAvwapPreset('mtd')" title="Start of current month">MTD</button>
                <button class="preset-chip" @click="setAvwapPreset('ytd')" title="Start of current year">YTD</button>
              </div>
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

<script lang="ts">
// Module-level cache — survives component re-mounts (e.g. panel switches in multi-layout mode)
import type { InstrumentMembership } from '@/types'
const _membershipCache = new Map<number, InstrumentMembership>()
export {}
</script>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'
import { useWatchlistStore } from '@/stores/watchlist'
import { formatMoney } from '@/lib/format'
import { usePanelStore }   from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { usePresetsStore }  from '@/stores/presets'
import AlertForm from '@/components/alerts/AlertForm.vue'
import InstrumentInfoPanel from '@/components/chart/InstrumentInfoPanel.vue'
import type { ChartDrawing, IndicatorAlert, PriceAlert, IndicatorConfig, IndicatorType } from '@/types'
import { api } from '@/lib/api'
import { VueDraggable } from 'vue-draggable-plus'

const props = defineProps<{ panelId: string }>()
const emit = defineEmits<{ selectSymbol: [symbol: string] }>()

const router         = useRouter()
const alertsStore    = useAlertsStore()
const watchlistStore = useWatchlistStore()
const chartStore     = usePanelStore(props.panelId)
const drawStore      = useDrawingsStore()
const presetsStore   = usePresetsStore()

// ── DnD wiring ────────────────────────────────────────────────────────────────
const draggableIndicators = computed({
  get: () => chartStore.indicators,
  set: (val) => chartStore.reorderIndicators(val),
})

const draggableDrawings = computed({
  get: () => drawStore.drawings,
  set: (val) => { drawStore.drawings = val },
})

function onDrawingsReorder() {
  const ids = drawStore.drawings.map(d => d.id)
  api.post('/drawings/reorder', { ids }).catch(e => console.error('Failed to reorder drawings', e))
}

// ── Panel & section collapse state ───────────────────────────────────────────
const isPanelOpen    = ref(false)   // starts hidden until an instrument is loaded
const alertsOpen     = ref(true)
const indicatorsOpen = ref(true)
const drawingsOpen   = ref(true)
const watchlistsOpen = ref(true)
const screenersOpen  = ref(true)

// ── ⋯ row dropdown menu ───────────────────────────────────────────────────────
const menuOpenId = ref<string | null>(null)
const rowMenuStyle = ref<Record<string, string>>({})

function toggleMenu(key: string, event: MouseEvent) {
  if (menuOpenId.value === key) {
    closeMenu()
    return
  }

  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const menuH = estimateMenuHeight(key)
  const menuW = 158
  const gap = 6
  const below = window.innerHeight - rect.bottom
  const above = rect.top
  const openUp = below < menuH + gap && above > below
  const maxH = Math.max(96, Math.min(menuH, window.innerHeight - 16))
  const top = openUp
    ? Math.max(8, rect.top - maxH - gap)
    : Math.min(window.innerHeight - maxH - 8, rect.bottom + gap)
  const left = Math.max(8, Math.min(window.innerWidth - menuW - 8, rect.right - menuW))

  rowMenuStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${menuW}px`,
    maxHeight: `${maxH}px`,
  }
  menuOpenId.value = key
}

function closeMenu() {
  menuOpenId.value = null
}

function estimateMenuHeight(key: string): number {
  if (key.startsWith('draw-')) return 174
  if (key.startsWith('palert-')) return 198
  if (key.startsWith('ialert-')) return 164
  return 154
}

onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))

const membership = ref<InstrumentMembership | null>(null)

const activeScreeners = computed(() =>
  membership.value?.screeners.filter(s => s.in_current_results) ?? []
)

watch(() => chartStore.instrument?.id, async (id) => {
  if (!id) { membership.value = null; isPanelOpen.value = false; return }
  // Auto-open panel when an instrument is first loaded
  isPanelOpen.value = true
  if (_membershipCache.has(id)) {
    membership.value = _membershipCache.get(id)!
    return
  }
  try {
    const data = await api.get<InstrumentMembership>(`/instruments/${id}/membership`)
    _membershipCache.set(id, data)
    membership.value = data
  } catch {
    membership.value = null
  }
}, { immediate: true })

function onScreenerClick(scId: number) {
  router.push(`/screener?selectedId=${scId}`)
}

function onWatchlistClick(wlId: number) {
  watchlistStore.requestFocusWatchlist(wlId)
}

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

function toggleIndProjection(i: number) {
  const ind = chartStore.indicators[i]
  if (!ind) return
  chartStore.updateIndicator(i, { ...ind, showYProjection: !ind.showYProjection })
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
  rectangle: '▭', circle: '○', half_circle: '◒', fibonacci_retracement: 'φ',
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
    circle: ['Bounds start', 'Bounds end'],
    half_circle: ['Bounds start', 'Bounds end'],
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
const NON_INTRADAY_TFS = new Set(['D1', 'W1', 'MN'])
const isNonIntradayTf = computed(() => NON_INTRADAY_TFS.has(chartStore.timeframe))

function paramLabel(key: string): string {
  const m: Record<string, string> = {
    period: 'Period', fast: 'Fast', slow: 'Slow',
    signal: 'Signal', stdDev: 'Std dev', anchorTime: 'Anchor date',
  }
  return m[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

function tsToDateInput(ts: number | undefined): string {
  if (!ts) return ''
  const d   = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function tsToDateOnlyInput(ts: number | undefined): string {
  if (!ts) return ''
  const d   = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
}

function dateInputToTs(val: string): number {
  return Math.floor(new Date(val).getTime() / 1000)
}

function dateOnlyInputToTs(val: string): number {
  // Interpret as midnight UTC
  return Math.floor(new Date(val + 'T00:00:00Z').getTime() / 1000)
}

function setAvwapPreset(preset: 'yesterday' | 'mtd' | 'ytd') {
  const now = new Date()
  let d: Date
  if (preset === 'yesterday') {
    d = new Date(now)
    d.setDate(d.getDate() - 1)
    d.setHours(0, 0, 0, 0)
  } else if (preset === 'mtd') {
    d = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0)
  } else {
    d = new Date(now.getFullYear(), 0, 1, 0, 0, 0, 0)
  }
  indFields.params.anchorTime = Math.floor(d.getTime() / 1000)
}

// ── Chart-item double-click → open editor ─────────────────────────────────────
watch(() => drawStore.editRequestId, (id) => {
  if (id == null) return
  const d = drawStore.drawings.find(x => x.id === id)
  if (d) openDrawEditor(d)
  drawStore.requestEditDrawing(null)
})

watch(() => alertsStore.editRequestAlertId, (id) => {
  if (id == null) return
  const pa = alertsStore.alerts.find(x => x.id === id)
  if (pa) { openAlertEditor(pa, null); alertsStore.requestEditAlert(null); return }
  const ia = alertsStore.indicatorAlerts.find(x => x.id === id)
  if (ia) { openAlertEditor(null, ia); alertsStore.requestEditAlert(null) }
})

watch(() => chartStore.editRequestIndicatorIndex, (i) => {
  if (i == null) return
  openIndEditor(i)
  chartStore.requestEditIndicator(null)
})
</script>

<style scoped>
.side-panel {
  background: #111;
  border-left: 1px solid #222;
  width: 220px;
  display: flex;
  flex-direction: row;
  font-size: 12px;
  color: #aaa;
  overflow: hidden;
  flex-shrink: 0;
  transition: width 0.2s ease;
}
.side-panel--collapsed { width: 16px; }

.panel-toggle {
  width: 16px;
  flex-shrink: 0;
  background: #0d0d0d;
  border: none;
  border-left: 1px solid #1a1a1a;
  color: #444;
  cursor: pointer;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  align-self: stretch;
  transition: color 0.1s, background 0.1s;
}
.panel-toggle:hover { color: #aaa; background: #111; }

.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-width: 0;
}

/* ── Section chrome ────────────────────────────────────────────────────── */
.section {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  border-bottom: 1px solid #1a1a1a;
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

.section-content {
  display: flex;
  flex-direction: column;
}

.section-body {
  overflow-y: auto;
  max-height: 200px;
  min-height: 32px;
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

.ind-drag-handle,
.draw-drag-handle {
  color: #2a2a2a;
  cursor: grab;
  font-size: 13px;
  line-height: 1;
  flex-shrink: 0;
  user-select: none;
  padding: 0 1px;
}
.ind-drag-handle:hover,
.draw-drag-handle:hover { color: #555; }

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

/* ── Row ⋯ dropdown ────────────────────────────────────────────────────── */
.row-menu-wrap {
  position: relative;
  flex-shrink: 0;
}

.row-menu-btn {
  font-size: 13px;
  letter-spacing: 0.5px;
  padding: 0 3px;
  line-height: 1;
}

.row-dropdown {
  position: absolute;
  right: 0;
  top: 100%;
  z-index: 200;
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.6);
  padding: 3px 0;
}

.row-dropdown--fixed {
  position: fixed;
  right: auto;
  top: auto;
  overflow-y: auto;
}

.dd-item {
  display: block;
  width: 100%;
  background: none;
  border: none;
  color: #aaa;
  text-align: left;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 11px;
  white-space: nowrap;
}
.dd-item:hover { background: #242424; color: #fff; }
.dd-item--danger { color: #777; }
.dd-item--danger:hover { background: #2a1515; color: #ef5350; }

.dd-sep {
  height: 1px;
  background: #2a2a2a;
  margin: 3px 0;
}

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

/* ── AVWAP presets ────────────────────────────────────────────────────── */
.avwap-presets {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.preset-chip {
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid #2a4a6a;
  background: #0d1f2d;
  color: #64b5f6;
  font-size: 10px;
  cursor: pointer;
  font-family: monospace;
  transition: background 0.1s;
}
.preset-chip:hover { background: #1a3a5c; }

/* ── Membership badges ───────────────────────────────────────────────── */
.membership-row { cursor: pointer; }

.mem-icon { color: #444; font-size: 10px; flex-shrink: 0; }

.mem-badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  flex-shrink: 0;
  background: #1a1a1a;
  color: #555;
}

/* ── Transitions ──────────────────────────────────────────────────────── */
.slide-enter-active, .slide-leave-active { transition: all 0.18s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; }
.slide-enter-to, .slide-leave-from { opacity: 1; max-height: 800px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
