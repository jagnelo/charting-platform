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
              v-if="isExpression"
              :class="['psr-item', 'psr-item--expr', { highlighted: hlIdx === 0 }]"
              @click="selectExpression"
              @mouseenter="hlIdx = 0"
            >
              <span class="psr-sym">f(x)</span>
              <span class="psr-name">Create expression chart: {{ searchQuery }}</span>
            </div>
            <template v-else>
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
            </template>
          </div>
        </div>
      </div>

      <!-- Symbol link group -->
      <div class="panel-link-wrap" ref="linkWrapRef">
        <button
          class="panel-link-btn"
          :class="{ linked: !!linkGroup }"
          :style="{ borderColor: linkGroup ? linkColor : undefined, color: linkGroup ? linkColor : undefined }"
          :title="linkGroup ? `Symbol link group: ${linkGroup}` : 'Symbol link disabled'"
          @click.stop="linkMenuOpen = !linkMenuOpen"
        >
          <span class="link-dot" :style="{ background: linkColor }" />
        </button>
        <div v-if="linkMenuOpen" class="panel-link-menu" @click.stop>
          <button class="plm-item" :class="{ active: !linkGroup }" @click="setLinkGroup(null)">
            <span class="plm-dot plm-dot--none" /> None
          </button>
          <button
            v-for="group in PANEL_LINK_GROUPS"
            :key="group.id"
            class="plm-item"
            :class="{ active: linkGroup === group.id }"
            @click="setLinkGroup(group.id)"
          >
            <span class="plm-dot" :style="{ background: group.color }" /> {{ group.label }}
          </button>
        </div>
      </div>

      <span v-if="store.instrument?.name" class="psym-name">{{ store.instrument.name }}</span>

      <TimeframeSelector v-if="store.symbol" v-model="localTf" class="panel-tf" />
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
import { usePanelLinksStore, PANEL_LINK_GROUPS } from '@/stores/panelLinks'
import { useDrawingsStore } from '@/stores/drawings'
import { useAlertsStore } from '@/stores/alerts'
import TimeframeSelector from '@/components/chart/TimeframeSelector.vue'
import UPlotChart        from '@/components/chart/UPlotChart.vue'
import { api }           from '@/lib/api'
import type { Timeframe } from '@/types'

interface SearchResult { symbol: string; name: string; exchange: string; type: string }

const props = defineProps<{ panelId: string }>()

// Provide panel ID so UPlotChart uses the correct store instance
provide('panelId', props.panelId)

const layoutStore = useLayoutStore()
const panelLinks  = usePanelLinksStore()
const store       = usePanelStore(props.panelId)
const drawStore   = useDrawingsStore()
const alertsStore = useAlertsStore()
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
const linkWrapRef   = ref<HTMLDivElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null
const linkMenuOpen = ref(false)

const linkGroup = computed(() => panelLinks.groupFor(props.panelId))
const linkColor = computed(() => panelLinks.colorFor(props.panelId))

const EXPR_RE = /^\s*=/
const isExpression = computed(() => EXPR_RE.test(searchQuery.value.trim()))

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
  if (isExpression.value) {
    searchResults.value = [{ symbol: searchQuery.value.trim(), name: '', exchange: '', type: 'Synthetic' }]
    hlIdx.value = 0
    return
  }
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

async function selectExpression() {
  const expr = searchQuery.value.trim()
  if (!expr) return
  try {
    const instr = await api.post<{ symbol: string }>('/instruments/resolve-expression', { expression: expr })
    closeSearch()
    await onSymbolSelect(instr.symbol)
  } catch (e) {
    console.error('Failed to resolve expression', e)
  }
}

function selectFirst() {
  if (isExpression.value) { selectExpression(); return }
  if (searchResults.value.length) selectResult(searchResults.value[hlIdx.value])
}

function moveDown() { hlIdx.value = Math.min(hlIdx.value + 1, searchResults.value.length - 1) }
function moveUp()   { hlIdx.value = Math.max(hlIdx.value - 1, 0) }

function handleClickOutside(e: MouseEvent) {
  if (symWrapRef.value && !symWrapRef.value.contains(e.target as Node)) closeSearch()
  if (linkWrapRef.value && !linkWrapRef.value.contains(e.target as Node)) linkMenuOpen.value = false
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', handleClickOutside))

// ── Symbol / link actions ──────────────────────────────────────────────────
function setLinkGroup(group: ReturnType<typeof panelLinks.groupFor>) {
  panelLinks.setPanelGroup(props.panelId, group)
  linkMenuOpen.value = false
}

async function onSymbolSelect(symbol: string) {
  const targetIds = panelLinks.linkedPanelIds(props.panelId, layoutStore.panels.map(p => p.id))
  for (const id of targetIds) {
    const panel = layoutStore.panels.find(p => p.id === id)
    if (!panel) continue
    const tf = id === props.panelId ? localTf.value : panel.timeframe
    const pStore = id === props.panelId ? store : usePanelStore(id)
    layoutStore.updatePanel(id, { symbol, timeframe: tf })
    await pStore.loadBars(symbol, tf)
  }
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, localTf.value)
    await alertsStore.loadAlerts(store.instrument.id)
  }
}

watch(localTf, async (tf) => {
  layoutStore.updatePanel(props.panelId, { timeframe: tf })
  if (!store.symbol) return
  await store.loadBars(store.symbol, tf)
  if (store.instrument) {
    await drawStore.loadDrawings(store.instrument.id, tf)
    await alertsStore.loadAlerts(store.instrument.id)
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
      await alertsStore.loadAlerts(store.instrument.id)
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
.psr-item--expr { border-left: 2px solid #64b5f6; }
.psr-sym { color: #64b5f6; font-weight: 700; min-width: 56px; font-family: monospace; }
.psr-name { color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.panel-link-wrap {
  position: relative;
}

.panel-link-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  width: 22px;
  height: 22px;
  padding: 0;
  cursor: pointer;
  line-height: 1;
  opacity: 0.5;
  transition: opacity 0.15s, border-color 0.15s;
}
.panel-link-btn:hover { opacity: 1; border-color: #333; }
.panel-link-btn.linked { opacity: 1; }
.link-dot {
  display: block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #555;
}

.panel-link-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 210;
  min-width: 104px;
  padding: 3px 0;
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.45);
}
.plm-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 9px;
  background: none;
  border: none;
  color: #888;
  cursor: pointer;
  font-family: monospace;
  font-size: 11px;
  text-align: left;
}
.plm-item:hover,
.plm-item.active { background: #1d1d1d; color: #ddd; }
.plm-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.plm-dot--none {
  background: transparent;
  border: 1px solid #555;
}

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
