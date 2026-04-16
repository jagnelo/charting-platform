<template>
  <div class="dash-search" ref="rootRef">
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
    <div v-if="showDropdown" class="dash-search-results">
      <button
        v-if="isExpression"
        type="button"
        :class="['dash-search-item', 'expr', { highlighted: highlightIdx === 0 }]"
        @click="selectExpression"
        @mouseenter="highlightIdx = 0"
      >
        <b>f(x)</b>
        <span>Create {{ trimmedQuery }}</span>
        <small>Expression</small>
      </button>
      <template v-else>
        <button
          v-for="(result, i) in results"
          :key="result.symbol"
          type="button"
          :class="['dash-search-item', { highlighted: i === highlightIdx }]"
          @click="selectResult(result)"
          @mouseenter="highlightIdx = i"
        >
          <b>{{ result.symbol }}</b>
          <span>{{ result.name }}</span>
          <small>{{ result.type || result.exchange }}</small>
        </button>
        <button
          v-if="trimmedQuery"
          type="button"
          :class="['dash-search-item', 'expr', { highlighted: highlightIdx === results.length }]"
          @click="selectRawSymbol"
          @mouseenter="highlightIdx = results.length"
        >
          <b>{{ trimmedQuery.toUpperCase() }}</b>
          <span>Try this symbol</span>
          <small>Yahoo</small>
        </button>
      </template>
      <div v-if="error" class="dash-search-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface SearchResult {
  symbol: string
  name: string
  exchange: string
  type: string
}

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
}>(), {
  modelValue: '',
  placeholder: 'Symbol or expression...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  select: [value: string]
}>()

const query = ref(props.modelValue)
const results = ref<SearchResult[]>([])
const loading = ref(false)
const error = ref('')
const dismissed = ref(true)
const highlightIdx = ref(0)
const rootRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let searchSeq = 0

const EXPR_RE = /^[A-Z0-9.^]+(\s*[+\-*/]\s*[A-Z0-9.^]+)+$/i
const trimmedQuery = computed(() => query.value.trim())
const isExpression = computed(() => EXPR_RE.test(trimmedQuery.value))
const showDropdown = computed(() =>
  !dismissed.value && (isExpression.value || results.value.length > 0 || trimmedQuery.value.length > 0)
)

watch(() => props.modelValue, value => {
  if (value !== query.value) query.value = value ?? ''
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
  emit('update:modelValue', query.value)
  if (timer) clearTimeout(timer)
  if (!trimmedQuery.value || isExpression.value) {
    searchSeq++
    results.value = []
    highlightIdx.value = 0
    return
  }
  const seq = ++searchSeq
  timer = setTimeout(async () => {
    loading.value = true
    try {
      const loaded = await api.get<SearchResult[]>('/instruments/search', { q: trimmedQuery.value })
      if (seq === searchSeq) {
        results.value = loaded
        highlightIdx.value = 0
      }
    } catch (e: any) {
      if (seq === searchSeq) {
        error.value = e?.message ?? 'Search unavailable'
        results.value = []
      }
    } finally {
      if (seq === searchSeq) loading.value = false
    }
  }, 220)
}

async function selectResult(result: SearchResult) {
  await selectSymbol(result.symbol)
}

async function selectRawSymbol() {
  await selectSymbol(trimmedQuery.value.toUpperCase())
}

async function selectSymbol(symbol: string) {
  loading.value = true
  try {
    await api.get(`/instruments/${encodeURIComponent(symbol)}`)
    commit(symbol.toUpperCase())
  } catch {
    error.value = `Could not find ${symbol}`
    dismissed.value = false
  } finally {
    loading.value = false
  }
}

async function selectExpression() {
  loading.value = true
  try {
    const instrument = await api.post<{ symbol: string }>('/instruments/resolve-expression', {
      expression: trimmedQuery.value,
    })
    commit(instrument.symbol)
  } catch {
    error.value = `Could not resolve ${trimmedQuery.value}`
    dismissed.value = false
  } finally {
    loading.value = false
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
    selectExpression()
    return
  }
  if (highlightIdx.value < results.value.length) {
    selectResult(results.value[highlightIdx.value])
    return
  }
  if (trimmedQuery.value) selectRawSymbol()
}

function moveDown() {
  const max = isExpression.value ? 0 : results.value.length
  highlightIdx.value = Math.min(highlightIdx.value + 1, max)
}

function moveUp() {
  highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
}

function handleClickOutside(event: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) dismiss()
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
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
  position: absolute;
  z-index: 500;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
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
</style>
