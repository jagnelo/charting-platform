<template>
  <div class="search-bar" :class="{ 'search-bar--fluid': fluid }" ref="rootRef">
    <div class="search-input-wrap">
      <span class="search-icon">⌕</span>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        :readonly="readonly"
        :placeholder="placeholder"
        class="search-input"
        role="combobox"
        aria-haspopup="listbox"
        :aria-expanded="showDropdown ? 'true' : 'false'"
        :aria-controls="optionsListId"
        :aria-activedescendant="activeOptionId"
        :aria-label="inputAriaLabel || placeholder"
        @input="onInput"
        @focus="onFocus"
        @keydown.escape="handleEscape"
        @keydown.enter="selectFirst"
        @keydown.arrow-down.prevent="moveDown"
        @keydown.arrow-up.prevent="moveUp"
      />
      <span v-if="loading" class="search-spinner">⟳</span>
    </div>
    <div v-if="showDropdown" :id="dropdownId" class="search-results" role="group" aria-label="Symbol search">
      <!-- Expression chart row (shown instead of normal results when query looks like expression) -->
      <div v-if="canResolveExpression" :id="optionsListId" class="search-option-list" role="listbox" aria-label="Symbol search results">
      <div
        :class="['result-item', 'result-item--expr', { highlighted: highlightIdx === 0 }]"
        role="option"
        :aria-selected="highlightIdx === 0 ? 'true' : 'false'"
        @click="selectExpression"
        @mouseenter="highlightIdx = 0"
      >
        <span class="r-symbol r-expr-icon">f(x)</span>
        <span class="r-name">{{ expressionActionLabel }}: <em>{{ query }}</em></span>
        <span class="r-type">Synthetic</span>
      </div>
      </div>
      <template v-else>
        <template v-if="query.trim() && !isExpression">
          <div :id="optionsListId" class="search-option-list" role="listbox" aria-label="Symbol search results">
          <div
            v-for="(r, i) in results"
            :key="r.symbol"
            :id="optionId(i)"
            :class="['result-item', { highlighted: i === highlightIdx }]"
            role="option"
            :aria-selected="i === highlightIdx ? 'true' : 'false'"
            @click="select(r)"
            @mouseenter="highlightOption(i)"
          >
            <span class="r-symbol">{{ r.symbol }}</span>
            <span class="r-name">{{ r.name }}</span>
            <span class="r-type">{{ r.type }}</span>
          </div>
          <button
            v-for="(candidate, index) in discoveryCandidates"
            :id="candidateOptionId(index)"
            :key="`${candidate.provider}:${candidate.symbol}:${candidate.exchange}`"
            type="button"
            role="option"
            class="search-source-candidate"
            :class="{ highlighted: highlightIdx === results.length + index }"
            :aria-selected="highlightIdx === results.length + index ? 'true' : 'false'"
            :disabled="discoveryLoading || resolvingCandidate"
            @click="resolveCandidate(candidate)"
            @mouseenter="highlightOption(results.length + index)"
          >Use {{ candidate.symbol }} · {{ candidate.exchange || candidate.type }} <span>{{ candidate.name }}</span></button>
          </div>
        </template>
        <template v-else>
          <template v-if="showRecentResults">
            <div class="recent-title">Recently viewed</div>
            <div :id="optionsListId" class="search-option-list" role="listbox" aria-label="Recently viewed symbols">
            <div
              v-for="(r, i) in recentStore.recent"
              :key="r.symbol"
              :id="optionId(i)"
              :class="['result-item', { highlighted: i === highlightIdx }]"
              role="option"
              :aria-selected="i === highlightIdx ? 'true' : 'false'"
              @click="selectRecent(r.symbol)"
              @mouseenter="highlightOption(i)"
            >
              <span class="r-symbol">{{ r.symbol }}</span>
              <span class="r-name">{{ r.name || 'Recent instrument' }}</span>
              <span class="r-type">Recent</span>
            </div>
            </div>
          </template>
        </template>
        <section v-if="allowSourceDiscovery && query.trim() && !isExpression" class="search-source-discovery" aria-label="Ticker availability" @keydown.esc="handleEscape">
          <p v-if="discoveryScheduled || discoveryLoading" class="search-message" role="status" aria-live="polite">No exact local match. Checking ticker availability…</p>
          <p v-if="resolvingCandidate" class="search-message" role="status" aria-live="polite">Verifying ticker identity…</p>
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
import { ref, computed, onMounted, onUnmounted, watch, useId } from 'vue'
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
  type InstrumentAcquireResponse,
} from '@/lib/onDemandAcquisition'
import { scheduleTickerDiscovery, shouldDiscoverTicker, tickerDiscoveryMessage } from '@/lib/workstationSymbolSearch'

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
  readonly?: boolean
  sourceDiscoveryOnly?: boolean
  openOnMount?: boolean
  requiredResolvedSymbol?: string
  resultsId?: string
  inputAriaLabel?: string
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
  readonly: false,
  sourceDiscoveryOnly: false,
  openOnMount: false,
  requiredResolvedSymbol: '',
  resultsId: '',
  inputAriaLabel: '',
})
const emit = defineEmits<{
  select: [symbol: string, result?: SearchResult, confirmedIdentity?: InstrumentAcquireResponse]
  'update:modelValue': [value: string]
}>()
const recentStore = useRecentInstrumentsStore()
const generatedSearchId = useId()
const searchId = computed(() => props.resultsId || `search-bar-${generatedSearchId}`)
const dropdownId = computed(() => `${searchId.value}-popup`)
const optionsListId = computed(() => searchId.value)

const query            = ref(props.modelValue)
const results          = ref<SearchResult[]>([])
const loading          = ref(false)
const highlightIdx     = ref(0)
const rootRef          = ref<HTMLDivElement | null>(null)
const inputRef         = ref<HTMLInputElement | null>(null)
const expressionSelected = ref(false)
const dropdownDismissed  = ref(!props.openOnMount)
const errorMessage       = ref('')
const discoveryCandidates = ref<InstrumentDiscoveryCandidate[]>([])
const discoveryLoading = ref(false)
const discoveryScheduled = ref(false)
const resolvingCandidate = ref(false)
const discoveryMessage = ref('')
const discoveryError = ref('')
const discoveryRetryAt = ref<string | null>(null)
const discoveryHeld = ref(false)
const optionExplicitlyNavigated = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let discoveryTimer: ReturnType<typeof setTimeout> | null = null
let searchGeneration = 0
let pendingSearch: { generation: number; query: string; promise: Promise<void>; resolve: () => void } | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let resolveRetryWait: ((ready: boolean) => void) | null = null
let pendingEnterIntent: { generation: number; query: string; lastRetryAtMs: number } | null = null
let candidateResolutionSequence = 0

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
const activeOptionId = computed(() => {
  if (canResolveExpression.value) return optionsListId.value
  if (query.value.trim() && highlightIdx.value >= 0) {
    if (highlightIdx.value < results.value.length) return optionId(highlightIdx.value)
    const candidateIndex = highlightIdx.value - results.value.length
    if (discoveryCandidates.value[candidateIndex]) return candidateOptionId(candidateIndex)
  }
  if (!query.value.trim() && showRecentResults.value && recentStore.recent[highlightIdx.value]) {
    return optionId(highlightIdx.value)
  }
  return undefined
})

watch(() => props.modelValue, value => {
  if (value !== query.value) {
    invalidateSearch()
    query.value = value ?? ''
  }
})

async function onInput() {
  const generation = ++searchGeneration
  cancelKnownRetryWait()
  pendingEnterIntent = null
  finishPendingSearch()
  beginPendingSearch(generation, query.value.trim())
  optionExplicitlyNavigated.value = false
  expressionSelected.value = false
  dropdownDismissed.value = false
  errorMessage.value = ''
  discoveryCandidates.value = []
  results.value = []
  highlightIdx.value = query.value.trim() ? -1 : 0
  discoveryMessage.value = ''
  discoveryError.value = ''
  discoveryRetryAt.value = null
  discoveryHeld.value = false
  loading.value = false
  if (debounceTimer) clearTimeout(debounceTimer)
  if (discoveryTimer) clearTimeout(discoveryTimer)
  discoveryScheduled.value = false
  // A superseded lookup may still be awaiting its response. Let the newest
  // input start its own bounded lookup; generation checks keep the old result
  // from updating this query.
  discoveryLoading.value = false
  resolvingCandidate.value = false
  if (props.readonly) { results.value = []; finishSearch(generation); return }
  if (query.value.length < 1) { results.value = []; finishSearch(generation); return }
  // Don't hit search API for expressions
  if (isExpression.value) { results.value = []; finishSearch(generation); return }
  const requested = query.value.trim()
  if (props.sourceDiscoveryOnly) {
    results.value = []
    if (!scheduleDiscovery(requested, generation)) finishSearch(generation)
    return
  }
  debounceTimer = setTimeout(async () => {
    loading.value = true
    try {
      const loaded = await api.get<SearchResult[]>('/instruments/search', {
        q: requested,
        canonical_only: true,
        ...(props.resultTypes.length ? { types: props.resultTypes.join(',') } : {}),
      })
      if (generation !== searchGeneration || query.value.trim() !== requested) return
      results.value = loaded.filter(matchesResultTypeScope)
      highlightIdx.value = results.value.length ? 0 : -1
      if (props.allowSourceDiscovery && shouldDiscoverTicker(requested, results.value)) {
        if (!scheduleDiscovery(requested, generation)) finishSearch(generation)
      } else {
        finishSearch(generation)
      }
    } catch {
      if (generation === searchGeneration && query.value.trim() === requested) {
        results.value = []
        errorMessage.value = 'Unable to search canonical instruments. Ticker availability was not checked.'
      }
      finishSearch(generation)
    } finally {
      if (generation === searchGeneration) loading.value = false
    }
  }, 250)
}

function scheduleDiscovery(requested: string, generation: number) {
  if (!props.allowSourceDiscovery || !requested || isExpression.value || !shouldDiscoverTicker(requested, [])) return false
  if (discoveryTimer) clearTimeout(discoveryTimer)
  discoveryScheduled.value = true
  discoveryTimer = scheduleTickerDiscovery(() => {
    if (generation === searchGeneration && query.value.trim() === requested) {
      void discoverTicker(requested, generation)
    } else {
      finishSearch(generation)
    }
  })
  return true
}

async function discoverTicker(requested: string, generation: number) {
  if (!props.allowSourceDiscovery || !requested || isExpression.value || discoveryLoading.value) return
  const queryKey = requested.toUpperCase()
  discoveryLoading.value = true
  discoveryScheduled.value = false
  discoveryError.value = ''
  discoveryMessage.value = ''
  discoveryCandidates.value = []
  try {
    while (true) {
      const response = await discoverInstruments(requested, props.resultTypes, 10)
      if (generation !== searchGeneration || query.value.trim().toUpperCase() !== queryKey) return
      discoveryCandidates.value = response.candidates.filter(matchesResultTypeScope)
      discoveryHeld.value = response.status === 'held'
      discoveryRetryAt.value = response.retry_at
        ?? response.source_outcomes.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at
        ?? null
      discoveryMessage.value = discoveryHeld.value
        ? `Ticker availability is temporarily held${discoveryRetryAt.value ? `; checking again after ${new Date(discoveryRetryAt.value).toLocaleTimeString()}` : '. Enter to check again when ready.'}`
        : tickerDiscoveryMessage(response.status, discoveryCandidates.value.length)
      if (!results.value.length && discoveryCandidates.value.length && highlightIdx.value < 0) highlightIdx.value = 0

      const intent = pendingEnterIntent
      if (!discoveryHeld.value || !discoveryRetryAt.value || !intent
        || intent.generation !== generation || intent.query.toUpperCase() !== queryKey) break
      const retryDue = nextKnownRetryAt(discoveryRetryAt.value, intent.lastRetryAtMs)
      if (retryDue == null) {
        discoveryMessage.value = 'Ticker availability is temporarily held. Press Enter to check again when available.'
        break
      }
      intent.lastRetryAtMs = retryDue
      discoveryLoading.value = false
      discoveryScheduled.value = true
      const ready = await waitForKnownRetry(discoveryRetryAt.value, generation, queryKey, retryDue)
      if (!ready || generation !== searchGeneration || query.value.trim().toUpperCase() !== queryKey) return
      discoveryLoading.value = true
      discoveryScheduled.value = false
      discoveryCandidates.value = []
    }
  } catch {
    if (generation === searchGeneration && query.value.trim().toUpperCase() === queryKey) {
      discoveryError.value = 'Ticker availability could not be checked. Local results remain available.'
    }
  } finally {
    if (generation === searchGeneration) discoveryLoading.value = false
    if (generation === searchGeneration) discoveryScheduled.value = false
    finishSearch(generation)
  }
}

function finishSearch(generation: number) {
  if (!pendingSearch || pendingSearch.generation !== generation) return
  const pending = pendingSearch
  pendingSearch = null
  pending.resolve()
}

function finishPendingSearch() {
  if (!pendingSearch) return
  const pending = pendingSearch
  pendingSearch = null
  pending.resolve()
}

function beginPendingSearch(generation: number, requested: string) {
  finishPendingSearch()
  let resolve!: () => void
  const promise = new Promise<void>(done => { resolve = done })
  pendingSearch = { generation, query: requested, promise, resolve }
  return pendingSearch
}

function cancelKnownRetryWait() {
  if (retryTimer) clearTimeout(retryTimer)
  retryTimer = null
  const resolve = resolveRetryWait
  resolveRetryWait = null
  resolve?.(false)
}

function nextKnownRetryAt(retryAt: string, previousRetryAtMs: number): number | null {
  const due = Date.parse(retryAt)
  if (!Number.isFinite(due) || due <= Date.now() || due <= previousRetryAtMs) return null
  const delay = due - Date.now()
  // Avoid browser timer overflow rather than firing early or creating a retry
  // loop from an implausibly distant admission timestamp.
  if (delay > 2_147_000_000) return null
  return due
}

function waitForKnownRetry(retryAt: string, generation: number, queryKey: string, expectedDue: number): Promise<boolean> {
  const due = Date.parse(retryAt)
  if (!Number.isFinite(due) || due !== expectedDue) return Promise.resolve(false)
  const delay = due - Date.now()
  if (delay <= 0) return Promise.resolve(false)
  cancelKnownRetryWait()
  return new Promise(resolve => {
    resolveRetryWait = resolve
    retryTimer = setTimeout(() => {
      retryTimer = null
      resolveRetryWait = null
      resolve(generation === searchGeneration && query.value.trim().toUpperCase() === queryKey)
    }, delay)
  })
}

function retryHeldDiscoveryForEnter(requested: string, generation: number) {
  const queryKey = requested.toUpperCase()
  const pending = beginPendingSearch(generation, requested)
  pendingEnterIntent = { generation, query: requested, lastRetryAtMs: 0 }
  const retryAt = discoveryRetryAt.value
  const retry = async () => {
    const retryDue = retryAt ? nextKnownRetryAt(retryAt, 0) : null
    if (retryDue != null) {
      discoveryScheduled.value = true
      discoveryMessage.value = `Ticker availability is temporarily held; checking again after ${new Date(retryDue).toLocaleTimeString()}.`
      if (!await waitForKnownRetry(retryAt!, generation, queryKey, retryDue)) {
        discoveryScheduled.value = false
        finishSearch(generation)
        return
      }
      if (pendingEnterIntent?.generation === generation) pendingEnterIntent.lastRetryAtMs = retryDue
    }
    if (generation === searchGeneration && query.value.trim().toUpperCase() === queryKey) {
      void discoverTicker(requested, generation)
    } else finishSearch(generation)
  }
  void retry()
  return pending.promise
}

async function resolveCandidate(candidate: InstrumentDiscoveryCandidate) {
  pendingEnterIntent = null
  candidateResolutionSequence += 1
  cancelKnownRetryWait()
  return resolveCandidateAttempt(candidate, candidateResolutionSequence)
}

async function resolveCandidateAttempt(candidate: InstrumentDiscoveryCandidate, resolutionId: number) {
  const generation = searchGeneration
  const queryKey = query.value.trim().toUpperCase()
  const requiredSymbol = props.requiredResolvedSymbol.trim().toUpperCase()
  if (requiredSymbol && candidate.symbol.trim().toUpperCase() !== requiredSymbol) {
    discoveryMessage.value = 'This candidate does not match the exact reported ticker.'
    return
  }
  resolvingCandidate.value = true
  discoveryError.value = ''
  try {
    let lastRetryAtMs = 0
    while (true) {
      const response = await resolveDiscoveredInstrument(candidate)
      if (resolutionId !== candidateResolutionSequence || generation !== searchGeneration
        || query.value.trim().toUpperCase() !== queryKey) return
      const retryAt = response.retry_at
        ?? response.source_outcomes.find(outcome => outcome.status === 'held' && outcome.retry_at)?.retry_at
        ?? null
      if (response.status === 'held') {
        const retryDue = retryAt ? nextKnownRetryAt(retryAt, lastRetryAtMs) : null
        discoveryRetryAt.value = retryAt
        if (retryDue == null) {
          discoveryMessage.value = 'Identity verification is temporarily held. Select the candidate to try again when available.'
          return
        }
        lastRetryAtMs = retryDue
        discoveryMessage.value = `Identity verification is temporarily held; checking again after ${new Date(retryAt!).toLocaleTimeString()}.`
        if (!await waitForKnownRetry(retryAt!, generation, queryKey, retryDue)) return
        if (resolutionId !== candidateResolutionSequence || generation !== searchGeneration
          || query.value.trim().toUpperCase() !== queryKey) return
        continue
      }
      if (response.status !== 'resolved' || !response.instrument
        || !Number.isSafeInteger(response.instrument.instrument_id) || response.instrument.instrument_id <= 0) {
        discoveryMessage.value = response.status === 'identity_conflict'
          ? 'Identity conflict: this candidate was not opened.'
          : response.status === 'no_match'
            ? 'No canonical instrument matched this candidate.'
            : response.status === 'failed'
              ? 'Identity resolution failed.'
              : 'Candidate identity is not resolved.'
        return
      }
      if (requiredSymbol && response.instrument.symbol.trim().toUpperCase() !== requiredSymbol) {
        discoveryMessage.value = 'The resolved canonical symbol does not match the exact reported ticker.'
        return
      }
      if (requiredSymbol && !['resolved', 'verified'].includes(response.instrument.identity_status.trim().toLowerCase())) {
        discoveryMessage.value = 'The provider did not verify this canonical identity. The holding was not opened.'
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
      commitSelection(result.symbol, result.name, result, response)
      return
    }
  } catch {
    if (resolutionId === candidateResolutionSequence && generation === searchGeneration
      && query.value.trim().toUpperCase() === queryKey) {
      discoveryError.value = 'Ticker identity verification failed. No chart was opened.'
    }
  } finally {
    if (resolutionId === candidateResolutionSequence) resolvingCandidate.value = false
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

function optionId(index: number) {
  return `${optionsListId.value}-option-${index}`
}

function candidateOptionId(index: number) {
  return `${optionsListId.value}-candidate-${index}`
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
    commitSelection(symbol, expr, { symbol, name: expr, exchange: '', type: 'Synthetic' })
    expressionSelected.value = true
  } catch (e) {
    errorMessage.value = formatInstrumentLookupError(expr, e)
  } finally {
    loading.value = false
  }
}

function commitSelection(
  symbol: string,
  label?: string,
  result?: SearchResult,
  confirmedIdentity?: InstrumentAcquireResponse,
) {
  invalidateSearch()
  emit('update:modelValue', symbol)
  if (confirmedIdentity) emit('select', symbol, result, confirmedIdentity)
  else emit('select', symbol, result)
  recentStore.add(symbol, label)
  query.value = symbol
  results.value = []
  discoveryCandidates.value = []
  discoveryMessage.value = ''
  discoveryError.value = ''
  discoveryRetryAt.value = null
  discoveryHeld.value = false
  dropdownDismissed.value = true
  errorMessage.value = ''
}

async function selectFirst() {
  if (isExpression.value) { void selectExpression(); return }
  if (query.value.trim()) {
    if (props.mode === 'chart' && !optionExplicitlyNavigated.value) {
      const submittedQuery = query.value.trim()
      const exact = results.value.find(result =>
        result.symbol.trim().toUpperCase() === submittedQuery.toUpperCase(),
      )
      if (exact) {
        select(exact)
        return
      }
      const generation = searchGeneration
      const pending = pendingSearch
      if (props.allowSourceDiscovery && pending?.generation === generation && pending.query === submittedQuery) {
        pendingEnterIntent = { generation, query: submittedQuery, lastRetryAtMs: 0 }
        await pending.promise
        if (generation !== searchGeneration || query.value.trim() !== submittedQuery) return
        if (pendingEnterIntent?.generation === generation) pendingEnterIntent = null
      } else if (props.allowSourceDiscovery && discoveryHeld.value) {
        await retryHeldDiscoveryForEnter(submittedQuery, generation)
        if (generation !== searchGeneration || query.value.trim() !== submittedQuery) return
        if (pendingEnterIntent?.generation === generation) pendingEnterIntent = null
      }
      if (discoveryHeld.value) return
      if (optionExplicitlyNavigated.value) {
        if (highlightIdx.value >= 0 && highlightIdx.value < results.value.length) {
          select(results.value[highlightIdx.value])
        } else if (highlightIdx.value >= results.value.length && discoveryCandidates.value.length) {
          void resolveCandidate(discoveryCandidates.value[highlightIdx.value - results.value.length])
        }
        return
      }
      const exactCandidates = discoveryCandidates.value.filter(candidate =>
        candidate.symbol.trim().toUpperCase() === submittedQuery.toUpperCase(),
      )
      if (exactCandidates.length === 1) {
        void resolveCandidate(exactCandidates[0])
      } else if (exactCandidates.length > 1) {
        discoveryMessage.value = `More than one listing matches ${submittedQuery.toUpperCase()}. Choose the correct exchange listing.`
      } else {
        commitSelection(submittedQuery)
      }
      return
    }
    if (highlightIdx.value >= 0 && highlightIdx.value < results.value.length) {
      select(results.value[highlightIdx.value])
      return
    }
    if (highlightIdx.value >= results.value.length && discoveryCandidates.value.length) {
      void resolveCandidate(discoveryCandidates.value[highlightIdx.value - results.value.length] ?? discoveryCandidates.value[0])
      return
    }
  }
  else if (!query.value.trim() && recentStore.recent.length) {
    selectRecent(recentStore.recent[highlightIdx.value]?.symbol ?? recentStore.recent[0].symbol)
  }
}

function moveDown() {
  if (pendingEnterIntent) {
    pendingEnterIntent = null
    cancelKnownRetryWait()
  }
  if (query.value.trim() && discoveryCandidates.value.length) {
    const count = results.value.length + discoveryCandidates.value.length
    optionExplicitlyNavigated.value = true
    highlightIdx.value = Math.min(highlightIdx.value + 1, count - 1)
    return
  }
  const len = query.value.trim()
    ? results.value.length
    : recentStore.recent.length
  if (len) optionExplicitlyNavigated.value = true
  highlightIdx.value = Math.min(highlightIdx.value + 1, Math.max(0, len - 1))
}
function moveUp() {
  if (pendingEnterIntent) {
    pendingEnterIntent = null
    cancelKnownRetryWait()
  }
  if (query.value.trim() && discoveryCandidates.value.length) {
    optionExplicitlyNavigated.value = true
    highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
    return
  }
  const len = query.value.trim() ? results.value.length : recentStore.recent.length
  if (len) optionExplicitlyNavigated.value = true
  highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
}
function highlightOption(index: number) {
  highlightIdx.value = index
}
function clear()    {
  invalidateSearch()
  optionExplicitlyNavigated.value = false
  query.value = ''
  results.value = []
  discoveryCandidates.value = []
  discoveryMessage.value = ''
  discoveryError.value = ''
  discoveryRetryAt.value = null
  discoveryHeld.value = false
  expressionSelected.value = false
  dropdownDismissed.value = true
  errorMessage.value = ''
  emit('update:modelValue', '')
}

function handleEscape() {
  if (props.mode === 'picker') {
    invalidateSearch()
    results.value = []
    dropdownDismissed.value = true
    errorMessage.value = ''
    resetToCommitted()
    return
  }
  clear()
}

function invalidateSearch() {
  cancelKnownRetryWait()
  pendingEnterIntent = null
  finishPendingSearch()
  searchGeneration += 1
  optionExplicitlyNavigated.value = false
  if (debounceTimer) clearTimeout(debounceTimer)
  if (discoveryTimer) clearTimeout(discoveryTimer)
  debounceTimer = null
  discoveryTimer = null
  loading.value = false
  discoveryLoading.value = false
  discoveryScheduled.value = false
  resolvingCandidate.value = false
}

function resetToCommitted() {
  const committed = props.modelValue ?? ''
  if (query.value !== committed) query.value = committed
}

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    invalidateSearch()
    results.value = []
    dropdownDismissed.value = true
    errorMessage.value = ''
    resetToCommitted()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', handleClickOutside)
  if (props.openOnMount) dropdownDismissed.value = false
  if (props.openOnMount && props.sourceDiscoveryOnly && props.allowSourceDiscovery) {
    scheduleDiscovery(query.value.trim(), searchGeneration)
  }
})
onUnmounted(() => {
  invalidateSearch()
  document.removeEventListener('mousedown', handleClickOutside)
})
defineExpose({
  focusInput() {
    inputRef.value?.focus()
    inputRef.value?.select()
  },
})
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

.search-source-candidate {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  color: var(--tc-text);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  text-align: left;
}
.search-source-candidate span { color: var(--tc-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-source-candidate.highlighted { background: color-mix(in srgb, var(--tc-accent) 15%, var(--tc-panel-bg)); }
.search-source-candidate:disabled { cursor: wait; opacity: 0.65; }

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
