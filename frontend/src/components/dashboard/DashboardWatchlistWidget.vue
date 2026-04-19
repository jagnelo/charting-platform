<template>
  <div class="dash-watchlist">
    <div class="watchlist-toolbar">
      <select :value="selectedId || ''" @change="selectWatchlist">
        <option value="">Select watchlist...</option>
        <option v-for="wl in store.watchlists" :key="wl.id" :value="wl.id">
          {{ wl.name }}
        </option>
      </select>
      <button @click="createWatchlist">New</button>
      <button v-if="watchlist" @click="copyWatchlist">Copy</button>
      <button v-if="watchlist && !watchlist.is_managed" @click="toggleLock">
        {{ watchlist.is_locked ? 'Unlock' : 'Lock' }}
      </button>
      <button v-if="watchlist && (watchlist.is_managed || !watchlist.is_locked)" class="danger" @click="deleteWatchlist">
        Delete
      </button>
    </div>

    <div v-if="watchlist" class="watchlist-name-row">
      <input
        :value="watchlist.name"
        :disabled="watchlist.is_managed"
        @change="renameWatchlist"
      />
      <span v-if="watchlist.is_managed" class="badge">Managed</span>
      <span v-if="watchlist.is_locked" class="badge">Locked</span>
    </div>

    <div v-if="watchlist && !watchlist.is_locked && !watchlist.is_managed" class="add-row">
      <DashboardInstrumentSearch
        v-model="addSymbol"
        placeholder="Add symbol or =expression..."
        @select="addToWatchlist"
      />
    </div>

    <div v-if="watchlist" class="watchlist-items">
      <div
        v-for="item in activeItems"
        :key="item.id"
        class="watchlist-row"
        @click="focusedSymbol = item.symbol ?? null"
      >
        <div class="row-main">
          <b>{{ item.symbol }}</b>
          <span>{{ item.name }}</span>
        </div>
        <Sparkline v-if="config.showSparklines !== false && item.symbol" :symbol="item.symbol" />
        <button
          v-if="!watchlist.is_locked && !watchlist.is_managed"
          class="row-btn danger"
          @click.stop="store.removeItem(watchlist.id, item.id)"
        >
          Remove
        </button>
        <router-link class="row-btn" :to="`/chart/${encodeURIComponent(item.symbol ?? '')}`" @click.stop>
          Chart
        </router-link>
      </div>
      <div v-if="!activeItems.length" class="empty-small">No instruments in this watchlist.</div>
    </div>
    <div v-else class="empty-small">Create or select a watchlist.</div>

    <div v-if="focusedSymbol" class="focused-strip">
      <span>Focused</span>
      <b>{{ focusedSymbol }}</b>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DashboardInstrumentSearch from '@/components/dashboard/DashboardInstrumentSearch.vue'
import Sparkline from '@/components/common/Sparkline.vue'
import { useWatchlistStore } from '@/stores/watchlist'

const props = defineProps<{ config: Record<string, any> }>()
const emit = defineEmits<{ patchConfig: [patch: Record<string, any>] }>()

const store = useWatchlistStore()
const addSymbol = ref('')
const focusedSymbol = ref<string | null>(null)

const selectedId = computed(() => Number(props.config.watchlistId) || store.watchlists[0]?.id || null)
const watchlist = computed(() => store.watchlists.find(w => w.id === selectedId.value) ?? null)
const activeItems = computed(() =>
  [...(watchlist.value?.items ?? [])]
    .filter(item => !item.left_screener_at)
    .sort((a, b) => a.position - b.position)
)

watch(watchlist, wl => {
  if (wl) store.fetchPrices(wl.items.map(item => item.symbol).filter(Boolean) as string[])
}, { immediate: true })

function selectWatchlist(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value) || null
  emit('patchConfig', { watchlistId: id })
}

async function createWatchlist() {
  const created = await store.createWatchlist('New Watchlist')
  if (created) emit('patchConfig', { watchlistId: created.id })
}

async function renameWatchlist(event: Event) {
  if (!watchlist.value) return
  const name = (event.target as HTMLInputElement).value.trim()
  if (name && name !== watchlist.value.name) await store.renameWatchlist(watchlist.value.id, name)
}

async function deleteWatchlist() {
  if (!watchlist.value) return
  const id = watchlist.value.id
  await store.deleteWatchlist(id)
  emit('patchConfig', { watchlistId: store.watchlists[0]?.id ?? null })
}

async function copyWatchlist() {
  if (!watchlist.value) return
  const copied = await store.copyWatchlist(watchlist.value.id)
  if (copied) emit('patchConfig', { watchlistId: copied.id })
}

async function toggleLock() {
  if (!watchlist.value) return
  if (watchlist.value.is_locked) await store.unlockWatchlist(watchlist.value.id)
  else await store.lockWatchlist(watchlist.value.id)
}

async function addToWatchlist(symbol: string) {
  if (!watchlist.value || watchlist.value.is_locked || watchlist.value.is_managed) return
  await store.addBySymbol(watchlist.value.id, symbol)
  addSymbol.value = ''
}
</script>

<style scoped>
.dash-watchlist {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.watchlist-toolbar,
.watchlist-name-row {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-shrink: 0;
}
.watchlist-toolbar select,
.watchlist-name-row input {
  min-width: 0;
  flex: 1;
  background: #050505;
  color: #ccc;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 5px 7px;
  font-family: inherit;
  font-size: 10px;
}
.watchlist-toolbar button,
.row-btn {
  background: #151515;
  color: #aaa;
  border: 1px solid #282828;
  border-radius: 4px;
  padding: 5px 6px;
  font-family: inherit;
  font-size: 9px;
  cursor: pointer;
  text-decoration: none;
}
.watchlist-toolbar button:hover,
.row-btn:hover { border-color: #3a3a3a; color: #ddd; }
.danger { color: #ef5350 !important; }
.badge {
  color: #777;
  border: 1px solid #2a2a2a;
  border-radius: 4px;
  padding: 3px 5px;
  font-size: 9px;
}
.add-row { flex-shrink: 0; }
.watchlist-items {
  min-height: 0;
  flex: 1;
  overflow: auto;
}
.watchlist-row {
  min-height: 34px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 7px;
  border-bottom: 1px solid #181818;
  padding: 5px 0;
  cursor: default;
}
.row-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.row-main b { color: #64b5f6; font-size: 11px; }
.row-main span {
  color: #777;
  font-size: 10px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.focused-strip {
  flex-shrink: 0;
  display: flex;
  gap: 7px;
  align-items: center;
  border-top: 1px solid #1a1a1a;
  padding-top: 6px;
  color: #777;
  font-size: 10px;
}
.focused-strip b { color: #ddd; }
.empty-small {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
}
</style>
