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
        <div class="saved-view-controls">
          <select v-model="selectedSavedView" class="filter-select" :disabled="runningScan" @change="applySavedView">
            <option value="">Saved views</option>
            <option v-for="view in radarStore.savedViews" :key="view.name" :value="view.name">{{ view.name }}</option>
          </select>
          <button class="action-btn" :disabled="runningScan" @click="showSaveViewInput = !showSaveViewInput">
            Save view
          </button>
        </div>
        <select v-model="filters.timeframe" class="filter-select" :disabled="runningScan" @change="refresh">
          <option v-for="timeframe in timeframeOptions" :key="timeframe" :value="timeframe">{{ timeframe }}</option>
        </select>
        <select v-model="filters.setupType" class="filter-select" :disabled="runningScan" @change="refresh">
          <option value="">All setups</option>
          <option v-for="type in setupTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
        </select>
        <select v-model="filters.state" class="filter-select" :disabled="runningScan" @change="refresh">
          <option value="">All states</option>
          <option v-for="state in radarStates" :key="state.value" :value="state.value">{{ state.label }}</option>
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
          <input v-model.number="filters.minScore" class="score-slider" type="range" min="0" max="1" step="0.05" :disabled="runningScan" @change="refresh" />
          <span class="score-value">{{ filters.minScore.toFixed(2) }}</span>
        </label>
        <label class="fresh-toggle">
          <input v-model="filters.activeOnly" type="checkbox" :disabled="runningScan" @change="refresh" />
          <span>Open only</span>
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
          <div v-else-if="isCompactResults" class="detections-card-list">
            <button
              v-for="detection in radarStore.detections"
              :key="detection.id"
              type="button"
              class="detection-card"
              :class="{ active: radarStore.selectedDetection?.id === detection.id }"
              @click="selectDetection(detection.id)"
            >
              <div class="detection-card-top">
                <span class="td-symbol">{{ detection.instrument_symbol }}</span>
                <span class="td-score">{{ detection.score.toFixed(2) }}</span>
              </div>
              <div class="detection-card-main">
                <span class="detection-card-setup">{{ labelForSetup(detection.setup_type) }}</span>
                <span class="td-setup-sub">{{ formatRadarEventLabel(detection) }}</span>
              </div>
              <div class="detection-card-meta">
                <span :class="['state-pill', `state-pill--${detection.state}`]">{{ labelForState(detection.state) }}</span>
                <span class="td-dim">#{{ formatThreadSequence(detection) || '—' }}</span>
                <span class="td-dim">{{ formatRadarEventDate(detection) }}</span>
              </div>
              <div class="detection-card-meta detection-card-meta--bottom">
                <span class="td-dim">Level {{ formatPrice(detection.key_level_price) }}</span>
                <span class="td-dim">{{ formatOutcomeStatusCompact(detection) }}</span>
              </div>
            </button>
          </div>
          <table v-else class="detections-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Setup</th>
                <th>State</th>
                <th class="col-seq">Seq</th>
                <th class="col-event">Event date</th>
                <th>Score</th>
                <th class="col-level">Level</th>
                <th>Outcome</th>
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
                <td class="td-setup">
                  <span>{{ labelForSetup(detection.setup_type) }}</span>
                  <span class="td-setup-sub">{{ formatRadarEventLabel(detection) }}</span>
                </td>
                <td class="td-state">
                  <span :class="['state-pill', `state-pill--${detection.state}`]">{{ labelForState(detection.state) }}</span>
                </td>
                <td class="td-mono td-dim col-seq">{{ formatThreadSequence(detection) }}</td>
                <td class="td-mono td-dim col-event">{{ formatRadarEventDate(detection) }}</td>
                <td class="td-score">{{ detection.score.toFixed(2) }}</td>
                <td class="td-mono col-level">{{ formatPrice(detection.key_level_price) }}</td>
                <td class="td-mono td-dim">{{ formatOutcomeStatusCompact(detection) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── Detail panel ───────────────────────────────────────────────────── -->
      <div class="radar-detail-resize" role="separator" aria-orientation="vertical" aria-label="Resize radar details" @pointerdown="startDetailResize"></div>
      <aside class="radar-detail" :style="{ width: `${detailWidth}px` }">
        <template v-if="radarStore.selectedDetection?.evidence">
          <div class="detail-head">
            <div>
              <span class="detail-symbol">{{ radarStore.selectedDetection.instrument_symbol }}</span>
              <span class="detail-setup">{{ labelForSetup(radarStore.selectedDetection.setup_type) }}</span>
              <span :class="['detail-state-pill', `detail-state-pill--${radarStore.selectedDetection.state}`]">
                {{ labelForState(radarStore.selectedDetection.state) }}
              </span>
              <span v-if="selectedThreadStatusLabel" class="detail-thread-pill">{{ selectedThreadStatusLabel }}</span>
            </div>
            <button class="action-btn primary" :disabled="runningScan" @click="openInChart(radarStore.selectedDetection)">
              Open in chart
            </button>
          </div>
          <div class="detail-actions-row">
            <button class="action-btn" :disabled="runningScan || workflowPending" @click="createAlertFromDetection">
              {{ workflowPendingAction === 'alert' ? 'Creating…' : 'Create alert' }}
            </button>
            <select v-model="selectedWatchlistId" class="filter-select detail-watchlist-select" :disabled="runningScan || workflowPending">
              <option value="">Default watchlist</option>
              <option v-for="watchlist in watchlistOptions" :key="watchlist.id" :value="String(watchlist.id)">
                {{ watchlist.name }}
              </option>
            </select>
            <button class="action-btn" :disabled="runningScan || workflowPending" @click="addDetectionToWatchlist">
              {{ workflowPendingAction === 'watchlist' ? 'Adding…' : 'Add to watchlist' }}
            </button>
          </div>
          <div v-if="workflowMessage" class="detail-workflow-msg">{{ workflowMessage }}</div>
          <RadarDetailPreviewChart
            :key="radarStore.selectedDetection.id"
            :detection="radarStore.selectedDetection"
          />

          <p class="detail-summary">{{ radarStore.selectedDetection.summary }}</p>
          <p class="detail-invalid">{{ radarStore.selectedDetection.invalidation_hint }}</p>
          <p v-if="radarStore.selectedDetection.state_reason" class="detail-state-copy">
            {{ radarStore.selectedDetection.state_reason }}
          </p>

          <div v-if="rationaleItems.length" class="detail-section">
            <div class="section-title">Why flagged</div>
            <div class="rationale-list">
              <div v-for="item in rationaleItems" :key="item" class="rationale-item">{{ item }}</div>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">Action plan</div>
            <div class="kv-grid">
              <template v-for="row in actionPlanRows" :key="row.key">
                <span class="kv-key">
                  {{ row.key }}
                  <HoverTooltip v-if="row.info" :text="row.info">
                    <button type="button" class="kv-info" :aria-label="`${row.key} info`">i</button>
                  </HoverTooltip>
                </span>
                <span class="kv-val-block">
                  <span class="kv-val">{{ row.value }}</span>
                  <span v-if="row.hint" class="kv-hint">{{ row.hint }}</span>
                </span>
              </template>
            </div>
          </div>

          <div v-if="selectedThread" class="detail-section">
            <div class="section-title-row">
              <div class="section-title">Thread</div>
              <HoverTooltip text="One evolving setup around the same level across radar runs.">
                <button type="button" class="section-info" aria-label="Thread info">i</button>
              </HoverTooltip>
            </div>
            <div class="kv-grid">
              <span class="kv-key">Current state</span>
              <span class="kv-val">{{ labelForState(selectedThread.current_state) }}</span>
              <span class="kv-key">Context</span>
              <span class="kv-val">{{ selectedThread.context_role || 'mixed' }}</span>
              <span class="kv-key">Reference level</span>
              <span class="kv-val">{{ formatPrice(selectedThread.reference_price) }}</span>
              <span class="kv-key">Events</span>
              <span class="kv-val">{{ selectedThread.detection_count }}</span>
              <span class="kv-key">State changed</span>
              <span class="kv-val">{{ formatDateShort(selectedThread.state_changed_at) }}</span>
              <span class="kv-key">Started</span>
              <span class="kv-val">{{ formatDateShort(selectedThread.started_at) }}</span>
              <span class="kv-key">Last seen</span>
              <span class="kv-val">{{ formatDateShort(selectedThread.last_seen_at) }}</span>
            </div>
            <div v-if="selectedThreadHistory.length" class="thread-history">
              <button
                v-for="event in selectedThreadHistory"
                :key="event.id"
                type="button"
                class="thread-event"
                :class="{ 'thread-event--active': event.id === radarStore.selectedDetection?.id }"
                :disabled="runningScan"
                @click="selectDetection(event.id)"
              >
                <span class="thread-event-seq">#{{ event.thread_event_index ?? '—' }}</span>
                <span class="thread-event-main">
                  <span class="thread-event-title">{{ labelForSetup(event.setup_type) }}</span>
                  <span class="thread-event-meta">
                    {{ formatRadarEventLabel(event) }} · {{ formatRadarEventDate(event) }} · {{ labelForState(event.state) }} · {{ event.score.toFixed(2) }}
                  </span>
                  <span class="thread-event-hint">Recorded {{ formatDateTimeUtc(event.created_at) }}</span>
                </span>
              </button>
            </div>
          </div>

          <div v-if="instrumentTimeline.length" class="detail-section">
            <div class="section-title-row">
              <div class="section-title">Timeline</div>
              <HoverTooltip text="How the latest radar run currently sees this symbol on the selected timeframe.">
                <button type="button" class="section-info" aria-label="Timeline info">i</button>
              </HoverTooltip>
            </div>
            <div class="thread-history">
              <button
                v-for="event in instrumentTimeline"
                :key="event.id"
                type="button"
                class="thread-event"
                :class="{ 'thread-event--active': event.id === radarStore.selectedDetection?.id }"
                :disabled="runningScan"
                @click="selectDetection(event.id)"
              >
                <span class="thread-event-seq">{{ formatThreadSequence(event) || '•' }}</span>
                <span class="thread-event-main">
                  <span class="thread-event-title">{{ labelForSetup(event.setup_type) }}</span>
                  <span class="thread-event-meta">
                    {{ formatRadarEventLabel(event) }} · {{ formatRadarEventDate(event) }} · {{ labelForState(event.state) }} · {{ event.score.toFixed(2) }}
                  </span>
                  <span class="thread-event-hint">Recorded {{ formatDateTimeUtc(event.created_at) }}</span>
                </span>
              </button>
            </div>
          </div>

          <div v-if="instrumentHistory.length" class="detail-section">
            <div class="section-title-row">
              <div class="section-title">History</div>
              <HoverTooltip text="Persisted radar events for this symbol across older runs.">
                <button type="button" class="section-info" aria-label="History info">i</button>
              </HoverTooltip>
            </div>
            <div class="thread-history">
              <button
                v-for="event in instrumentHistory"
                :key="event.id"
                type="button"
                class="thread-event"
                :class="{ 'thread-event--active': event.id === radarStore.selectedDetection?.id }"
                :disabled="runningScan"
                @click="selectDetection(event.id)"
              >
                <span class="thread-event-seq">{{ event.timeframe }}</span>
                <span class="thread-event-main">
                  <span class="thread-event-title">{{ labelForSetup(event.setup_type) }}</span>
                  <span class="thread-event-meta">
                    {{ formatRadarEventLabel(event) }} · {{ formatRadarEventDate(event) }} · {{ labelForState(event.state) }} · {{ formatOutcomeStatusCompact(event) }}
                  </span>
                  <span class="thread-event-hint">Recorded {{ formatDateTimeUtc(event.created_at) }}</span>
                </span>
              </button>
            </div>
          </div>

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
            <div class="kv-grid kv-grid--evidence">
              <template v-for="row in evidenceMetricRows" :key="row.key">
                <span class="kv-key kv-key--metric">{{ row.key }}</span>
                <span class="kv-val-block">
                  <span class="kv-val">{{ row.value }}</span>
                  <span v-if="row.hint" class="kv-hint">{{ row.hint }}</span>
                </span>
              </template>
            </div>
          </div>

          <div v-if="currentOutcomeSummary.length" class="detail-section">
            <div class="section-title-row">
              <div class="section-title">Outcome stats</div>
              <HoverTooltip text="Historical hit and invalidation rates for this setup family on the selected timeframe.">
                <button type="button" class="section-info" aria-label="Outcome stats info">i</button>
              </HoverTooltip>
            </div>
            <div class="research-summary-list">
              <div
                v-for="summary in currentOutcomeSummary"
                :key="`${summary.timeframe}-${summary.setup_type}`"
                class="research-summary-card"
              >
                <span class="research-summary-seq">{{ summary.timeframe }}</span>
                <span class="research-summary-main">
                  <span class="research-summary-title">{{ labelForSetup(summary.setup_type) }}</span>
                  <span class="research-summary-meta">
                    hit {{ formatPercent(summary.target_hit_rate) }} · invalidated {{ formatPercent(summary.invalidated_rate) }} · stale {{ formatPercent(summary.stale_rate) }} · n={{ summary.total }}
                  </span>
                </span>
              </div>
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

      <div v-if="showSaveViewInput" class="save-view-card">
        <input
          v-model.trim="saveViewDraft"
          class="filter-input"
          placeholder="View name…"
          :disabled="runningScan"
          @keydown.enter="persistCurrentView"
        />
        <button class="action-btn primary" :disabled="runningScan || !saveViewDraft" @click="persistCurrentView">
          Save
        </button>
        <button
          v-if="selectedSavedView"
          class="action-btn"
          :disabled="runningScan"
          @click="removeSelectedView"
        >
          Delete
        </button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import HoverTooltip from '@/components/common/HoverTooltip.vue'
import RadarDetailPreviewChart from '@/components/radar/RadarDetailPreviewChart.vue'
import { useRadarStore } from '@/stores/radar'
import { useWatchlistStore } from '@/stores/watchlist'
import type {
  RadarDetection,
  RadarOutcomeSummary,
  RadarSetupType,
  RadarState,
  Timeframe,
} from '@/types'

const radarStore = useRadarStore()
const watchlistStore = useWatchlistStore()
const router = useRouter()
const scanPending = ref(false)
const showSaveViewInput = ref(false)
const saveViewDraft = ref('')
const selectedSavedView = ref('')
const selectedWatchlistId = ref('')
const workflowPendingAction = ref<'alert' | 'watchlist' | null>(null)
const workflowMessage = ref('')
const detailWidth = ref(380)
const RADAR_DETAIL_WIDTH_KEY = 'charting-platform.radar.detail-width'
const DETAIL_WIDTH_MIN = 340
const DETAIL_WIDTH_MAX = 680
let detailResizeStartX = 0
let detailResizeStartWidth = 380

const filters = reactive({
  timeframe: 'D1' as Timeframe,
  setupType: '',
  state: '',
  symbol: '',
  minScore: 0.35,
  activeOnly: true,
})

const timeframeOptions: Timeframe[] = ['M30', 'H1', 'H4', 'D1', 'W1', 'MN']

const setupTypes: Array<{ value: RadarSetupType; label: string }> = [
  { value: 'approaching_support', label: 'Approaching support' },
  { value: 'approaching_resistance', label: 'Approaching resistance' },
  { value: 'compression_support', label: 'Compression support' },
  { value: 'compression_resistance', label: 'Compression resistance' },
  { value: 'breakout', label: 'Breakout' },
  { value: 'breakout_retest', label: 'Breakout retest' },
  { value: 'breakdown', label: 'Breakdown' },
  { value: 'breakdown_retest', label: 'Breakdown retest' },
  { value: 'fakeout', label: 'Fakeout' },
  { value: 'fakedown', label: 'Fakedown' },
  { value: 'failed_reclaim', label: 'Failed reclaim' },
  { value: 'failed_breakdown_recovery', label: 'Failed breakdown recovery' },
  { value: 'reclaim', label: 'Reclaim' },
  { value: 'rejection', label: 'Rejection' },
]
const radarStates: Array<{ value: RadarState; label: string }> = [
  { value: 'developing', label: 'Developing' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'invalidated', label: 'Invalidated' },
  { value: 'stale', label: 'Stale' },
]

const latestRun = computed(() => radarStore.runs[0] ?? null)
const selectedThread = computed(() => radarStore.selectedDetection?.thread ?? null)
const selectedThreadHistory = computed(() => radarStore.selectedDetection?.thread_history ?? [])
const instrumentHistory = computed(() => radarStore.selectedInstrumentHistory)
const watchlistOptions = computed(() => watchlistStore.watchlists.filter(w => !w.is_managed && !w.is_locked))
const currentOutcomeSummary = computed(() => {
  const setup = radarStore.selectedDetection?.setup_type
  return setup
    ? radarStore.outcomeSummary.filter(summary => summary.setup_type === setup)
    : radarStore.outcomeSummary
})
const instrumentTimeline = computed(() => {
  const instrumentId = radarStore.selectedDetection?.instrument_id
  if (!instrumentId) return []
  return [...radarStore.detections]
    .filter(
      detection => detection.instrument_id === instrumentId && detection.timeframe === filters.timeframe,
    )
    .sort(compareRadarEventsAscending)
})
const selectedThreadStatusLabel = computed(() => {
  const detection = radarStore.selectedDetection
  if (!detection) return ''
  const stateLabel = labelForState(detection.thread?.current_state ?? detection.state)
  if (detection.thread) {
    const sequence = formatThreadSequence(detection)
    return sequence ? `${stateLabel} · Thread ${sequence}` : `${stateLabel} · Threaded`
  }
  return `${stateLabel} · Unthreaded`
})

interface MetricRow {
  key: string
  value: string
  hint?: string
  info?: string
}

const evidenceMetricRows = computed((): MetricRow[] => {
  const det = radarStore.selectedDetection
  if (!det?.evidence?.metrics) return []
  const m = det.evidence.metrics as Record<string, unknown>
  const rows: MetricRow[] = []
  const contextualTimeFor = (baseKey: string) =>
    typeof m[`${baseKey}_time`] === 'number' ? (m[`${baseKey}_time`] as number) : null
  const avwapAnchorType = typeof m.avwap_anchor_type === 'string' ? m.avwap_anchor_type : null
  const avwapAnchorTime = typeof m.avwap_anchor_time === 'number' ? m.avwap_anchor_time : null
  const avwapAnchorPrice = typeof m.avwap_anchor_price === 'number' ? m.avwap_anchor_price : null
  const secondaryAvwapAnchorType =
    typeof m.secondary_avwap_anchor_type === 'string' ? m.secondary_avwap_anchor_type : null

  for (const [key, val] of Object.entries(m)) {
    if (
      key === 'entry_price'
      || key === 'invalidation_price'
      || key === 'target_price'
      || key === 'target_source'
      || key === 'risk_reward'
      || key === 'state'
      || key === 'state_reason'
      || (key.endsWith('_time') && key !== 'signal_time' && key !== 'context_time')
      || key === 'avwap_anchor_type'
      || key === 'avwap_anchor_time'
      || key === 'avwap_anchor_price'
      || key === 'secondary_avwap_anchor_type'
    ) continue

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
      rows.push({
        key: 'AVWAP',
        value: formatMetricValue(key, val),
        hint: buildAnchorHint(avwapAnchorType, avwapAnchorTime, avwapAnchorPrice, det),
      })
      continue
    }

    if (key === 'secondary_avwap') {
      rows.push({
        key: 'Secondary AVWAP',
        value: formatMetricValue(key, val),
        hint: secondaryAvwapAnchorType
          ? `anchor: ${humanizeRadarToken(secondaryAvwapAnchorType)}`
          : undefined,
      })
      continue
    }

    if (key === 'close') {
      rows.push({ key: 'Close', value: formatMetricValue(key, val), hint: `as of ${formatDateShort(det.observed_at)}` })
      continue
    }

    if (key === 'signal_time') {
      const preferDateOnly = prefersDateOnly(det)
      rows.push({
        key: preferDateOnly ? 'Signal date' : 'Signal time',
        value: formatMetricTimestamp(
          det.signal_at ?? (typeof val === 'number' ? val : null),
          { preferDateOnly },
        ),
      })
      continue
    }

    if (key === 'context_time') {
      const preferDateOnly = prefersDateOnly(det)
      rows.push({
        key: preferDateOnly ? 'Context date' : 'Context time',
        value: formatMetricTimestamp(
          det.context_at ?? (typeof val === 'number' ? val : null),
          { preferDateOnly },
        ),
      })
      continue
    }

    if (key === 'week52_high') {
      rows.push({
        key: humanizeMetricKey(key),
        value: formatMetricValue(key, val),
        hint: contextualTimeFor(key) ? `occurred: ${formatUnixMetricTimestamp(contextualTimeFor(key), det)}` : undefined,
      })
      continue
    }

    if (key === 'week52_low') {
      rows.push({
        key: humanizeMetricKey(key),
        value: formatMetricValue(key, val),
        hint: contextualTimeFor(key) ? `occurred: ${formatUnixMetricTimestamp(contextualTimeFor(key), det)}` : undefined,
      })
      continue
    }

    if (isContextualLevelMetric(key)) {
      rows.push({
        key: humanizeMetricKey(key),
        value: formatMetricValue(key, val),
        hint: contextualTimeFor(key) ? `occurred: ${formatUnixMetricTimestamp(contextualTimeFor(key), det)}` : undefined,
      })
      continue
    }

    rows.push({ key: humanizeMetricKey(key), value: formatMetricValue(key, val) })
  }
  return rows
})

const actionPlanRows = computed((): MetricRow[] => {
  const detection = radarStore.selectedDetection
  if (!detection) return []
  const metrics = detection.evidence?.metrics as Record<string, unknown> | undefined
  const targetSource = typeof metrics?.target_source === 'string' ? metrics.target_source : undefined
  const riskReward = typeof metrics?.risk_reward === 'number' ? metrics.risk_reward : null
  return [
    {
      key: 'Entry',
      value: formatPrice(detection.entry_price),
      hint: detection.state === 'developing' ? 'watch level' : 'trigger level',
    },
    {
      key: 'Invalidation',
      value: formatPrice(detection.invalidation_price),
    },
    {
      key: 'Target',
      value: formatPrice(detection.target_price),
      hint: humanizeTargetSource(targetSource),
      info: targetSourceInfo(targetSource),
    },
    {
      key: 'Reward / risk',
      value: riskReward != null ? `${riskReward.toFixed(2)}R` : '—',
      info: 'Expected reward divided by the distance to invalidation.',
    },
  ]
})

const rationaleItems = computed(() => {
  const detection = radarStore.selectedDetection
  if (!detection?.evidence) return []
  const metrics = detection.evidence.metrics as Record<string, unknown>
  const structures = detection.evidence.structures ?? []
  const items: string[] = []
  const touchCount = Number(detection.score_factors.touch_count ?? 0)
  if (Number.isFinite(touchCount) && touchCount > 0) {
    items.push(`${Math.max(2, Math.round(touchCount * 4))} swing touches define this level.`)
  }
  const multiTfHits = typeof metrics.multi_timeframe_hits === 'number' ? metrics.multi_timeframe_hits : 0
  if (multiTfHits > 0) {
    items.push(`${Math.round(multiTfHits)} higher-horizon levels overlap this zone.`)
  }
  if (metrics.volatility_squeeze_active) {
    items.push('Volatility is compressed, so a larger move may be brewing.')
  }
  if (typeof metrics.avwap_anchor_type === 'string') {
    items.push(`Primary AVWAP is anchored to ${humanizeRadarToken(metrics.avwap_anchor_type)}.`)
  }
  const structureTypes = new Set(structures.map(structure => String(structure.type)))
  if (structureTypes.has('channel') || structureTypes.has('wedge') || structureTypes.has('triangle')) {
    items.push('Pattern structure is reinforcing the setup context.')
  } else if (structureTypes.has('trendline')) {
    items.push('A nearby trendline is reinforcing this area.')
  }
  if ((typeof metrics.gap_count === 'number' ? metrics.gap_count : 0) > 0) {
    items.push('A nearby gap adds context to the reaction zone.')
  }
  return items.slice(0, 4)
})

const SCORE_FACTOR_HINTS: Record<string, string> = {
  distance_to_level: 'How close price is to the zone center. 1.0 = exactly at the level, 0 = far away.',
  touch_count: 'Number of times price has tested and respected this zone. More touches = stronger zone.',
  recency: 'How recently the zone was last tested. Decays over 120 bars from the last touch.',
  structure_age: 'How long the zone has existed since its first touch. Matures over 180 bars.',
  overlap_confluence: 'Overlap with EMAs, anchored VWAP, or 52-week levels. Higher = more confluence.',
  multi_timeframe_alignment: 'How much higher-timeframe structure overlaps with the current setup zone.',
  trend_pattern_quality: 'Strength of trendline, channel, wedge, or triangle context supporting this setup.',
  gap_context: 'Whether nearby open gaps reinforce the setup or define an unfilled reaction zone.',
  avwap_anchor_quality: 'Quality of the chosen AVWAP anchor based on its type and contextual relevance.',
  volatility_squeeze: 'How compressed Bollinger-band volatility is right now. Higher means price is coiling more tightly.',
  recent_reaction_quality: 'How cleanly price respected this zone in the last 10 bars.',
  timeframe_importance: 'Weight assigned to this timeframe. Fixed at 1.0 — placeholder for multi-timeframe scoring.',
  normalized_score: 'Final composite score: weighted blend of all factors above.',
}

function scoreFactorHint(key: string): string {
  return SCORE_FACTOR_HINTS[key] ?? ''
}
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1440)
const runningScan = computed(() => scanPending.value || latestRun.value?.status === 'running')
const workflowPending = computed(() => workflowPendingAction.value !== null)
const isCompactResults = computed(() => viewportWidth.value < 1180)
const RADAR_STATE_SEQUENCE_PRIORITY: Record<RadarState, number> = {
  developing: 0,
  confirmed: 1,
  resolved: 2,
  stale: 3,
  invalidated: 4,
}
const TERMINAL_RADAR_STATES = new Set<RadarState>(['resolved', 'stale', 'invalidated'])

function labelForSetup(setup: RadarSetupType) {
  return humanizeRadarToken(setup)
}

function titleCaseWords(value: string) {
  return value
    .split(' ')
    .filter(Boolean)
    .map(word => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}

function labelForState(state: RadarState) {
  return titleCaseWords(state.replace(/_/g, ' '))
}

function syncViewportWidth() {
  viewportWidth.value = window.innerWidth
}

function formatOutcomeStatus(status: RadarDetection['outcome_status']) {
  return titleCaseWords(status.replace(/_/g, ' '))
}

function formatOutcomeStatusCompact(detection: Pick<RadarDetection, 'outcome_status'>) {
  return detection.outcome_status === 'open'
    ? 'Open'
    : formatOutcomeStatus(detection.outcome_status)
}

function prettifyKey(key: string) {
  return key.replace(/_/g, ' ')
}

function humanizeRadarToken(value: string) {
  const normalized = value.replace(/_/g, ' ')
  const special = normalized
    .replace(/\bweek52\b/gi, '52-week')
    .replace(/\bytd\b/gi, 'YTD')
    .replace(/\bavwap\b/gi, 'AVWAP')
    .replace(/\bema\b/gi, 'EMA')
  return titleCaseWords(special)
}

function humanizeTargetSource(targetSource?: string) {
  if (!targetSource) return undefined
  if (targetSource === 'two-risk extension') return '2R extension'
  return humanizeRadarToken(targetSource)
}

function targetSourceInfo(targetSource?: string) {
  if (!targetSource) return undefined
  if (targetSource === 'two-risk extension') {
    return 'No clearer nearby structural target was found, so radar projects a fallback target two risk units away from entry.'
  }
  if (targetSource === 'next resistance') return 'Targeting the next nearby resistance zone.'
  if (targetSource === 'next support') return 'Targeting the next nearby support zone.'
  return humanizeRadarToken(targetSource)
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

function formatUnixMetricTimestamp(
  value: number | null,
  detection: Pick<RadarDetection, 'timeframe'> | { timeframe?: Timeframe | null },
) {
  if (value == null) return '—'
  return formatMetricTimestamp(value, { preferDateOnly: prefersDateOnly(detection) })
}

function prefersDateOnly(detection: Pick<RadarDetection, 'timeframe'> | { timeframe?: Timeframe | null }) {
  return !detection.timeframe || detection.timeframe === 'D1' || detection.timeframe === 'W1' || detection.timeframe === 'MN'
}

function formatDateTimeUtc(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${hh}:${mm} UTC`
}

function formatMetricTimestamp(
  value: number | string | null | undefined,
  options: { preferDateOnly?: boolean } = {},
) {
  if (value == null) return '—'
  const isoValue = typeof value === 'number'
    ? new Date(value * 1000).toISOString()
    : value
  const parsed = new Date(isoValue)
  if (Number.isNaN(parsed.getTime())) return '—'
  const isWholeDay =
    parsed.getUTCHours() === 0
    && parsed.getUTCMinutes() === 0
    && parsed.getUTCSeconds() === 0
  if (options.preferDateOnly || isWholeDay) {
    return formatDateShort(parsed.toISOString())
  }
  return formatDateTimeUtc(parsed.toISOString())
}

function radarEventTimeValue(
  detection: Pick<
    RadarDetection,
    'signal_at' | 'observed_at' | 'invalidated_at' | 'target_hit_at' | 'outcome_last_evaluated_at' | 'state'
  >,
) {
  if (detection.state === 'invalidated') return detection.invalidated_at ?? detection.outcome_last_evaluated_at ?? detection.observed_at
  if (detection.state === 'stale') return detection.outcome_last_evaluated_at ?? detection.observed_at
  if (detection.target_hit_at) return detection.target_hit_at
  return detection.signal_at ?? detection.observed_at
}

function formatRadarEventDate(
  detection: Pick<
    RadarDetection,
    'signal_at' | 'observed_at' | 'invalidated_at' | 'target_hit_at' | 'outcome_last_evaluated_at' | 'state'
  > & { timeframe?: Timeframe | null },
) {
  return formatMetricTimestamp(radarEventTimeValue(detection), {
    preferDateOnly: prefersDateOnly(detection),
  })
}

function formatRadarEventLabel(
  detection: Pick<RadarDetection, 'state' | 'target_hit_at' | 'invalidated_at' | 'outcome_status'>,
) {
  if (detection.state === 'resolved') return 'Target hit'
  if (detection.state === 'invalidated') return 'Invalidated'
  if (detection.state === 'stale') return 'Stale'
  if (detection.target_hit_at || detection.outcome_status === 'target_hit') return 'Target hit'
  return 'Detected'
}

function compareRadarEventsAscending(left: RadarDetection, right: RadarDetection) {
  const timeDelta = new Date(radarEventTimeValue(left) ?? left.observed_at).getTime()
    - new Date(radarEventTimeValue(right) ?? right.observed_at).getTime()
  if (timeDelta !== 0) return timeDelta
  const createdDelta = new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
  if (createdDelta !== 0) return createdDelta
  const stateDelta = (RADAR_STATE_SEQUENCE_PRIORITY[left.state] ?? 99) - (RADAR_STATE_SEQUENCE_PRIORITY[right.state] ?? 99)
  if (stateDelta !== 0) return stateDelta
  const sequenceDelta = (left.thread_event_index ?? Number.MAX_SAFE_INTEGER) - (right.thread_event_index ?? Number.MAX_SAFE_INTEGER)
  if (sequenceDelta !== 0) return sequenceDelta
  return left.id - right.id
}

function formatThreadSequence(
  detection: Pick<RadarDetection, 'id' | 'thread_event_index' | 'thread' | 'thread_history'>,
) {
  const fallbackIndex = detection.thread_history?.findIndex(event => event.id === detection.id) ?? -1
  const eventIndex = detection.thread_event_index ?? (fallbackIndex >= 0 ? fallbackIndex + 1 : null)
  const totalEvents = detection.thread?.detection_count ?? detection.thread_history?.length
  if (eventIndex != null && totalEvents) return `${eventIndex}/${totalEvents}`
  if (eventIndex != null) return `#${eventIndex}`
  return ''
}

function formatPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

function formatPercent(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatFactor(value: unknown) {
  if (typeof value === 'number') return value.toFixed(2)
  return String(value)
}

function isContextualLevelMetric(key: string) {
  return [
    'week52_high',
    'week52_low',
    'all_time_high',
    'all_time_low',
    'ytd_open',
    'ytd_high',
    'ytd_low',
  ].includes(key)
}

function humanizeMetricKey(key: string) {
  switch (key) {
    case 'atr_14':
      return 'ATR 14'
    case 'bb_width':
      return 'BB width'
    case 'bb_width_percentile':
      return 'BB width percentile'
    case 'inside_keltner':
      return 'Inside Keltner'
    case 'volatility_squeeze_active':
      return 'Squeeze active'
    case 'week52_high':
      return '52-week high'
    case 'week52_low':
      return '52-week low'
    case 'all_time_high':
      return 'All-time high'
    case 'all_time_low':
      return 'All-time low'
    case 'ytd_open':
      return 'YTD open'
    case 'ytd_high':
      return 'YTD high'
    case 'ytd_low':
      return 'YTD low'
    default:
      return humanizeRadarToken(key)
  }
}

function formatMetricValue(key: string, value: unknown) {
  if (value == null) return '—'
  if (typeof value === 'string') return humanizeRadarToken(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') {
    if (key === 'bars_since_signal' || key === 'gap_count' || key === 'pattern_count' || key === 'multi_timeframe_hits') {
      return String(Math.round(value))
    }
    return value.toFixed(2)
  }
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function buildAnchorHint(
  anchorType: string | null,
  anchorTime: number | null,
  anchorPrice: number | null,
  detection: Pick<RadarDetection, 'timeframe'> | { timeframe?: Timeframe | null },
) {
  const parts: string[] = []
  if (anchorType) parts.push(humanizeRadarToken(anchorType))
  if (anchorTime != null) parts.push(formatUnixMetricTimestamp(anchorTime, detection))
  if (anchorPrice != null) parts.push(`@ ${anchorPrice.toFixed(2)}`)
  return parts.length ? `anchor: ${parts.join(' · ')}` : undefined
}

async function refresh() {
  const activeOnly =
    filters.activeOnly
    && !(filters.state && TERMINAL_RADAR_STATES.has(filters.state as RadarState))
  await Promise.all([
    radarStore.loadRuns(5, filters.timeframe),
    radarStore.loadDetections({
      timeframe: filters.timeframe,
      setup_type: filters.setupType || undefined,
      state: filters.state || undefined,
      symbol: filters.symbol || undefined,
      min_score: filters.minScore,
      active_only: activeOnly,
    }),
    radarStore.loadOutcomeSummary(filters.timeframe),
  ])
  const selectedId = radarStore.selectedDetection?.id
  if (selectedId && radarStore.detections.some(detection => detection.id === selectedId)) {
    await selectDetection(selectedId)
    return
  }
  if (radarStore.detections[0]) {
    await selectDetection(radarStore.detections[0].id)
  } else {
    workflowMessage.value = ''
  }
}

function persistCurrentView() {
  if (!saveViewDraft.value) return
  radarStore.saveView(saveViewDraft.value, {
    timeframe: filters.timeframe,
    setup_type: filters.setupType || undefined,
    state: filters.state || undefined,
    symbol: filters.symbol || undefined,
    min_score: filters.minScore,
    active_only: filters.activeOnly,
  })
  selectedSavedView.value = saveViewDraft.value
  showSaveViewInput.value = false
  saveViewDraft.value = ''
}

async function applySavedView() {
  const view = radarStore.savedViews.find(item => item.name === selectedSavedView.value)
  if (!view) return
  filters.setupType = view.filters.setup_type ?? ''
  filters.state = view.filters.state ?? ''
  filters.symbol = view.filters.symbol ?? ''
  filters.timeframe = (view.filters.timeframe as Timeframe | undefined) ?? 'D1'
  filters.minScore = view.filters.min_score ?? 0.35
  filters.activeOnly = view.filters.active_only ?? view.filters.fresh_only ?? true
  await refresh()
}

async function removeSelectedView() {
  if (!selectedSavedView.value) return
  radarStore.deleteView(selectedSavedView.value)
  selectedSavedView.value = ''
}

async function selectDetection(id: number) {
  if (runningScan.value) return
  const detection = await radarStore.loadDetection(id)
  if (detection) {
    await radarStore.loadInstrumentHistory(detection.instrument_id, detection.timeframe)
  }
}

async function runScan() {
  if (runningScan.value) return
  scanPending.value = true
  try {
    await radarStore.runScan(filters.timeframe)
    await refresh()
  } finally {
    scanPending.value = false
  }
}

function openInChart(detection: RadarDetection) {
  if (runningScan.value) return
  const preferredDetectionId = detection.run_id === latestRun.value?.id
    ? detection.id
    : detection.thread_history?.[detection.thread_history.length - 1]?.id ?? detection.id
  radarStore.queueChartDetection({
    id: preferredDetectionId,
    instrument_id: detection.instrument_id,
    instrument_symbol: detection.instrument_symbol,
    timeframe: detection.timeframe,
  })
  router.push({
    path: `/chart/${encodeURIComponent(detection.instrument_symbol)}`,
  })
}

async function addDetectionToWatchlist() {
  const detection = radarStore.selectedDetection
  if (!detection || workflowPending.value) return
  workflowPendingAction.value = 'watchlist'
  workflowMessage.value = ''
  try {
    const result = await radarStore.addDetectionToWatchlist(
      detection.id,
      selectedWatchlistId.value ? Number(selectedWatchlistId.value) : undefined,
    )
    workflowMessage.value = `Added to ${result.watchlist_name}.`
    await watchlistStore.loadWatchlists()
  } finally {
    workflowPendingAction.value = null
  }
}

async function createAlertFromDetection() {
  const detection = radarStore.selectedDetection
  if (!detection || workflowPending.value) return
  workflowPendingAction.value = 'alert'
  workflowMessage.value = ''
  try {
    const alert = await radarStore.createDetectionPriceAlert(detection.id)
    workflowMessage.value = `Created ${alert.condition.replace(/_/g, ' ')} alert on ${alert.instrument_symbol}.`
  } finally {
    workflowPendingAction.value = null
  }
}

function clampDetailWidth(value: number) {
  return Math.max(DETAIL_WIDTH_MIN, Math.min(DETAIL_WIDTH_MAX, Math.round(value)))
}

function persistDetailWidth() {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(RADAR_DETAIL_WIDTH_KEY, String(detailWidth.value))
}

function stopDetailResize() {
  window.removeEventListener('pointermove', onDetailResizeMove)
  window.removeEventListener('pointerup', stopDetailResize)
  persistDetailWidth()
}

function onDetailResizeMove(event: PointerEvent) {
  detailWidth.value = clampDetailWidth(detailResizeStartWidth + (detailResizeStartX - event.clientX))
}

function startDetailResize(event: PointerEvent) {
  event.preventDefault()
  detailResizeStartX = event.clientX
  detailResizeStartWidth = detailWidth.value
  window.addEventListener('pointermove', onDetailResizeMove)
  window.addEventListener('pointerup', stopDetailResize)
}

onMounted(async () => {
  if (typeof localStorage !== 'undefined') {
    const raw = localStorage.getItem(RADAR_DETAIL_WIDTH_KEY)
    const parsed = raw ? Number(raw) : NaN
    if (Number.isFinite(parsed)) {
      detailWidth.value = clampDetailWidth(parsed)
    }
  }
  window.addEventListener('resize', syncViewportWidth)
  radarStore.loadSavedViews()
  await watchlistStore.loadWatchlists()
  await refresh()
})

onBeforeUnmount(() => {
  stopDetailResize()
  window.removeEventListener('resize', syncViewportWidth)
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

.saved-view-controls,
.save-view-card {
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-view-card {
  margin-top: -4px;
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
  min-width: 0;
  align-items: stretch;
}

.radar-detail-resize {
  width: 8px;
  flex: 0 0 8px;
  cursor: col-resize;
  position: relative;
}

.radar-detail-resize::before {
  content: '';
  position: absolute;
  inset: 0 2px;
  border-radius: 999px;
  background: transparent;
  transition: background 0.12s ease;
}

.radar-detail-resize:hover::before {
  background: rgba(100, 181, 246, 0.16);
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
  flex: 1 1 460px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.detections-table-wrap {
  flex: 1;
  overflow: auto;
  min-width: 0;
}

.detections-card-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detection-card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 7px;
  text-align: left;
  background: #0f0f0f;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  padding: 10px 11px;
  color: inherit;
  font-family: inherit;
  cursor: pointer;
}

.detection-card:hover {
  border-color: #23384d;
  background: #101418;
}

.detection-card.active {
  background: #0f1f2e;
  border-color: #274969;
}

.detection-card-top,
.detection-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.detection-card-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.detection-card-setup {
  color: #d3d3d3;
}

.detection-card-meta {
  flex-wrap: wrap;
}

.detection-card-meta--bottom {
  color: #666;
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
  min-width: 0;
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
  white-space: normal;
}

.td-setup > span {
  display: block;
}

.td-setup-sub {
  color: #5f5f5f;
  font-size: 10px;
  margin-top: 2px;
  text-transform: none;
}

.td-state {
  min-width: 94px;
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
  flex: 0 1 auto;
  flex-shrink: 1;
  border: 1px solid #1a1a1a;
  border-radius: 6px;
  background: #0d0d0d;
  padding: 14px;
  overflow-y: auto;
  overflow-x: hidden;
  max-width: 100%;
  min-width: 280px;
  max-width: min(520px, 42vw);
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

.detail-thread-pill {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 2px 7px;
  border: 1px solid #1a2e42;
  border-radius: 999px;
  color: #7fb7ee;
  background: #102133;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.detail-state-pill,
.state-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  text-transform: capitalize;
}

.detail-state-pill {
  margin-top: 8px;
  margin-right: 6px;
}

.state-pill--developing,
.detail-state-pill--developing {
  border: 1px solid #4f4a1b;
  background: #26210d;
  color: #e0c972;
}

.state-pill--confirmed,
.detail-state-pill--confirmed {
  border: 1px solid #194331;
  background: #0f231b;
  color: #63d0aa;
}

.state-pill--resolved,
.detail-state-pill--resolved {
  border: 1px solid #27513b;
  background: #13271d;
  color: #7fe0b8;
}

.state-pill--stale,
.detail-state-pill--stale {
  border: 1px solid #313131;
  background: #171717;
  color: #8b8b8b;
}

.state-pill--invalidated,
.detail-state-pill--invalidated {
  border: 1px solid #5f231f;
  background: #2a1210;
  color: #ef8a85;
}

.detail-summary {
  color: #aaa;
  font-size: 12px;
  line-height: 1.55;
  margin-bottom: 6px;
}

.detail-actions-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.detail-watchlist-select {
  min-width: 150px;
}

.detail-workflow-msg {
  color: #6fb98f;
  font-size: 11px;
  margin-bottom: 12px;
}

.detail-invalid {
  color: #666;
  font-size: 11px;
  margin-bottom: 6px;
}

.detail-state-copy {
  color: #7b7b7b;
  font-size: 11px;
  line-height: 1.5;
  margin-bottom: 16px;
}

.detail-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #1a1a1a;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.section-title-row .section-title {
  margin-bottom: 0;
}

.section-info {
  appearance: none;
  width: 10px;
  height: 10px;
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
  line-height: 1;
  padding: 0;
}

.section-info:hover,
.section-info:focus-visible {
  color: #aaa;
  border-color: #505050;
  outline: none;
}

.rationale-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rationale-item {
  border: 1px solid #1d2833;
  border-radius: 6px;
  background: #101820;
  color: #8fb7d8;
  font-size: 11px;
  line-height: 1.45;
  padding: 7px 9px;
}

.thread-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.thread-event {
  appearance: none;
  width: 100%;
  border: 1px solid #1f1f1f;
  border-radius: 6px;
  background: #111;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  text-align: left;
  cursor: pointer;
}

.thread-event:disabled {
  opacity: 0.7;
  cursor: default;
}

.thread-event:hover,
.thread-event:focus-visible,
.thread-event--active {
  border-color: #164164;
  background: #0f1d2c;
  outline: none;
}

.thread-event-seq {
  color: #26a69a;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}

.thread-event-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.thread-event-title {
  color: #d6d6d6;
}

.thread-event-meta {
  color: #666;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.thread-event-hint {
  color: #4b4b4b;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.kv-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 5px 12px;
  font-size: 12px;
  min-width: 0;
}

.kv-grid--evidence {
  grid-template-columns: minmax(168px, 1.25fr) minmax(110px, auto);
  gap: 7px 14px;
}

.kv-key {
  color: #666;
  text-transform: capitalize;
  display: flex;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.kv-key--metric {
  text-transform: none;
  line-height: 1.35;
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

.research-summary-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.research-summary-card {
  width: 100%;
  border: 1px solid #1f1f1f;
  border-radius: 6px;
  background: #101010;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
}

.research-summary-seq {
  color: #6aa8d8;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  flex: 0 0 auto;
}

.research-summary-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.research-summary-title {
  color: #d6d6d6;
}

.research-summary-meta {
  color: #666;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 1320px) {
  .col-seq,
  .col-event,
  .col-level {
    display: none;
  }
}

@media (max-width: 1080px) {
  .page-header,
  .page-header-left {
    flex-wrap: wrap;
  }

  .radar-detail {
    max-width: min(420px, 44vw);
    min-width: 260px;
  }
}

@media (max-width: 760px) {
  .page-header,
  .page-header-left {
    flex-wrap: wrap;
  }

  .radar-layout {
    flex-direction: column;
  }

  .radar-detail-resize {
    display: none;
  }

  .radar-detail {
    width: 100% !important;
    min-width: 0;
  }
}

</style>
