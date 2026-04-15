<template>
  <div class="heatmap-widget">
    <div v-if="loading" class="widget-state">Loading heat map...</div>
    <div v-else-if="!rows.length" class="widget-state">No watchlist symbols available</div>
    <div v-else class="sector-wrap">
      <section v-for="group in sectorGroups" :key="group.sector" class="sector-group">
        <div class="sector-title">{{ group.sector }}</div>
        <div class="tile-wrap">
          <router-link
            v-for="row in group.rows"
            :key="row.symbol"
            class="heat-tile"
            :style="tileStyle(row)"
            :to="`/chart/${encodeURIComponent(row.symbol)}`"
          >
            <span class="tile-symbol">{{ row.symbol }}</span>
            <span class="tile-pct">{{ pct(row.pct) }}</span>
          </router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'
import type { Instrument, Watchlist } from '@/types'

interface HeatRow {
  symbol: string
  sector: string
  pct: number
  marketCap: number
}

const props = defineProps<{ config: Record<string, any> }>()
const watchlistStore = useWatchlistStore()
const rows = ref<HeatRow[]>([])
const loading = ref(false)

const selectedWatchlist = computed<Watchlist | null>(() => {
  const id = Number(props.config.watchlistId)
  return watchlistStore.watchlists.find(w => w.id === id) ?? watchlistStore.watchlists[0] ?? null
})

const sectorGroups = computed(() => {
  const grouped = new Map<string, HeatRow[]>()
  for (const row of rows.value) {
    grouped.set(row.sector, [...(grouped.get(row.sector) ?? []), row])
  }
  return [...grouped.entries()]
    .map(([sector, sectorRows]) => ({
      sector,
      rows: sectorRows.sort((a, b) => Math.abs(b.marketCap) - Math.abs(a.marketCap)),
    }))
    .sort((a, b) => b.rows.length - a.rows.length)
})

async function load() {
  loading.value = true
  try {
    if (!watchlistStore.watchlists.length) await watchlistStore.loadWatchlists()
    const wl = selectedWatchlist.value
    const symbols = wl?.items.map(i => i.symbol).filter(Boolean) as string[] | undefined
    if (!symbols?.length) {
      rows.value = []
      return
    }
    await watchlistStore.fetchPrices(symbols, true)
    const instruments = await Promise.all(symbols.map(async symbol => {
      try {
        return await api.get<Instrument>(`/instruments/${encodeURIComponent(symbol)}`)
      } catch {
        return null
      }
    }))
    rows.value = instruments
      .filter((instrument): instrument is Instrument => !!instrument)
      .map(instrument => ({
        symbol: instrument.symbol,
        sector: instrument.equity_detail?.sector || 'Unclassified',
        pct: watchlistStore.priceMap[instrument.symbol]?.pct ?? 0,
        marketCap: Number(instrument.stats?.market_cap ?? 1),
      }))
  } finally {
    loading.value = false
  }
}

function pct(value: number) {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function tileStyle(row: HeatRow) {
  const intensity = Math.min(0.82, Math.max(0.18, Math.abs(row.pct) * 10 + 0.18))
  const bg = row.pct >= 0
    ? `rgba(38,166,154,${intensity})`
    : `rgba(239,83,80,${intensity})`
  return {
    background: bg,
    flexGrow: Math.max(1, Math.min(8, Math.log10(Math.max(row.marketCap, 10)) - 7)),
  }
}

watch(() => props.config.watchlistId, load)
onMounted(load)
</script>

<style scoped>
.heatmap-widget {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.sector-wrap {
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sector-title {
  color: #777;
  font-size: 10px;
  text-transform: uppercase;
  margin-bottom: 4px;
}
.tile-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}
.heat-tile {
  min-width: 64px;
  min-height: 42px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 6px;
  color: #f5f5f5;
  text-decoration: none;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.tile-symbol {
  font-size: 12px;
  font-weight: 700;
}
.tile-pct {
  font-size: 10px;
}
.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
}
</style>
