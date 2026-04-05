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
        <div
          v-for="s in screeners"
          :key="s.id"
          :class="['screener-item', { active: selectedId === s.id }]"
          @click="select(s)"
        >
          <div class="si-name">{{ s.name }}</div>
          <div class="si-meta">{{ s.timeframe }} · {{ s.universe_type }}</div>
        </div>
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
          placeholder="Search symbol or name…"
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
                  v-if="watchlistStore.watchlists.length"
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
            <select v-model="cond.type" class="form-select cond-type" @change="onCondTypeChange(cond)">
              <option value="indicator_threshold">Indicator vs Value</option>
              <option value="indicator_cross">Indicator vs Indicator</option>
              <option value="price_threshold">Price vs Value</option>
              <option value="price_change_period">Price % Change (period)</option>
              <option value="price_change">Price % Change (bars)</option>
            </select>

            <template v-if="cond.type === 'indicator_threshold'">
              <select v-model="cond.indicator" class="form-select cond-ind">
                <option v-for="ind in INDICATOR_TYPES" :key="ind" :value="ind">{{ ind.toUpperCase() }}</option>
              </select>
              <input
                v-if="['rsi','sma','ema','bb','atr','stoch','cci','adx'].includes(cond.indicator)"
                v-model.number="cond.params.period"
                type="number" class="form-input cond-param" placeholder="period"
              />
              <select v-model="cond.op" class="form-select cond-op">
                <option value="lt">&lt;</option><option value="lte">≤</option>
                <option value="gt">&gt;</option><option value="gte">≥</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.01" />
            </template>

            <template v-else-if="cond.type === 'indicator_cross'">
              <select v-model="cond.indicator_a.type" class="form-select cond-ind">
                <option v-for="ind in INDICATOR_TYPES" :key="ind" :value="ind">{{ ind.toUpperCase() }}</option>
              </select>
              <span class="cond-label">crosses</span>
              <select v-model="cond.op" class="form-select" style="width:120px">
                <option value="crosses_above">above</option>
                <option value="crosses_below">below</option>
                <option value="gt">above (current)</option>
                <option value="lt">below (current)</option>
              </select>
              <select v-model="cond.indicator_b.type" class="form-select cond-ind">
                <option v-for="ind in INDICATOR_TYPES" :key="ind" :value="ind">{{ ind.toUpperCase() }}</option>
              </select>
            </template>

            <template v-else-if="cond.type === 'price_threshold'">
              <select v-model="cond.field" class="form-select cond-ind">
                <option value="close">Close</option><option value="open">Open</option>
                <option value="high">High</option><option value="low">Low</option>
                <option value="volume">Volume</option>
              </select>
              <select v-model="cond.op" class="form-select cond-op">
                <option value="gt">&gt;</option><option value="lt">&lt;</option>
                <option value="gte">≥</option><option value="lte">≤</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.01" />
            </template>

            <template v-else-if="cond.type === 'price_change_period'">
              <span class="cond-label">over</span>
              <select v-model="cond.period" class="form-select" style="width:70px">
                <option v-for="p in PERIODS" :key="p" :value="p">{{ p }}</option>
              </select>
              <select v-model="cond.op" class="form-select cond-op">
                <option value="gt">&gt;</option><option value="lt">&lt;</option>
                <option value="gte">≥</option><option value="lte">≤</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.001" placeholder="0.03" />
            </template>

            <template v-else-if="cond.type === 'price_change'">
              <span class="cond-label">over</span>
              <input v-model.number="cond.lookback_bars" type="number" class="form-input cond-param" placeholder="bars" />
              <span class="cond-label">bars</span>
              <select v-model="cond.op" class="form-select cond-op">
                <option value="gt">&gt;</option><option value="lt">&lt;</option>
              </select>
              <input v-model.number="cond.value" type="number" class="form-input cond-val" step="0.001" placeholder="0.03" />
            </template>

            <button class="btn-remove-cond" @click="draftConditions.splice(i, 1)">✕</button>
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
            <template v-if="showSaveWlForm">
              <input v-model="saveWlName" class="form-input wl-name-input" placeholder="Watchlist name…"
                     @keydown.enter="saveResultsAsWatchlist" @keydown.esc="showSaveWlForm = false" />
              <button class="btn-save-wl-confirm" :disabled="!saveWlName.trim()" @click="saveResultsAsWatchlist">Save</button>
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
                    v-if="watchlistStore.watchlists.length"
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
        v-for="wl in watchlistStore.watchlists"
        :key="wl.id"
        class="wl-menu-item"
        @click="addToWatchlist(wl.id)"
      >
        {{ wl.name }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'

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

const watchlistStore = useWatchlistStore()

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
const wlMenuX    = ref(0)
const wlMenuY    = ref(0)
const wlMenuRef  = ref<HTMLElement | null>(null)

function onDocClick(e: MouseEvent) {
  if (wlMenuInstrId.value !== null && wlMenuRef.value && !wlMenuRef.value.contains(e.target as Node)) {
    wlMenuInstrId.value = null
  }
}

// Save-as-watchlist state
const showSaveWlForm = ref(false)
const saveWlName     = ref('')

const selectedScreener = computed(() => screeners.value.find(s => s.id === selectedId.value) ?? null)
const latestResult     = computed(() => results.value[0] ?? null)
const displayResult    = computed(() =>
  running.value && streamingResult.value ? streamingResult.value : latestResult.value
)

const TIMEFRAMES = ['M1','M5','M15','M30','H1','H2','H4','H12','D1','W1','MN']
const INDICATOR_TYPES = ['rsi','sma','ema','macd','bb','vwap','avwap','atr','stoch','cci','adx']
const PERIODS = ['1D','1W','1M','MTD','YTD','1Y']

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
    draftConditions.value = (conds.conditions || []).filter((c: any) => c.type !== 'fundamental_filter')
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
  draftConditions.value.push({
    type: 'indicator_threshold',
    indicator: 'rsi',
    params: { period: 14 },
    op: 'lt',
    value: 30,
  })
}

function onCondTypeChange(cond: any) {
  if (cond.type === 'price_change_period') {
    cond.period = '1D'
    cond.op = 'gt'
    cond.value = 0
  } else if (cond.type === 'indicator_cross') {
    cond.indicator_a = { type: 'sma', params: { period: 20 } }
    cond.indicator_b = { type: 'sma', params: { period: 50 } }
    cond.op = 'crosses_above'
  }
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

async function saveResultsAsWatchlist() {
  if (!saveWlName.value.trim() || !latestResult.value) return
  const wl = await watchlistStore.createWatchlist(saveWlName.value.trim())
  if (!wl) return
  const symbols = latestResult.value.matched_ids
    .map(id => instrMap.value[id]?.symbol)
    .filter((s): s is string => !!s && !/^\d+$/.test(s))
  await Promise.allSettled(symbols.map(sym => watchlistStore.addBySymbol(wl.id, sym)))
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
  await watchlistStore.loadWatchlists()
  filterOptions.value = await api.get<FilterOptions>('/instruments/filter-options').catch(() => filterOptions.value)

  // Activate browse mode if ?q= is in the URL
  const q = route.query.q as string | undefined
  if (q) {
    browseMode.value = true
    browseQ.value = q
    await fetchBrowse()
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
.screener-item { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #111; }
.screener-item:hover { background: #111; }
.screener-item.active { background: #0f1f30; border-left: 2px solid #64b5f6; }
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
