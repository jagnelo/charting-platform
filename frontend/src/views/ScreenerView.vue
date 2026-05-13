<template>
  <div class="screener-view">
    <!-- ── Left sidebar: saved screeners ──────────────────────────────────── -->
    <div class="screener-sidebar">
      <div class="sidebar-header">
        <span>Screeners</span>
        <div class="sidebar-actions">
          <button class="btn-browse" title="Browse all instruments" @click="browseMode = true; fetchBrowse()">Browse</button>
          <button class="btn-new" @click="startNew">+ New</button>
        </div>
      </div>
      <div class="screener-list">
        <VueDraggable
          v-model="draggableScreeners"
          handle=".si-drag-handle"
          :animation="150"
          @end="onScreenerReorder"
        >
          <div
            v-for="s in draggableScreeners"
            :key="s.id"
            :class="['screener-item', { active: selectedId === s.id }]"
            @click="select(s)"
          >
            <span class="si-drag-handle" @click.stop title="Drag to reorder">⠿</span>
            <div class="si-content">
              <div class="si-name">{{ s.name }}</div>
              <div class="si-meta">{{ s.timeframe }} · {{ s.universe_type }}</div>
            </div>
          </div>
        </VueDraggable>
        <div v-if="!screeners.length" class="empty-list">No screeners yet</div>
      </div>
    </div>

    <!-- ── Browse mode panel ─────────────────────────────────────────────── -->
    <div v-if="browseMode" class="browse-panel">
      <div class="browse-header">
        <span class="browse-title">Browse Instruments</span>
        <button class="btn-close-browse" @click="browseMode = false; resetBrowseFilters()">✕ Close</button>
      </div>

      <!-- Browse filters -->
      <div class="browse-filters">
        <input
          v-model="browseQ"
          class="form-input browse-search"
          placeholder="Symbol…"
          @input="browsePage = 1; fetchBrowse()"
        />
        <select v-model="browseSector" class="form-select">
          <option value="">All Sectors</option>
          <option v-for="s in filterOptions.sectors" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="browseIndustry" class="form-select">
          <option value="">All Industries</option>
          <option v-for="i in filterOptions.industries" :key="i" :value="i">{{ i }}</option>
        </select>
        <select v-model="browseCountry" class="form-select">
          <option value="">All Countries</option>
          <option v-for="c in filterOptions.countries" :key="c" :value="c">{{ c }}</option>
        </select>
        <select v-model="browseExchange" class="form-select">
          <option value="">All Exchanges</option>
          <option v-for="e in filterOptions.exchanges" :key="e" :value="e">{{ e }}</option>
        </select>
        <select v-model="browseCurrency" class="form-select">
          <option value="">All Currencies</option>
          <option v-for="c in filterOptions.currencies" :key="c" :value="c">{{ c }}</option>
        </select>
        <select v-model="browseCapTier" class="form-select">
          <option value="">Any Cap</option>
          <option value="mega">Mega</option><option value="large">Large</option>
          <option value="mid">Mid</option><option value="small">Small</option>
          <option value="micro">Micro</option><option value="nano">Nano</option>
        </select>
      </div>

      <!-- Browse results -->
      <div class="browse-results-wrap">
        <div v-if="browseFetching" class="browse-loading">Loading…</div>
        <table v-else class="results-table">
          <thead>
            <tr>
              <th>Symbol</th><th>Name</th><th>Type</th>
              <th>Sector</th><th>Industry</th><th>Country</th>
              <th>Exchange</th><th>Currency</th><th>Cap</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in browseItems" :key="item.id">
              <td class="td-sym"><router-link :to="`/chart/${item.symbol}`">{{ item.symbol }}</router-link></td>
              <td class="td-name">{{ item.name }}</td>
              <td class="td-meta">{{ item.type || '—' }}</td>
              <td class="td-meta">{{ item.sector || '—' }}</td>
              <td class="td-meta">{{ item.industry || '—' }}</td>
              <td class="td-meta">{{ item.country || '—' }}</td>
              <td class="td-meta">{{ item.exchange || '—' }}</td>
              <td class="td-meta">{{ item.currency || '—' }}</td>
              <td class="td-meta">{{ item.market_cap_tier || '—' }}</td>
              <td class="td-action">
                <button
                  class="btn-add-wl"
                  title="Add to watchlist"
                  @click="showWlMenu(item.id, $event)"
                >★</button>
              </td>
            </tr>
            <tr v-if="!browseItems.length">
              <td colspan="10" class="no-matches" style="padding: 20px; text-align: center">No instruments found</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div v-if="browseTotal > BROWSE_PAGE_SIZE" class="browse-pager">
        <button class="btn-page" :disabled="browsePage <= 1" @click="browsePage--; fetchBrowse()">‹ Prev</button>
        <span class="page-info">Page {{ browsePage }} / {{ browsePages }} &nbsp;({{ browseTotal }} total)</span>
        <button class="btn-page" :disabled="browsePage >= browsePages" @click="browsePage++; fetchBrowse()">Next ›</button>
      </div>
    </div>

    <!-- ── Main area ───────────────────────────────────────────────────────── -->
    <div v-if="!browseMode" class="screener-main">

      <!-- Builder panel -->
      <div v-if="showBuilder" class="builder-panel">
        <h3>{{ editingId ? 'Edit Screener' : 'New Screener' }}</h3>

        <div class="field-row">
          <div class="field">
            <label>Name</label>
            <input v-model="draft.name" class="form-input" placeholder="e.g. RSI Oversold" />
          </div>
          <div class="field">
            <label>Timeframe</label>
            <select v-model="draft.timeframe" class="form-select">
              <option v-for="tf in TIMEFRAMES" :key="tf" :value="tf">{{ tf }}</option>
            </select>
          </div>
          <div class="field">
            <label>Universe</label>
            <select v-model="draft.universe_type" class="form-select">
              <option value="all">All instruments</option>
              <option value="asset_class">Asset class</option>
            </select>
          </div>
        </div>

        <!-- Fundamental filters strip -->
        <div class="section-label">Fundamental Filters</div>
        <div class="fundamental-strip">
          <div class="fund-field">
            <label>Sector</label>
            <select v-model="fundamentals.sector" class="form-select">
              <option value="">Any</option>
              <option v-for="s in filterOptions.sectors" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="fund-field">
            <label>Industry</label>
            <select v-model="fundamentals.industry" class="form-select">
              <option value="">Any</option>
              <option v-for="i in filterOptions.industries" :key="i" :value="i">{{ i }}</option>
            </select>
          </div>
          <div class="fund-field">
            <label>Country</label>
            <select v-model="fundamentals.country" class="form-select">
              <option value="">Any</option>
              <option v-for="c in filterOptions.countries" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div class="fund-field">
            <label>Exchange</label>
            <select v-model="fundamentals.exchange" class="form-select">
              <option value="">Any</option>
              <option v-for="e in filterOptions.exchanges" :key="e" :value="e">{{ e }}</option>
            </select>
          </div>
          <div class="fund-field">
            <label>Market Cap Tier</label>
            <select v-model="fundamentals.market_cap_tier" class="form-select">
              <option value="">Any</option>
              <option value="mega">Mega</option>
              <option value="large">Large</option>
              <option value="mid">Mid</option>
              <option value="small">Small</option>
              <option value="micro">Micro</option>
              <option value="nano">Nano</option>
            </select>
          </div>
          <div class="fund-field">
            <label>Currency</label>
            <select v-model="fundamentals.currency" class="form-select">
              <option value="">Any</option>
              <option v-for="c in filterOptions.currencies" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
        </div>

        <!-- Technical conditions -->
        <div class="conditions-builder">
          <div class="cb-header">
            <span class="section-label" style="margin:0">Technical Conditions</span>
            <select v-model="draftRootOp" class="op-select">
              <option value="AND">Match ALL (AND)</option>
              <option value="OR">Match ANY (OR)</option>
            </select>
          </div>

          <div v-for="(cond, i) in draftConditions" :key="i" class="condition-row">
            <TechnicalConditionEditor
              v-model="draftConditions[i]"
              @remove="draftConditions.splice(i, 1)"
            />
          </div>

          <button class="btn-add-cond" @click="addCondition">+ Add Technical Condition</button>
        </div>

        <div class="builder-actions">
          <button class="btn-cancel" @click="showBuilder = false">Cancel</button>
          <button class="btn-save" :disabled="!draft.name" @click="saveScreener">Save Screener</button>
        </div>
      </div>

      <!-- Results panel -->
      <div v-else-if="selectedScreener" class="results-panel">
        <div class="results-header">
          <div class="rh-left">
            <h3>{{ selectedScreener.name }}</h3>
            <span class="rh-meta">{{ selectedScreener.timeframe }} · {{ selectedScreener.universe_type }}</span>
          </div>
          <div class="rh-right">
            <!-- Alert bell -->
            <div class="alert-bell-wrap" ref="alertBellRef">
              <button
                :class="['btn-alert-bell', { 'btn-alert-bell--active': screenerAlert != null }]"
                :title="screenerAlert ? 'Screener alert active — click to edit' : 'Create screener alert'"
                @click="alertPopupOpen = !alertPopupOpen"
              >🔔{{ screenerAlert ? ' ●' : '' }}</button>
              <!-- Alert popup -->
              <div v-if="alertPopupOpen" class="alert-popup">
                <div class="ap-header">
                  <span>Screener Alert</span>
                  <button class="ap-close" @click="alertPopupOpen = false">✕</button>
                </div>
                <div class="ap-body">
                  <div class="ap-row">
                    <label>Trigger on</label>
                    <select v-model="alertDraft.trigger_type" class="form-select ap-select">
                      <option value="entered">Entered screener</option>
                      <option value="left">Left screener</option>
                      <option value="both">Entered or left</option>
                    </select>
                  </div>
                  <div class="ap-row">
                    <label>Repeat</label>
                    <input type="checkbox" v-model="alertDraft.repeat" class="ap-check" />
                  </div>
                  <div class="ap-row">
                    <label>Notes</label>
                    <input type="text" v-model="alertDraft.notes" class="form-input ap-notes" placeholder="Optional…" />
                  </div>
                </div>
                <div class="ap-footer">
                  <button v-if="screenerAlert" class="btn-cancel ap-del" @click="deleteScreenerAlert">Delete</button>
                  <button class="btn-save" @click="saveScreenerAlert">
                    {{ screenerAlert ? 'Update' : 'Create Alert' }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Save as watchlist / Sync to managed watchlist -->
            <template v-if="showSaveWlForm">
              <input v-model="saveWlName" class="form-input wl-name-input" placeholder="Watchlist name…"
                     @keydown.enter="saveResultsAsWatchlist(false)" @keydown.esc="showSaveWlForm = false" />
              <button class="btn-save-wl-confirm" :disabled="!saveWlName.trim()" @click="saveResultsAsWatchlist(false)">Save</button>
              <button class="btn-save-wl-confirm" :disabled="!saveWlName.trim()" title="Create a managed watchlist that auto-updates on each run" @click="saveResultsAsWatchlist(true)">+ Managed</button>
              <button class="btn-cancel" @click="showSaveWlForm = false">✕</button>
            </template>
            <button v-else-if="!running && latestResult?.matched_ids.length" class="btn-save-wl"
                    title="Save results as a new watchlist" @click="showSaveWlForm = true">
              ★ Save as Watchlist
            </button>
            <button class="btn-edit" @click="editScreener(selectedScreener)">Edit</button>
            <button class="btn-run" :disabled="running" @click="runScreener">
              {{ running ? 'Scanning…' : '▶ Run' }}
            </button>
            <button class="btn-delete" @click="deleteScreener(selectedScreener.id)">Delete</button>
          </div>
        </div>

        <!-- Scanning progress bar -->
        <div v-if="running && scanProgress" class="scan-progress">
          <span class="scan-badge">Scanning</span>
          <span class="scan-counts">
            <strong>{{ scanProgress.matches }}</strong> match{{ scanProgress.matches !== 1 ? 'es' : '' }} found
            &nbsp;·&nbsp;
            evaluating {{ (scanProgress.total - scanProgress.evaluated).toLocaleString() }} remaining symbols
          </span>
          <div class="scan-bar-wrap">
            <div class="scan-bar" :style="{ width: `${Math.round(scanProgress.evaluated / scanProgress.total * 100)}%` }" />
          </div>
        </div>
        <div v-else-if="latestResult" class="results-meta">
          Ran {{ fmtDate(latestResult.run_at) }} · {{ latestResult.duration_ms }}ms ·
          <strong>{{ latestResult.matched_ids.length }}</strong> matches
        </div>

        <div v-if="displayResult?.matched_ids.length" class="results-table-wrap">
          <table class="results-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th>Name</th>
                <th>Type</th>
                <th>Exchange</th>
                <th>Price</th>
                <th>1D %</th>
                <th>Market Cap</th>
                <th>Sector</th>
                <th>Industry</th>
                <th class="th-spark"><SparkTfSelector v-if="displayResult?.matched_ids.length" /></th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(id, i) in displayResult!.matched_ids"
                :key="id"
              >
                <td class="td-num">{{ i + 1 }}</td>
                <td class="td-sym">
                  <router-link :to="`/chart/${instrMap[id]?.symbol || id}`">
                    {{ instrMap[id]?.symbol || id }}
                  </router-link>
                </td>
                <td class="td-name">{{ instrMap[id]?.name || '—' }}</td>
                <td class="td-meta">{{ instrMap[id]?.type || '—' }}</td>
                <td class="td-meta">{{ instrMap[id]?.exchange || '—' }}</td>
                <td class="td-num">{{ fmtVal(displayResult!.result_data[String(id)]?.close) }}</td>
                <td :class="['td-change', changeClass(displayResult!.result_data[String(id)]?.price_change)]">
                  {{ fmtPct(displayResult!.result_data[String(id)]?.price_change) }}
                </td>
                <td class="td-meta">{{ instrMap[id]?.market_cap_tier || '—' }}</td>
                <td class="td-meta">{{ instrMap[id]?.sector || '—' }}</td>
                <td class="td-meta">{{ instrMap[id]?.industry || '—' }}</td>
                <td class="td-spark">
                  <Sparkline v-if="instrMap[id]?.symbol" :symbol="instrMap[id].symbol" />
                </td>
                <td class="td-action">
                  <button
                    class="btn-add-wl"
                    title="Add to watchlist"
                    @click="showWlMenu(id, $event)"
                  >★</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="!running && displayResult" class="no-matches">No instruments matched this screener</div>
        <div v-else-if="!running && !displayResult" class="no-matches">Run the screener to see results</div>
      </div>

      <div v-else class="screener-empty">
        <p>Select a screener or create a new one</p>
      </div>
    </div>

    <!-- ── Watchlist picker dropdown ─────────────────────────────────────────── -->
    <div
      v-if="wlMenuInstrId !== null"
      ref="wlMenuRef"
      class="wl-menu"
      :style="{ top: wlMenuY + 'px', left: wlMenuX + 'px' }"
    >
      <div class="wl-menu-title">Add to watchlist</div>
      <div
        v-for="wl in editableWatchlists"
        :key="wl.id"
        class="wl-menu-item"
        @click="addToWatchlist(wl.id)"
      >
        {{ wl.name }}
      </div>
      <div class="wl-menu-item wl-menu-new" @click="createAndAddToWatchlist">+ New watchlist</div>
    </div>

    <TextPromptModal
      v-model="showCreateWatchlistModal"
      title="Create Watchlist"
      label="Watchlist name"
      placeholder="Watchlist name"
      confirm-label="Create"
      @submit="confirmCreateWatchlist"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'
import { useScreenerAlertsStore } from '@/stores/screener_alerts'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'
import TechnicalConditionEditor from '@/components/common/TechnicalConditionEditor.vue'
import TextPromptModal from '@/components/common/TextPromptModal.vue'
import { createDefaultTechnicalCondition, normalizeTechnicalCondition } from '@/lib/technicalConditions'
import { VueDraggable } from 'vue-draggable-plus'

const route = useRoute()

interface Screener {
  id: number
  name: string
  timeframe: string
  universe_type: string
  conditions: any
}

interface ScreenerResult {
  id: number
  run_at: string
  duration_ms: number
  matched_ids: number[]
  result_data: Record<string, any>
  error?: string
}

interface InstrInfo {
  id: number
  symbol: string
  name: string
  type?: string
  exchange?: string
  sector?: string
  industry?: string
  country?: string
  market_cap_tier?: string
}

const watchlistStore      = useWatchlistStore()
const screenerAlertsStore = useScreenerAlertsStore()

const editableWatchlists = computed(() =>
  watchlistStore.watchlists.filter(w => !w.is_managed && !w.is_locked)
)

// ── Filter options (for dropdowns) ────────────────────────────────────────────

interface FilterOptions {
  sectors: string[]
  industries: string[]
  countries: string[]
  exchanges: string[]
  currencies: string[]
}
const filterOptions = ref<FilterOptions>({ sectors: [], industries: [], countries: [], exchanges: [], currencies: [] })

// ── Browse mode ───────────────────────────────────────────────────────────────

interface BrowseItem {
  id: number; symbol: string; name: string; type?: string
  sector?: string; industry?: string; country?: string; exchange?: string
  currency?: string; market_cap_tier?: string
}

const browseMode        = ref(false)
const browseQ           = ref('')
const browseSector      = ref('')
const browseIndustry    = ref('')
const browseCountry     = ref('')
const browseExchange    = ref('')
const browseCurrency    = ref('')
const browseCapTier     = ref('')
const browseItems       = ref<BrowseItem[]>([])
const browseTotal       = ref(0)
const browsePage        = ref(1)
const browseFetching    = ref(false)
const BROWSE_PAGE_SIZE  = 50

async function fetchBrowse() {
  browseFetching.value = true
  try {
    const params: Record<string, any> = { page: browsePage.value, page_size: BROWSE_PAGE_SIZE }
    if (browseQ.value)        params.q              = browseQ.value
    if (browseSector.value)   params.sector         = browseSector.value
    if (browseIndustry.value) params.industry       = browseIndustry.value
    if (browseCountry.value)  params.country        = browseCountry.value
    if (browseExchange.value) params.exchange       = browseExchange.value
    if (browseCurrency.value) params.currency       = browseCurrency.value
    if (browseCapTier.value)  params.market_cap_tier = browseCapTier.value

    const resp = await api.get<{ total: number; items: BrowseItem[] }>('/instruments/browse', params)
    browseItems.value = resp.items
    browseTotal.value = resp.total
  } finally {
    browseFetching.value = false
  }
}

function resetBrowseFilters() {
  browseSector.value = ''; browseIndustry.value = ''; browseCountry.value = ''
  browseExchange.value = ''; browseCurrency.value = ''; browseCapTier.value = ''
  browsePage.value = 1
}

watch([browseSector, browseIndustry, browseCountry, browseExchange, browseCurrency, browseCapTier], () => {
  browsePage.value = 1
  fetchBrowse()
})

const browsePages = computed(() => Math.ceil(browseTotal.value / BROWSE_PAGE_SIZE))

const screeners   = ref<Screener[]>([])

const draggableScreeners = computed({
  get: () => screeners.value,
  set: (val) => { screeners.value = val },
})

async function onScreenerReorder() {
  const ids = screeners.value.map(s => s.id)
  try {
    await api.post('/screeners/reorder', { ids })
  } catch (e) {
    console.error('Failed to reorder screeners', e)
  }
}

const selectedId  = ref<number | null>(null)
const showBuilder = ref(false)
const editingId   = ref<number | null>(null)
const running     = ref(false)
const results     = ref<ScreenerResult[]>([])
const instrMap    = ref<Record<number, InstrInfo>>({})

interface ScanProgress { evaluated: number; total: number; matches: number }
const scanProgress    = ref<ScanProgress | null>(null)
const streamingResult = ref<{ matched_ids: number[]; result_data: Record<string, any> } | null>(null)

// Watchlist menu state
const wlMenuInstrId = ref<number | null>(null)
const showCreateWatchlistModal = ref(false)
const wlMenuX    = ref(0)
const wlMenuY    = ref(0)
const wlMenuRef  = ref<HTMLElement | null>(null)
const alertBellRef = ref<HTMLElement | null>(null)

function onDocClick(e: MouseEvent) {
  if (wlMenuInstrId.value !== null && wlMenuRef.value && !wlMenuRef.value.contains(e.target as Node)) {
    wlMenuInstrId.value = null
  }
  if (alertPopupOpen.value && alertBellRef.value && !alertBellRef.value.contains(e.target as Node)) {
    alertPopupOpen.value = false
  }
}

// Save-as-watchlist state
const showSaveWlForm = ref(false)
const saveWlName     = ref('')

// Screener alert state
const alertPopupOpen = ref(false)
const alertDraft     = reactive({ trigger_type: 'both', repeat: false, notes: '' })

const screenerAlert = computed(() =>
  selectedId.value != null ? screenerAlertsStore.forScreener(selectedId.value) : undefined
)

watch(screenerAlert, (a) => {
  if (a) {
    alertDraft.trigger_type = a.trigger_type
    alertDraft.repeat       = a.repeat
    alertDraft.notes        = a.notes ?? ''
  } else {
    alertDraft.trigger_type = 'both'
    alertDraft.repeat       = false
    alertDraft.notes        = ''
  }
}, { immediate: true })

watch(selectedId, () => { alertPopupOpen.value = false })

async function saveScreenerAlert() {
  if (!selectedId.value) return
  if (screenerAlert.value) {
    await screenerAlertsStore.updateAlert(screenerAlert.value.id, {
      trigger_type: alertDraft.trigger_type as any,
      repeat: alertDraft.repeat,
      notes: alertDraft.notes,
    })
  } else {
    await screenerAlertsStore.createAlert(
      selectedId.value,
      alertDraft.trigger_type as any,
      alertDraft.repeat,
      alertDraft.notes || undefined,
    )
  }
  alertPopupOpen.value = false
}

async function deleteScreenerAlert() {
  if (!screenerAlert.value) return
  await screenerAlertsStore.deleteAlert(screenerAlert.value.id)
  alertPopupOpen.value = false
}

const selectedScreener = computed(() => screeners.value.find(s => s.id === selectedId.value) ?? null)
const latestResult     = computed(() => results.value[0] ?? null)
const displayResult    = computed(() =>
  running.value && streamingResult.value ? streamingResult.value : latestResult.value
)

const TIMEFRAMES = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN']
// ── Draft state ───────────────────────────────────────────────────────────────

const draft = reactive({ name: '', timeframe: 'D1', universe_type: 'all' })
const draftRootOp = ref('AND')
const draftConditions = ref<any[]>([])
const fundamentals = reactive({
  sector: '',
  industry: '',
  country: '',
  exchange: '',
  market_cap_tier: '',
  currency: '',
})

function resetDraft() {
  draft.name = ''
  draft.timeframe = 'D1'
  draft.universe_type = 'all'
  draftRootOp.value = 'AND'
  draftConditions.value = []
  Object.assign(fundamentals, { sector: '', industry: '', country: '', exchange: '', market_cap_tier: '', currency: '' })
  editingId.value = null
}

function startNew() {
  resetDraft()
  showBuilder.value = true
}

function editScreener(s: Screener) {
  resetDraft()
  draft.name = s.name
  draft.timeframe = s.timeframe
  draft.universe_type = s.universe_type
  editingId.value = s.id

  // Reconstruct draft conditions from saved conditions
  const conds = s.conditions
  if (conds?.operator) {
    draftRootOp.value = conds.operator
    draftConditions.value = (conds.conditions || [])
      .filter((c: any) => c.type !== 'fundamental_filter')
      .map((c: any) => normalizeTechnicalCondition(c))
    // Re-hydrate fundamental filters
    for (const c of (conds.conditions || [])) {
      if (c.type === 'fundamental_filter' && c.field in fundamentals) {
        (fundamentals as any)[c.field] = c.value
      }
    }
  }
  showBuilder.value = true
}

function addCondition() {
  draftConditions.value.push(createDefaultTechnicalCondition())
}

function buildConditions(): any {
  const techConditions = [...draftConditions.value]

  // Append fundamental filters as conditions
  const fundFields: Array<keyof typeof fundamentals> = ['sector', 'industry', 'country', 'exchange', 'market_cap_tier', 'currency']
  for (const field of fundFields) {
    const val = fundamentals[field]
    if (val) {
      const backendField = field === 'exchange' ? 'exchange_mic' : field === 'currency' ? 'currency' : field
      techConditions.push({
        type: 'fundamental_filter',
        field: backendField,
        op: 'eq',
        value: val,
      })
    }
  }

  return { operator: draftRootOp.value, conditions: techConditions }
}

async function saveScreener() {
  const conditions = buildConditions()
  if (editingId.value) {
    const updated = await api.patch<Screener>(`/screeners/${editingId.value}`, { ...draft, conditions })
    const idx = screeners.value.findIndex(s => s.id === editingId.value)
    if (idx !== -1) screeners.value[idx] = updated
    selectedId.value = updated.id
  } else {
    const s = await api.post<Screener>('/screeners', { ...draft, conditions })
    screeners.value.push(s)
    selectedId.value = s.id
  }
  showBuilder.value = false
  resetDraft()
}

function select(s: Screener) {
  selectedId.value = s.id
  loadResults(s.id)
}

async function loadResults(id: number) {
  results.value = await api.get(`/screeners/${id}/results`, { limit: 5 })
  if (latestResult.value?.matched_ids.length) {
    await loadInstrumentInfo(latestResult.value.matched_ids)
  }
}

async function loadInstrumentInfo(ids: number[]) {
  // Load browse info for matched instruments
  const missing = ids.filter(id => !instrMap.value[id])
  if (!missing.length) return
  // Batch via browse with custom_ids if backend supports it; fallback: fetch individually
  try {
    const resp = await api.get<{ items: InstrInfo[] }>('/instruments/browse', {
      ids: missing.join(','),
      page_size: missing.length,
      page: 1,
    })
    for (const item of resp.items) {
      instrMap.value[item.id] = item
    }
  } catch {
    // non-critical
  }
}

async function runScreener() {
  if (!selectedId.value) return
  const screenerId = selectedId.value
  running.value = true
  scanProgress.value = null
  streamingResult.value = { matched_ids: [], result_data: {} }

  const token = localStorage.getItem('access_token')
  const headers: Record<string, string> = { 'Accept': 'application/x-ndjson' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  try {
    const resp = await fetch(
      `/api/v1/screeners/${screenerId}/run/stream`,
      { method: 'POST', headers },
    )
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const event = JSON.parse(line)
          if (event.type === 'progress') {
            scanProgress.value = { evaluated: event.evaluated, total: event.total, matches: event.matches }
          } else if (event.type === 'match') {
            streamingResult.value!.matched_ids.push(event.instrument_id)
            if (event.computed) streamingResult.value!.result_data[String(event.instrument_id)] = event.computed
            await loadInstrumentInfo([event.instrument_id])
          } else if (event.type === 'done') {
            scanProgress.value = { evaluated: event.evaluated, total: event.total, matches: event.matches }
            const saved = await api.get<ScreenerResult[]>(`/screeners/${screenerId}/results`, { limit: 1 })
            if (saved.length) results.value.unshift(saved[0])
            // Sync managed watchlists after screener run (backend already updated them)
            watchlistStore.loadWatchlists()
          }
        } catch {
          // malformed line — skip
        }
      }
    }
  } catch (err) {
    console.error('Screener stream error:', err)
  } finally {
    running.value = false
    scanProgress.value = null
    streamingResult.value = null
  }
}

async function deleteScreener(id: number) {
  await api.delete(`/screeners/${id}`)
  screeners.value = screeners.value.filter(s => s.id !== id)
  if (selectedId.value === id) { selectedId.value = null; results.value = [] }
}

// ── Watchlist menu ────────────────────────────────────────────────────────────

function showWlMenu(instrId: number, event: MouseEvent) {
  wlMenuInstrId.value = instrId
  const rect = (event.target as HTMLElement).getBoundingClientRect()
  wlMenuX.value = rect.left
  wlMenuY.value = rect.bottom + 4
}

async function addToWatchlist(watchlistId: number) {
  if (wlMenuInstrId.value === null) return
  await watchlistStore.addItem(watchlistId, wlMenuInstrId.value)
  wlMenuInstrId.value = null
}

async function createAndAddToWatchlist() {
  if (wlMenuInstrId.value === null) return
  showCreateWatchlistModal.value = true
}

async function confirmCreateWatchlist(name: string) {
  if (wlMenuInstrId.value === null) return
  const instrId = wlMenuInstrId.value
  const wl = await watchlistStore.createWatchlist(name)
  if (!wl) return
  await watchlistStore.addItem(wl.id, instrId)
  showCreateWatchlistModal.value = false
  wlMenuInstrId.value = null
}

async function saveResultsAsWatchlist(managed = false) {
  if (!saveWlName.value.trim() || !latestResult.value) return
  const screener_id = managed && selectedId.value ? selectedId.value : undefined
  const wl = await watchlistStore.createWatchlist(saveWlName.value.trim(), undefined, screener_id)
  if (!wl) return
  if (managed) {
    // Use seed endpoint to bypass managed-watchlist protection
    await watchlistStore.seedWatchlist(wl.id, latestResult.value.matched_ids)
  } else {
    const symbols = latestResult.value.matched_ids
      .map(id => instrMap.value[id]?.symbol)
      .filter((s): s is string => !!s && !/^\d+$/.test(s))
    await Promise.allSettled(symbols.map(sym => watchlistStore.addBySymbol(wl.id, sym)))
  }
  saveWlName.value = ''
  showSaveWlForm.value = false
}

// ── Formatters ────────────────────────────────────────────────────────────────

const fmtDate   = (d: string) => new Date(d).toLocaleString()
const fmtVal    = (v: any)    => v == null ? '—' : typeof v === 'number' ? v.toFixed(2) : String(v)
const fmtPct    = (v: any)    => v == null ? '—' : `${(v * 100).toFixed(2)}%`
const changeClass = (v: any)  => v == null ? '' : v >= 0 ? 'up' : 'down'

onMounted(async () => {
  document.addEventListener('click', onDocClick, true)
  screeners.value = await api.get('/screeners')
  await Promise.all([
    watchlistStore.loadWatchlists(),
    screenerAlertsStore.loadAlerts(),
  ])
  filterOptions.value = await api.get<FilterOptions>('/instruments/filter-options').catch(() => filterOptions.value)

  // Activate browse mode if ?q= is in the URL
  const q = route.query.q as string | undefined
  if (q) {
    browseMode.value = true
    browseQ.value = q
    await fetchBrowse()
  }

  // Select a screener if ?selectedId=id is in the URL
  const selectId = route.query.selectedId ? Number(route.query.selectedId) : null
  if (selectId) {
    const s = screeners.value.find(sc => sc.id === selectId)
    if (s) select(s)
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick, true)
})
</script>

<style scoped>
.screener-view { display: flex; height: 100%; color: #ccc; font-size: 12px; overflow: hidden; position: relative; font-family: 'JetBrains Mono', 'Fira Code', monospace; }

/* ── Sidebar ───────────────────────────────────────────────── */
.screener-sidebar {
  width: 210px;
  background: #0d0d0d;
  border-right: 1px solid #1a1a1a;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #1a1a1a;
  color: #eee;
  font-weight: 600;
}
.btn-new {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 3px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 11px;
}
.screener-list { flex: 1; overflow-y: auto; }
.screener-item { display: flex; align-items: center; padding: 10px 8px 10px 4px; cursor: pointer; border-bottom: 1px solid #111; gap: 4px; }
.screener-item:hover { background: #111; }
.screener-item.active { background: #0f1f30; border-left: 2px solid #64b5f6; }
.si-drag-handle { color: #333; cursor: grab; padding: 0 4px; font-size: 14px; line-height: 1; flex-shrink: 0; user-select: none; }
.si-drag-handle:hover { color: #666; }
.si-content { flex: 1; min-width: 0; }
.si-name { color: #ddd; font-weight: 500; }
.si-meta { color: #555; font-size: 10px; margin-top: 2px; }
.empty-list { padding: 16px 12px; color: #444; font-style: italic; }

/* ── Main ─────────────────────────────────────────────────── */
.screener-main { flex: 1; overflow: auto; padding: 20px; }

/* ── Builder ──────────────────────────────────────────────── */
.builder-panel { width: 100%; }
.builder-panel h3 { color: #fff; font-size: 15px; margin-bottom: 16px; }

.field-row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 10px; color: #666; text-transform: uppercase; }

.section-label { font-size: 10px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; margin-top: 4px; }

.fundamental-strip {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  background: #0d0d0d;
  border: 1px solid #1e1e1e;
  border-radius: 4px;
  padding: 10px 12px;
  margin-bottom: 14px;
}
.fund-field { display: flex; flex-direction: column; gap: 3px; }
.fund-field label { font-size: 10px; color: #666; text-transform: uppercase; }

.form-input, .form-select {
  background: #141414;
  border: 1px solid #2a2a2a;
  color: #ccc;
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 12px;
  font-family: inherit;
}

.conditions-builder {
  background: #0d0d0d;
  border: 1px solid #1e1e1e;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 16px;
}
.cb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.op-select { background: #1a1a1a; border: 1px solid #333; color: #aaa; border-radius: 3px; padding: 3px 6px; font-size: 11px; }

.condition-row { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.cond-type  { min-width: 180px; }
.cond-ind   { min-width: 80px; }
.cond-op    { width: 50px; }
.cond-param { width: 60px; }
.cond-val   { width: 80px; }
.cond-label { color: #666; font-size: 11px; white-space: nowrap; }

.btn-add-cond { background: none; border: 1px dashed #333; color: #555; border-radius: 3px; padding: 4px 12px; cursor: pointer; font-size: 11px; width: 100%; margin-top: 4px; }
.btn-add-cond:hover { border-color: #555; color: #888; }
.btn-remove-cond { background: none; border: none; color: #444; cursor: pointer; font-size: 11px; padding: 0 4px; }
.btn-remove-cond:hover { color: #ef5350; }

.builder-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-cancel { background: none; border: 1px solid #333; color: #666; border-radius: 3px; padding: 6px 16px; cursor: pointer; }
.btn-save   { background: #1a3a5c; border: 1px solid #64b5f6; color: #64b5f6; border-radius: 3px; padding: 6px 16px; cursor: pointer; }
.btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Results ──────────────────────────────────────────────── */
.results-panel { height: 100%; display: flex; flex-direction: column; }
.results-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; flex-shrink: 0; }
.rh-left h3 { margin: 0 0 4px; color: #fff; font-size: 15px; }
.rh-meta { color: #555; font-size: 10px; }
.rh-right { display: flex; gap: 8px; }
.btn-run    { background: #1a3a5c; border: 1px solid #64b5f6; color: #64b5f6; border-radius: 3px; padding: 5px 14px; cursor: pointer; font-size: 12px; }
.btn-run:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-edit   { background: none; border: 1px solid #333; color: #888; border-radius: 3px; padding: 5px 10px; cursor: pointer; font-size: 11px; }
.btn-edit:hover { border-color: #64b5f6; color: #64b5f6; }
.btn-delete { background: none; border: 1px solid #333; color: #666; border-radius: 3px; padding: 5px 10px; cursor: pointer; font-size: 11px; }
.btn-delete:hover { border-color: #ef5350; color: #ef5350; }
.btn-save-wl { background: none; border: 1px solid #444; color: #aaa; border-radius: 3px; padding: 5px 10px; cursor: pointer; font-size: 11px; }
.btn-save-wl:hover { border-color: #ffd54f; color: #ffd54f; }
.btn-save-wl-confirm { background: #1a3a1a; border: 1px solid #4caf50; color: #4caf50; border-radius: 3px; padding: 5px 10px; cursor: pointer; font-size: 11px; }
.btn-save-wl-confirm:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Alert bell ───────────────────────────────────────────── */
.alert-bell-wrap { position: relative; }

.btn-alert-bell {
  background: none;
  border: 1px solid #444;
  color: #aaa;
  border-radius: 3px;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 11px;
}
.btn-alert-bell:hover { border-color: #f59e0b; color: #f59e0b; }
.btn-alert-bell--active { border-color: #f59e0b; color: #f59e0b; }

.alert-popup {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  width: 260px;
  z-index: 200;
  box-shadow: 0 8px 30px rgba(0,0,0,0.6);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

.ap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 12px;
  border-bottom: 1px solid #1f1f1f;
  color: #ccc;
  font-weight: 600;
}

.ap-close {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 13px;
}

.ap-body { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }

.ap-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ap-row label { font-size: 10px; color: #555; text-transform: uppercase; min-width: 70px; }

.ap-select, .ap-notes { flex: 1; }
.ap-check { flex-shrink: 0; }

.ap-footer {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid #1f1f1f;
}

.ap-del { color: #ef5350 !important; border-color: #ef5350 !important; }
.wl-name-input { width: 140px; }
.btn-cancel { background: none; border: 1px solid #333; color: #666; border-radius: 3px; padding: 5px 8px; cursor: pointer; font-size: 11px; }

.results-meta { color: #666; font-size: 11px; margin-bottom: 10px; flex-shrink: 0; }

/* ── Scan progress ────────────────────────────────────────── */
.scan-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.scan-badge {
  background: #1a3a5c;
  border: 1px solid #64b5f6;
  color: #64b5f6;
  border-radius: 3px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  animation: scan-pulse 1.2s ease-in-out infinite;
}
@keyframes scan-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}
.scan-counts { color: #888; font-size: 11px; flex: 1; min-width: 200px; }
.scan-counts strong { color: #ccc; }
.scan-bar-wrap {
  width: 100%;
  height: 2px;
  background: #1a1a1a;
  border-radius: 1px;
  overflow: hidden;
}
.scan-bar {
  height: 100%;
  background: #64b5f6;
  border-radius: 1px;
  transition: width 0.3s ease;
}

.results-table-wrap { flex: 1; overflow: auto; }
.results-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.results-table th {
  background: #0d0d0d;
  color: #555;
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1a1a1a;
  white-space: nowrap;
  position: sticky;
  top: 0;
}
.results-table td { padding: 5px 8px; border-bottom: 1px solid #0f0f0f; white-space: nowrap; }
.results-table tr:hover td { background: #141414; }

.td-num  { color: #555; font-family: monospace; }
.td-sym a { color: #64b5f6; text-decoration: none; font-weight: 700; }
.td-sym a:hover { text-decoration: underline; }
.td-name  { color: #aaa; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.td-meta  { color: #666; }
.td-change.up   { color: #26a69a; }
.td-change.down { color: #ef5350; }
.td-spark  { padding: 2px 8px; }
.th-spark  { padding: 3px 8px; vertical-align: middle; }
.td-action { text-align: center; }
.btn-add-wl {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 13px;
  padding: 0 4px;
}
.btn-add-wl:hover { color: #ffb74d; }

/* ── Watchlist menu ───────────────────────────────────────── */
.wl-menu {
  position: fixed;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  z-index: 1000;
  min-width: 160px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}
.wl-menu-title { padding: 6px 10px; font-size: 10px; color: #555; border-bottom: 1px solid #2a2a2a; text-transform: uppercase; }
.wl-menu-item { padding: 7px 10px; cursor: pointer; font-size: 12px; color: #ccc; }
.wl-menu-item:hover { background: #2a2a2a; color: #fff; }
.wl-menu-new { color: #64b5f6; border-top: 1px solid #222; margin-top: 2px; }

.no-matches { color: #444; padding: 24px 0; font-style: italic; }
.screener-empty { display: flex; align-items: center; justify-content: center; height: 200px; color: #333; }

/* ── Browse panel ─────────────────────────────────────────── */
.browse-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #0a0a0a;
}

.browse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.browse-title { font-weight: 700; color: #fff; font-size: 13px; }
.btn-close-browse {
  background: none;
  border: 1px solid #333;
  color: #666;
  border-radius: 3px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.btn-close-browse:hover { border-color: #555; color: #aaa; }

.browse-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px;
  background: #0d0d0d;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.browse-search { flex: 1; min-width: 160px; }

.browse-results-wrap {
  flex: 1;
  overflow: auto;
  padding: 0 16px 8px;
}
.browse-loading { padding: 24px; text-align: center; color: #444; font-size: 12px; }

.browse-pager {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-top: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.btn-page {
  background: #141414;
  border: 1px solid #2a2a2a;
  color: #888;
  border-radius: 3px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.btn-page:hover:not(:disabled) { border-color: #555; color: #ccc; }
.btn-page:disabled { opacity: 0.3; cursor: not-allowed; }
.page-info { font-size: 11px; color: #555; }

/* sidebar browse button */
.sidebar-actions { display: flex; gap: 6px; }
.btn-browse {
  background: none;
  border: 1px solid #333;
  color: #888;
  border-radius: 3px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.btn-browse:hover { border-color: #64b5f6; color: #64b5f6; }
</style>
