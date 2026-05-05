<template>
  <div class="radar-view">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">Technical Radar</h2>
        <span v-if="latestRun" class="run-meta">
          Last run: {{ formatDate(latestRun.completed_at || latestRun.started_at) }}
        </span>
      </div>
      <div class="radar-actions">
        <button class="action-btn" @click="refresh">Refresh</button>
        <button class="action-btn primary" :disabled="runningScan" @click="runScan">
          {{ runningScan ? 'Running…' : 'Run scan' }}
        </button>
      </div>
    </div>

    <div class="filter-bar">
      <select v-model="filters.setupType" class="filter-select">
        <option value="">All setups</option>
        <option v-for="type in setupTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
      </select>
      <input
        v-model="filters.symbol"
        class="filter-input"
        placeholder="Symbol…"
        @keydown.enter="refresh"
      />
      <label class="score-filter">
        <span>Min score</span>
        <input v-model.number="filters.minScore" class="score-slider" type="range" min="0" max="1" step="0.05" />
        <span class="score-value">{{ filters.minScore.toFixed(2) }}</span>
      </label>
      <label class="fresh-toggle">
        <input v-model="filters.freshOnly" type="checkbox" />
        <span>Fresh only</span>
      </label>
    </div>

    <div class="radar-layout">
      <!-- ── Detection list ─────────────────────────────────────────────────── -->
      <section class="radar-results">
        <div class="section-title">Detections</div>
        <div class="detections-table-wrap">
          <div v-if="radarStore.isLoading" class="empty-row">Loading detections…</div>
          <div v-else-if="!radarStore.detections.length" class="empty-row">
            No detections. Run a scan or relax the filters.
          </div>
          <table v-else class="detections-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Setup</th>
                <th>Score</th>
                <th>Level</th>
                <th>Fresh until</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="detection in radarStore.detections"
                :key="detection.id"
                :class="{ active: radarStore.selectedDetection?.id === detection.id }"
                @click="selectDetection(detection.id)"
              >
                <td class="td-symbol">{{ detection.instrument_symbol }}</td>
                <td class="td-setup">{{ labelForSetup(detection.setup_type) }}</td>
                <td class="td-score">{{ detection.score.toFixed(2) }}</td>
                <td class="td-mono">{{ formatPrice(detection.key_level_price) }}</td>
                <td class="td-mono td-dim">{{ formatDateShort(detection.fresh_until) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── Detail panel ───────────────────────────────────────────────────── -->
      <aside class="radar-detail">
        <template v-if="radarStore.selectedDetection?.evidence">
          <div class="detail-head">
            <div>
              <span class="detail-symbol">{{ radarStore.selectedDetection.instrument_symbol }}</span>
              <span class="detail-setup">{{ labelForSetup(radarStore.selectedDetection.setup_type) }}</span>
            </div>
            <button class="action-btn primary" @click="openInChart(radarStore.selectedDetection)">
              Open in chart
            </button>
          </div>

          <p class="detail-summary">{{ radarStore.selectedDetection.summary }}</p>
          <p class="detail-invalid">{{ radarStore.selectedDetection.invalidation_hint }}</p>

          <div class="detail-section">
            <div class="section-title">Score factors</div>
            <div class="kv-grid">
              <template v-for="(value, key) in radarStore.selectedDetection.score_factors" :key="key">
                <span class="kv-key">{{ prettifyKey(String(key)) }}</span>
                <span :class="['kv-val', key === 'normalized_score' ? 'kv-score' : '']">
                  {{ formatFactor(value) }}
                </span>
              </template>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">Evidence metrics</div>
            <div class="kv-grid">
              <template v-for="(value, key) in radarStore.selectedDetection.evidence.metrics" :key="key">
                <span class="kv-key">{{ prettifyKey(String(key)) }}</span>
                <span class="kv-val">{{ formatMetric(value) }}</span>
              </template>
            </div>
          </div>
        </template>
        <div v-else class="empty-detail">Select a detection to inspect its evidence.</div>
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

function formatDateShort(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
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
/* ── Root ───────────────────────────────────────────────────────────────────── */
.radar-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  color: #ccc;
  font-size: 13px;
  padding: 24px;
  gap: 16px;
  box-sizing: border-box;
  overflow: hidden;
}

/* ── Page header ────────────────────────────────────────────────────────────── */
.page-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
}

.page-header-left {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.page-title {
  color: #fff;
  font-size: 20px;
  font-weight: 700;
}

.run-meta {
  color: #555;
  font-size: 11px;
}

.radar-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #aaa;
  border-radius: 4px;
  padding: 5px 12px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  transition: background 0.1s, color 0.1s;
}

.action-btn:hover {
  background: #222;
  color: #ccc;
}

.action-btn.primary {
  background: #0f1f2e;
  border-color: #1e3a5c;
  color: #64b5f6;
}

.action-btn.primary:hover {
  background: #122437;
  border-color: #2a5080;
}

.action-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

/* ── Filter bar ─────────────────────────────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-select,
.filter-input {
  background: #1a1a1a;
  border: 1px solid #333;
  color: #aaa;
  border-radius: 3px;
  padding: 4px 8px;
  font-family: inherit;
  font-size: 12px;
}

.filter-input::placeholder {
  color: #555;
}

.filter-select:focus,
.filter-input:focus {
  outline: none;
  border-color: #444;
}

.score-filter,
.fresh-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #666;
  font-size: 12px;
}

.score-slider {
  width: 80px;
  accent-color: #64b5f6;
}

.score-value {
  color: #aaa;
  min-width: 28px;
}

/* ── Two-column layout ──────────────────────────────────────────────────────── */
.radar-layout {
  display: flex;
  gap: 12px;
  min-height: 0;
  flex: 1;
}

.section-title {
  color: #888;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

/* ── Detection list ─────────────────────────────────────────────────────────── */
.radar-results {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.detections-table-wrap {
  flex: 1;
  overflow-y: auto;
}

.empty-row {
  color: #555;
  font-size: 12px;
  padding: 20px;
  text-align: center;
}

.detections-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.detections-table th {
  background: #111;
  color: #555;
  text-align: left;
  padding: 7px 10px;
  border-bottom: 1px solid #1a1a1a;
  font-weight: 600;
  position: sticky;
  top: 0;
  white-space: nowrap;
}

.detections-table td {
  padding: 7px 10px;
  border-bottom: 1px solid #111;
  cursor: pointer;
  white-space: nowrap;
}

.detections-table tbody tr:hover td {
  background: #111;
}

.detections-table tbody tr.active td {
  background: #0f1f2e;
  border-bottom-color: #1a2e42;
}

.td-symbol {
  color: #e8e8e8;
  font-weight: 600;
}

.td-setup {
  color: #aaa;
  text-transform: capitalize;
}

.td-score {
  color: #26a69a;
  font-weight: 600;
}

.td-mono {
  font-variant-numeric: tabular-nums;
}

.td-dim {
  color: #555;
}

/* ── Detail panel ───────────────────────────────────────────────────────────── */
.radar-detail {
  width: 320px;
  flex-shrink: 0;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  background: #0d0d0d;
  padding: 14px;
  overflow-y: auto;
}

.empty-detail {
  color: #555;
  font-size: 12px;
  text-align: center;
  padding: 32px 0;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.detail-symbol {
  display: block;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
}

.detail-setup {
  display: block;
  color: #666;
  font-size: 11px;
  text-transform: capitalize;
  margin-top: 2px;
}

.detail-summary {
  color: #aaa;
  font-size: 12px;
  line-height: 1.55;
  margin-bottom: 6px;
}

.detail-invalid {
  color: #666;
  font-size: 11px;
  margin-bottom: 16px;
}

.detail-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #1a1a1a;
}

.kv-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 5px 12px;
  font-size: 12px;
}

.kv-key {
  color: #666;
  text-transform: capitalize;
}

.kv-val {
  color: #aaa;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.kv-score {
  color: #26a69a;
  font-weight: 600;
}
</style>
