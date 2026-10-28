<template>
  <div class="search-bar" :class="{ 'search-bar--fluid': fluid }" ref="rootRef">
    <div class="search-input-wrap">
      <span class="search-icon">⌕</span>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        :placeholder="placeholder"
        class="search-input"
        @input="onInput"
        @focus="onFocus"
        @keydown.escape="handleEscape"
        @keydown.enter="selectFirst"
        @keydown.arrow-down.prevent="moveDown"
        @keydown.arrow-up.prevent="moveUp"
      />
      <span v-if="loading" class="search-spinner">⟳</span>
    </div>
    <div v-if="showDropdown" class="search-results">
      <!-- Expression chart row (shown instead of normal results when query looks like expression) -->
      <div
        v-if="canResolveExpression"
        :class="['result-item', 'result-item--expr', { highlighted: highlightIdx === 0 }]"
        @click="selectExpression"
        @mouseenter="highlightIdx = 0"
      >
        <span class="r-symbol r-expr-icon">f(x)</span>
        <span class="r-name">{{ expressionActionLabel }}: <em>{{ query }}</em></span>
        <span class="r-type">Synthetic</span>
      </div>
      <template v-else>
        <template v-if="query.trim() && !isExpression">
          <div
            v-for="(r, i) in results"
            :key="r.symbol"
            :class="['result-item', { highlighted: i === highlightIdx }]"
            @click="select(r)"
            @mouseenter="highlightIdx = i"
          >
            <span class="r-symbol">{{ r.symbol }}</span>
            <span class="r-name">{{ r.name }}</span>
            <span class="r-type">{{ r.type }}</span>
          </div>
        </template>
        <template v-else>
          <template v-if="showRecentResults">
            <div class="recent-title">Recently viewed</div>
            <div
              v-for="(r, i) in recentStore.recent"
              :key="r.symbol"
              :class="['result-item', { highlighted: i === highlightIdx }]"
              @click="selectRecent(r.symbol)"
              @mouseenter="highlightIdx = i"
            >
              <span class="r-symbol">{{ r.symbol }}</span>
              <span class="r-name">{{ r.name || 'Recent instrument' }}</span>
              <span class="r-type">Recent</span>
            </div>
          </template>
        </template>
        <section v-if="allowSourceDiscovery && query.trim() && !isExpression" class="search-source-discovery" aria-label="Free source discovery" @keydown.esc="handleEscape">
          <button type="button" :disabled="discoveryLoading || resolvingCandidate" @click="discoverFreeSources">
            {{ discoveryLoading ? 'Searching free sources…' : `Search free sources for ${query.trim().toUpperCase()}` }}
          </button>
          <button
            v-for="candidate in discoveryCandidates"
            :key="`${candidate.provider}:${candidate.symbol}:${candidate.exchange}`"
            type="button"
            class="search-source-candidate"
            :disabled="discoveryLoading || resolvingCandidate"
            @click="resolveCandidate(candidate)"
          >Resolve {{ candidate.symbol }} · {{ candidate.exchange || candidate.provider }} <span>{{ candidate.name }}</span></button>
          <p v-if="discoveryMessage" class="search-message" role="status" aria-live="polite">{{ discoveryMessage }}</p>
          <p v-if="discoveryError" class="search-message search-message--error" role="alert">{{ discoveryError }}</p>
        </section>
        <div v-if="showScreenerShortcut && query.trim() && !isExpression" class="screener-link-row">
          <router-link :to="`/screener?q=${encodeURIComponent(query)}`" class="screener-link" @click="clear">
            Open in Screener →
          </router-link>
        </div>
      </template>
      <div
        v-if="expressionHint || errorMessage"
        class="search-message"
        :class="{ 'search-message--hint': expressionHint && !errorMessage }"
      >
        {{ errorMessage || expressionHint }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api } from '@/lib/api'
import {
  ensureKnownInstrumentSymbol,
  formatInstrumentLookupError,
  getInstrumentInputHint,
  isExpressionInput,
  isResolvableExpressionInput,
} from '@/lib/instruments'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'
import {
  discoverInstruments,
  resolveDiscoveredInstrument,
  type InstrumentDiscoveryCandidate,
} from '@/lib/onDemandAcquisition'

interface SearchResult { symbol: string; name: string; exchange: string; type: string; instrument_id?: number | null; identity_status?: string; explicitlyResolved?: boolean }

const props = withDefaults(defineProps<{
  placeholder?: string
  modelValue?: string
  mode?: 'chart' | 'picker'
  fluid?: boolean
  showRecent?: boolean
  showScreenerLink?: boolean
  resultTypes?: string[]
  allowExpressions?: boolean
  allowSourceDiscovery?: boolean
}>(), {
  placeholder: 'Symbol…',
  modelValue: '',
  mode: 'chart',
  fluid: false,
  showRecent: true,
  showScreenerLink: undefined,
  resultTypes: () => [],
  allowExpressions: true,
  allowSourceDiscovery: false,
})
const emit = defineEmits<{
  select: [symbol: string, result?: SearchResult]
  'update:modelValue': [value: string]
}>()
const recentStore = useRecentInstrumentsStore()

const query            = ref(props.modelValue)
const results          = ref<SearchResult[]>([])
const loading          = ref(false)
const highlightIdx     = ref(0)
const rootRef          = ref<HTMLDivElement | null>(null)
const inputRef         = ref<HTMLInputElement | null>(null)
const expressionSelected = ref(false)
const dropdownDismissed  = ref(true)
const errorMessage       = ref('')
const discoveryCandidates = ref<InstrumentDiscoveryCandidate[]>([])
const discoveryLoading = ref(false)
const resolvingCandidate = ref(false)
const discoveryMessage = ref('')
const discoveryError = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const showRecentResults = computed(() => props.showRecent)
const showScreenerShortcut = computed(() =>
  props.showScreenerLink ?? props.mode === 'chart'
)
const expressionActionLabel = computed(() =>
  props.mode === 'chart' ? 'Create expression chart' : 'Use expression instrument'
)
const isExpression = computed(() =>
  props.allowExpressions && !expressionSelected.value && isExpressionInput(query.value.trim())
)
const canResolveExpression = computed(() =>
  props.allowExpressions && !expressionSelected.value && isResolvableExpressionInput(query.value.trim())
)
const expressionHint = computed(() =>
  expressionSelected.value ? '' : getInstrumentInputHint(query.value.trim())
)
const showDropdown = computed(() =>
  !dropdownDismissed.value
  && (
    isExpression.value
    || results.value.length > 0
    || (props.allowSourceDiscovery && Boolean(query.value.trim()))
    || (!query.value.trim() && showRecentResults.value && recentStore.recent.length > 0)
  )
)

watch(() => props.modelValue, value => {
  if (value !== query.value) query.value = value ?? ''
})

async function onInput() {
  expressionSelected.value = false
  dropdownDismissed.value = false
  errorMessage.value = ''
  discoveryCandidates.value = []
  discoveryMessage.value = ''
  discoveryError.value = ''
  if (debounceTimer) clearTimeout(debounceTimer)
  if (query.value.length < 1) { results.value = []; return }
  // Don't hit search API for expressions
  if (isExpression.value) { results.value = []; return }
  debounceTimer = setTimeout(async () => {
    loading.value = true
    try {
      const loaded = await api.get<SearchResult[]>('/instruments/search', {
        q: query.value,
        canonical_only: true,
        ...(props.resultTypes.length ? { types: props.resultTypes.join(',') } : {}),
      })
      results.value = loaded.filter(matchesResultTypeScope)
      highlightIdx.value = 0
    } finally {
      loading.value = false
    }
  }, 250)
}

async function discoverFreeSources() {
  const requested = query.value.trim()
  if (!props.allowSourceDiscovery || !requested || isExpression.value || discoveryLoading.value) return
  const queryKey = requested.toUpperCase()
  discoveryLoading.value = true
  discoveryError.value = ''
  discoveryMessage.value = ''
  discoveryCandidates.value = []
  try {
    const response = await discoverInstruments(requested, props.resultTypes, 10)
    if (query.value.trim().toUpperCase() !== queryKey) return
    discoveryCandidates.value = response.candidates
    discoveryMessage.value = response.candidates.length
      ? `${response.candidates.length} source candidate${response.candidates.length === 1 ? '' : 's'} found. Resolve a candidate to verify its canonical identity.`
      : response.status === 'held'
        ? 'Free source discovery is held.'
        : response.status === 'unavailable'
          ? 'Free source discovery is unavailable.'
          : response.status === 'no_match'
            ? 'No source candidates matched.'
            : 'No candidates were returned.'
  } catch {
    if (query.value.trim().toUpperCase() === queryKey) {
      discoveryError.value = 'Free source discovery failed. Cached and local results remain available.'
    }
  } finally {
    discoveryLoading.value = false
  }
}

async function resolveCandidate(candidate: InstrumentDiscoveryCandidate) {
  if (resolvingCandidate.value) return
  const queryKey = query.value.trim().toUpperCase()
  resolvingCandidate.value = true
  discoveryError.value = ''
  try {
    const response = await resolveDiscoveredInstrument(candidate)
    if (query.value.trim().toUpperCase() !== queryKey) return
    if (response.status !== 'resolved' || !response.instrument
      || !Number.isSafeInteger(response.instrument.instrument_id) || response.instrument.instrument_id <= 0) {
      discoveryMessage.value = response.status === 'held'
        ? 'Identity resolution is held.'
        : response.status === 'identity_conflict'
          ? 'Identity conflict: this candidate was not opened.'
          : response.status === 'no_match'
            ? 'No canonical instrument matched this candidate.'
            : response.status === 'failed'
              ? 'Identity resolution failed.'
              : 'Candidate identity is not resolved.'
      return
    }
    const result: SearchResult = {
      symbol: response.instrument.symbol,
      name: candidate.name,
      exchange: candidate.exchange,
      type: candidate.type,
      instrument_id: response.instrument.instrument_id,
      identity_status: response.instrument.identity_status,
      explicitlyResolved: true,
    }
    commitSelection(result.symbol, result.name, result)
  } catch {
    if (query.value.trim().toUpperCase() === queryKey) {
      discoveryError.value = 'Identity resolution failed. No chart was opened.'
    }
  } finally {
    resolvingCandidate.value = false
  }
}

function matchesResultTypeScope(result: SearchResult) {
  if (!props.resultTypes.length) return true
  const normalizedType = result.type.trim().toUpperCase()
  return props.resultTypes.some(type => normalizedType.includes(type.trim().toUpperCase()))
}

function onFocus() {
  dropdownDismissed.value = false
  if (!query.value.trim()) highlightIdx.value = 0
}

function select(r: SearchResult) {
  commitSelection(r.symbol, r.name, r)
}

function selectRecent(symbol: string) {
  commitSelection(symbol)
}

async function selectExpression() {
  const expr = query.value.trim()
  loading.value = true
  try {
    const symbol = await ensureKnownInstrumentSymbol(expr)
    commitSelection(symbol, expr)
    expressionSelected.value = true
  } catch (e) {
    errorMessage.value = formatInstrumentLookupError(expr, e)
  } finally {
    loading.value = false
  }
}

function commitSelection(symbol: string, label?: string, result?: SearchResult) {
  emit('update:modelValue', symbol)
  emit('select', symbol, result)
  recentStore.add(symbol, label)
  query.value = symbol
  results.value = []
  discoveryCandidates.value = []
  discoveryMessage.value = ''
  discoveryError.value = ''
  dropdownDismissed.value = true
  errorMessage.value = ''
}

function selectFirst() {
  if (isExpression.value) { void selectExpression(); return }
  if (query.value.trim()) {
    if (highlightIdx.value >= 0 && highlightIdx.value < results.value.length) {
      select(results.value[highlightIdx.value])
      return
    }
  }
  else if (!query.value.trim() && recentStore.recent.length) {
    selectRecent(recentStore.recent[highlightIdx.value]?.symbol ?? recentStore.recent[0].symbol)
  }
}

function moveDown() {
  const len = query.value.trim()
    ? results.value.length
    : recentStore.recent.length
  highlightIdx.value = Math.min(highlightIdx.value + 1, Math.max(0, len - 1))
}
function moveUp()   { highlightIdx.value = Math.max(highlightIdx.value - 1, 0) }
function clear()    {
  query.value = ''
  results.value = []
  discoveryCandidates.value = []
  discoveryMessage.value = ''
  discoveryError.value = ''
  expressionSelected.value = false
  dropdownDismissed.value = true
  errorMessage.value = ''
  emit('update:modelValue', '')
}

function handleEscape() {
  if (props.mode === 'picker') {
    results.value = []
    dropdownDismissed.value = true
    errorMessage.value = ''
    resetToCommitted()
    return
  }
  clear()
}

function resetToCommitted() {
  const committed = props.modelValue ?? ''
  if (query.value !== committed) query.value = committed
}

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    results.value = []
    dropdownDismissed.value = true
    errorMessage.value = ''
    resetToCommitted()
  }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))
</script>

<style scoped>
.search-bar {
  position: relative;
  width: 280px;
}

.search-bar--fluid {
  width: 100%;
}

.search-input-wrap {
  display: flex;
  align-items: center;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 0 8px;
  gap: 6px;
}

.search-icon { color: #555; font-size: 16px; }

.search-input {
  flex: 1;
  background: none;
  border: none;
  color: #ccc;
  font-size: 13px;
  padding: 6px 0;
  outline: none;
  font-family: 'JetBrains Mono', monospace;
}

.search-input::placeholder { color: #444; }

.search-spinner { color: #64b5f6; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.search-results {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #111;
  border: 1px solid #333;
  border-radius: 4px;
  z-index: 100;
  max-height: 260px;
  overflow-y: auto;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  cursor: pointer;
  font-size: 12px;
}

.result-item.highlighted { background: #1a2a3a; }
.result-item--expr { border-left: 2px solid #64b5f6; }
.result-item--expr em { color: #64b5f6; font-style: normal; font-family: 'JetBrains Mono', monospace; }
.recent-title {
  padding: 7px 10px 4px;
  color: #555;
  font-size: 10px;
  text-transform: uppercase;
  border-bottom: 1px solid #1d1d1d;
}

.r-symbol { color: #64b5f6; font-weight: 700; min-width: 60px; font-family: monospace; }
.r-expr-icon { min-width: 44px; font-family: 'JetBrains Mono', monospace; }
.r-name   { flex: 1; color: #aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r-type   { color: #555; font-size: 10px; }

.screener-link-row {
  border-top: 1px solid #222;
  padding: 6px 10px;
  text-align: right;
}
.screener-link {
  color: #64b5f6;
  font-size: 11px;
  text-decoration: none;
}
.screener-link:hover { text-decoration: underline; }
.search-message {
  padding: 7px 10px;
  border-top: 1px solid #241414;
  color: #ef5350;
  font-size: 10px;
}
.search-message--hint {
  border-top-color: #1f2c38;
  color: #8aa3bb;
}
.search-input-wrap, .search-results { border-color: var(--tc-border-strong); border-radius: var(--tc-radius); background: var(--tc-panel-bg); }
.search-input { color: var(--tc-text); font-family: var(--tc-font-family); }
.search-input::placeholder, .search-icon, .recent-title, .r-type { color: var(--tc-text-muted); }
.result-item { color: var(--tc-text); font-family: var(--tc-font-family); }
.result-item.highlighted { background: color-mix(in srgb, var(--tc-accent) 15%, var(--tc-panel-bg)); }
.recent-title, .screener-link-row { border-color: var(--tc-border); }
.r-name { color: var(--tc-text-muted); }
.screener-link { color: var(--tc-accent-soft); }
.search-message--hint { border-color: var(--tc-border); color: var(--tc-text-muted); }
</style>
