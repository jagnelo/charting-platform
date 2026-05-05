<template>
  <div class="radar-view" :class="{ 'radar-view--busy': runningScan }" :aria-busy="runningScan">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">Technical Radar</h2>
        <span v-if="latestRun" class="run-meta">
          Last run: {{ formatDate(latestRun.completed_at || latestRun.started_at) }}
        </span>
      </div>
      <div class="radar-actions">
        <button class="action-btn" :disabled="runningScan" @click="refresh">Refresh</button>
        <button class="action-btn primary" :disabled="runningScan" @click="runScan">
          {{ runningScan ? 'Running…' : 'Run scan' }}
        </button>
      </div>
    </div>

    <div class="radar-stage">
      <div class="filter-bar">
        <select v-model="filters.setupType" class="filter-select" :disabled="runningScan">
          <option value="">All setups</option>
          <option v-for="type in setupTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
        </select>
        <input
          v-model="filters.symbol"
          class="filter-input"
          placeholder="Symbol…"
          :disabled="runningScan"
          @keydown.enter="refresh"
        />
        <label class="score-filter">
          <span>Min score</span>
          <input v-model.number="filters.minScore" class="score-slider" type="range" min="0" max="1" step="0.05" :disabled="runningScan" />
          <span class="score-value">{{ filters.minScore.toFixed(2) }}</span>
        </label>
        <label class="fresh-toggle">
          <input v-model="filters.freshOnly" type="checkbox" :disabled="runningScan" />
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
            <button class="action-btn primary" :disabled="runningScan" @click="openInChart(radarStore.selectedDetection)">
              Open in chart
            </button>
          </div>

          <p class="detail-summary">{{ radarStore.selectedDetection.summary }}</p>
          <p class="detail-invalid">{{ radarStore.selectedDetection.invalidation_hint }}</p>

          <div class="detail-section">
            <div class="section-title">Score factors</div>
            <div class="kv-grid">
              <template v-for="(value, key) in radarStore.selectedDetection.score_factors" :key="key">
                <span class="kv-key">
                  {{ prettifyKey(String(key)) }}
                  <HoverTooltip v-if="scoreFactorHint(String(key))" :text="scoreFactorHint(String(key))">
                    <button
                      type="button"
                      class="kv-info"
                      :aria-label="`${prettifyKey(String(key))} info`"
                    >
                      i
                    </button>
                  </HoverTooltip>
                </span>
                <span :class="['kv-val', key === 'normalized_score' ? 'kv-score' : '']">
                  {{ formatFactor(value) }}
                </span>
              </template>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">Evidence metrics</div>
            <div class="kv-grid">
              <template v-for="row in evidenceMetricRows" :key="row.key">
                <span class="kv-key">{{ row.key }}</span>
                <span class="kv-val-block">
                  <span class="kv-val">{{ row.value }}</span>
                  <span v-if="row.hint" class="kv-hint">{{ row.hint }}</span>
                </span>
              </template>
            </div>
          </div>
        </template>
        <div v-else class="empty-detail">Select a detection to inspect its evidence.</div>
      </aside>
      </div>

      <div v-if="runningScan" class="radar-busy-overlay" role="status" aria-live="polite">
        <div class="radar-busy-card">
          <div class="radar-busy-title">Running radar scan…</div>
          <div class="radar-busy-copy">Refreshing detections and locking interactions until the new run finishes.</div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import { useRadarStore } from '@/stores/radar'
import type { RadarDetection, RadarSetupType } from '@/types'

const radarStore = useRadarStore()
const router = useRouter()
const scanPending = ref(false)

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

interface MetricRow {
  key: string
  value: string
  hint?: string
}

const evidenceMetricRows = computed((): MetricRow[] => {
  const det = radarStore.selectedDetection
  if (!det?.evidence?.metrics) return []
  const m = det.evidence.metrics as Record<string, unknown>
  const s = det.evidence.structures?.[0] as Record<string, unknown> | undefined
  const rows: MetricRow[] = []
  const week52HighTime = typeof m.week52_high_time === 'number' ? m.week52_high_time : null
  const week52LowTime = typeof m.week52_low_time === 'number' ? m.week52_low_time : null

  for (const [key, val] of Object.entries(m)) {
    if (key === 'invalidation_price' || key === 'week52_high_time' || key === 'week52_low_time') continue

    if (key === 'ema_levels' && val && typeof val === 'object' && !Array.isArray(val)) {
      for (const [period, level] of Object.entries(val as Record<string, number>)) {
        rows.push({
          key: period.replace('ema_', 'EMA '),
          value: typeof level === 'number' ? level.toFixed(4) : String(level),
        })
      }
      continue
    }

    if (key === 'avwap') {
      const anchorTs = s?.last_touch_time
      const anchorDate = typeof anchorTs === 'number'
        ? formatDateShort(new Date(anchorTs * 1000).toISOString())
        : undefined
      rows.push({ key: 'AVWAP', value: formatMetric(val), hint: anchorDate ? `anchor: ${anchorDate}` : undefined })
      continue
    }

    if (key === 'close') {
      rows.push({ key: 'Close', value: formatMetric(val), hint: `as of ${formatDateShort(det.observed_at)}` })
      continue
    }

    if (key === 'week52_high') {
      rows.push({
        key: '52W High',
        value: formatMetric(val),
        hint: week52HighTime ? `occurred: ${formatUnixDateShort(week52HighTime)}` : undefined,
      })
      continue
    }

    if (key === 'week52_low') {
      rows.push({
        key: '52W Low',
        value: formatMetric(val),
        hint: week52LowTime ? `occurred: ${formatUnixDateShort(week52LowTime)}` : undefined,
      })
      continue
    }

    rows.push({ key: prettifyKey(key), value: formatMetric(val) })
  }
  return rows
})

const SCORE_FACTOR_HINTS: Record<string, string> = {
  distance_to_level: 'How close price is to the zone center. 1.0 = exactly at the level, 0 = far away.',
  touch_count: 'Number of times price has tested and respected this zone. More touches = stronger zone.',
  recency: 'How recently the zone was last tested. Decays over 120 bars from the last touch.',
  structure_age: 'How long the zone has existed since its first touch. Matures over 180 bars.',
  overlap_confluence: 'Overlap with EMAs, anchored VWAP, or 52-week levels. Higher = more confluence.',
  recent_reaction_quality: 'How cleanly price respected this zone in the last 10 bars.',
  timeframe_importance: 'Weight assigned to this timeframe. Fixed at 1.0 — placeholder for multi-timeframe scoring.',
  normalized_score: 'Final composite score: weighted blend of all factors above.',
}

function scoreFactorHint(key: string): string {
  return SCORE_FACTOR_HINTS[key] ?? ''
}
const runningScan = computed(() => scanPending.value || latestRun.value?.status === 'running')

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
  const match = value.match(/^\d{4}-\d{2}-\d{2}/)
  if (match) return match[0]
  const d = new Date(value)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

function formatUnixDateShort(value: number) {
  return formatDateShort(new Date(value * 1000).toISOString())
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
  if (runningScan.value) return
  await radarStore.loadDetection(id)
}

async function runScan() {
  if (runningScan.value) return
  scanPending.value = true
  try {
    await radarStore.runScan()
    await refresh()
  } finally {
    scanPending.value = false
  }
}

function openInChart(detection: RadarDetection) {
  if (runningScan.value) return
  radarStore.queueChartDetection(detection)
  router.push({
    path: `/chart/${encodeURIComponent(detection.instrument_symbol)}`,
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
  position: relative;
  height: 100%;
  color: #ccc;
  font-size: 13px;
  padding: 24px;
  gap: 16px;
  box-sizing: border-box;
  overflow: hidden;
}

.radar-stage {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.radar-view--busy .radar-stage {
  opacity: 0.55;
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

.radar-busy-overlay {
  position: absolute;
  inset: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(8, 8, 8, 0.2);
  backdrop-filter: blur(1px);
}

.radar-busy-card {
  width: min(420px, 100%);
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  background: rgba(18, 18, 18, 0.95);
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.42);
  padding: 16px 18px;
}

.radar-busy-title {
  color: #f5f5f5;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
}

.radar-busy-copy {
  color: #8a8a8a;
  line-height: 1.5;
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
  overflow-x: hidden;
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
  display: flex;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.kv-val {
  color: #aaa;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.kv-val-block {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.kv-hint {
  color: #444;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.kv-score {
  color: #26a69a;
  font-weight: 600;
}

.kv-info {
  appearance: none;
  width: 9px;
  height: 9px;
  border: 1px solid #303030;
  border-radius: 999px;
  background: #151515;
  color: #5e5e5e;
  cursor: help;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 7px;
  font-weight: 700;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-style: normal;
  text-transform: none;
  letter-spacing: 0;
  position: relative;
  line-height: 1;
  flex: 0 0 auto;
  margin-top: 0;
  vertical-align: super;
  transform: translateY(-0.2em);
  padding: 0;
}

.kv-info:hover,
.kv-info:focus-visible {
  color: #aaa;
  border-color: #505050;
  outline: none;
}

</style>
