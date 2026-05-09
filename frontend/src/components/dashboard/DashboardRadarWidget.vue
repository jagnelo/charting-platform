<template>
  <div class="radar-widget">
    <div class="radar-widget-head">
      <div>
        <div class="radar-widget-title">Technical Radar</div>
        <div class="radar-widget-meta">
          {{ timeframeLabel }} · {{ stateLabel }} · {{ setupLabel }} · {{ effectiveActiveOnly ? 'open' : 'all' }}
        </div>
      </div>
      <button class="radar-widget-refresh" @click="refresh">Refresh</button>
    </div>
    <div v-if="loading" class="widget-state">Loading radar...</div>
    <div v-else-if="error" class="widget-state error">{{ error }}</div>
    <div v-else-if="!rows.length" class="widget-state">No radar detections</div>
    <template v-else>
      <div class="radar-widget-list">
        <button
          v-for="row in rows"
          :key="row.id"
          type="button"
          class="radar-widget-row"
          :class="{ active: selectedRowId === row.id }"
          @click="selectRow(row.id)"
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
        </button>
      </div>
    </template>

    <div v-if="selectedRowId" class="radar-widget-detail-overlay" @click.self="clearSelectedRow">
      <div class="radar-widget-detail">
        <div class="radar-widget-detail-head">
          <div>
            <div class="radar-widget-detail-symbol">
              {{ selectedDetail?.instrument_symbol || selectedSummary?.instrument_symbol || 'Radar detail' }}
            </div>
            <div class="radar-widget-detail-setup">
              {{ formatSetup(selectedDetail?.setup_type || selectedSummary?.setup_type || '') }}
            </div>
          </div>
          <button type="button" class="radar-widget-close" @click="clearSelectedRow">x</button>
        </div>
        <div v-if="detailLoading" class="widget-state">Loading detail…</div>
        <div v-else-if="selectedDetail" class="radar-widget-detail-body">
          <div class="radar-widget-detail-pills">
            <span :class="['radar-widget-pill', `radar-widget-pill--${selectedDetail.state}`]">
              {{ formatState(selectedDetail.state) }}
            </span>
            <span class="radar-widget-pill radar-widget-pill--thread">
              {{ selectedDetail.thread_event_index ? `Thread ${selectedDetail.thread_event_index}` : 'Unthreaded' }}
            </span>
          </div>
          <div class="radar-widget-detail-grid">
            <span>Signal</span>
            <b>{{ formatDate(selectedDetail.signal_at || selectedDetail.observed_at) }}</b>
            <span>Score</span>
            <b>{{ selectedDetail.score.toFixed(2) }}</b>
            <span>Level</span>
            <b>{{ formatPrice(selectedDetail.key_level_price) }}</b>
            <span>Entry</span>
            <b>{{ formatPrice(selectedDetail.entry_price) }}</b>
            <span>Invalidation</span>
            <b>{{ formatPrice(selectedDetail.invalidation_price) }}</b>
            <span>Target</span>
            <b>{{ formatPrice(selectedDetail.target_price) }}</b>
          </div>
          <p class="radar-widget-detail-summary">{{ selectedDetail.summary }}</p>
          <p v-if="selectedDetail.invalidation_hint" class="radar-widget-detail-hint">
            {{ selectedDetail.invalidation_hint }}
          </p>
          <div class="radar-widget-detail-actions">
            <button type="button" class="radar-widget-refresh" @click="openInChart(selectedDetail)">
              Open chart
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/lib/api'
import type { RadarDetection } from '@/types'

const props = defineProps<{ config: Record<string, any> }>()

const loading = ref(false)
const error = ref<string | null>(null)
const rows = ref<RadarDetection[]>([])
const selectedRowId = ref<number | null>(null)
const selectedDetail = ref<RadarDetection | null>(null)
const detailLoading = ref(false)
const router = useRouter()

const stateLabel = computed(() => formatState(String(props.config.state || 'confirmed')))
const timeframeLabel = computed(() => String(props.config.timeframe || 'D1'))
const selectedSetupTypes = computed(() => {
  const multi = Array.isArray(props.config.setup_types)
    ? props.config.setup_types.map((value: unknown) => String(value || '').trim()).filter(Boolean)
    : []
  if (multi.length) return [...new Set(multi)]
  const single = String(props.config.setup_type || '').trim()
  return single ? [single] : []
})
const setupLabel = computed(() => {
  if (!selectedSetupTypes.value.length) return 'all setups'
  if (selectedSetupTypes.value.length === 1) return formatSetup(selectedSetupTypes.value[0])
  return `${selectedSetupTypes.value.length} setups`
})
const activeOnly = computed(() => (props.config.active_only ?? props.config.fresh_only) !== false)
const effectiveActiveOnly = computed(() => {
  const state = String(props.config.state || '')
  if (['resolved', 'invalidated', 'stale'].includes(state)) return false
  return activeOnly.value
})

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

function formatPrice(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'
}

const selectedSummary = computed(() =>
  selectedRowId.value != null ? rows.value.find(row => row.id === selectedRowId.value) ?? null : null
)

async function refresh() {
  loading.value = true
  error.value = null
  try {
    const baseParams = {
      timeframe: props.config.timeframe || 'D1',
      state: props.config.state || undefined,
      min_score: Number(props.config.min_score ?? 0.6),
      limit: Number(props.config.limit ?? 6),
      active_only: effectiveActiveOnly.value,
      symbol: props.config.symbol || undefined,
    }
    if (selectedSetupTypes.value.length <= 1) {
      rows.value = await api.get<RadarDetection[]>('/radar/detections', {
        ...baseParams,
        setup_type: selectedSetupTypes.value[0] || undefined,
      })
      return
    }
    const batches = await Promise.all(
      selectedSetupTypes.value.map(setupType =>
        api.get<RadarDetection[]>('/radar/detections', {
          ...baseParams,
          setup_type: setupType,
        }),
      ),
    )
    const merged = new Map<number, RadarDetection>()
    for (const batch of batches) {
      for (const row of batch) {
        merged.set(row.id, row)
      }
    }
    rows.value = [...merged.values()]
      .sort((left, right) => {
        if (left.score !== right.score) return right.score - left.score
        const leftTime = new Date(left.signal_at || left.observed_at).getTime()
        const rightTime = new Date(right.signal_at || right.observed_at).getTime()
        if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
          return rightTime - leftTime
        }
        return right.id - left.id
      })
      .slice(0, baseParams.limit)
    if (selectedRowId.value != null && !rows.value.some(row => row.id === selectedRowId.value)) {
      clearSelectedRow()
    }
  } catch (err: any) {
    error.value = err?.message ?? 'Radar unavailable'
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function selectRow(id: number) {
  if (selectedRowId.value === id && selectedDetail.value) return
  selectedRowId.value = id
  detailLoading.value = true
  try {
    selectedDetail.value = await api.get<RadarDetection>(`/radar/detections/${id}`)
  } catch (err: any) {
    error.value = err?.message ?? 'Radar detail unavailable'
    selectedDetail.value = null
  } finally {
    detailLoading.value = false
  }
}

function clearSelectedRow() {
  selectedRowId.value = null
  selectedDetail.value = null
  detailLoading.value = false
}

function openInChart(row: RadarDetection) {
  router.push(`/chart/${encodeURIComponent(row.instrument_symbol)}`)
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
  position: relative;
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
  text-align: left;
  font-family: inherit;
  cursor: pointer;
}

.radar-widget-row:hover,
.radar-widget-row.active {
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

.radar-widget-detail-overlay {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
  background: rgba(4, 6, 10, 0.68);
}

.radar-widget-detail {
  width: min(100%, 360px);
  max-height: 100%;
  overflow: auto;
  border: 1px solid #263649;
  border-radius: 8px;
  background: #0d1116;
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.44);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.radar-widget-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.radar-widget-detail-symbol {
  color: #f2f2f2;
  font-size: 18px;
  font-weight: 700;
}

.radar-widget-detail-setup {
  color: #8c8c8c;
  font-size: 12px;
  text-transform: capitalize;
}

.radar-widget-close {
  background: transparent;
  border: 0;
  color: #8b8b8b;
  font-size: 14px;
  cursor: pointer;
}

.radar-widget-detail-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.radar-widget-pill {
  border: 1px solid #30455d;
  border-radius: 999px;
  padding: 4px 8px;
  color: #9fbfe4;
  font-size: 10px;
  text-transform: capitalize;
}

.radar-widget-pill--confirmed { color: #7ec8a3; border-color: #335a48; }
.radar-widget-pill--developing { color: #d8c46f; border-color: #5f5228; }
.radar-widget-pill--resolved { color: #7fbef5; border-color: #2f4f70; }
.radar-widget-pill--invalidated { color: #ef8a85; border-color: #6b3532; }
.radar-widget-pill--stale { color: #b0b0b0; border-color: #4e4e4e; }
.radar-widget-pill--thread { color: #82b9ea; border-color: #28435e; }

.radar-widget-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  font-size: 11px;
}

.radar-widget-detail-grid span {
  color: #737373;
}

.radar-widget-detail-grid b {
  color: #dfdfdf;
  font-weight: 600;
}

.radar-widget-detail-summary {
  color: #c6c6c6;
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
}

.radar-widget-detail-hint {
  color: #8b8b8b;
  font-size: 11px;
  line-height: 1.45;
  margin: 0;
}

.radar-widget-detail-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
