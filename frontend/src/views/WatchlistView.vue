<template>
  <div class="watchlist-view">
    <div class="page-header">
      <h1>Watchlists</h1>
      <button class="create-btn" @click="createWatchlist">+ New Watchlist</button>
    </div>

    <div class="watchlists-grid">
      <div v-for="wl in watchlists" :key="wl.id" class="watchlist-card">
        <div class="card-header">
          <span class="wl-name">{{ wl.name }}</span>
          <button class="del-btn" @click="deleteWatchlist(wl.id)">✕</button>
        </div>

        <div class="wl-items">
          <div
            v-for="item in wl.items"
            :key="item.id"
            class="wl-item"
            @click="openChart(item.symbol!)"
          >
            <span class="item-symbol">{{ item.symbol }}</span>
            <span class="item-name">{{ item.name }}</span>
          </div>
          <div v-if="!wl.items.length" class="empty-items">No items</div>
        </div>

        <div class="card-footer">
          <input
            v-model="newSymbols[wl.id]"
            class="symbol-input"
            placeholder="Add symbol..."
            @keydown.enter="addToWatchlist(wl.id)"
          />
          <button class="add-btn" @click="addToWatchlist(wl.id)">+</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import type { Watchlist } from '@/types'
import { useChartStore } from '@/stores/chart'

const router = useRouter()
const chartStore = useChartStore()
const watchlists = ref<Watchlist[]>([])
const newSymbols = ref<Record<number, string>>({})

async function loadWatchlists() {
  const { data } = await axios.get('/api/v1/watchlists/')
  watchlists.value = data
}

async function createWatchlist() {
  const name = prompt('Watchlist name:')
  if (!name) return
  await axios.post('/api/v1/watchlists/', { name })
  await loadWatchlists()
}

async function deleteWatchlist(id: number) {
  if (!confirm('Delete this watchlist?')) return
  await axios.delete(`/api/v1/watchlists/${id}`)
  await loadWatchlists()
}

async function addToWatchlist(watchlistId: number) {
  const symbol = newSymbols.value[watchlistId]?.trim().toUpperCase()
  if (!symbol) return
  // First ensure instrument exists
  const { data: instr } = await axios.get(`/api/v1/instruments/${symbol}`)
  await axios.post(`/api/v1/watchlists/${watchlistId}/items`, {
    instrument_id: instr.id,
  })
  newSymbols.value[watchlistId] = ''
  await loadWatchlists()
}

function openChart(symbol: string) {
  chartStore.loadInstrument(symbol)
  router.push('/chart')
}

onMounted(loadWatchlists)
</script>

<style scoped>
.watchlist-view {
  padding: 24px;
  color: #d1d4dc;
  font-family: 'IBM Plex Sans', sans-serif;
  background: #131722;
  min-height: 100vh;
}

.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
h1 { font-size: 20px; font-weight: 600; color: #fff; margin: 0; }

.create-btn {
  padding: 6px 14px;
  background: #2962ff;
  border: none;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.watchlists-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.watchlist-card {
  background: #1e222d;
  border: 1px solid #2a2e39;
  border-radius: 6px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #2a2e39;
}
.wl-name { font-weight: 600; font-size: 13px; }
.del-btn { background: none; border: none; color: #555; cursor: pointer; }
.del-btn:hover { color: #ef5350; }

.wl-items { min-height: 60px; max-height: 300px; overflow-y: auto; }
.wl-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  cursor: pointer;
  border-bottom: 1px solid #1a1d27;
  transition: background 0.1s;
}
.wl-item:hover { background: #2a2e39; }
.item-symbol { font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 13px; color: #fff; min-width: 70px; }
.item-name { font-size: 11px; color: #666; }
.empty-items { padding: 16px; text-align: center; color: #555; font-size: 12px; }

.card-footer {
  display: flex;
  padding: 8px;
  gap: 6px;
  border-top: 1px solid #2a2e39;
}
.symbol-input {
  flex: 1;
  background: #131722;
  border: 1px solid #2a2e39;
  border-radius: 3px;
  color: #d1d4dc;
  padding: 4px 8px;
  font-size: 12px;
  font-family: 'IBM Plex Mono', monospace;
}
.add-btn {
  padding: 4px 10px;
  background: #2a2e39;
  border: 1px solid #363a46;
  border-radius: 3px;
  color: #d1d4dc;
  cursor: pointer;
  font-size: 14px;
}
.add-btn:hover { background: #363a46; }
</style>
