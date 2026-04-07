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
        <div
          v-for="wl in store.watchlists"
          :key="wl.id"
          :class="['wls-item', { active: activeId === wl.id }]"
          @click="setActive(wl.id)"
        >
          <span class="wlsi-name">{{ wl.name }}</span>
          <span v-if="wl.is_managed" class="wlsi-badge wlsi-badge--managed" title="Managed by screener">⊞</span>
          <span v-if="wl.is_locked" class="wlsi-badge wlsi-badge--locked" title="Locked">🔒</span>
          <span class="wlsi-count">{{ wl.items.length }}</span>
        </div>
        <div v-if="!store.watchlists.length" class="wls-empty">No watchlists yet</div>
      </div>
    </div>

    <!-- ── Right: selected watchlist ─────────────────────────────────────────── -->
    <div class="wl-main">
      <template v-if="activeWl">
        <div class="wlm-header">
          <template v-if="renamingActive">
            <input
              ref="renameInput"
              v-model="renameValue"
              class="wlm-rename-input"
              @keydown.enter="submitRename"
              @keydown.esc="cancelRename"
            />
            <button class="act-btn confirm" :disabled="!renameValue.trim()" @click="submitRename">✓</button>
            <button class="act-btn" @click="cancelRename">✕</button>
          </template>
          <template v-else>
            <span class="wlm-title">{{ activeWl.name }}</span>
            <div class="wlm-actions">
              <!-- Rename -->
              <button class="act-btn" title="Rename watchlist" @click="startRename">✎ Rename</button>
              <!-- Copy for managed watchlists -->
              <button
                v-if="activeWl.is_managed"
                class="act-btn"
                title="Copy as independent watchlist"
                @click="copyActive"
              >⎘ Copy</button>
              <!-- Lock / Unlock for non-managed watchlists -->
              <button
                v-if="!activeWl.is_managed && !activeWl.is_locked"
                class="act-btn"
                title="Lock watchlist (prevent modifications)"
                @click="store.lockWatchlist(activeWl.id)"
              >🔒 Lock</button>
              <button
                v-if="!activeWl.is_managed && activeWl.is_locked"
                class="act-btn"
                title="Unlock watchlist"
                @click="store.unlockWatchlist(activeWl.id)"
              >🔓 Unlock</button>
              <!-- Delete — hidden for locked watchlists (must unlock first) -->
              <template v-if="!activeWl.is_locked">
                <template v-if="deletingActive">
                  <span class="del-prompt">Delete?</span>
                  <button class="act-btn confirm" @click="doDelete">Yes</button>
                  <button class="act-btn" @click="deletingActive = false">No</button>
                </template>
                <button v-else class="act-btn danger" @click="deletingActive = true" title="Delete watchlist">✕ Delete</button>
              </template>
            </div>
          </template>
        </div>

        <!-- Add via SearchBar — hidden for managed or locked watchlists -->
        <div v-if="!activeWl.is_managed && !activeWl.is_locked" class="wlm-add">
          <SearchBar placeholder="Add symbol…" @select="addToActive" />
          <SparkTfSelector />
        </div>
        <div v-else class="wlm-add wlm-add--readonly">
          <span class="wlm-readonly-msg">{{ activeWl.is_managed ? 'Managed by screener — read only' : 'Locked — unlock to edit' }}</span>
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

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWatchlistStore } from '@/stores/watchlist'
import SearchBar from '@/components/common/SearchBar.vue'
import Sparkline from '@/components/common/Sparkline.vue'
import SparkTfSelector from '@/components/common/SparkTfSelector.vue'

const router = useRouter()
const store  = useWatchlistStore()

const activeId       = ref<number | null>(null)
const showCreateForm = ref(false)
const newName        = ref('')
const createInput    = ref<HTMLInputElement | null>(null)
const deletingActive = ref(false)
const renamingActive = ref(false)
const renameValue    = ref('')
const renameInput    = ref<HTMLInputElement | null>(null)

const activeWl = computed(() => store.watchlists.find(w => w.id === activeId.value) ?? null)

function setActive(id: number) {
  activeId.value = id
  deletingActive.value = false
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

async function startRename() {
  if (!activeWl.value) return
  renameValue.value = activeWl.value.name
  renamingActive.value = true
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

async function submitRename() {
  if (!activeId.value || !renameValue.value.trim()) return
  try {
    await store.renameWatchlist(activeId.value, renameValue.value.trim())
    renamingActive.value = false
  } catch (e: any) {
    if (e?.status === 409) alert(e.message || 'Name already in use')
  }
}

function cancelRename() {
  renamingActive.value = false
  renameValue.value = ''
}

watch(showCreateForm, async (v) => {
  if (v) { await nextTick(); createInput.value?.focus() }
})

async function copyActive() {
  if (!activeId.value) return
  const copy = await store.copyWatchlist(activeId.value)
  if (copy) activeId.value = copy.id
}

async function doDelete() {
  if (!activeId.value) return
  await store.deleteWatchlist(activeId.value)
  activeId.value = store.watchlists[0]?.id ?? null
  deletingActive.value = false
}

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

.wls-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  cursor: pointer;
  border-bottom: 1px solid #111;
  transition: background 0.1s;
}
.wls-item:hover  { background: #141414; }
.wls-item.active { background: #161e2e; border-left: 2px solid #64b5f6; }

.wlsi-name { font-size: 12px; color: #ccc; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wlsi-count {
  font-size: 10px;
  color: #444;
  background: #1a1a1a;
  border-radius: 10px;
  padding: 1px 6px;
}
.wls-item.active .wlsi-name  { color: #fff; }
.wls-item.active .wlsi-count { color: #64b5f6; }

.wlsi-badge { font-size: 10px; flex-shrink: 0; }
.wlsi-badge--managed { color: #64b5f6; }
.wlsi-badge--locked  { color: #888; }

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
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #1a1a1a;
  background: #111;
  flex-shrink: 0;
}
.wlm-title { font-size: 14px; font-weight: 700; color: #fff; }
.wlm-rename-input {
  flex: 1;
  background: #0a0a0a;
  border: 1px solid #64b5f6;
  border-radius: 3px;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  padding: 2px 6px;
  font-family: inherit;
  outline: none;
  min-width: 0;
}
.wlm-actions { display: flex; align-items: center; gap: 6px; }
.del-prompt { font-size: 11px; color: #ef5350; }
.act-btn {
  background: none;
  border: 1px solid #333;
  color: #666;
  border-radius: 3px;
  padding: 3px 8px;
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
}
.act-btn:hover { border-color: #555; color: #aaa; }
.act-btn.confirm { border-color: #4caf50; color: #4caf50; }
.act-btn.danger:hover  { border-color: #ef5350; color: #ef5350; }

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
.wlm-readonly-msg { font-size: 11px; color: #555; font-style: italic; flex: 1; }

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

/* Transitions */
.slide-down-enter-active, .slide-down-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  max-height: 60px;
  overflow: hidden;
}
.slide-down-enter-from, .slide-down-leave-to { max-height: 0; opacity: 0; }
</style>
