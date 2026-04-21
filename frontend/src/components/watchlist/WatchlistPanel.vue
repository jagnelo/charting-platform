<template>
  <div :class="['wl-panel', { 'wl-panel--open': isOpen }]">
    <!-- Panel body -->
    <div v-show="isOpen" class="wlp-body" :style="props.bodyWidth ? { width: `${props.bodyWidth}px` } : undefined">
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

      <!-- Scrollable accordion — DnD reorderable -->
      <div class="wlp-scroll">
        <template v-if="store.watchlists.length">
          <VueDraggable
            v-model="draggableWatchlists"
            handle=".wlp-drag-handle"
            ghost-class="wlp-ghost"
            @end="onWlReorder"
          >
            <div v-for="wl in draggableWatchlists" :key="wl.id" class="wlp-section">
                <!-- Section header -->
                <div class="wlp-section-hdr" @click="toggleSection(wl.id)">
                  <span class="wlp-drag-handle" title="Drag to reorder" @click.stop>⠿</span>
                  <span class="wlp-section-arrow">{{ expanded.has(wl.id) ? '▾' : '▸' }}</span>
                  <span class="wlp-section-name">{{ wl.name }}</span>
                  <span v-if="wl.is_managed" class="wlp-badge wlp-badge--managed" title="Managed by screener">⊞</span>
                  <span v-if="wl.is_locked" class="wlp-badge wlp-badge--locked" title="Locked">🔒</span>
                  <span class="wlp-section-count">{{ activeItemCount(wl) }}</span>

                  <!-- ⋯ menu button -->
                  <button
                    class="wlp-hdr-btn wlp-menu-btn"
                    title="More options"
                    @click.stop="toggleMenu(wl.id)"
                  >⋯</button>
                </div>

                <!-- Inline rename input (replaces header when renaming) -->
                <div v-if="renamingId === wl.id" class="wlp-rename-row" @click.stop>
                  <input
                    ref="renameInputRef"
                    v-model="renameValue"
                    class="wlp-rename-input"
                    @keydown.enter="commitRename(wl.id)"
                    @keydown.escape="cancelRename"
                    @click.stop
                  />
                  <button class="wlp-rename-confirm" @click.stop="commitRename(wl.id)">✓</button>
                  <button class="wlp-rename-cancel"  @click.stop="cancelRename">✕</button>
                </div>

                <!-- ⋯ dropdown menu -->
                <div v-if="menuOpenId === wl.id" class="wlp-dropdown" @click.stop>
                  <button class="wlp-dd-item" @click.stop="startRename(wl)">Rename</button>
                  <button v-if="canDeleteWatchlist(wl)" class="wlp-dd-item" @click.stop="startDelete(wl.id)">Delete</button>
                  <button class="wlp-dd-item" @click.stop="doCopy(wl.id)">Copy</button>
                  <template v-if="!wl.is_managed">
                    <button v-if="wl.is_locked" class="wlp-dd-item" @click.stop="doUnlock(wl.id)">Unlock</button>
                    <button v-else class="wlp-dd-item" @click.stop="doLock(wl.id)">Lock</button>
                  </template>
                  <!-- Managed badge with screener link -->
                  <div v-if="wl.is_managed && wl.screener_id" class="wlp-dd-managed">
                    Managed by
                    <router-link :to="`/screener?selectedId=${wl.screener_id}`" class="wlp-screener-link" @click="closeMenu">
                      {{ wl.screener_name || 'screener' }}
                    </router-link>
                  </div>
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
                        <div v-if="quoteFor(item.symbol)" class="wlpi-prices">
                          <span :class="['wlpi-close', tickClass(item.symbol)]">{{ fmt(quoteFor(item.symbol)!.close) }}</span>
                          <span :class="['wlpi-pct', quoteFor(item.symbol)!.pct >= 0 ? 'up' : 'down']">
                            {{ fmtPct(quoteFor(item.symbol)!.pct) }}
                          </span>
                          <span class="wlpi-vol">V {{ fmtCompact(quoteFor(item.symbol)!.volume) }}</span>
                          <span class="wlpi-range">
                            {{ fmtCompact(quoteFor(item.symbol)!.dayLow) }}-{{ fmtCompact(quoteFor(item.symbol)!.dayHigh) }}
                          </span>
                        </div>
                      </div>
                      <Sparkline v-if="item.symbol" :symbol="item.symbol" class="wlpi-spark" />
                    </div>
                  </template>
                  <div v-if="!wl.items.length" class="wlp-no-items">Empty</div>
                </div>
              </div>
          </VueDraggable>
        </template>
        <div v-else class="wlp-empty">
          <router-link to="/watchlist" class="wlp-create-link">+ Create a watchlist</router-link>
        </div>
      </div>
    </div>

    <!-- Toggle strip — on the right (inner) side, facing the chart -->
    <button
      class="wlp-toggle"
      :title="isOpen ? 'Hide watchlists' : 'Show watchlists'"
      @click="isOpen = !isOpen"
    >{{ isOpen ? '‹' : '›' }}</button>

    <!-- Delete confirmation modal -->
    <Teleport to="body">
      <div v-if="deleteTargetId !== null" class="wlp-modal-overlay" @click.self="cancelDelete">
        <div class="wlp-modal">
          <p class="wlp-modal-msg">Delete watchlist "{{ store.watchlists.find(w => w.id === deleteTargetId)?.name }}"?</p>
          <div class="wlp-modal-actions">
            <button class="wlp-modal-cancel" @click="cancelDelete">Cancel</button>
            <button class="wlp-modal-confirm" @click="confirmDelete">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'

const props = defineProps<{ currentSymbol?: string | null; bodyWidth?: number }>()
const emit  = defineEmits<{ select: [symbol: string] }>()

const store  = useWatchlistStore()
const isOpen = ref(true)

/** Set of watchlist IDs that are currently expanded */
const expanded = reactive(new Set<number>())
let pollTimer: ReturnType<typeof setInterval> | null = null

function canDeleteWatchlist(wl: Watchlist) {
  return wl.is_managed || !wl.is_locked
}

// DnD — mirror store.watchlists for vue-draggable-plus
const draggableWatchlists = computed({
  get: () => store.watchlists,
  set: (val) => { store.watchlists.splice(0, store.watchlists.length, ...val) },
})

async function onWlReorder() {
  await store.reorderWatchlists(store.watchlists.map(w => w.id))
}

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
    restartPolling()
  } else {
    expanded.add(id)
    const wl = store.watchlists.find(w => w.id === id)
    if (wl) {
      const syms = wl.items.map(i => i.symbol).filter(Boolean) as string[]
      store.fetchPrices(syms)
      restartPolling()
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
  restartPolling()
}

function expandedSymbols(): string[] {
  return store.watchlists
    .filter(wl => expanded.has(wl.id))
    .flatMap(wl => wl.items.map(item => item.symbol).filter(Boolean) as string[])
}

function restartPolling() {
  if (pollTimer) clearInterval(pollTimer)
  const symbols = expandedSymbols()
  if (!symbols.length) return
  pollTimer = setInterval(() => {
    store.fetchPrices(expandedSymbols(), true)
  }, 15_000)
}

// ── ⋯ dropdown menu ────────────────────────────────────────────────────────
const menuOpenId = ref<number | null>(null)

function toggleMenu(id: number) {
  menuOpenId.value = menuOpenId.value === id ? null : id
  cancelRename()
}

function closeMenu() {
  menuOpenId.value = null
}

function handleDocClick() {
  closeMenu()
  cancelRename()
}

onMounted(() => document.addEventListener('click', handleDocClick))
onUnmounted(() => {
  document.removeEventListener('click', handleDocClick)
  if (pollTimer) clearInterval(pollTimer)
})

// ── Rename ──────────────────────────────────────────────────────────────────
const renamingId   = ref<number | null>(null)
const renameValue  = ref('')
const renameInputRef = ref<HTMLInputElement | HTMLInputElement[] | null>(null)
const renameError  = ref('')

function selectRenameInput() {
  const input = Array.isArray(renameInputRef.value)
    ? renameInputRef.value[0]
    : renameInputRef.value
  input?.select()
}

function startRename(wl: Watchlist) {
  closeMenu()
  renamingId.value  = wl.id
  renameValue.value = wl.name
  renameError.value = ''
  nextTick(selectRenameInput)
}

function cancelRename() {
  renamingId.value = null
  renameValue.value = ''
  renameError.value = ''
}

async function commitRename(id: number) {
  const name = renameValue.value.trim()
  if (!name) return
  try {
    await store.renameWatchlist(id, name)
    cancelRename()
  } catch (e: any) {
    if (e?.status === 409) renameError.value = 'Name already exists'
    else renameError.value = 'Rename failed'
  }
}

// ── Delete ──────────────────────────────────────────────────────────────────
const deleteTargetId = ref<number | null>(null)

function startDelete(id: number) {
  closeMenu()
  deleteTargetId.value = id
}

function cancelDelete() {
  deleteTargetId.value = null
}

async function confirmDelete() {
  if (deleteTargetId.value === null) return
  await store.deleteWatchlist(deleteTargetId.value)
  deleteTargetId.value = null
}

// ── Copy / Lock / Unlock ────────────────────────────────────────────────────
async function doCopy(id: number) {
  closeMenu()
  await store.copyWatchlist(id)
}

async function doLock(id: number) {
  closeMenu()
  await store.lockWatchlist(id)
}

async function doUnlock(id: number) {
  closeMenu()
  await store.unlockWatchlist(id)
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
  restartPolling()
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
function fmtCompact(v?: number) {
  if (v == null || !Number.isFinite(v)) return '--'
  const abs = Math.abs(v)
  if (abs >= 1e9) return `${(v / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${(v / 1e3).toFixed(0)}K`
  return String(Math.round(v))
}
function quoteFor(symbol?: string | null) {
  return symbol ? store.priceMap[symbol.toUpperCase()] : null
}
function tickClass(symbol?: string | null) {
  if (!symbol) return ''
  const flash = store.flashMap[symbol.toUpperCase()]
  return flash ? `tick-${flash}` : ''
}
</script>

<style scoped>
.wl-panel {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  flex-shrink: 0;
  background: #0d0d0d;
}

.wlp-toggle {
  width: 16px;
  background: #0d0d0d;
  border: none;
  border-left: 1px solid #1a1a1a;
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
  width: 300px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid #1a1a1a;
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
.wlp-section { border-bottom: 1px solid #111; position: relative; }
.wlp-ghost { opacity: 0.35; background: #1a2a3a; }

.wlp-section-hdr {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 6px 5px 8px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}
.wlp-section-hdr:hover { background: #141414; }

.wlp-drag-handle {
  color: #2a2a2a;
  font-size: 11px;
  cursor: grab;
  flex-shrink: 0;
  line-height: 1;
  padding: 0 1px;
}
.wlp-drag-handle:hover { color: #555; }

.wlp-section-arrow { font-size: 9px; color: #555; flex-shrink: 0; }
.wlp-section-name  { flex: 1; font-size: 11px; font-weight: 700; color: #ccc; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wlp-section-count { font-size: 10px; color: #444; background: #1a1a1a; border-radius: 8px; padding: 0 5px; flex-shrink: 0; }

.wlp-badge {
  font-size: 10px;
  flex-shrink: 0;
}
.wlp-badge--managed { color: #64b5f6; }
.wlp-badge--locked  { color: #888; }

.wlp-hdr-btn {
  background: none;
  border: none;
  color: #444;
  cursor: pointer;
  font-size: 13px;
  padding: 1px 4px;
  border-radius: 2px;
  flex-shrink: 0;
  transition: color 0.1s;
  line-height: 1;
}
.wlp-hdr-btn:hover { color: #aaa; background: #222; }
.wlp-menu-btn { letter-spacing: 0; }

/* ── Rename row ────────────────────────────────── */
.wlp-rename-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: #111;
  border-bottom: 1px solid #1a1a1a;
}

.wlp-rename-input {
  flex: 1;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 3px;
  color: #ccc;
  font-size: 11px;
  font-family: inherit;
  padding: 3px 6px;
  outline: none;
}
.wlp-rename-input:focus { border-color: #64b5f6; }

.wlp-rename-confirm,
.wlp-rename-cancel {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 2px;
  flex-shrink: 0;
}
.wlp-rename-confirm:hover { color: #26a69a; }
.wlp-rename-cancel:hover  { color: #ef5350; }

/* ── ⋯ dropdown ────────────────────────────────── */
.wlp-dropdown {
  position: absolute;
  top: 28px;
  right: 4px;
  z-index: 300;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

.wlp-dd-item {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: #ccc;
  font-size: 11px;
  font-family: inherit;
  padding: 7px 12px;
  cursor: pointer;
  transition: background 0.1s;
}
.wlp-dd-item:hover { background: #2a2a2a; color: #fff; }

.wlp-dd-managed {
  padding: 6px 12px;
  border-top: 1px solid #2a2a2a;
  font-size: 10px;
  color: #555;
}

.wlp-screener-link {
  color: #64b5f6;
  text-decoration: none;
}
.wlp-screener-link:hover { text-decoration: underline; }

/* ── Items inside an expanded section ─────────── */
.wlp-section-items { background: #0a0a0a; }

.wlp-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 58px;
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
.wlpi-prices {
  display: grid;
  grid-template-columns: 62px 56px 54px minmax(0, 1fr);
  align-items: center;
  gap: 5px;
}
.wlpi-close { font-size: 10px; color: #aaa; }
.wlpi-pct   { font-size: 10px; font-weight: 600; }
.wlpi-vol,
.wlpi-range {
  font-size: 9px;
  color: #555;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wlpi-spark { flex-shrink: 0; }

.tick-up {
  animation: tickUp 0.85s ease;
}
.tick-down {
  animation: tickDown 0.85s ease;
}
@keyframes tickUp {
  0% { background: rgba(38,166,154,0.36); color: #d9fff8; }
  100% { background: transparent; color: #aaa; }
}
@keyframes tickDown {
  0% { background: rgba(239,83,80,0.34); color: #ffe1df; }
  100% { background: transparent; color: #aaa; }
}

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

/* ── Delete modal ──────────────────────────────── */
.wlp-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.wlp-modal {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 20px 24px;
  min-width: 260px;
}

.wlp-modal-msg {
  font-size: 13px;
  color: #ccc;
  margin: 0 0 16px;
}

.wlp-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.wlp-modal-cancel,
.wlp-modal-confirm {
  border: none;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}

.wlp-modal-cancel  { background: #2a2a2a; color: #aaa; }
.wlp-modal-cancel:hover  { background: #333; color: #ccc; }
.wlp-modal-confirm { background: #c62828; color: #fff; }
.wlp-modal-confirm:hover { background: #e53935; }
</style>
