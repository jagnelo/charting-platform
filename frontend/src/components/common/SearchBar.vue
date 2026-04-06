<template>
  <div class="search-bar" ref="rootRef">
    <div class="search-input-wrap">
      <span class="search-icon">⌕</span>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        :placeholder="placeholder"
        class="search-input"
        @input="onInput"
        @keydown.escape="clear"
        @keydown.enter="selectFirst"
        @keydown.arrow-down.prevent="moveDown"
        @keydown.arrow-up.prevent="moveUp"
      />
      <span v-if="loading" class="search-spinner">⟳</span>
    </div>
    <div v-if="showDropdown" class="search-results">
      <!-- Expression chart row (shown instead of normal results when query looks like expression) -->
      <div
        v-if="isExpression"
        :class="['result-item', 'result-item--expr', { highlighted: highlightIdx === 0 }]"
        @click="selectExpression"
        @mouseenter="highlightIdx = 0"
      >
        <span class="r-symbol r-expr-icon">f(x)</span>
        <span class="r-name">Create expression chart: <em>{{ query }}</em></span>
        <span class="r-type">Synthetic</span>
      </div>
      <template v-else>
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
        <div class="screener-link-row">
          <router-link :to="`/screener?q=${encodeURIComponent(query)}`" class="screener-link" @click="clear">
            Open in Screener →
          </router-link>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@/lib/api'

interface SearchResult { symbol: string; name: string; exchange: string; type: string }

withDefaults(defineProps<{ placeholder?: string }>(), { placeholder: 'Search symbol or company…' })
const emit = defineEmits<{ select: [symbol: string] }>()

const query        = ref('')
const results      = ref<SearchResult[]>([])
const loading      = ref(false)
const highlightIdx = ref(0)
const rootRef      = ref<HTMLDivElement | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Detect if the query looks like a math expression between ticker tokens
const EXPR_RE = /^[A-Z0-9.^]+(\s*[+\-*/]\s*[A-Z0-9.^]+)+$/i
const isExpression = computed(() => EXPR_RE.test(query.value.trim()))
const showDropdown = computed(() => isExpression.value || results.value.length > 0)

async function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (query.value.length < 1) { results.value = []; return }
  // Don't hit search API for expressions
  if (isExpression.value) { results.value = []; return }
  debounceTimer = setTimeout(async () => {
    loading.value = true
    try {
      results.value = await api.get('/instruments/search', { q: query.value })
      highlightIdx.value = 0
    } finally {
      loading.value = false
    }
  }, 250)
}

function select(r: SearchResult) {
  emit('select', r.symbol)
  query.value = r.symbol
  results.value = []
}

async function selectExpression() {
  const expr = query.value.trim()
  loading.value = true
  try {
    const instr = await api.post<{ symbol: string }>('/instruments/resolve-expression', { expression: expr })
    emit('select', instr.symbol)
    query.value = instr.symbol
    results.value = []
  } catch (e) {
    console.error('Failed to resolve expression', e)
  } finally {
    loading.value = false
  }
}

function selectFirst() {
  if (isExpression.value) { selectExpression(); return }
  if (results.value.length) select(results.value[highlightIdx.value])
}

function moveDown() { highlightIdx.value = Math.min(highlightIdx.value + 1, results.value.length - 1) }
function moveUp()   { highlightIdx.value = Math.max(highlightIdx.value - 1, 0) }
function clear()    { query.value = ''; results.value = [] }

function handleClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) results.value = []
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))
</script>

<style scoped>
.search-bar {
  position: relative;
  width: 280px;
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
</style>
