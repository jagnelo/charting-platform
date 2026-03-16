<template>
  <div class="search-bar" ref="rootRef">
    <div class="search-input-wrap">
      <span class="search-icon">⌕</span>
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        placeholder="Search symbol or company…"
        class="search-input"
        @input="onInput"
        @keydown.escape="clear"
        @keydown.enter="selectFirst"
        @keydown.arrow-down.prevent="moveDown"
        @keydown.arrow-up.prevent="moveUp"
      />
      <span v-if="loading" class="search-spinner">⟳</span>
    </div>
    <div v-if="results.length" class="search-results">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '@/lib/api'

interface SearchResult { symbol: string; name: string; exchange: string; type: string }

const emit = defineEmits<{ select: [symbol: string] }>()

const query        = ref('')
const results      = ref<SearchResult[]>([])
const loading      = ref(false)
const highlightIdx = ref(0)
const rootRef      = ref<HTMLDivElement | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

async function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (query.value.length < 1) { results.value = []; return }
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

function selectFirst() {
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

.r-symbol { color: #64b5f6; font-weight: 700; min-width: 60px; font-family: monospace; }
.r-name   { flex: 1; color: #aaa; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r-type   { color: #555; font-size: 10px; }
</style>
