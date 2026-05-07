<template>
  <div class="radar-widget">
    <div class="radar-widget-head">
      <div>
        <div class="radar-widget-title">Technical Radar</div>
        <div class="radar-widget-meta">
          {{ timeframeLabel }} · {{ stateLabel }} · {{ setupLabel }} · {{ freshOnly ? 'fresh' : 'all' }}
        </div>
      </div>
      <button class="radar-widget-refresh" @click="refresh">Refresh</button>
    </div>
    <div v-if="loading" class="widget-state">Loading radar...</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!rows.length" class="widget-state">No radar detections</div>
    <template v-else>
      <div class="radar-widget-list">
        <router-link
          v-for="row in rows"
          :key="row.id"
          class="radar-widget-row"
          :to="`/chart/${encodeURIComponent(row.instrument_symbol)}`"
        >
          <div class="radar-widget-row-top">
            <strong>{{ row.instrument_symbol }}</strong>
            <span class="radar-widget-score">{{ row.score.toFixed(2) }}</span>
          </div>
          <div class="radar-widget-row-meta">
            <span>{{ formatSetup(row.setup_type) }}</span>
            <span>{{ formatState(row.state) }}</span>
            <span>{{ formatDate(row.signal_at || row.observed_at) }}</span>
          </div>
          <div class="radar-widget-row-copy">{{ row.summary }}</div>
        </router-link>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/lib/api'
import type { RadarDetection } from '@/types'

const props = defineProps<{ config: Record<string, any> }>()

const loading = ref(false)
const error = ref<string | null>(null)
const rows = ref<RadarDetection[]>([])

const stateLabel = computed(() => formatState(String(props.config.state || 'confirmed')))
const timeframeLabel = computed(() => String(props.config.timeframe || 'D1'))
const setupLabel = computed(() =>
  props.config.setup_type ? formatSetup(String(props.config.setup_type)) : 'all setups'
)
const freshOnly = computed(() => props.config.fresh_only !== false)

function formatSetup(value: string) {
  return value.replace(/_/g, ' ')
}

function formatState(value: string) {
  return value.replace(/_/g, ' ')
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  return value.slice(0, 10)
}

async function refresh() {
  loading.value = true
  error.value = null
  try {
    rows.value = await api.get<RadarDetection[]>('/radar/detections', {
      timeframe: props.config.timeframe || 'D1',
      setup_type: props.config.setup_type || undefined,
      state: props.config.state || undefined,
      min_score: Number(props.config.min_score ?? 0.6),
      limit: Number(props.config.limit ?? 6),
      fresh_only: props.config.fresh_only !== false,
      symbol: props.config.symbol || undefined,
    })
  } catch (err: any) {
    error.value = err?.message ?? 'Radar unavailable'
    rows.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.config, refresh, { deep: true })
onMounted(refresh)
</script>

<style scoped>
.radar-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.radar-widget-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.radar-widget-title {
  color: #f1f1f1;
  font-size: 14px;
  font-weight: 700;
}

.radar-widget-meta {
  color: #777;
  font-size: 10px;
  text-transform: capitalize;
}

.radar-widget-refresh {
  border: 1px solid #242424;
  background: #111;
  color: #8fbef5;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 10px;
  cursor: pointer;
}

.radar-widget-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
}

.radar-widget-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid #242424;
  border-radius: 6px;
  background: #0f0f0f;
  padding: 9px 10px;
  color: inherit;
  text-decoration: none;
}

.radar-widget-row:hover {
  border-color: #1d4f76;
  background: #102033;
}

.radar-widget-row-top,
.radar-widget-row-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.radar-widget-row-top {
  color: #f1f1f1;
}

.radar-widget-row-meta {
  color: #6f6f6f;
  font-size: 10px;
  text-transform: capitalize;
}

.radar-widget-score {
  color: #26a69a;
}

.radar-widget-row-copy {
  color: #a0a0a0;
  font-size: 11px;
  line-height: 1.45;
}

.widget-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 12px;
  text-align: center;
  padding: 12px;
}

.widget-state.error {
  color: #ef5350;
  font-size: 10px;
}
</style>
