<template>
  <div class="dash-screener">
    <div class="screener-toolbar">
      <select :value="selectedId || ''" @change="selectScreener">
        <option value="">Select screener...</option>
        <option v-for="screener in screeners" :key="screener.id" :value="screener.id">
          {{ screener.name }}
        </option>
      </select>
      <button :disabled="!selectedId || running" @click="runScreener">
        {{ running ? 'Running' : 'Run' }}
      </button>
      <router-link class="toolbar-link" to="/screener">Open</router-link>
    </div>
    <div v-if="latest" class="screener-meta">
      <span>{{ latest.matched_ids.length }} matches</span>
      <span>{{ new Date(latest.run_at).toLocaleString() }}</span>
    </div>
    <div class="screener-list">
      <div v-for="(id, index) in matchedIds" :key="id" class="screener-row">
        <span>{{ index + 1 }}</span>
        <b>{{ instrumentMap[id]?.symbol ?? id }}</b>
        <small>{{ instrumentMap[id]?.name ?? 'Loading...' }}</small>
        <em>{{ formatValue(latest?.result_data[String(id)]?.close) }}</em>
      </div>
      <div v-if="!matchedIds.length" class="empty-small">No screener results yet.</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/lib/api'

interface ScreenerOut {
  id: number
  name: string
  timeframe: string
}

interface ScreenerResultOut {
  id: number
  screener_id: number
  result_data: Record<string, any>
  matched_ids: number[]
  run_at: string
}

interface InstrumentInfo {
  id: number
  symbol: string
  name: string
}

const props = defineProps<{ config: Record<string, any> }>()
const emit = defineEmits<{ patchConfig: [patch: Record<string, any>] }>()

const screeners = ref<ScreenerOut[]>([])
const latest = ref<ScreenerResultOut | null>(null)
const instrumentMap = ref<Record<number, InstrumentInfo>>({})
const running = ref(false)

const selectedId = computed(() => Number(props.config.screenerId) || screeners.value[0]?.id || null)
const matchedIds = computed(() => latest.value?.matched_ids.slice(0, 80) ?? [])

async function load() {
  screeners.value = await api.get<ScreenerOut[]>('/screeners')
  if (selectedId.value) await loadResults(selectedId.value)
}

async function loadResults(id: number) {
  const results = await api.get<ScreenerResultOut[]>(`/screeners/${id}/results`, { limit: 1 })
  latest.value = results[0] ?? null
  if (latest.value?.matched_ids.length) await loadInstrumentInfo(latest.value.matched_ids)
}

async function loadInstrumentInfo(ids: number[]) {
  const missing = ids.filter(id => !instrumentMap.value[id])
  if (!missing.length) return
  const resp = await api.get<{ items: InstrumentInfo[] }>('/instruments/browse', {
    ids: missing.join(','),
    page_size: Math.min(200, missing.length),
    page: 1,
  })
  for (const item of resp.items) instrumentMap.value[item.id] = item
}

function selectScreener(event: Event) {
  const id = Number((event.target as HTMLSelectElement).value) || null
  emit('patchConfig', { screenerId: id })
}

async function runScreener() {
  if (!selectedId.value) return
  running.value = true
  try {
    latest.value = await api.post<ScreenerResultOut>(`/screeners/${selectedId.value}/run`, {})
    if (latest.value.matched_ids.length) await loadInstrumentInfo(latest.value.matched_ids)
  } finally {
    running.value = false
  }
}

function formatValue(value: unknown) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  return n >= 1000 ? n.toFixed(0) : n.toFixed(2)
}

watch(selectedId, id => {
  if (id) loadResults(id)
})
onMounted(load)
</script>

<style scoped>
.dash-screener {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.screener-toolbar {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-shrink: 0;
}
.screener-toolbar select {
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
.screener-toolbar button,
.toolbar-link {
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
.screener-toolbar button:disabled { opacity: 0.45; cursor: default; }
.screener-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: #777;
  font-size: 10px;
  flex-shrink: 0;
}
.screener-list {
  min-height: 0;
  flex: 1;
  overflow: auto;
}
.screener-row {
  display: grid;
  grid-template-columns: 28px 72px 1fr auto;
  gap: 7px;
  align-items: center;
  min-height: 28px;
  border-bottom: 1px solid #181818;
  font-size: 10px;
}
.screener-row span,
.screener-row small { color: #777; }
.screener-row b { color: #64b5f6; }
.screener-row small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.screener-row em { color: #ccc; font-style: normal; }
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
