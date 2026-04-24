<template>
  <div class="exposure-panel">
    <div class="panel-header">
      <span class="panel-title">{{ title }}</span>
      <button class="refresh-btn" @click="reload" title="Refresh">↺</button>
    </div>

    <div v-if="store.isLoading" class="panel-state">Loading…</div>
    <div v-else-if="store.error" class="panel-state error">{{ store.error }}</div>
    <template v-else-if="store.data">
      <div v-if="store.data.expirations.length === 0" class="panel-state empty-chain">
        No options chain data for <strong>{{ symbol }}</strong>.<br>
        Sync the options chain to populate exposure data.
      </div>
      <template v-else>
      <OptionsKeyMetrics :data="store.data" />

      <!-- Expiration selector + strike range controls -->
      <div class="controls-bar">
        <div class="exp-selector">
          <span class="ctrl-label">Expirations</span>
          <button
            class="ctrl-btn"
            :class="{ active: allEnabled }"
            @click="store.setAllExpirations(true)"
          >All</button>
          <button
            class="ctrl-btn"
            :class="{ active: noneEnabled }"
            @click="store.setAllExpirations(false)"
          >None</button>
          <button
            v-for="exp in store.availableExpirations"
            :key="exp"
            class="exp-pill"
            :class="{ active: store.enabledExpirations.has(exp) }"
            :style="{ '--pill-color': palette.get(exp) ?? '#666' }"
            @click="store.toggleExpiration(exp)"
          >{{ formatExp(exp) }}</button>
        </div>
        <div class="range-controls">
          <span class="ctrl-label">Strike Range</span>
          <input
            type="number"
            class="range-input"
            placeholder="Min"
            :value="store.strikeRange.min ?? ''"
            @change="onMinChange($event)"
          />
          <span class="range-sep">—</span>
          <input
            type="number"
            class="range-input"
            placeholder="Max"
            :value="store.strikeRange.max ?? ''"
            @change="onMaxChange($event)"
          />
          <button class="ctrl-btn" @click="store.setStrikeRange(null, null)">Reset</button>
        </div>
      </div>

      <div class="charts-scroll">
        <GexLadder
          :ladder="store.filteredLadder"
          :spot="store.data.spot"
          :enabled-expirations="store.enabledExpirations"
          :all-expirations="store.availableExpirations"
        />
        <OiDistribution
          :ladder="store.filteredLadder"
          :spot="store.data.spot"
          :enabled-expirations="store.enabledExpirations"
          :all-expirations="store.availableExpirations"
        />
        <IvSkew
          :ladder="store.filteredLadder"
          :spot="store.data.spot"
        />
      </div>
      </template>
    </template>
    <div v-else class="panel-state">No options data for {{ symbol }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useOptionsExposureStore } from '@/stores/optionsExposure'
import { buildExpirationPalette } from '@/lib/expirationPalette'
import GexLadder from './GexLadder.vue'
import OiDistribution from './OiDistribution.vue'
import IvSkew from './IvSkew.vue'
import OptionsKeyMetrics from './OptionsKeyMetrics.vue'

const props = withDefaults(defineProps<{
  symbol: string
  title?: string
}>(), { title: 'Options Exposure' })

const store = useOptionsExposureStore()

const palette = computed(() => buildExpirationPalette(store.availableExpirations))

const allEnabled = computed(() =>
  store.availableExpirations.every(e => store.enabledExpirations.has(e))
)
const noneEnabled = computed(() => store.enabledExpirations.size === 0)

function formatExp(iso: string) {
  // "2024-01-19" → "Jan 19"
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function onMinChange(e: Event) {
  const v = (e.target as HTMLInputElement).value
  store.setStrikeRange(v ? Number(v) : null, store.strikeRange.max)
}

function onMaxChange(e: Event) {
  const v = (e.target as HTMLInputElement).value
  store.setStrikeRange(store.strikeRange.min, v ? Number(v) : null)
}

async function reload() {
  await store.load(props.symbol)
}

watch(() => props.symbol, sym => {
  if (sym) store.load(sym)
}, { immediate: false })

onMounted(() => {
  if (props.symbol) store.load(props.symbol)
})
</script>

<style scoped>
.exposure-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #111;
  font-family: 'JetBrains Mono', monospace;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid #222;
  flex-shrink: 0;
}
.panel-title {
  font-size: 12px;
  color: #ccc;
  letter-spacing: 0.04em;
}
.refresh-btn {
  background: none;
  border: none;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  padding: 0 4px;
}
.refresh-btn:hover { color: #ccc; }

.panel-state {
  padding: 20px;
  color: #555;
  font-size: 12px;
  text-align: center;
}
.panel-state.error { color: #ef5350; }
.panel-state.empty-chain { color: #666; line-height: 1.6; }
.panel-state.empty-chain strong { color: #999; }

.controls-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid #1a1a1a;
  flex-shrink: 0;
}
.exp-selector, .range-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.ctrl-label {
  font-size: 10px;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-right: 4px;
  white-space: nowrap;
}
.ctrl-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #888;
  font-size: 10px;
  font-family: inherit;
  padding: 2px 6px;
  cursor: pointer;
  border-radius: 2px;
}
.ctrl-btn:hover { color: #ccc; border-color: #555; }
.ctrl-btn.active { background: #222; color: #ccc; border-color: #555; }

.exp-pill {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #666;
  font-size: 10px;
  font-family: inherit;
  padding: 2px 7px;
  cursor: pointer;
  border-radius: 10px;
  transition: background 0.1s, color 0.1s;
}
.exp-pill.active {
  background: color-mix(in srgb, var(--pill-color) 15%, #1a1a1a);
  border-color: var(--pill-color);
  color: var(--pill-color);
}
.exp-pill:hover { border-color: #555; }

.range-input {
  width: 72px;
  background: #1a1a1a;
  border: 1px solid #333;
  color: #ccc;
  font-size: 11px;
  font-family: inherit;
  padding: 2px 6px;
  border-radius: 2px;
  outline: none;
}
.range-input:focus { border-color: #555; }
.range-sep { color: #555; font-size: 10px; }

.charts-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
