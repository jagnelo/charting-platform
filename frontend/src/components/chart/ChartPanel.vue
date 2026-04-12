<template>
  <div
    class="chart-panel"
    :class="{ 'is-active': isActive }"
    @mousedown="layoutStore.setActivePanel(panelId)"
  >
    <!-- Panel header -->
    <div class="panel-header">
      <!-- Symbol badge — click to open inline search for this panel -->
      <div class="panel-sym-wrap" ref="symWrapRef">
        <button
          class="panel-sym-btn"
          :title="store.symbol ? 'Change symbol for this panel' : 'Search symbol'"
          @click.stop="toggleSearch"
        >
          <span v-if="store.symbol" class="psym">{{ store.symbol }}</span>
          <span v-else class="psym-empty">Symbol…</span>
        </button>
        <!-- Inline search dropdown -->
        <div v-if="searchOpen" class="panel-search-dropdown" @click.stop>
          <input
            ref="searchInputRef"
            v-model="searchQuery"
            class="panel-search-input"
            placeholder="Symbol…"
            @input="onSearchInput"
            @keydown.escape="closeSearch"
            @keydown.enter="selectFirst"
            @keydown.arrow-down.prevent="moveDown"
            @keydown.arrow-up.prevent="moveUp"
          />
          <div v-if="searchResults.length" class="panel-search-results">
            <div
              v-for="(r, i) in searchResults"
              :key="r.symbol"
              :class="['psr-item', { highlighted: i === hlIdx }]"
              @click="selectResult(r)"
              @mouseenter="hlIdx = i"
            >
              <span class="psr-sym">{{ r.symbol }}</span>
              <span class="psr-name">{{ r.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Link toggle: chain icon -->
      <button
        class="panel-link-btn"
        :class="{ linked: panelConfig?.linkedToGlobal }"
        :title="panelConfig?.linkedToGlobal ? 'Unlink from global search' : 'Link to global search'"
        @click.stop="toggleLink"
      >
        <span v-if="panelConfig?.linkedToGlobal" class="link-icon">⛓</span>
        <span v-else class="link-icon unlinked">⛓‍💥</span>
      </button>

      <span v-if="store.instrument?.name" class="psym-name">{{ store.instrument.name }}</span>

      <TimeframeSelector v-model="localTf" class="panel-tf" />
    </div>

    <!-- Chart area -->
    <div class="panel-body">
      <div v-if="store.isLoading" class="panel-loading">
        Loading {{ store.symbol || '…' }}
      </div>
      <div v-else-if="!store.symbol" class="panel-empty">
        Click symbol to search
      </div>
      <UPlotChart v-else ref="chartRef" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, provide, onMounted, onUnmounted, nextTick } from 'vue'
import { usePanelStore }   from '@/stores/chart'
import { useLayoutStore }  from '@/stores/layout'
import { useDrawingsStore } from '@/stores/drawings'
import TimeframeSelector from '@/components/chart/TimeframeSelector.vue'
import UPlotChart        from '@/components/chart/UPlotChart.vue'
import { api }           from '@/lib/api'
import type { Timeframe } from '@/types'

interface SearchResult { symbol: string; name: string; exchange: string; type: string }

const props = defineProps<{ panelId: string }>()

// Provide panel ID so UPlotChart uses the correct store instance
provide('panelId', props.panelId)

const layoutStore = useLayoutStore()
const store       = usePanelStore(props.panelId)
const drawStore   = useDrawingsStore()
const chartRef    = ref<InstanceType<typeof UPlotChart> | null>(null)

const panelConfig = computed(() => layoutStore.panels.find(p => p.id === props.panelId))
const isActive    = computed(() => layoutStore.activePanelId === props.panelId)

const localTf = ref<Timeframe>(panelConfig.value?.timeframe ?? 'D1')

// ── Inline search ──────────────────────────────────────────────────────────
const searchOpen    = ref(false)
const searchQuery   = ref('')
const searchResults = ref<SearchResult[]>([])
const hlIdx         = ref(0)
const symWrapRef    = ref<HTMLDivElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

async function toggleSearch() {
  if (searchOpen.value) { closeSearch(); return }
  searchOpen.value = true
  searchQuery.value = store.symbol ?? ''
  await nextTick()
  searchInputRef.value?.select()
}

function closeSearch() {
  searchOpen.value = false
  searchQuery.value = ''
  searchResults.value = []
}

async function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQuery.value) { searchResults.value = []; return }
  searchTimer = setTimeout(async () => {
    try {
      searchResults.value = await api.get('/instruments/search', { q: searchQuery.value })
      hlIdx.value = 0
    } catch { /* ignore */ }
  }, 250)
}

async function selectResult(r: SearchResult) {
  closeSearch()
  await onSymbolSelect(r.symbol)
}

function selectFirst() {
  if (searchResults.value.length) selectResult(searchResults.value[hlIdx.value])
}

function moveDown() { hlIdx.value = Math.min(hlIdx.value + 1, searchResults.value.length - 1) }
function moveUp()   { hlIdx.value = Math.max(hlIdx.value - 1, 0) }

function handleClickOutside(e: MouseEvent) {
  if (symWrapRef.value && !symWrapRef.value.contains(e.target as Node)) closeSearch()
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))

// ── Symbol / link actions ──────────────────────────────────────────────────
function toggleLink() {
  const cfg = panelConfig.value
  if (!cfg) return
  layoutStore.updatePanel(props.panelId, { linkedToGlobal: !cfg.linkedToGlobal })
}

async function onSymbolSelect(symbol: string) {
  layoutStore.updatePanel(props.panelId, { symbol, timeframe: localTf.value })
  await store.loadBars(symbol, localTf.value)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, localTf.value)
  }
}

watch(localTf, async (tf) => {
  layoutStore.updatePanel(props.panelId, { timeframe: tf })
  if (!store.symbol) return
  await store.loadBars(store.symbol, tf)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, tf)
  }
})

// Cross-panel cursor sync: when another panel moves the cursor, jump here too
watch(
  () => layoutStore.syncedTs,
  (ts) => {
    if (!ts || layoutStore.syncSourcePanel === props.panelId) return
    chartRef.value?.jumpToTs(ts)
  },
  { flush: 'sync' }
)

// Restore symbol from layout config on mount
onMounted(async () => {
  const cfg = panelConfig.value
  if (cfg?.symbol) {
    await store.loadBars(cfg.symbol, cfg.timeframe)
    if (store.instrument) {
      await drawStore.loadDrawings(store.instrument.id, cfg.timeframe)
    }
  }
})
</script>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #1a1a1a;
  background: #0a0a0a;
  position: relative;
}

.chart-panel.is-active { border-color: #2a3a4a; }

.panel-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: #111;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.panel-sym-wrap {
  position: relative;
}

.panel-sym-btn {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.4;
  transition: background 0.1s;
}
.panel-sym-btn:hover { background: #222; border-color: #3a3a3a; }

.psym-empty { color: #444; font-weight: 400; }

.panel-search-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 200;
  background: #111;
  border: 1px solid #333;
  border-radius: 4px;
  min-width: 240px;
}

.panel-search-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  background: #1a1a1a;
  border: none;
  border-bottom: 1px solid #222;
  color: #ccc;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  padding: 7px 10px;
  outline: none;
}

.panel-search-results { max-height: 200px; overflow-y: auto; }

.psr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 11px;
}
.psr-item.highlighted { background: #1a2a3a; }
.psr-sym { color: #64b5f6; font-weight: 700; min-width: 56px; font-family: monospace; }
.psr-name { color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.panel-link-btn {
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 2px 5px;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  opacity: 0.5;
  transition: opacity 0.15s, border-color 0.15s;
}
.panel-link-btn:hover { opacity: 1; border-color: #333; }
.panel-link-btn.linked { opacity: 1; }
.link-icon { display: block; }

.psym-name {
  font-size: 10px;
  color: #555;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.panel-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.panel-loading,
.panel-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #444;
  font-size: 12px;
}
</style>
