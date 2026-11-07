<template>
  <div class="dash-search" ref="rootRef" @focusout="handleFocusOut">
    <input
      ref="inputRef"
      v-model="query"
      class="dash-search-input"
      :placeholder="placeholder"
      @focus="open"
      @input="onInput"
      @keydown.escape="dismiss"
      @keydown.enter.prevent="selectFirst"
      @keydown.arrow-down.prevent="moveDown"
      @keydown.arrow-up.prevent="moveUp"
    />
    <span v-if="loading" class="dash-search-spin">...</span>
    <Teleport to="body">
      <div v-if="showDropdown" ref="dropdownRef" class="dash-search-results" :style="dropdownStyle" @focusout="handleFocusOut">
        <button
          v-if="canResolveExpression"
          type="button"
          :class="['dash-search-item', 'expr', { highlighted: highlightIdx === 0 }]"
          @click="selectExpression"
          @mouseenter="highlightIdx = 0"
        >
          <b>f(x)</b>
          <span>Create {{ trimmedQuery }}</span>
          <small>Expression</small>
        </button>
        <template v-else-if="!isExpression">
          <button
            v-for="(result, i) in results"
            :key="`${result.symbol}:${result.exchange}:${result.provider}:${result.instrument_id ?? 'new'}`"
            type="button"
            :class="['dash-search-item', { highlighted: i === highlightIdx }]"
            @click="selectResult(result)"
            @mouseenter="highlightIdx = i"
          >
            <b>{{ result.symbol }}</b>
            <span>{{ result.name }}</span>
            <small>{{ result.type || 'Instrument' }}<span v-if="result.exchange"> · {{ result.exchange }}</span></small>
          </button>
        </template>
        <div
          v-if="expressionHint || error"
          class="dash-search-error"
          :class="{ 'dash-search-hint': expressionHint && !error }"
        >
          {{ error || expressionHint }}
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  discoverInstruments,
  resolveDiscoveredInstrument,
  resolveExistingInstrument,
  type InstrumentDiscoveryCandidate,
} from '@/lib/onDemandAcquisition'
import {
  ensureKnownInstrumentSymbol,
  formatInstrumentLookupError,
  getInstrumentInputHint,
  isExpressionInput,
  isResolvableExpressionInput,
} from '@/lib/instruments'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
}>(), {
  modelValue: '',
  placeholder: 'Symbol or =expression...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  select: [value: string]
}>()

const query = ref(props.modelValue)
const results = ref<InstrumentDiscoveryCandidate[]>([])
const loading = ref(false)
const error = ref('')
const dismissed = ref(true)
const highlightIdx = ref(0)
const rootRef = ref<HTMLDivElement | null>(null)
const dropdownRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let searchSeq = 0
let resolveSeq = 0
let mounted = false

const dropdownPos = ref({ top: 0, left: 0, width: 0 })
const dropdownStyle = computed(() => ({
  position: 'fixed' as const,
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: `${dropdownPos.value.width}px`,
  zIndex: 9999,
}))

function updateDropdownPos() {
  if (!inputRef.value) return
  const rect = inputRef.value.getBoundingClientRect()
  dropdownPos.value = { top: rect.bottom + 4, left: rect.left, width: rect.width }
}

const trimmedQuery = computed(() => query.value.trim())
const isExpression = computed(() => isExpressionInput(trimmedQuery.value))
const canResolveExpression = computed(() => isResolvableExpressionInput(trimmedQuery.value))
const expressionHint = computed(() => getInstrumentInputHint(trimmedQuery.value))
const showDropdown = computed(() =>
  !dismissed.value && (isExpression.value || results.value.length > 0 || trimmedQuery.value.length > 0)
)

watch(() => props.modelValue, value => {
  if (value !== query.value) query.value = value ?? ''
})

watch(showDropdown, (val) => {
  if (val) updateDropdownPos()
})

function open() {
  dismissed.value = false
  if (!results.value.length && trimmedQuery.value && !isExpression.value) onInput()
}

function dismiss() {
  dismissed.value = true
}

async function onInput() {
  dismissed.value = false
  error.value = ''
  resolveSeq++
  results.value = []
  highlightIdx.value = 0
  if (timer) clearTimeout(timer)
  if (!trimmedQuery.value || isExpression.value) {
    searchSeq++
    results.value = []
    highlightIdx.value = 0
    return
  }
  const seq = ++searchSeq
  timer = setTimeout(async () => {
    if (!mounted || seq !== searchSeq) return
    loading.value = true
    try {
      const requestedQuery = trimmedQuery.value
      const loaded = await discoverInstruments(requestedQuery, [], 10)
      if (mounted && seq === searchSeq) {
        results.value = loaded.candidates
        highlightIdx.value = 0
        if (!loaded.candidates.length) {
          error.value = discoveryStatusMessage(loaded.status)
        } else if (loaded.status === 'held' || loaded.status === 'unavailable' || loaded.status === 'partial') {
          error.value = discoveryStatusMessage(loaded.status)
        }
        const exact = loaded.status === 'complete'
          ? loaded.candidates.filter(candidate => candidate.symbol.trim().toUpperCase() === requestedQuery.toUpperCase())
          : []
        if (exact.length === 1) await resolveCandidate(exact[0]!, seq)
      }
    } catch (e: any) {
      if (mounted && seq === searchSeq) {
        error.value = 'Instrument discovery is temporarily unavailable. Your current selection is unchanged.'
        results.value = []
      }
    } finally {
      if (mounted && seq === searchSeq) loading.value = false
    }
  }, 220)
}

function discoveryStatusMessage(status: string) {
  if (status === 'held') return 'Instrument discovery is temporarily held. Your current selection is unchanged.'
  if (status === 'unavailable') return 'Instrument discovery is unavailable. Your current selection is unchanged.'
  if (status === 'partial') return 'Some instrument candidates may be missing. Choose only a verified listing.'
  return 'No matching instrument was found. Your current selection is unchanged.'
}

async function selectResult(candidate: InstrumentDiscoveryCandidate) {
  await resolveCandidate(candidate)
}

async function resolveCandidate(
  candidate: InstrumentDiscoveryCandidate,
  expectedSearchSeq?: number,
) {
  if (expectedSearchSeq !== undefined && expectedSearchSeq !== searchSeq) return
  const seq = ++resolveSeq
  loading.value = true
  error.value = ''
  try {
    const response = await resolveDiscoveredInstrument(candidate)
    if (!mounted || seq !== resolveSeq || (expectedSearchSeq !== undefined && expectedSearchSeq !== searchSeq)) return
    if (response.status !== 'resolved' || !response.instrument?.symbol) {
      error.value = resolutionStatusMessage(response.status)
      dismissed.value = false
      return
    }
    commit(response.instrument.symbol)
  } catch {
    if (mounted && seq === resolveSeq) {
      error.value = 'Instrument identity could not be confirmed. Your current selection is unchanged.'
      dismissed.value = false
    }
  } finally {
    if (mounted && seq === resolveSeq) loading.value = false
  }
}

function resolutionStatusMessage(status: string) {
  if (status === 'held') return 'This instrument is temporarily unavailable for selection.'
  if (status === 'identity_conflict') return 'Instrument identity could not be confirmed. Choose a different listing.'
  if (status === 'no_match') return 'No verified instrument matched this selection. Choose a listed candidate.'
  return 'Instrument could not be resolved. Your current selection is unchanged.'
}

async function selectExpression() {
  const seq = ++resolveSeq
  loading.value = true
  const expression = trimmedQuery.value
  try {
    const resolved = await ensureKnownInstrumentSymbol(expression, 'Instrument', { canonicalOnly: true })
    if (mounted && seq === resolveSeq) commit(resolved)
  } catch (e) {
    if (mounted && seq === resolveSeq) {
      error.value = formatInstrumentLookupError(expression, e)
      dismissed.value = false
    }
  } finally {
    if (mounted && seq === resolveSeq) loading.value = false
  }
}

function commit(value: string) {
  query.value = value
  results.value = []
  error.value = ''
  dismissed.value = true
  emit('update:modelValue', value)
  emit('select', value)
}

function selectFirst() {
  if (isExpression.value) {
    void selectExpression()
    return
  }
  if (highlightIdx.value < results.value.length) {
    void selectResult(results.value[highlightIdx.value])
    return
  }
  if (/^[A-Za-z0-9][A-Za-z0-9.-]{0,19}$/.test(trimmedQuery.value)) void resolveTypedExisting()
}

async function resolveTypedExisting() {
  const requested = trimmedQuery.value
  const seq = ++resolveSeq
  loading.value = true
  error.value = ''
  try {
    const response = await resolveExistingInstrument(requested)
    if (!mounted || seq !== resolveSeq || requested !== trimmedQuery.value) return
    if (response.status === 'resolved' && response.instrument?.symbol) commit(response.instrument.symbol)
    else error.value = resolutionStatusMessage(response.status)
  } catch {
    if (mounted && seq === resolveSeq) error.value = 'Instrument identity could not be confirmed. Your current selection is unchanged.'
  } finally {
    if (mounted && seq === resolveSeq) loading.value = false
  }
}

function moveDown() {
  const max = isExpression.value ? 0 : Math.max(0, results.value.length - 1)
  highlightIdx.value = Math.min(highlightIdx.value + 1, max)
}

function moveUp() {
  highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
}

function handleClickOutside(event: MouseEvent) {
  if (!isInsideSearch(event.target)) dismiss()
}

function isInsideSearch(target: EventTarget | null) {
  if (!(target instanceof Node)) return false
  return Boolean(rootRef.value?.contains(target) || dropdownRef.value?.contains(target))
}

function handleFocusOut(event: FocusEvent) {
  if (!isInsideSearch(event.relatedTarget)) dismiss()
}

onMounted(() => {
  mounted = true
  document.addEventListener('mousedown', handleClickOutside)
})
onBeforeUnmount(() => {
  mounted = false
  searchSeq += 1
  resolveSeq += 1
  if (timer) clearTimeout(timer)
  timer = null
})
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))
</script>

<style scoped>
.dash-search {
  position: relative;
  min-width: 0;
}
.dash-search-input {
  width: 100%;
  min-width: 0;
  background: #050505;
  color: #ccc;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: inherit;
  font-size: 11px;
  outline: none;
}
.dash-search-input:focus { border-color: #345; }
.dash-search-spin {
  position: absolute;
  top: 6px;
  right: 7px;
  color: #64b5f6;
  font-size: 10px;
}
.dash-search-results {
  max-height: 230px;
  overflow-y: auto;
  border: 1px solid #333;
  border-radius: 4px;
  background: #101010;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.45);
}
.dash-search-item {
  width: 100%;
  display: grid;
  grid-template-columns: 66px 1fr auto;
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 6px 8px;
  border: 0;
  border-bottom: 1px solid #1a1a1a;
  background: transparent;
  color: #aaa;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  text-align: left;
}
.dash-search-item.highlighted,
.dash-search-item:hover { background: #17222d; }
.dash-search-item.expr { border-left: 2px solid #64b5f6; }
.dash-search-item b {
  color: #64b5f6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dash-search-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dash-search-item small {
  color: #555;
  font-size: 9px;
}
.dash-search-error {
  padding: 7px 9px;
  color: #ef5350;
  font-size: 10px;
  border-top: 1px solid #241414;
}
.dash-search-hint {
  color: #8aa3bb;
  border-top-color: #1f2c38;
}
</style>
