<template>
  <div class="watchlist-view">

    <!-- ── Left: watchlist list ──────────────────────────────────────────────── -->
    <div class="wl-sidebar">
      <div class="wls-header">
        <span class="wls-title">Watchlists</span>
        <button class="wls-new-btn" @click="showCreateForm = !showCreateForm">+ New</button>
      </div>

      <Transition name="slide-down">
        <div v-if="showCreateForm" class="create-form">
          <input
            ref="createInput"
            v-model="newName"
            class="cf-input"
            placeholder="Name…"
            @keydown.enter="submitCreate"
            @keydown.esc="cancelCreate"
          />
          <button class="cf-btn confirm" :disabled="!newName.trim()" @click="submitCreate">✓</button>
          <button class="cf-btn" @click="cancelCreate">✕</button>
        </div>
      </Transition>

      <div v-if="store.loading" class="wls-loading">Loading…</div>
      <div v-else class="wls-list">
        <!-- DnD draggable watchlist list -->
        <VueDraggable
          v-model="draggableWatchlists"
          handle=".wls-drag-handle"
          ghost-class="wls-ghost"
          @end="onWlReorder"
        >
            <div
              v-for="wl in draggableWatchlists"
              :key="wl.id"
              :class="['wls-item', { active: activeId === wl.id }]"
              @click="setActive(wl.id)"
            >
              <!-- Inline rename input -->
              <template v-if="sidebarRenamingId === wl.id">
                <input
                  ref="sidebarRenameInput"
                  v-model="sidebarRenameValue"
                  class="wls-rename-input"
                  @keydown.enter="commitSidebarRename(wl.id)"
                  @keydown.escape="cancelSidebarRename"
                  @click.stop
                />
                <button class="wls-rename-btn confirm" @click.stop="commitSidebarRename(wl.id)">✓</button>
                <button class="wls-rename-btn"         @click.stop="cancelSidebarRename">✕</button>
              </template>
              <template v-else>
                <span class="wls-drag-handle" @click.stop>⠿</span>
                <span class="wlsi-name">{{ wl.name }}</span>
                <span v-if="wl.is_managed" class="wlsi-badge wlsi-badge--managed" title="Managed by screener">⊞</span>
                <span v-if="wl.is_locked" class="wlsi-badge wlsi-badge--locked" title="Locked">🔒</span>
                <span class="wlsi-count">{{ wl.items.length }}</span>

                <!-- ⋯ hover menu trigger -->
                <button
                  class="wlsi-menu-btn"
                  title="More options"
                  @click.stop="toggleSidebarMenu(wl.id)"
                >⋯</button>
              </template>

              <!-- ⋯ dropdown -->
              <div v-if="sidebarMenuId === wl.id" class="wlsi-dropdown" @click.stop>
                <button class="wlsi-dd-item" @click.stop="startSidebarRename(wl)">Rename</button>
                <button v-if="canDeleteWatchlist(wl)" class="wlsi-dd-item" @click.stop="startSidebarDelete(wl.id)">Delete</button>
                <button class="wlsi-dd-item" @click.stop="doSidebarCopy(wl.id)">Copy</button>
                <template v-if="!wl.is_managed">
                  <button v-if="wl.is_locked" class="wlsi-dd-item" @click.stop="doSidebarUnlock(wl.id)">Unlock</button>
                  <button v-else class="wlsi-dd-item" @click.stop="doSidebarLock(wl.id)">Lock</button>
                </template>
                <div v-if="wl.is_managed && wl.screener_id" class="wlsi-dd-managed">
                  Managed by
                  <router-link :to="`/screener?selectedId=${wl.screener_id}`" class="wlsi-screener-link" @click="closeSidebarMenu">
                    {{ wl.screener_name || 'screener' }}
                  </router-link>
                </div>
              </div>
            </div>
        </VueDraggable>
        <div v-if="!store.watchlists.length" class="wls-empty">No watchlists yet</div>
      </div>
    </div>

    <!-- ── Right: selected watchlist ─────────────────────────────────────────── -->
    <div class="wl-main">
      <template v-if="activeWl">
        <div class="wlm-header">
          <span class="wlm-title">{{ activeWl.name }}</span>
        </div>

        <!-- Add via SearchBar — hidden for managed or locked watchlists -->
        <div v-if="!activeWl.is_managed && !activeWl.is_locked" class="wlm-add">
          <SearchBar placeholder="Symbol…" @select="addToActive" />
          <SparkTfSelector />
        </div>
        <div v-else class="wlm-add wlm-add--readonly">
          <span class="wlm-readonly-msg">
            <template v-if="activeWl.is_managed && activeWl.screener_id">
              Managed by
              <router-link :to="`/screener?selectedId=${activeWl.screener_id}`" class="wlm-screener-link">
                {{ activeWl.screener_name || 'screener' }}
              </router-link>
            </template>
            <template v-else-if="activeWl.is_managed">Managed by screener</template>
            <template v-else>Locked — unlock to edit</template>
          </span>
          <SparkTfSelector />
        </div>

        <!-- Symbol rows -->
        <div class="wlm-items">
          <div
            v-for="item in activeWl.items"
            :key="item.id"
            class="wlm-item"
            @click="openChart(item.symbol!)"
          >
            <div class="wlmi-left">
              <span class="wlmi-sym">{{ item.symbol }}</span>
              <span class="wlmi-name">{{ item.name }}</span>
            </div>
            <div class="wlmi-right">
              <template v-if="store.priceMap[item.symbol!]">
                <span class="wlmi-price">{{ fmtClose(store.priceMap[item.symbol!].close) }}</span>
                <span :class="['wlmi-pct', store.priceMap[item.symbol!].pct >= 0 ? 'up' : 'down']">
                  {{ fmtPct(store.priceMap[item.symbol!].pct) }}
                </span>
              </template>
              <span v-else class="wlmi-no-price">—</span>
            </div>
            <Sparkline v-if="item.symbol" :symbol="item.symbol" class="wlmi-spark" />
            <button v-if="!activeWl.is_managed && !activeWl.is_locked" class="wlmi-remove" title="Remove" @click.stop="store.removeItem(activeWl.id, item.id)">✕</button>
          </div>
          <div v-if="!activeWl.items.length" class="wlm-empty">
            Search for a symbol above to add it
          </div>
        </div>
      </template>

      <div v-else class="wlm-placeholder">
        <p>Select a watchlist or create a new one</p>
      </div>
    </div>

    <!-- Delete confirmation modal -->
    <Teleport to="body">
      <div v-if="sidebarDeleteTargetId !== null" class="wls-modal-overlay" @click.self="cancelSidebarDelete">
        <div class="wls-modal">
          <p class="wls-modal-msg">Delete watchlist "{{ store.watchlists.find(w => w.id === sidebarDeleteTargetId)?.name }}"?</p>
          <div class="wls-modal-actions">
            <button class="wls-modal-cancel"  @click="cancelSidebarDelete">Cancel</button>
            <button class="wls-modal-confirm" @click="confirmSidebarDelete">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Watchlist } from '@/types'
import SearchBar from '@/components/common/SearchBar.vue'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'

const router = useRouter()
const store  = useWatchlistStore()

const activeId       = ref<number | null>(null)
const showCreateForm = ref(false)
const newName        = ref('')
const createInput    = ref<HTMLInputElement | null>(null)

const activeWl = computed(() => store.watchlists.find(w => w.id === activeId.value) ?? null)

function canDeleteWatchlist(wl: Watchlist) {
  return wl.is_managed || !wl.is_locked
}

// DnD
const draggableWatchlists = computed({
  get: () => store.watchlists,
  set: (val) => { store.watchlists.splice(0, store.watchlists.length, ...val) },
})

async function onWlReorder() {
  await store.reorderWatchlists(store.watchlists.map(w => w.id))
}

function setActive(id: number) {
  activeId.value = id
  const syms = (store.watchlists.find(w => w.id === id)?.items ?? [])
    .map(i => i.symbol).filter(Boolean) as string[]
  store.fetchPrices(syms)
}

async function submitCreate() {
  if (!newName.value.trim()) return
  const wl = await store.createWatchlist(newName.value.trim())
  if (wl) activeId.value = wl.id
  cancelCreate()
}

function cancelCreate() {
  showCreateForm.value = false
  newName.value = ''
}

watch(showCreateForm, async (v) => {
  if (v) { await nextTick(); createInput.value?.focus() }
})

// ── Sidebar ⋯ menu ──────────────────────────────────────────────────────────
const sidebarMenuId = ref<number | null>(null)

function toggleSidebarMenu(id: number) {
  sidebarMenuId.value = sidebarMenuId.value === id ? null : id
  cancelSidebarRename()
}

function closeSidebarMenu() {
  sidebarMenuId.value = null
}

function handleDocClick() {
  closeSidebarMenu()
  cancelSidebarRename()
}

onMounted(() => document.addEventListener('click', handleDocClick))
onUnmounted(() => document.removeEventListener('click', handleDocClick))

// ── Sidebar rename ──────────────────────────────────────────────────────────
const sidebarRenamingId   = ref<number | null>(null)
const sidebarRenameValue  = ref('')
const sidebarRenameInput  = ref<HTMLInputElement | HTMLInputElement[] | null>(null)

function selectSidebarRenameInput() {
  const input = Array.isArray(sidebarRenameInput.value)
    ? sidebarRenameInput.value[0]
    : sidebarRenameInput.value
  input?.select()
}

function startSidebarRename(wl: Watchlist) {
  closeSidebarMenu()
  sidebarRenamingId.value  = wl.id
  sidebarRenameValue.value = wl.name
  nextTick(selectSidebarRenameInput)
}

function cancelSidebarRename() {
  sidebarRenamingId.value = null
  sidebarRenameValue.value = ''
}

async function commitSidebarRename(id: number) {
  const name = sidebarRenameValue.value.trim()
  if (!name) return
  try {
    await store.renameWatchlist(id, name)
    cancelSidebarRename()
  } catch (e: any) {
    if (e?.status === 409) alert(e.message || 'Name already in use')
    else cancelSidebarRename()
  }
}

// ── Sidebar delete ──────────────────────────────────────────────────────────
const sidebarDeleteTargetId = ref<number | null>(null)

function startSidebarDelete(id: number) {
  closeSidebarMenu()
  sidebarDeleteTargetId.value = id
}

function cancelSidebarDelete() {
  sidebarDeleteTargetId.value = null
}

async function confirmSidebarDelete() {
  if (sidebarDeleteTargetId.value === null) return
  const id = sidebarDeleteTargetId.value
  await store.deleteWatchlist(id)
  sidebarDeleteTargetId.value = null
  if (activeId.value === id) activeId.value = store.watchlists[0]?.id ?? null
}

// ── Sidebar copy / lock / unlock ────────────────────────────────────────────
async function doSidebarCopy(id: number) {
  closeSidebarMenu()
  const copy = await store.copyWatchlist(id)
  if (copy) activeId.value = copy.id
}

async function doSidebarLock(id: number) {
  closeSidebarMenu()
  await store.lockWatchlist(id)
}

async function doSidebarUnlock(id: number) {
  closeSidebarMenu()
  await store.unlockWatchlist(id)
}

// ── Main panel actions ──────────────────────────────────────────────────────
async function addToActive(symbol: string) {
  if (!activeId.value) return
  await store.addBySymbol(activeId.value, symbol)
  store.fetchPrices([symbol])
}

function openChart(symbol: string) {
  router.push(`/chart/${encodeURIComponent(symbol)}`)
}

function fmtClose(v: number) {
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: number) {
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}

onMounted(async () => {
  await store.loadWatchlists()
  if (store.watchlists.length) {
    activeId.value = store.watchlists[0].id
    const syms = store.watchlists[0].items.map(i => i.symbol).filter(Boolean) as string[]
    store.fetchPrices(syms)
  }
})
</script>

<style scoped>
.watchlist-view {
  display: flex;
  height: 100%;
  background: #0a0a0a;
  color: #ccc;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  overflow: hidden;
}

/* ── Left sidebar ─────────────────────────────────────────── */
.wl-sidebar {
  width: 200px;
  flex-shrink: 0;
  background: #0d0d0d;
  border-right: 1px solid #1a1a1a;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wls-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.wls-title  { font-size: 12px; font-weight: 700; color: #fff; }
.wls-new-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #aaa;
  border-radius: 3px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.wls-new-btn:hover { border-color: #64b5f6; color: #64b5f6; }

.create-form {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  background: #111;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.cf-input {
  flex: 1;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 3px;
  color: #ccc;
  padding: 4px 8px;
  font-size: 11px;
  font-family: inherit;
  outline: none;
  min-width: 0;
}
.cf-input:focus { border-color: #64b5f6; }
.cf-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #666;
  border-radius: 3px;
  padding: 3px 7px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
  flex-shrink: 0;
}
.cf-btn:hover { border-color: #555; color: #aaa; }
.cf-btn.confirm { border-color: #4caf50; color: #4caf50; }
.cf-btn.confirm:disabled { opacity: 0.4; cursor: not-allowed; }

.wls-loading { padding: 16px; text-align: center; color: #444; font-size: 11px; }

.wls-list { flex: 1; overflow-y: auto; }
.wls-ghost { opacity: 0.35; background: #1a2a3a; }

.wls-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 8px 7px 10px;
  cursor: pointer;
  border-bottom: 1px solid #111;
  transition: background 0.1s;
}
.wls-item:hover  { background: #141414; }
.wls-item.active { background: #161e2e; border-left: 2px solid #64b5f6; }

.wls-drag-handle {
  color: #2a2a2a;
  font-size: 11px;
  cursor: grab;
  flex-shrink: 0;
  line-height: 1;
  padding: 0 1px;
}
.wls-drag-handle:hover { color: #555; }

.wlsi-name {
  font-size: 12px;
  color: #ccc;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wls-item.active .wlsi-name  { color: #fff; }
.wlsi-count {
  font-size: 10px;
  color: #444;
  background: #1a1a1a;
  border-radius: 10px;
  padding: 1px 6px;
  flex-shrink: 0;
}
.wls-item.active .wlsi-count { color: #64b5f6; }

.wlsi-badge { font-size: 10px; flex-shrink: 0; }
.wlsi-badge--managed { color: #64b5f6; }
.wlsi-badge--locked  { color: #888; }

/* ⋯ menu button — only visible on hover */
.wlsi-menu-btn {
  background: none;
  border: none;
  color: #444;
  cursor: pointer;
  font-size: 13px;
  padding: 1px 4px;
  border-radius: 2px;
  flex-shrink: 0;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.1s, color 0.1s;
}
.wls-item:hover .wlsi-menu-btn,
.wls-item.active .wlsi-menu-btn { opacity: 1; }
.wlsi-menu-btn:hover { color: #ccc; background: #2a2a2a; }

/* ⋯ dropdown */
.wlsi-dropdown {
  position: absolute;
  top: 100%;
  right: 4px;
  z-index: 300;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 4px;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

.wlsi-dd-item {
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
.wlsi-dd-item:hover { background: #2a2a2a; color: #fff; }

.wlsi-dd-managed {
  padding: 6px 12px;
  border-top: 1px solid #2a2a2a;
  font-size: 10px;
  color: #555;
}

.wlsi-screener-link {
  color: #64b5f6;
  text-decoration: none;
}
.wlsi-screener-link:hover { text-decoration: underline; }

/* Rename inline input in sidebar */
.wls-rename-input {
  flex: 1;
  background: #0a0a0a;
  border: 1px solid #64b5f6;
  border-radius: 3px;
  color: #fff;
  font-size: 11px;
  font-family: inherit;
  padding: 2px 6px;
  outline: none;
  min-width: 0;
}

.wls-rename-btn {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 2px;
  flex-shrink: 0;
}
.wls-rename-btn.confirm:hover { color: #26a69a; }
.wls-rename-btn:not(.confirm):hover { color: #ef5350; }

.wls-empty { padding: 20px; text-align: center; color: #333; font-size: 11px; }

/* ── Main panel ───────────────────────────────────────────── */
.wl-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.wlm-header {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid #1a1a1a;
  background: #111;
  flex-shrink: 0;
}
.wlm-title { font-size: 14px; font-weight: 700; color: #fff; }

.wlm-add {
  padding: 8px 12px;
  border-bottom: 1px solid #1a1a1a;
  background: #0d0d0d;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.wlm-add--readonly { opacity: 0.7; }
.wlm-readonly-msg {
  font-size: 11px;
  color: #555;
  font-style: italic;
  flex: 1;
}

.wlm-screener-link {
  color: #64b5f6;
  text-decoration: none;
  font-style: normal;
}
.wlm-screener-link:hover { text-decoration: underline; }

.wlm-items { flex: 1; overflow-y: auto; }

.wlm-item {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  border-bottom: 1px solid #111;
  transition: background 0.1s;
}
.wlm-item:hover { background: #111; }
.wlm-item:hover .wlmi-remove { opacity: 1; }

.wlmi-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.wlmi-sym {
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
.wlmi-name {
  font-size: 10px;
  color: #555;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wlmi-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  margin-right: 10px;
}
.wlmi-price { font-size: 12px; color: #ccc; }
.wlmi-pct   { font-size: 11px; font-weight: 600; }
.wlmi-no-price { font-size: 11px; color: #333; }

.up   { color: #26a69a; }
.down { color: #ef5350; }

.wlmi-spark { flex-shrink: 0; margin-right: 4px; }

.wlmi-remove {
  background: none;
  border: none;
  color: #ef5350;
  cursor: pointer;
  font-size: 10px;
  opacity: 0;
  padding: 2px 4px;
  transition: opacity 0.1s;
  flex-shrink: 0;
}

.wlm-empty {
  padding: 30px;
  text-align: center;
  color: #333;
  font-size: 11px;
}

.wlm-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #333;
  font-size: 12px;
}

/* ── Delete modal ───────────────────────────────────────────── */
.wls-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.wls-modal {
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 20px 24px;
  min-width: 260px;
}

.wls-modal-msg {
  font-size: 13px;
  color: #ccc;
  margin: 0 0 16px;
}

.wls-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.wls-modal-cancel,
.wls-modal-confirm {
  border: none;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}

.wls-modal-cancel  { background: #2a2a2a; color: #aaa; }
.wls-modal-cancel:hover  { background: #333; color: #ccc; }
.wls-modal-confirm { background: #c62828; color: #fff; }
.wls-modal-confirm:hover { background: #e53935; }

/* Transitions */
.slide-down-enter-active, .slide-down-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  max-height: 60px;
  overflow: hidden;
}
.slide-down-enter-from, .slide-down-leave-to { max-height: 0; opacity: 0; }
</style>
