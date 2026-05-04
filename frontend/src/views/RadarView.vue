<template>
  <div class="radar-view">
    <header class="radar-header">
      <div>
        <h1>Technical Radar</h1>
        <p>Daily swing-focused setups with persisted evidence and chart-ready overlays.</p>
      </div>
      <div class="radar-actions">
        <button class="radar-btn" @click="refresh">Refresh</button>
        <button class="radar-btn primary" :disabled="runningScan" @click="runScan">
          {{ runningScan ? 'Running…' : 'Run scan' }}
        </button>
      </div>
    </header>

    <div class="radar-toolbar">
      <select v-model="filters.setupType" class="radar-input">
        <option value="">All setups</option>
        <option v-for="type in setupTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
      </select>
      <input
        v-model="filters.symbol"
        class="radar-input"
        placeholder="Filter symbol"
        @keydown.enter="refresh"
      />
      <label class="score-filter">
        <span>Min score</span>
        <input v-model.number="filters.minScore" class="radar-slider" type="range" min="0" max="1" step="0.05" />
        <b>{{ filters.minScore.toFixed(2) }}</b>
      </label>
      <label class="fresh-toggle">
        <input v-model="filters.freshOnly" type="checkbox" />
        Fresh only
      </label>
    </div>

    <div class="radar-layout">
      <section class="radar-results">
        <div class="results-head">
          <strong>Detections</strong>
          <small v-if="latestRun">Latest run: {{ formatDate(latestRun.completed_at || latestRun.started_at) }}</small>
        </div>
        <div v-if="radarStore.isLoading" class="state-block">Loading detections…</div>
        <div v-else-if="!radarStore.detections.length" class="state-block">No detections yet. Run a scan or relax the filters.</div>
        <button
          v-for="detection in radarStore.detections"
          :key="detection.id"
          class="result-card"
          :class="{ active: radarStore.selectedDetection?.id === detection.id }"
          @click="selectDetection(detection.id)"
        >
          <div class="result-top">
            <div>
              <strong>{{ detection.instrument_symbol }}</strong>
              <span>{{ labelForSetup(detection.setup_type) }}</span>
            </div>
            <b>{{ detection.score.toFixed(2) }}</b>
          </div>
          <p>{{ detection.summary }}</p>
          <div class="result-meta">
            <span>Level {{ formatPrice(detection.key_level_price) }}</span>
            <span>Fresh until {{ formatDate(detection.fresh_until) }}</span>
          </div>
        </button>
      </section>

      <aside class="radar-detail">
        <template v-if="radarStore.selectedDetection?.evidence">
          <div class="detail-head">
            <div>
              <h2>{{ radarStore.selectedDetection.instrument_symbol }}</h2>
              <p>{{ labelForSetup(radarStore.selectedDetection.setup_type) }}</p>
            </div>
            <button class="radar-btn primary" @click="openInChart(radarStore.selectedDetection)">Open in chart</button>
          </div>
          <p class="detail-summary">{{ radarStore.selectedDetection.summary }}</p>
          <p class="detail-invalid">{{ radarStore.selectedDetection.invalidation_hint }}</p>

          <div class="detail-section">
            <strong>Score factors</strong>
            <div class="score-grid">
              <template v-for="(value, key) in radarStore.selectedDetection.score_factors" :key="key">
                <span>{{ prettifyKey(key) }}</span>
                <b>{{ formatFactor(value) }}</b>
              </template>
            </div>
          </div>

          <div class="detail-section">
            <strong>Evidence metrics</strong>
            <div class="metrics-grid">
              <template v-for="(value, key) in radarStore.selectedDetection.evidence.metrics" :key="key">
                <span>{{ prettifyKey(key) }}</span>
                <b>{{ formatMetric(value) }}</b>
              </template>
            </div>
          </div>
        </template>
        <div v-else class="state-block">Select a detection to inspect its evidence.</div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'

import { useRadarStore } from '@/stores/radar'
import type { RadarDetection, RadarSetupType } from '@/types'

const radarStore = useRadarStore()
const router = useRouter()

const filters = reactive({
  setupType: '',
  symbol: '',
  minScore: 0.35,
  freshOnly: true,
})

const setupTypes: Array<{ value: RadarSetupType; label: string }> = [
  { value: 'approaching_support', label: 'Approaching support' },
  { value: 'approaching_resistance', label: 'Approaching resistance' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'breakdown', label: 'Breakdown' },
  { value: 'reclaim', label: 'Reclaim' },
  { value: 'rejection', label: 'Rejection' },
]

const latestRun = computed(() => radarStore.runs[0] ?? null)
const runningScan = computed(() => latestRun.value?.status === 'running')

function labelForSetup(setup: RadarSetupType) {
  return setup.replace(/_/g, ' ')
}

function prettifyKey(key: string) {
  return key.replace(/_/g, ' ')
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function formatPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function formatFactor(value: unknown) {
  if (typeof value === 'number') return value.toFixed(2)
  return String(value)
}

function formatMetric(value: unknown) {
  if (typeof value === 'number') return value.toFixed(2)
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value ?? '—')
}

async function refresh() {
  await Promise.all([
    radarStore.loadRuns(),
    radarStore.loadDetections({
      setup_type: filters.setupType || undefined,
      symbol: filters.symbol || undefined,
      min_score: filters.minScore,
      fresh_only: filters.freshOnly,
    }),
  ])
  if (!radarStore.selectedDetection && radarStore.detections[0]) {
    await selectDetection(radarStore.detections[0].id)
  }
}

async function selectDetection(id: number) {
  await radarStore.loadDetection(id)
}

async function runScan() {
  await radarStore.runScan()
  await refresh()
}

function openInChart(detection: RadarDetection) {
  router.push({
    path: `/chart/${encodeURIComponent(detection.instrument_symbol)}`,
    query: { radarDetectionId: String(detection.id) },
  })
}

onMounted(async () => {
  await refresh()
})
</script>

<style scoped>
.radar-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(180deg, #0a0f14 0%, #0a0a0a 100%);
  color: #d7dde5;
  padding: 18px;
  gap: 14px;
}

.radar-header,
.radar-toolbar,
.radar-layout {
  display: flex;
  gap: 12px;
}

.radar-header {
  align-items: center;
  justify-content: space-between;
}

.radar-header h1 {
  font-size: 28px;
  color: #f7fbff;
}

.radar-header p {
  color: #7f93a8;
  margin-top: 4px;
}

.radar-actions,
.results-head,
.result-top,
.result-meta,
.detail-head {
  display: flex;
  align-items: center;
}

.radar-actions,
.results-head,
.result-meta,
.detail-head {
  justify-content: space-between;
}

.radar-btn {
  border: 1px solid #284255;
  background: #0d1823;
  color: #b7cadb;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-family: inherit;
}

.radar-btn.primary {
  background: #18344a;
  border-color: #4ea8de;
  color: #eef8ff;
}

.radar-toolbar {
  align-items: center;
  flex-wrap: wrap;
}

.radar-input,
.radar-slider {
  background: #0b1118;
  color: #d7dde5;
  border: 1px solid #243647;
  border-radius: 8px;
  padding: 8px 10px;
  font-family: inherit;
}

.score-filter,
.fresh-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #93a7b9;
}

.radar-layout {
  min-height: 0;
  flex: 1;
}

.radar-results,
.radar-detail {
  min-height: 0;
  border: 1px solid #17212b;
  background: rgba(9, 14, 20, 0.85);
  border-radius: 14px;
  padding: 14px;
}

.radar-results {
  flex: 1.25;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.radar-detail {
  width: 360px;
  overflow: auto;
}

.results-head small,
.result-card span,
.detail-head p,
.detail-invalid {
  color: #7f93a8;
}

.result-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #1b2a37;
  border-radius: 12px;
  background: #0b1218;
  padding: 12px;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.result-card.active {
  border-color: #4ea8de;
  box-shadow: 0 0 0 1px rgba(78, 168, 222, 0.25);
}

.result-top b {
  color: #74c69d;
}

.result-meta {
  font-size: 11px;
}

.detail-head h2 {
  font-size: 22px;
  color: #fff;
}

.detail-summary {
  margin: 14px 0 8px;
  line-height: 1.5;
}

.detail-invalid {
  margin-bottom: 16px;
}

.detail-section {
  margin-top: 16px;
}

.score-grid,
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 10px;
  margin-top: 10px;
  font-size: 12px;
}

.state-block {
  border: 1px dashed #223240;
  border-radius: 12px;
  padding: 18px;
  color: #7f93a8;
  text-align: center;
}
</style>
