<template>
  <div :class="['wl-panel', { 'wl-panel--open': isOpen }]">
    <!-- Toggle strip -->
    <button
      class="wlp-toggle"
      :title="isOpen ? 'Hide watchlists' : 'Show watchlists'"
      @click="isOpen = !isOpen"
    >{{ isOpen ? '‹' : '›' }}</button>

    <!-- Panel body -->
    <div v-show="isOpen" class="wlp-body">
      <!-- Top bar: title + collapse-all + TF selector -->
      <div class="wlp-topbar">
        <span class="wlp-panel-title">Watchlists</span>
        <div class="wlp-topbar-right">
          <SparkTfSelector />
          <button class="wlp-toggle-all" :title="allExpanded ? 'Collapse all' : 'Expand all'" @click="toggleAll">
            {{ allExpanded ? '▲' : '▼' }}
          </button>
        </div>
      </div>

      <!-- Scrollable accordion -->
      <div class="wlp-scroll">
        <template v-if="store.watchlists.length">
          <div v-for="wl in store.watchlists" :key="wl.id" class="wlp-section">
            <!-- Section header -->
            <div class="wlp-section-hdr" @click="toggleSection(wl.id)">
              <span class="wlp-section-arrow">{{ expanded.has(wl.id) ? '▾' : '▸' }}</span>
              <span class="wlp-section-name">{{ wl.name }}</span>
              <!-- Badges -->
              <span v-if="wl.is_managed" class="wlp-badge wlp-badge--managed" title="Managed by screener">⊞</span>
              <span v-if="wl.is_locked" class="wlp-badge wlp-badge--locked" title="Locked">🔒</span>
              <span class="wlp-section-count">{{ activeItemCount(wl) }}</span>
              <!-- Copy button for managed watchlists -->
              <button
                v-if="wl.is_managed"
                class="wlp-hdr-btn"
                title="Copy as independent watchlist"
                @click.stop="store.copyWatchlist(wl.id)"
              >⎘</button>
              <!-- Lock toggle for non-managed watchlists -->
              <button
                v-if="!wl.is_managed"
                :class="['wlp-hdr-btn', wl.is_locked ? 'wlp-hdr-btn--locked' : 'wlp-hdr-btn--unlocked']"
                :title="wl.is_locked ? 'Unlock watchlist' : 'Lock watchlist'"
                @click.stop="wl.is_locked ? store.unlockWatchlist(wl.id) : store.lockWatchlist(wl.id)"
              >{{ wl.is_locked ? '🔒' : '○' }}</button>
            </div>

            <!-- Items (shown when expanded) -->
            <div v-if="expanded.has(wl.id)" class="wlp-section-items">
              <template v-for="item in sortedItems(wl)" :key="item.id">
                <!-- Departed items: shown greyed out with a label -->
                <div
                  v-if="item.left_screener_at"
                  class="wlp-item wlp-item--departed"
                >
                  <div class="wlpi-left">
                    <span class="wlpi-sym">{{ item.symbol }}</span>
                    <span class="wlpi-departed-label">Left screener {{ daysAgo(item.left_screener_at) }}d ago</span>
                  </div>
                </div>
                <!-- Normal items -->
                <div
                  v-else
                  :class="['wlp-item', { 'wlp-item--active': item.symbol === currentSymbol }]"
                  @click="item.symbol && emit('select', item.symbol)"
                >
                  <div class="wlpi-left">
                    <span class="wlpi-sym">{{ item.symbol }}</span>
                    <div v-if="store.priceMap[item.symbol!]" class="wlpi-prices">
                      <span class="wlpi-close">{{ fmt(store.priceMap[item.symbol!].close) }}</span>
                      <span :class="['wlpi-pct', store.priceMap[item.symbol!].pct >= 0 ? 'up' : 'down']">
                        {{ fmtPct(store.priceMap[item.symbol!].pct) }}
                      </span>
                    </div>
                  </div>
                  <Sparkline v-if="item.symbol" :symbol="item.symbol" class="wlpi-spark" />
                </div>
              </template>
              <div v-if="!wl.items.length" class="wlp-no-items">Empty</div>
            </div>
          </div>
        </template>
        <div v-else class="wlp-empty">
          <router-link to="/watchlist" class="wlp-create-link">+ Create a watchlist</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted } from 'vue'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'

const props = defineProps<{ currentSymbol?: string | null }>()
const emit  = defineEmits<{ select: [symbol: string] }>()

const store  = useWatchlistStore()
const isOpen = ref(true)

/** Set of watchlist IDs that are currently expanded */
const expanded = reactive(new Set<number>())

const allExpanded = computed(() => store.watchlists.length > 0 && store.watchlists.every(w => expanded.has(w.id)))

function activeItemCount(wl: Watchlist): number {
  return wl.items.filter(i => !i.left_screener_at).length
}

/** Sort items: active first, departed last (sorted by left_screener_at desc) */
function sortedItems(wl: Watchlist) {
  return [...wl.items].sort((a, b) => {
    if (!a.left_screener_at && b.left_screener_at) return -1
    if (a.left_screener_at && !b.left_screener_at) return 1
    return a.position - b.position
  })
}

function daysAgo(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24))
}

function toggleSection(id: number) {
  if (expanded.has(id)) {
    expanded.delete(id)
  } else {
    expanded.add(id)
    const wl = store.watchlists.find(w => w.id === id)
    if (wl) {
      const syms = wl.items.map(i => i.symbol).filter(Boolean) as string[]
      store.fetchPrices(syms)
    }
  }
}

function toggleAll() {
  if (allExpanded.value) {
    expanded.clear()
  } else {
    for (const wl of store.watchlists) {
      if (!expanded.has(wl.id)) {
        expanded.add(wl.id)
        const syms = wl.items.map(i => i.symbol).filter(Boolean) as string[]
        store.fetchPrices(syms)
      }
    }
  }
}

watch(() => store.watchlists, () => {}, { immediate: true })

// Handle focus requests from membership panel
watch(() => store.focusRequest, (id) => {
  if (id == null) return
  isOpen.value = true
  expanded.clear()
  expanded.add(id)
  const wl = store.watchlists.find(w => w.id === id)
  if (wl) {
    const syms = wl.items.map(i => i.symbol).filter(Boolean) as string[]
    store.fetchPrices(syms)
  }
  store.clearFocusRequest()
})

onMounted(async () => {
  if (!store.watchlists.length) await store.loadWatchlists()
})

function fmt(v: number) {
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: number) {
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}
</script>

<style scoped>
.wl-panel {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  flex-shrink: 0;
  background: #0d0d0d;
  border-right: 1px solid #1a1a1a;
}

.wlp-toggle {
  width: 16px;
  background: #0d0d0d;
  border: none;
  border-right: 1px solid #1a1a1a;
  color: #333;
  cursor: pointer;
  font-size: 10px;
  padding: 0;
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: color 0.1s, background 0.1s;
}
.wlp-toggle:hover { color: #aaa; background: #111; }

.wlp-body {
  width: 220px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wlp-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
  gap: 4px;
}

.wlp-panel-title {
  font-size: 11px;
  font-weight: 700;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.wlp-topbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.wlp-toggle-all {
  background: none;
  border: none;
  color: #444;
  cursor: pointer;
  font-size: 9px;
  padding: 2px 4px;
  border-radius: 2px;
  transition: color 0.1s;
}
.wlp-toggle-all:hover { color: #aaa; }

.wlp-scroll {
  flex: 1;
  overflow-y: auto;
}

/* ── Accordion section ─────────────────────────── */
.wlp-section { border-bottom: 1px solid #111; }

.wlp-section-hdr {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}
.wlp-section-hdr:hover { background: #141414; }

.wlp-section-arrow { font-size: 9px; color: #555; flex-shrink: 0; }
.wlp-section-name  { flex: 1; font-size: 11px; font-weight: 700; color: #ccc; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wlp-section-count { font-size: 10px; color: #444; background: #1a1a1a; border-radius: 8px; padding: 0 5px; flex-shrink: 0; }

.wlp-badge {
  font-size: 9px;
  flex-shrink: 0;
}
.wlp-badge--managed { color: #64b5f6; }
.wlp-badge--locked  { color: #888; }

.wlp-hdr-btn {
  background: none;
  border: none;
  color: #444;
  cursor: pointer;
  font-size: 11px;
  padding: 1px 3px;
  border-radius: 2px;
  flex-shrink: 0;
  transition: color 0.1s;
}
.wlp-hdr-btn:hover { color: #aaa; background: #222; }
.wlp-hdr-btn--locked { color: #888; }
.wlp-hdr-btn--unlocked { color: #2a2a2a; font-size: 9px; }
.wlp-hdr-btn--unlocked:hover { color: #666; }

/* ── Items inside an expanded section ─────────── */
.wlp-section-items { background: #0a0a0a; }

.wlp-item {
  display: flex;
  align-items: center;
  padding: 5px 8px 5px 18px;
  cursor: pointer;
  border-bottom: 1px solid #0f0f0f;
  transition: background 0.1s;
  gap: 6px;
}
.wlp-item:hover { background: #141414; }
.wlp-item--active { background: #0f1929; }
.wlp-item--active .wlpi-sym { color: #64b5f6; }

.wlp-item--departed {
  cursor: default;
  opacity: 0.45;
}
.wlp-item--departed:hover { background: transparent; }

.wlpi-left {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.wlpi-sym   { font-size: 12px; font-weight: 700; color: #ddd; }
.wlpi-prices { display: flex; align-items: center; gap: 4px; }
.wlpi-close { font-size: 10px; color: #aaa; }
.wlpi-pct   { font-size: 10px; font-weight: 600; }
.wlpi-spark { flex-shrink: 0; }

.wlpi-departed-label {
  font-size: 9px;
  color: #444;
  font-style: italic;
}

.up   { color: #26a69a; }
.down { color: #ef5350; }

.wlp-no-items {
  padding: 8px 18px;
  color: #333;
  font-size: 10px;
}

.wlp-empty {
  padding: 20px 8px;
  text-align: center;
}

.wlp-create-link {
  font-size: 11px;
  color: #64b5f6;
  text-decoration: none;
}
.wlp-create-link:hover { text-decoration: underline; }
</style>
