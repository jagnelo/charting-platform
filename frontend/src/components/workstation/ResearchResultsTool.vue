<template>
  <section ref="resultsRoot" class="research-results-tool" role="region" aria-label="Study Lab research results">
    <header aria-label="Research results toolbar">
      <strong>Persisted runs</strong>
      <button v-if="comparisonRuns.length === 2" type="button" @click="comparisonOpen = !comparisonOpen">{{ comparisonOpen ? 'Hide compare' : 'Compare' }}</button>
      <button type="button" :disabled="loading" @click="refresh">Refresh</button>
    </header>
    <p v-if="error" class="research-results-tool__error" role="alert" aria-live="assertive" aria-atomic="true">{{ error }}</p>
    <p v-else-if="loading && !runs.length" class="research-results-tool__notice" role="status" aria-live="polite" aria-atomic="true">Loading reproducible research runs…</p>
    <p v-else-if="!runs.length" class="research-results-tool__notice" role="status" aria-live="polite" aria-atomic="true">No persisted studies yet. Run a study in the adjacent Study Lab pane.</p>
    <div v-else class="research-results-tool__runs" role="list" aria-label="Persisted research runs">
      <button
        v-for="run in runs"
        :key="run.id"
        type="button"
        role="listitem"
        :class="{ 'research-results-tool__run--selected': selectedRun?.id === run.id }"
        class="research-results-tool__run"
        :aria-label="`Run ${run.id}, ${run.status}, ${run.artifact_count ?? run.artifacts.length} artifacts`"
        :aria-current="selectedRun?.id === run.id ? 'true' : undefined"
        @click="selectedRun = run"
      >
        <input type="checkbox" :checked="comparisonIds.includes(run.id)" :aria-label="`Compare run ${run.id}`" @click.stop @change="toggleComparison(run.id)" />
        <strong>Run #{{ run.id }}</strong>
        <span role="status" aria-live="polite" aria-atomic="true" :aria-label="`Run ${run.id} status: ${statusLabel(run.status)}`" :data-status="run.status" :class="`research-results-tool__status--${run.status}`">{{ statusLabel(run.status) }}</span>
        <small>{{ run.artifact_count ?? run.artifacts.length }} artifact{{ (run.artifact_count ?? run.artifacts.length) === 1 ? '' : 's' }}</small>
      </button>
    </div>
    <section v-if="comparisonOpen && comparisonRuns.length === 2" class="research-results-tool__comparison">
      <strong>Run {{ comparisonRuns[0].id }} vs {{ comparisonRuns[1].id }}</strong>
      <div><span>Code version</span><b :class="comparisonClass('code_version_id')">{{ comparisonRuns[0].code_version_id }} / {{ comparisonRuns[1].code_version_id }}</b></div>
      <div><span>Parameters</span><b :class="comparisonClass('run_config')">{{ compact(comparisonRuns[0].run_config) }} / {{ compact(comparisonRuns[1].run_config) }}</b></div>
      <div><span>Dataset</span><b :class="comparisonClass('dataset_manifest')">{{ compact(comparisonRuns[0].dataset_manifest) }} / {{ compact(comparisonRuns[1].dataset_manifest) }}</b></div>
      <div><span>Reproducibility</span><b :class="comparisonClass('reproducibility_hash')">{{ comparisonRuns[0].reproducibility_hash ?? '—' }} / {{ comparisonRuns[1].reproducibility_hash ?? '—' }}</b></div>
    </section>
    <article v-if="selectedRun" class="research-results-tool__detail" :aria-label="`Research run ${selectedRun.id} details`">
      <div class="research-results-tool__detail-header"><strong>Run #{{ selectedRun.id }}</strong><button v-if="canCancel(selectedRun)" type="button" :disabled="canceling" @click="cancel(selectedRun)">Cancel</button><button v-if="canPromoteBreadth(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteScan(selectedRun)">{{ promoting ? 'Promoting…' : 'Promote to EasyScan' }}</button><button v-if="canPromoteBreadthBoolean(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteAlert(selectedRun)">{{ promoting ? 'Promoting…' : 'Promote to alert' }}</button><button v-if="canPromoteBreadthBoolean(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteGauge(selectedRun)">{{ promoting ? 'Promoting…' : 'Use as Market Gauge' }}</button><button v-if="canPromoteBreadthBoolean(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteSignal(selectedRun)">{{ promoting ? 'Promoting…' : 'Save as Strategy signal' }}</button><button v-if="canPromoteEventSignal(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteEventSignal(selectedRun)">{{ promoting ? 'Promoting…' : 'Save events as Strategy signal' }}</button><button v-if="canPromoteEventFilter(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteEventFilter(selectedRun)">{{ promoting ? 'Promoting…' : 'Save events as watchlist filter' }}</button><button v-if="canPromoteEventFilter(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteEventAlert(selectedRun)">{{ promoting ? 'Promoting…' : 'Promote events to alert' }}</button><button v-if="canPromoteBreadthStudy(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteStudy(selectedRun)">{{ promoting ? 'Promoting…' : 'Save as Study Lab study' }}</button><button v-if="canPromoteBreadthPlot(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promotePlot(selectedRun)">{{ promoting ? 'Promoting…' : 'Save as chart plot' }}</button><button v-if="canPromoteBreadthAggregatePlot(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteAggregatePlot(selectedRun)">{{ promoting ? 'Promoting…' : 'Save as aggregate chart plot' }}</button><button v-if="canPromoteBreadthColumn(selectedRun)" type="button" :disabled="rerunning || canceling || promoting" @click="promoteColumn(selectedRun)">{{ promoting ? 'Promoting…' : 'Save as watchlist column' }}</button><button type="button" :disabled="rerunning || canceling || promoting" @click="rerun(selectedRun, true)">Rerun snapshot</button><button type="button" :disabled="rerunning || canceling || promoting" @click="rerun(selectedRun, false)">Rerun latest</button></div>
      <p class="research-results-tool__run-guidance" role="status" aria-live="polite" aria-atomic="true">{{ statusGuidance(selectedRun.status) }}</p>
      <p v-if="promotionMessage" class="research-results-tool__run-guidance" role="status" aria-live="polite" aria-atomic="true">{{ promotionMessage }}</p>
      <small v-if="selectedRun.reproducibility_hash">{{ selectedRun.reproducibility_hash }}</small>
      <details v-if="selectedRun.diagnostics?.length" class="research-results-tool__run-details"><summary>Diagnostics ({{ selectedRun.diagnostics.length }})</summary><pre>{{ formatMessages(selectedRun.diagnostics) }}</pre></details>
      <details v-if="selectedRun.warnings?.length" class="research-results-tool__run-details"><summary>Warnings ({{ selectedRun.warnings.length }})</summary><pre>{{ formatMessages(selectedRun.warnings) }}</pre></details>
      <details v-if="selectedRun.logs" class="research-results-tool__run-details"><summary>Execution log</summary><pre>{{ selectedRun.logs }}</pre></details>
      <details v-if="Object.keys(selectedRun.resource_usage ?? {}).length" class="research-results-tool__run-details"><summary>Resource usage</summary><pre>{{ formatObject(selectedRun.resource_usage) }}</pre></details>
      <div v-if="selectedRun.artifacts.length" class="research-results-tool__artifacts">
        <article v-for="artifact in selectedRun.artifacts" :key="artifact.id" :aria-label="`${artifact.name} ${artifact.artifact_type} result`">
          <div class="research-results-tool__artifact-header"><strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small><button type="button" :title="`Export ${artifact.name}`" @click="exportArtifact(selectedRun!, artifact)">Export</button></div>
          <div v-if="canPromoteStructuredArtifact(selectedRun, artifact)" class="research-results-tool__artifact-promotions" role="group" :aria-label="`${artifact.name} promotions`">
            <button v-if="artifact.artifact_type === 'scalar'" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save column: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, 'column')">{{ promoting ? 'Promoting…' : `Save column: ${artifact.name}` }}</button>
            <button v-if="artifact.artifact_type === 'series'" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save chart plot: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, 'plot')">{{ promoting ? 'Promoting…' : `Save chart plot: ${artifact.name}` }}</button>
            <button v-if="artifact.artifact_type === 'series' && latestSeriesValue(artifact) != null" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save latest column: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, 'column')">{{ promoting ? 'Promoting…' : `Save latest column: ${artifact.name}` }}</button>
            <template v-if="artifact.artifact_type === 'series' && hasFiniteSeriesValue(artifact)">
              <div class="research-results-tool__series-condition" role="group" :aria-label="`${artifact.name} thresholded condition`">
                <label>When <select v-model="seriesConditionOperator" :aria-label="`Series condition operator: ${artifact.name}`"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option><option value="eq">=</option><option value="ne">≠</option></select></label>
                <label>Value <input v-model.number="seriesConditionThreshold" type="number" step="any" :aria-label="`Series condition threshold: ${artifact.name}`" /></label>
                <button type="button" :disabled="rerunning || canceling || promoting || !Number.isFinite(seriesConditionThreshold)" :aria-label="`Save Boolean column: ${artifact.name}`" @click="promoteStructuredSeriesCondition(selectedRun, artifact, 'column')">{{ promoting ? 'Promoting…' : `Save Boolean column: ${artifact.name}` }}</button>
                <button v-for="target in structuredSeriesConditionTargets" :key="`${artifact.id}-series-${target}`" type="button" :disabled="rerunning || canceling || promoting || !Number.isFinite(seriesConditionThreshold)" :aria-label="`${structuredSeriesConditionLabel(target)}: ${artifact.name}`" @click="promoteStructuredSeriesCondition(selectedRun, artifact, target)">{{ promoting ? 'Promoting…' : `${structuredSeriesConditionLabel(target)}: ${artifact.name}` }}</button>
              </div>
            </template>
            <button v-if="artifact.artifact_type === 'range'" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save center chart plot: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, 'plot')">{{ promoting ? 'Promoting…' : `Save center chart plot: ${artifact.name}` }}</button>
            <button v-if="artifact.artifact_type === 'range' && rangeData(artifact)?.center?.some(value => Number.isFinite(value))" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save latest center column: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, 'column')">{{ promoting ? 'Promoting…' : `Save latest center column: ${artifact.name}` }}</button>
            <template v-if="artifact.artifact_type === 'range' && hasFiniteRangeCenterValue(artifact)">
              <div class="research-results-tool__series-condition" role="group" :aria-label="`${artifact.name} range center thresholded condition`">
                <label>Center when <select v-model="seriesConditionOperator" :aria-label="`Range center condition operator: ${artifact.name}`"><option value="gt">&gt;</option><option value="gte">≥</option><option value="lt">&lt;</option><option value="lte">≤</option><option value="eq">=</option><option value="ne">≠</option></select></label>
                <label>Value <input v-model.number="seriesConditionThreshold" type="number" step="any" :aria-label="`Range center condition threshold: ${artifact.name}`" /></label>
                <button type="button" :disabled="rerunning || canceling || promoting || !Number.isFinite(seriesConditionThreshold)" :aria-label="`Save Boolean column: ${artifact.name}`" @click="promoteStructuredRangeCenterCondition(selectedRun, artifact, 'column')">{{ promoting ? 'Promoting…' : `Save Boolean column: ${artifact.name}` }}</button>
                <button v-for="target in structuredSeriesConditionTargets" :key="`${artifact.id}-range-center-${target}`" type="button" :disabled="rerunning || canceling || promoting || !Number.isFinite(seriesConditionThreshold)" :aria-label="`${structuredSeriesConditionLabel(target)}: ${artifact.name}`" @click="promoteStructuredRangeCenterCondition(selectedRun, artifact, target)">{{ promoting ? 'Promoting…' : `${structuredSeriesConditionLabel(target)}: ${artifact.name}` }}</button>
              </div>
            </template>
            <template v-if="artifact.artifact_type === 'boolean'">
              <button v-for="target in structuredBooleanPromotionTargets" :key="`${artifact.id}-${target}`" type="button" :disabled="rerunning || canceling || promoting" :aria-label="`${structuredBooleanPromotionLabel(target)}: ${artifact.name}`" @click="promoteStructuredArtifact(selectedRun, artifact, target)">{{ promoting ? 'Promoting…' : `${structuredBooleanPromotionLabel(target)}: ${artifact.name}` }}</button>
            </template>
          </div>
          <small v-if="artifactCapabilityNote(artifact)" class="research-results-tool__artifact-capability" role="note">{{ artifactCapabilityNote(artifact) }}</small>
          <strong v-if="artifact.artifact_type === 'scalar' || artifact.artifact_type === 'boolean'" :class="{ 'research-results-tool__boolean--true': artifact.artifact_type === 'boolean' && artifact.payload.value === true, 'research-results-tool__boolean--false': artifact.artifact_type === 'boolean' && artifact.payload.value === false }">{{ formatMetric(artifact) }}</strong>
          <table v-else-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><caption class="sr-only">{{ artifact.name }} table</caption><thead><tr><th v-for="column in tableColumns(artifact)" :key="column" scope="col">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
          <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
          <StudyBarsUPlot v-else-if="artifact.artifact_type === 'bar' && barData(artifact)" :name="artifact.name" :labels="barData(artifact)!.labels" :values="barData(artifact)!.values" />
          <StudyHistogramUPlot v-else-if="artifact.artifact_type === 'histogram' && histogramData(artifact)" :name="artifact.name" :bins="histogramData(artifact)!.bins" :current="histogramData(artifact)!.current" />
          <StudyRangeUPlot v-else-if="artifact.artifact_type === 'range' && rangeData(artifact)" :name="artifact.name" :timestamps="rangeData(artifact)!.timestamps" :lower="rangeData(artifact)!.lower" :upper="rangeData(artifact)!.upper" :center="rangeData(artifact)!.center" />
          <StudyScatterUPlot v-else-if="artifact.artifact_type === 'scatter' && scatterData(artifact)" :name="artifact.name" :x="scatterData(artifact)!.x" :y="scatterData(artifact)!.y" />
          <StudyHeatmap v-else-if="artifact.artifact_type === 'heatmap' && heatmapData(artifact)" :name="artifact.name" :rows="heatmapData(artifact)!.rows" :columns="heatmapData(artifact)!.columns" :values="heatmapData(artifact)!.values" />
          <StudyDashboard v-else-if="artifact.artifact_type === 'dashboard' && dashboardData(artifact)" :name="artifact.name" :panels="dashboardData(artifact)!" :artifacts="selectedRun.artifacts" @occurrence="emit('occurrence', $event)" />
          <section v-else-if="artifact.artifact_type === 'breadth_history' && breadthHistoryData(artifact)" class="research-results-tool__breadth-history" aria-label="Historical breadth">
            <GenericBreadthHistoryUPlot :history="breadthHistoryData(artifact)!" />
            <div class="research-results-tool__occurrence-filters" role="group" aria-label="Historical breadth occurrence filters">
              <label>Symbol <input v-model="occurrenceSymbolFilter" type="search" aria-label="Occurrence symbol filter" placeholder="All symbols" /></label>
              <label>Transition <select v-model="occurrenceKindFilter" aria-label="Occurrence transition filter"><option value="all">All</option><option value="member_entered">Entered</option><option value="member_exited">Exited</option></select></label>
              <span role="status" aria-live="polite">{{ filteredBreadthHistoryOccurrences(artifact).length }} shown</span>
            </div>
            <div class="research-results-tool__events" role="list" aria-label="Historical breadth occurrences">
              <button v-for="(event, index) in filteredBreadthHistoryOccurrences(artifact).slice().reverse().slice(0, 100)" :key="event.occurrence_id + '-' + index" type="button" role="listitem" :aria-label="event.symbol + ' ' + (event.kind === 'member_entered' ? 'entered' : 'exited') + ' ' + event.timestamp" @click="emit('occurrence', event)">
                <strong>{{ event.symbol }}</strong><span>{{ event.kind === 'member_entered' ? 'Entered condition' : 'Exited condition' }} · {{ event.timestamp }}</span>
                <small v-if="event.percentage != null">{{ (event.percentage * 100).toFixed(1) }}%</small>
              </button>
              <small v-if="!filteredBreadthHistoryOccurrences(artifact).length">No member state changes match the current filters.</small>
            </div>
          </section>
          <section v-else-if="artifact.artifact_type === 'events'" class="research-results-tool__event-artifact" :aria-label="`${artifact.name} occurrences`">
            <div class="research-results-tool__occurrence-filters" role="group" :aria-label="`${artifact.name} occurrence filters`">
              <label>Symbol <input v-model="occurrenceSymbolFilter" type="search" :aria-label="`${artifact.name} symbol filter`" placeholder="All symbols" /></label>
              <label>Type <select v-model="occurrenceKindFilter" :aria-label="`${artifact.name} event type filter`"><option value="all">All</option><option v-for="kind in eventKinds(artifact)" :key="kind" :value="kind">{{ kind.replace(/_/g, ' ') }}</option></select></label>
              <span role="status" aria-live="polite">{{ filteredEventRows(artifact).length }} shown</span>
            </div>
            <div v-if="canPromoteStructuredEventArtifact(selectedRun, artifact)" class="research-results-tool__event-promotions" role="group" :aria-label="`${artifact.name} promotions`">
              <button type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save filter: ${artifact.name}`" @click="promoteEventArtifact(selectedRun, artifact.name, 'filter')">{{ promoting ? 'Promoting…' : `Save filter: ${artifact.name}` }}</button>
              <button type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Promote alert: ${artifact.name}`" @click="promoteEventArtifact(selectedRun, artifact.name, 'alert')">{{ promoting ? 'Promoting…' : `Promote alert: ${artifact.name}` }}</button>
              <button type="button" :disabled="rerunning || canceling || promoting" :aria-label="`Save Strategy signal: ${artifact.name}`" @click="promoteEventArtifact(selectedRun, artifact.name, 'signal')">{{ promoting ? 'Promoting…' : `Save Strategy signal: ${artifact.name}` }}</button>
            </div>
            <div class="research-results-tool__events" role="list" :aria-label="`${artifact.name} filtered occurrences`">
              <button v-for="(event, index) in filteredEventRows(artifact)" :key="`${event.symbol}-${event.timestamp}-${index}`" type="button" role="listitem" :aria-label="`${event.symbol} ${event.timestamp} occurrence`" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.kind ? `${event.kind.replace(/_/g, ' ')} · ` : '' }}{{ event.timestamp }}</span></button>
              <small v-if="!filteredEventRows(artifact).length">No events match the current filters.</small>
            </div>
          </section>
          <pre v-else>{{ artifactText(artifact.payload) }}</pre>
        </article>
      </div>
      <p v-else-if="detailLoading" class="research-results-tool__notice" role="status" aria-live="polite" aria-atomic="true">Loading selected run details…</p>
      <p v-else-if="detailError" class="research-results-tool__error" role="alert" aria-live="assertive" aria-atomic="true">{{ detailError }} <button type="button" :disabled="detailRetrying" @click="retryDetail">Retry</button></p>
      <p v-else class="research-results-tool__notice" role="status" aria-live="polite" aria-atomic="true">No structured artifacts have been produced yet.</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import { normalizeStudyDashboardPanels } from '@/lib/workstation/studyArtifacts'
import { studyArtifactCapability } from '@/lib/workstation/studyArtifactCapabilities'
import StudyBarsUPlot from './StudyBarsUPlot.vue'
import StudyHistogramUPlot from './StudyHistogramUPlot.vue'
import StudySeriesUPlot from './StudySeriesUPlot.vue'
import StudyScatterUPlot from './StudyScatterUPlot.vue'
import StudyHeatmap from './StudyHeatmap.vue'
import StudyDashboard from './StudyDashboard.vue'
import StudyRangeUPlot from './StudyRangeUPlot.vue'
import GenericBreadthHistoryUPlot from './GenericBreadthHistoryUPlot.vue'
import type { GenericBreadthHistoryState } from '@/stores/workspace'

interface ResearchRunSummary {
  id: number
  status: string
  code_version_id: number
  output_contract?: string | null
  run_config: Record<string, unknown>
  dataset_manifest: Record<string, unknown>
  reproducibility_hash?: string | null
  diagnostics?: unknown[]
  warnings?: unknown[]
  logs?: string
  resource_usage?: Record<string, unknown>
  artifact_count?: number
  artifacts: Array<{ id: number; name: string; artifact_type: string; payload: Record<string, unknown> }>
}

const runs = ref<ResearchRunSummary[]>([])
const resultsRoot = ref<HTMLElement | null>(null)
const selectedRun = ref<ResearchRunSummary | null>(null)
const comparisonIds = ref<number[]>([])
const comparisonOpen = ref(false)
const error = ref('')
const rerunning = ref(false)
const canceling = ref(false)
const promoting = ref(false)
const promotionMessage = ref('')
const promotedScans = ref<Record<number, { id: number; name: string; codeVersionId: number | null }>>({})
const promotedStructuredBooleanScans = ref<Record<string, { id: number; name: string; codeVersionId: number }>>({})
const promotedStructuredSeriesScans = ref<Record<string, { id: number; name: string; codeVersionId: number }>>({})
const promotedStructuredRangeCenterScans = ref<Record<string, { id: number; name: string; codeVersionId: number }>>({})
const promotedEventFilters = ref<Record<number, { id: number; name: string }>>({})
const occurrenceSymbolFilter = ref('')
const occurrenceKindFilter = ref<'all' | 'member_entered' | 'member_exited'>('all')
const seriesConditionOperator = ref<'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'ne'>('gte')
const seriesConditionThreshold = ref(0)
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string; instrument_id?: number }] }>()
const comparisonRuns = computed(() => comparisonIds.value.map(id => runs.value.find(run => run.id === id)).filter((run): run is ResearchRunSummary => Boolean(run)))
const surfaceVisible = ref(true)
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
const runsQueryKey = ['workstation', 'research-runs'] as const
const queryClient = useQueryClient()
let visibilityObserver: IntersectionObserver | null = null
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const runsQuery = useQuery({
  queryKey: runsQueryKey,
  queryFn: async () => (await api.get<ResearchRunSummary[]>('/research/runs', { limit: 25, include_artifacts: false })) ?? [],
  enabled: computed(() => surfaceVisible.value && documentVisible.value),
  staleTime: 5_000,
  refetchOnWindowFocus: true,
  refetchInterval: query => {
    const data = query.state.data
    return Array.isArray(data) && data.some(run => !['completed', 'failed', 'canceled'].includes(run.status)) ? 1_000 : false
  },
})
const selectedRunDetailQuery = useQuery({
  queryKey: computed(() => ['workstation', 'research-run', selectedRun.value?.id ?? null]),
  queryFn: async () => {
    const runId = selectedRun.value?.id
    if (!runId) throw new Error('Research result detail requires a run id')
    return api.get<ResearchRunSummary>(`/research/runs/${runId}`)
  },
  enabled: computed(() => Boolean(selectedRun.value?.id && selectedRun.value.artifacts.length === 0 && (selectedRun.value.artifact_count ?? 0) > 0)),
  staleTime: 5_000,
})
const detailLoading = computed(() => selectedRunDetailQuery.isFetching.value)
const detailError = computed(() => {
  const cause = selectedRunDetailQuery.error.value
  return cause ? (cause instanceof Error ? cause.message : 'Unable to load selected run details') : ''
})
const detailRetrying = ref(false)
const loading = computed(() => runsQuery.isFetching.value || rerunning.value || canceling.value)
watch(() => runsQuery.data.value, next => {
  if (!next) return
  runs.value = next
  const retained = selectedRun.value ? next.find(run => run.id === selectedRun.value?.id) : null
  selectedRun.value = retained ?? next[0] ?? null
  comparisonIds.value = comparisonIds.value.filter(id => next.some(run => run.id === id))
}, { immediate: true })
watch(() => runsQuery.error.value, cause => {
  if (cause) error.value = cause instanceof Error ? cause.message : 'Unable to load persisted research runs'
})
watch(() => selectedRunDetailQuery.data.value, detail => {
  if (detail && detail.id === selectedRun.value?.id) selectedRun.value = detail
})

function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
function statusLabel(status: string) {
  const labels: Record<string, string> = { queued: 'Queued', running: 'Running', completed: 'Completed', failed: 'Failed', canceled: 'Canceled' }
  return labels[status] ?? status.replace(/_/g, ' ')
}
function statusGuidance(status: string) {
  switch (status) {
    case 'queued': return 'The isolated runner is preparing the declared dataset.'
    case 'running': return 'The isolated runner is evaluating the study; results will refresh automatically.'
    case 'completed': return 'Study completed. Inspect artifacts or compare this run with another snapshot.'
    case 'failed': return 'Study failed. Inspect diagnostics and execution logs, then rerun the saved snapshot or latest data.'
    case 'canceled': return 'Study canceled. The saved configuration is preserved; rerun the snapshot or latest canonical data when ready.'
    default: return 'Study status is being resolved.'
  }
}
function formatMessages(messages: unknown[]) { return messages.map(message => typeof message === 'string' ? message : JSON.stringify(message)).join('\n') }
function formatObject(value: Record<string, unknown> | undefined) { return JSON.stringify(value ?? {}, null, 2) }
function formatMetric(artifact: ResearchRunSummary['artifacts'][number]) { return artifact.artifact_type === 'boolean' ? artifact.payload.value === true ? 'True' : artifact.payload.value === false ? 'False' : '—' : artifact.payload.value ?? '—' }
function artifactCapabilityNote(artifact: ResearchRunSummary['artifacts'][number]) {
  const capability = studyArtifactCapability(artifact.artifact_type)
  if (artifact.artifact_type === 'range' && rangeData(artifact)?.center == null) {
    return 'View/export only: this range has no aligned finite center series to promote; bounds remain source-only.'
  }
  if (artifact.artifact_type === 'series' && latestSeriesValue(artifact) == null) {
    return 'View/export only: this series has no finite observation to promote as a latest-value watchlist column.'
  }
  return capability?.note ?? ''
}
function tableRows(artifact: ResearchRunSummary['artifacts'][number]): Array<Record<string, unknown>> {
  const value = artifact.payload.value
  return Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? value as Array<Record<string, unknown>> : []
}
function tableColumns(artifact: ResearchRunSummary['artifacts'][number]) { return [...new Set(tableRows(artifact).flatMap(row => Object.keys(row)))] }
function formatCell(value: unknown) { return value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value) }
function seriesData(artifact: ResearchRunSummary['artifacts'][number]): { timestamps: string[]; values: Array<number | null> } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; values?: unknown }
  return Array.isArray(candidate.timestamps) && candidate.timestamps.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.timestamps.length === candidate.values.length && candidate.values.every(item => item == null || typeof item === 'number') ? { timestamps: candidate.timestamps, values: candidate.values } : null
}
function latestSeriesValue(artifact: ResearchRunSummary['artifacts'][number]): number | null {
  const values = seriesData(artifact)?.values
  if (!values) return null
  for (const value of values.slice().reverse()) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}
function latestRangeCenterValue(artifact: ResearchRunSummary['artifacts'][number]): number | null {
  const values = rangeData(artifact)?.center
  if (!values) return null
  for (const value of values.slice().reverse()) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}
function hasFiniteRangeCenterValue(artifact: ResearchRunSummary['artifacts'][number]) {
  return latestRangeCenterValue(artifact) != null
}
function hasFiniteSeriesValue(artifact: ResearchRunSummary['artifacts'][number]) {
  return Boolean(seriesData(artifact)?.values.some(value => typeof value === 'number' && Number.isFinite(value)))
}
function barData(artifact: ResearchRunSummary['artifacts'][number]): { labels: string[]; values: number[] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { labels?: unknown; values?: unknown }
  return Array.isArray(candidate.labels) && candidate.labels.every(item => typeof item === 'string') && Array.isArray(candidate.values) && candidate.labels.length === candidate.values.length && candidate.values.every(item => typeof item === 'number' && Number.isFinite(item)) ? { labels: candidate.labels, values: candidate.values } : null
}
function rangeData(artifact: ResearchRunSummary['artifacts'][number]): { timestamps: string[]; lower: number[]; upper: number[]; center: number[] | null } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; lower?: unknown; upper?: unknown; center?: unknown }
  if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.lower) || !Array.isArray(candidate.upper) || candidate.lower.length !== candidate.upper.length || candidate.timestamps.length !== candidate.lower.length || !candidate.lower.every(item => typeof item === 'number' && Number.isFinite(item)) || !candidate.upper.every(item => typeof item === 'number' && Number.isFinite(item))) return null
  const center = candidate.center == null ? null : Array.isArray(candidate.center) && candidate.center.length === candidate.lower.length && candidate.center.every(item => typeof item === 'number' && Number.isFinite(item)) ? candidate.center : null
  return { timestamps: candidate.timestamps, lower: candidate.lower, upper: candidate.upper, center }
}
function histogramData(artifact: ResearchRunSummary['artifacts'][number]): { bins: Array<{ start: number; end: number; count: number }>; current: number | null } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const bins = (value as { bins?: unknown }).bins
  if (!Array.isArray(bins)) return null
  const normalized = bins.filter((bin): bin is { start: number; end: number; count: number } => Boolean(bin) && typeof bin === 'object' && Number.isFinite((bin as Record<string, unknown>).start) && Number.isFinite((bin as Record<string, unknown>).end) && Number.isFinite((bin as Record<string, unknown>).count))
  const current = (value as { current?: unknown }).current
  return normalized.length ? { bins: normalized, current: typeof current === 'number' && Number.isFinite(current) ? current : null } : null
}
function scatterData(artifact: ResearchRunSummary['artifacts'][number]): { x: number[]; y: number[] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { x?: unknown; y?: unknown }
  if (!Array.isArray(candidate.x) || !Array.isArray(candidate.y) || candidate.x.length !== candidate.y.length) return null
  const x = candidate.x.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  const y = candidate.y.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  return x.length === candidate.x.length && y.length === candidate.y.length ? { x, y } : null
}
function heatmapData(artifact: ResearchRunSummary['artifacts'][number]): { rows: string[]; columns: string[]; values: number[][] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { rows?: unknown; columns?: unknown; values?: unknown }
  if (!Array.isArray(candidate.rows) || !candidate.rows.every(item => typeof item === 'string') || !Array.isArray(candidate.columns) || !candidate.columns.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || !candidate.values.every(row => Array.isArray(row) && row.every(item => typeof item === 'number' && Number.isFinite(item)))) return null
  const rows = candidate.rows as string[]
  const columns = candidate.columns as string[]
  const values = candidate.values as number[][]
  return values.length && values.length === rows.length && values.every(row => row.length === columns.length) ? { rows, columns, values } : null
}
function dashboardData(artifact: ResearchRunSummary['artifacts'][number]): Array<{ artifact: string; title: string; span: number }> | null {
  return normalizeStudyDashboardPanels(artifact.payload.value)
}
type BreadthHistoryOccurrence = {
  occurrence_id: string
  timestamp: string
  kind: 'member_entered' | 'member_exited'
  instrument_id: number
  symbol: string
  name: string
  value: boolean
  metric?: number | null
  percentage?: number | null
  pass_count: number
  eligible_count: number
}
function breadthHistoryData(artifact: ResearchRunSummary['artifacts'][number]): GenericBreadthHistoryState | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { points?: unknown }
  if (!Array.isArray(candidate.points) || !candidate.points.length) return null
  const points = candidate.points.filter((point): point is Record<string, unknown> => Boolean(point) && typeof point === 'object' && !Array.isArray(point))
  if (!points.length) return null
  return {
    definition_version: 1,
    definition_hash: 'research-run-' + artifact.id,
    universe: {},
    condition: {},
    timeframe: 'D1',
    adjustment: 'split_adjusted',
    points: points.flatMap(point => {
      const timestamp = point.timestamp
      const percentage = point.percentage
      if (typeof timestamp !== 'string' || !Number.isFinite(Date.parse(timestamp)) || (percentage != null && (typeof percentage !== 'number' || !Number.isFinite(percentage)))) return []
      return [{
        timestamp,
        requested_count: typeof point.requested_count === 'number' ? point.requested_count : 0,
        eligible_count: typeof point.eligible_count === 'number' ? point.eligible_count : 0,
        pass_count: typeof point.pass_count === 'number' ? point.pass_count : 0,
        excluded_count: typeof point.excluded_count === 'number' ? point.excluded_count : 0,
        percentage: percentage as number | null,
        coverage: typeof point.coverage === 'number' ? point.coverage : 0,
        members: [],
        exclusions: [],
      }]
    }),
    occurrences: breadthHistoryOccurrences(artifact),
    exclusions: [],
  }
}
function breadthHistoryOccurrences(artifact: ResearchRunSummary['artifacts'][number]): BreadthHistoryOccurrence[] {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const raw = (value as { occurrences?: unknown }).occurrences
  if (!Array.isArray(raw)) return []
  return raw.filter((event): event is BreadthHistoryOccurrence => {
    if (!event || typeof event !== 'object') return false
    const candidate = event as Record<string, unknown>
    return typeof candidate.occurrence_id === 'string'
      && typeof candidate.timestamp === 'string'
      && (candidate.kind === 'member_entered' || candidate.kind === 'member_exited')
      && typeof candidate.instrument_id === 'number'
      && typeof candidate.symbol === 'string'
  })
}
function filteredBreadthHistoryOccurrences(artifact: ResearchRunSummary['artifacts'][number]): BreadthHistoryOccurrence[] {
  const symbol = occurrenceSymbolFilter.value.trim().toUpperCase()
  return breadthHistoryOccurrences(artifact).filter(event => (
    (!symbol || event.symbol.toUpperCase().includes(symbol))
    && (occurrenceKindFilter.value === 'all' || event.kind === occurrenceKindFilter.value)
  ))
}
type EventRow = { symbol: string; timestamp: string; kind?: string; instrument_id?: number }
function eventRows(artifact: ResearchRunSummary['artifacts'][number]): EventRow[] {
  const value = artifact.payload.value
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item) && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string')
    .map(item => ({
      symbol: item.symbol as string,
      timestamp: item.timestamp as string,
      kind: typeof item.kind === 'string' ? item.kind : undefined,
      instrument_id: typeof item.instrument_id === 'number' && Number.isInteger(item.instrument_id) ? item.instrument_id : undefined,
    }))
}
function eventKinds(artifact: ResearchRunSummary['artifacts'][number]): string[] {
  return [...new Set(eventRows(artifact).map(event => event.kind).filter((kind): kind is string => Boolean(kind)))].sort()
}
function filteredEventRows(artifact: ResearchRunSummary['artifacts'][number]): EventRow[] {
  const symbol = occurrenceSymbolFilter.value.trim().toUpperCase()
  const kind = occurrenceKindFilter.value
  return eventRows(artifact).filter(event => (
    (!symbol || event.symbol.toUpperCase().includes(symbol))
    && (kind === 'all' || event.kind === kind)
  ))
}
function exportArtifact(run: ResearchRunSummary, artifact: ResearchRunSummary['artifacts'][number]) {
  const payload = JSON.stringify({ run_id: run.id, reproducibility_hash: run.reproducibility_hash ?? null, artifact }, null, 2)
  const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `study-run-${run.id}-${artifact.name.replace(/[^a-z0-9_-]+/gi, '-') || 'artifact'}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}
function toggleComparison(id: number) {
  comparisonIds.value = comparisonIds.value.includes(id) ? comparisonIds.value.filter(value => value !== id) : [...comparisonIds.value.slice(-1), id]
  if (comparisonIds.value.length < 2) comparisonOpen.value = false
}
function compact(value: unknown) { return JSON.stringify(value) }
function comparisonClass(key: keyof ResearchRunSummary) { return JSON.stringify(comparisonRuns.value[0][key]) === JSON.stringify(comparisonRuns.value[1][key]) ? 'research-results-tool__same' : 'research-results-tool__changed' }
function canCancel(run: ResearchRunSummary) { return !['completed', 'failed', 'canceled'].includes(run.status) }
function canPromoteBreadth(run: ResearchRunSummary) {
  return run.status === 'completed'
    && run.run_config?.execution_mode === 'breadth_history'
    && run.artifacts.some(artifact => artifact.artifact_type === 'breadth_history')
}
function canPromoteBreadthBoolean(run: ResearchRunSummary) {
  const target = run.run_config?.series_target
  return canPromoteBreadth(run)
    && (run.run_config?.output_contract === 'boolean'
      || (run.run_config?.output_contract === 'series' && (!target || typeof target !== 'object' || String((target as Record<string, unknown>).scope ?? 'member') === 'member')))
}
function canPromoteEventSignal(run: ResearchRunSummary) {
  return run.status === 'completed'
    && (!run.output_contract || run.output_contract === 'events')
    && run.artifacts.some(artifact => artifact.artifact_type === 'events')
}
function canPromoteEventFilter(run: ResearchRunSummary) {
  return run.status === 'completed'
    && run.output_contract === 'events'
    && run.artifacts.some(artifact => artifact.artifact_type === 'events')
}
function canPromoteStructuredEventArtifact(run: ResearchRunSummary | null, artifact: ResearchRunSummary['artifacts'][number]) {
  return Boolean(run)
    && run?.status === 'completed'
    && run.output_contract === 'study'
    && artifact.artifact_type === 'events'
}
function canPromoteStructuredArtifact(run: ResearchRunSummary | null, artifact: ResearchRunSummary['artifacts'][number]) {
  return Boolean(run)
    && run?.status === 'completed'
    && run.output_contract === 'study'
    && (artifact.artifact_type === 'scalar' || artifact.artifact_type === 'series' || artifact.artifact_type === 'boolean'
      || (artifact.artifact_type === 'range' && rangeData(artifact)?.center != null))
}
type StructuredBooleanPromotionTarget = 'column' | 'filter' | 'scan' | 'gauge' | 'alert'
const structuredBooleanPromotionTargets: StructuredBooleanPromotionTarget[] = ['column', 'filter', 'scan', 'gauge', 'alert']
function structuredBooleanPromotionLabel(target: StructuredBooleanPromotionTarget) {
  return target === 'column' ? 'Save column' : target === 'filter' ? 'Save filter' : target === 'scan' ? 'Promote scan' : target === 'gauge' ? 'Use Gauge' : 'Promote alert'
}
function structuredBooleanScanKey(run: ResearchRunSummary, artifact: ResearchRunSummary['artifacts'][number]) {
  return `${run.id}:${artifact.id}:${artifact.name}`
}
type StructuredSeriesConditionTarget = 'filter' | 'scan' | 'gauge' | 'alert'
const structuredSeriesConditionTargets: StructuredSeriesConditionTarget[] = ['filter', 'scan', 'gauge', 'alert']
function structuredSeriesConditionLabel(target: StructuredSeriesConditionTarget) {
  return target === 'filter' ? 'Save filter' : target === 'scan' ? 'Promote scan' : target === 'gauge' ? 'Use Gauge' : 'Promote alert'
}
function structuredSeriesScanKey(run: ResearchRunSummary, artifact: ResearchRunSummary['artifacts'][number]) {
  return `${run.id}:${artifact.id}:${artifact.name}:${seriesConditionOperator.value}:${seriesConditionThreshold.value}`
}
function declaredStudyInstrumentIds(run: ResearchRunSummary) {
  const manifest = run.dataset_manifest ?? {}
  const datasets = Array.isArray(manifest.datasets) ? manifest.datasets : []
  return [...new Set([
    ...(typeof manifest.instrument_id === 'number' ? [manifest.instrument_id] : []),
    ...datasets
      .filter(item => item && typeof item === 'object')
      .map(item => (item as Record<string, unknown>).instrument_id)
      .filter((item): item is number => typeof item === 'number' && Number.isInteger(item) && item > 0),
  ])]
}
function structuredStudyTimeframe(run: ResearchRunSummary) {
  const configured = run.run_config?.timeframe ?? run.dataset_manifest?.timeframe
  return typeof configured === 'string' && configured.trim() ? configured : 'D1'
}
function structuredStudySourceId(run: ResearchRunSummary) {
  const configured = run.run_config?.universe_source_id
  if (typeof configured === 'string' && configured.trim()) return configured
  const manifest = run.dataset_manifest?.universe_source_id
  return typeof manifest === 'string' && manifest.trim() ? manifest : null
}
function structuredStudyMembershipVersion(run: ResearchRunSummary) {
  const membership = run.dataset_manifest?.universe_membership_version
  return typeof membership === 'string' && membership.trim() ? membership : null
}
function canPromoteBreadthStudy(run: ResearchRunSummary) {
  return run.status === 'completed'
    && run.run_config?.execution_mode === 'breadth_history'
    && run.artifacts.some(artifact => artifact.artifact_type === 'breadth_history')
}
function canPromoteBreadthPlot(run: ResearchRunSummary) {
  const target = run.run_config?.series_target
  return run.status === 'completed'
    && run.run_config?.execution_mode?.toString().startsWith('breadth_')
    && run.run_config?.output_contract === 'series'
    && (!target || typeof target !== 'object' || String((target as Record<string, unknown>).scope ?? 'member') === 'member')
    && !run.run_config?.condition_tree
}
function canPromoteBreadthAggregatePlot(run: ResearchRunSummary) {
  const target = run.run_config?.series_target
  const crossSectional = Boolean(target && typeof target === 'object' && String((target as Record<string, unknown>).scope ?? 'member') === 'cross_sectional')
  return run.status === 'completed'
    && run.run_config?.execution_mode === 'breadth_history'
    && run.artifacts.some(artifact => artifact.artifact_type === 'breadth_history')
    && (crossSectional || Boolean(run.run_config?.condition_tree))
}
function canPromoteBreadthColumn(run: ResearchRunSummary) {
  return canPromoteBreadthPlot(run)
}

async function refresh() {
  error.value = ''
  try { await runsQuery.refetch() }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load persisted research runs' }
}
async function retryDetail() {
  detailRetrying.value = true
  try { await selectedRunDetailQuery.refetch() }
  finally { detailRetrying.value = false }
}
async function rerun(run: ResearchRunSummary, snapshot: boolean) {
  rerunning.value = true
  error.value = ''
  try {
    const queued = await api.post<ResearchRunSummary>(`/research/runs/${run.id}/rerun?snapshot=${snapshot}`, {})
    const nextRuns = [queued, ...runs.value.filter(item => item.id !== queued.id)]
    queryClient.setQueryData<ResearchRunSummary[]>(runsQueryKey, nextRuns)
    runs.value = nextRuns
    selectedRun.value = queued
    await runsQuery.refetch()
    queryClient.setQueryData<ResearchRunSummary[]>(runsQueryKey, current => [queued, ...(current ?? []).filter(item => item.id !== queued.id)])
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to queue study rerun'
  } finally {
    rerunning.value = false
  }
}
async function cancel(run: ResearchRunSummary) {
  canceling.value = true
  error.value = ''
  try {
    const canceled = await api.post<ResearchRunSummary>(`/research/runs/${run.id}/cancel`, {})
    const nextRuns = runs.value.map(item => item.id === run.id ? { ...item, ...canceled, status: canceled.status ?? 'canceled' } : item)
    queryClient.setQueryData<ResearchRunSummary[]>(runsQueryKey, nextRuns)
    runs.value = nextRuns
    if (selectedRun.value?.id === run.id) selectedRun.value = runs.value.find(item => item.id === run.id) ?? null
    await runsQuery.refetch()
    queryClient.setQueryData<ResearchRunSummary[]>(runsQueryKey, current => (current ?? []).map(item => item.id === run.id ? { ...item, ...canceled, status: canceled.status ?? 'canceled' } : item))
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to cancel research run'
  } finally {
    canceling.value = false
  }
}
async function promoteScan(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await ensurePromotedScan(run)
    promotionMessage.value = `EasyScan “${promoted.name}” (#${promoted.id}) created. It re-evaluates current data over the source member IDs; the historical run lineage remains attached.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to EasyScan'
  } finally {
    promoting.value = false
  }
}

async function ensurePromotedScan(run: ResearchRunSummary) {
  const existing = promotedScans.value[run.id]
  if (existing) return existing
  const promoted = await api.post<{ id: number; name: string; conditions?: { code_version_id?: number } }>(`/analysis/breadth/python/runs/${run.id}/promote-scan`, {})
  const result = {
    id: promoted.id,
    name: promoted.name,
    codeVersionId: typeof promoted.conditions?.code_version_id === 'number' ? promoted.conditions.code_version_id : null,
  }
  promotedScans.value = { ...promotedScans.value, [run.id]: result }
  return result
}

async function promoteAlert(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const scan = await ensurePromotedScan(run)
    await api.post('/alerts/screener', { screener_id: scan.id, trigger_type: 'entered', repeat: true, notes: `Created from Python breadth run ${run.id}` })
    promotionMessage.value = `Alert created from EasyScan “${scan.name}”.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to an alert'
  } finally {
    promoting.value = false
  }
}

async function promoteGauge(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const scan = await ensurePromotedScan(run)
    promotionMessage.value = `Available as a Market Gauge from EasyScan “${scan.name}”.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to a Market Gauge'
  } finally {
    promoting.value = false
  }
}

async function promoteSignal(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const scan = await ensurePromotedScan(run)
    if (scan.codeVersionId == null) throw new Error('The promoted EasyScan did not return its immutable Boolean code version.')
    await api.post(`/strategy-lab/signals/from-code/${scan.codeVersionId}`, {})
    promotionMessage.value = 'Saved as a reusable Strategy Lab signal.'
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to a Strategy signal'
  } finally {
    promoting.value = false
  }
}
async function promoteEventSignal(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await api.post<{ id: number; name: string }>(`/research/runs/${run.id}/promote-event-signal`, {})
    promotionMessage.value = `Saved event artifact as Strategy signal “${promoted.name}” (#${promoted.id}). Current-data re-evaluation and source lineage are preserved.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the event artifact to a Strategy signal'
  } finally {
    promoting.value = false
  }
}
async function ensurePromotedEventFilter(run: ResearchRunSummary) {
  const existing = promotedEventFilters.value[run.id]
  if (existing) return existing
  const promoted = await api.post<{ id: number; name: string }>(`/research/runs/${run.id}/promote-event-filter`, {})
  const result = { id: promoted.id, name: promoted.name }
  promotedEventFilters.value = { ...promotedEventFilters.value, [run.id]: result }
  return result
}
async function promoteEventFilter(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await ensurePromotedEventFilter(run)
    promotionMessage.value = `Watchlist filter “${promoted.name}” (#${promoted.id}) created. It checks event presence at the current observation over the declared canonical members; source lineage is preserved.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the event artifact to a watchlist filter'
  } finally {
    promoting.value = false
  }
}
async function promoteEventAlert(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await ensurePromotedEventFilter(run)
    await api.post('/alerts/screener', { screener_id: promoted.id, trigger_type: 'both', repeat: true, notes: `Created from event research run ${run.id}` })
    promotionMessage.value = `Alert created from event filter “${promoted.name}”; current-observation event semantics and source lineage are preserved.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the event artifact to an alert'
  } finally {
    promoting.value = false
  }
}
async function promoteEventArtifact(run: ResearchRunSummary, artifactName: string, target: 'filter' | 'alert' | 'signal') {
  promoting.value = true
  promotionMessage.value = ''
  try {
    if (target === 'signal') {
      const assets = await api.get<Array<{ versions?: Array<{ id?: number; source?: string; output_contract?: string; parameter_schema?: Record<string, unknown>; default_parameters?: Record<string, unknown> }> }>>('/code/assets')
      const sourceVersion = (assets ?? []).flatMap(asset => asset.versions ?? []).find(version => version.id === run.code_version_id)
      if (!sourceVersion?.source) throw new Error('The immutable source code version for this research run is unavailable.')
      const sourceManifest = run.dataset_manifest ?? {}
      const sourceRunConfig = run.run_config ?? {}
      const lineage = {
        type: 'study_run_promotion',
        source_run_id: run.id,
        source_code_version_id: run.code_version_id,
        source_reproducibility_hash: run.reproducibility_hash ?? null,
        source_dataset_manifest: sourceManifest,
        source_run_config: sourceRunConfig,
        source_output_name: artifactName,
        target: 'signal',
        output_adapter: 'events_to_signal',
        semantics: 'study_event_result_as_strategy_signal',
        point_in_time_source_preserved: false,
      }
      const asset = await api.post<{ id?: number; name?: string; versions?: Array<{ id?: number }> }>('/code/assets', {
        stable_key: `${run.id}-${artifactName}-signal-${Date.now().toString(36)}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `study-${run.id}-signal`,
        name: `${artifactName} signal`,
        kind: 'signal',
        initial_version: {
          source: sourceVersion.source,
          output_contract: 'events',
          output_name: artifactName,
          parameter_schema: sourceVersion.parameter_schema ?? {},
          default_parameters: sourceVersion.default_parameters ?? {},
          lineage,
        },
      })
      const codeVersionId = asset.versions?.[0]?.id ?? asset.id
      if (typeof codeVersionId !== 'number') throw new Error('The event signal asset did not return an immutable code version.')
      const promoted = await api.post<{ id: number; name: string }>(`/strategy-lab/signals/from-code/${codeVersionId}`, {})
      promotionMessage.value = `Saved event artifact “${artifactName}” as Strategy signal “${promoted.name}” (#${promoted.id}). Current-data re-evaluation and source lineage are preserved.`
      return
    }
    const promoted = await api.post<{ id: number; name: string }>(`/research/runs/${run.id}/promote-event-filter`, { artifact_name: artifactName })
    if (target === 'alert') {
      await api.post('/alerts/screener', { screener_id: promoted.id, trigger_type: 'both', repeat: true, notes: `Created from structured event research run ${run.id}` })
      promotionMessage.value = `Promoted event artifact “${artifactName}” to an active alert.`
    } else {
      promotionMessage.value = `Saved event artifact “${artifactName}” as a reusable watchlist filter.`
    }
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? `Unable to promote the structured event artifact to a ${target}`
  } finally {
    promoting.value = false
  }
}
async function promoteStructuredArtifact(run: ResearchRunSummary, artifact: ResearchRunSummary['artifacts'][number], target: 'column' | 'plot' | StructuredBooleanPromotionTarget) {
  if (!canPromoteStructuredArtifact(run, artifact) || promoting.value) return
  promoting.value = true
  promotionMessage.value = ''
  try {
    if (artifact.artifact_type === 'boolean' && target !== 'column' && target !== 'plot') {
      const scanKey = structuredBooleanScanKey(run, artifact)
      let promotedScan = promotedStructuredBooleanScans.value[scanKey]
      if (!promotedScan) {
        const declaredInstrumentIds = declaredStudyInstrumentIds(run)
        if (!declaredInstrumentIds.length) throw new Error('The study dataset has no declared canonical members; refusing to widen the promoted scan universe.')
        const assets = await api.get<Array<{ versions?: Array<{ id?: number; source?: string; output_contract?: string; output_name?: string | null; parameter_schema?: Record<string, unknown>; default_parameters?: Record<string, unknown> }> }>>('/code/assets')
        const sourceVersion = (assets ?? []).flatMap(asset => asset.versions ?? []).find(version => version.id === run.code_version_id)
        if (!sourceVersion?.source) throw new Error('The immutable source code version for this research run is unavailable.')
        const sourceManifest = run.dataset_manifest ?? {}
        const sourceRunConfig = run.run_config ?? {}
        const lineage = {
          type: 'study_run_promotion',
          source_run_id: run.id,
          source_code_version_id: run.code_version_id,
          source_reproducibility_hash: run.reproducibility_hash ?? null,
          source_dataset_manifest: sourceManifest,
          source_run_config: sourceRunConfig,
          source_output_name: artifact.name,
          target,
          semantics: 'current_data_re_evaluation_over_declared_study_members',
          source_universe_source_id: structuredStudySourceId(run),
          source_membership_version: structuredStudyMembershipVersion(run),
          source_instrument_ids: declaredInstrumentIds,
          point_in_time_source_preserved: false,
        }
        const condition = await api.post<{ id?: number; name?: string; versions?: Array<{ id?: number }> }>('/code/assets', {
          stable_key: `${run.id}-${artifact.name}-condition-${Date.now().toString(36)}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `study-${run.id}-condition`,
          name: `${artifact.name} condition`,
          kind: 'condition',
          initial_version: {
            source: sourceVersion.source,
            output_contract: 'boolean',
            output_name: artifact.name,
            parameter_schema: sourceVersion.parameter_schema ?? {},
            default_parameters: sourceVersion.default_parameters ?? {},
            lineage,
          },
        })
        const codeVersionId = condition.versions?.[0]?.id ?? condition.id
        if (typeof codeVersionId !== 'number') throw new Error('Boolean promotion did not return an immutable code version.')
        const screener = await api.post<{ id: number; name?: string }>(`/screeners/from-python-condition/${codeVersionId}`, {
          name: `${artifact.name} ${target === 'scan' ? 'Scan' : 'Filter'} ${run.id}`,
          description: `Current-data EasyScan promoted from structured Study run #${run.id}; source membership and snapshot lineage are retained in the condition provenance.`,
          universe_type: 'custom',
          universe_instrument_ids: declaredInstrumentIds,
          timeframe: structuredStudyTimeframe(run),
          provenance: lineage,
        })
        promotedScan = { id: screener.id, name: screener.name ?? `${artifact.name} scan`, codeVersionId }
        promotedStructuredBooleanScans.value = { ...promotedStructuredBooleanScans.value, [scanKey]: promotedScan }
      }
      if (target === 'filter') promotionMessage.value = `Saved Boolean artifact “${artifact.name}” as a reusable watchlist filter through EasyScan.`
      else if (target === 'scan') promotionMessage.value = `Promoted Boolean artifact “${artifact.name}” to a reusable scan.`
      else if (target === 'gauge') promotionMessage.value = `Boolean artifact “${artifact.name}” is available as a Market Gauge from the saved EasyScan.`
      else {
        await api.post('/alerts/screener', { screener_id: promotedScan.id, trigger_type: 'entered', repeat: true, notes: `Created from structured Boolean research run ${run.id} (${artifact.name})` })
        promotionMessage.value = `Promoted Boolean artifact “${artifact.name}” to an active scan alert.`
      }
      return
    }
    const assets = await api.get<Array<{ name: string; versions?: Array<{ id?: number; source?: string; output_contract?: string; output_name?: string | null; parameter_schema?: Record<string, unknown>; default_parameters?: Record<string, unknown> }> }>>('/code/assets')
    const sourceVersion = (assets ?? []).flatMap(asset => asset.versions ?? []).find(version => version.id === run.code_version_id)
    if (!sourceVersion?.source) throw new Error('The immutable source code version for this research run is unavailable.')
    const latestSeriesColumn = artifact.artifact_type === 'series' && target === 'column'
    const rangeCenterColumn = artifact.artifact_type === 'range' && target === 'column' && rangeData(artifact)?.center?.some(value => Number.isFinite(value)) === true
    const contract = artifact.artifact_type === 'scalar' ? 'scalar' : artifact.artifact_type === 'boolean' ? 'boolean' : latestSeriesColumn || rangeCenterColumn ? 'scalar' : 'series'
    const kind = target === 'column' ? 'column' : 'plot'
    const outputAdapter = artifact.artifact_type === 'range'
      ? rangeCenterColumn ? 'range_center_to_scalar' : 'range_center_to_series'
      : latestSeriesColumn ? 'latest_series_to_scalar' : undefined
    const lineage = {
      type: 'study_run_promotion',
      source_run_id: run.id,
      source_code_version_id: run.code_version_id,
      source_reproducibility_hash: run.reproducibility_hash ?? null,
      source_dataset_manifest: run.dataset_manifest,
      source_run_config: run.run_config,
      source_output_name: artifact.name,
      target,
      output_adapter: outputAdapter,
      semantics: target === 'column'
        ? artifact.artifact_type === 'boolean'
          ? 'study_boolean_result_as_typed_watchlist_column'
          : latestSeriesColumn ? 'study_series_latest_result_as_watchlist_column'
            : rangeCenterColumn ? 'study_range_center_result_as_latest_watchlist_column'
              : 'study_scalar_result_as_watchlist_column'
        : artifact.artifact_type === 'range'
          ? 'study_range_center_result_as_chart_plot'
          : 'study_series_result_as_chart_plot',
    }
    const promoted = await api.post<{ id: number; name: string }>('/code/assets', {
      stable_key: `${run.id}-${artifact.name}-${kind}-${Date.now().toString(36)}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `study-${kind}`,
      name: `${artifact.name} ${target === 'column' ? 'column' : 'plot'}`,
      kind,
      initial_version: {
        source: sourceVersion.source,
        output_contract: contract,
        output_name: artifact.name,
        parameter_schema: sourceVersion.parameter_schema ?? {},
        default_parameters: sourceVersion.default_parameters ?? {},
        lineage,
      },
    })
    promotionMessage.value = target === 'column'
      ? artifact.artifact_type === 'boolean'
        ? `Saved Boolean artifact “${artifact.name}” as watchlist column “${promoted.name}”.`
        : latestSeriesColumn
          ? `Saved series artifact “${artifact.name}” as watchlist column “${promoted.name}”.`
          : rangeCenterColumn
            ? `Saved range center “${artifact.name}” as watchlist column “${promoted.name}”.`
            : `Saved scalar artifact “${artifact.name}” as watchlist column “${promoted.name}”.`
      : artifact.artifact_type === 'range' && !rangeCenterColumn
        ? `Saved range center “${artifact.name}” as chart plot “${promoted.name}”.`
        : rangeCenterColumn
          ? `Saved range center “${artifact.name}” as watchlist column “${promoted.name}”.`
        : `Saved series artifact “${artifact.name}” as chart plot “${promoted.name}”.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? `Unable to promote the ${artifact.artifact_type} artifact`
  } finally {
    promoting.value = false
  }
}
async function promoteStructuredSeriesCondition(
  run: ResearchRunSummary,
  artifact: ResearchRunSummary['artifacts'][number],
  target: 'column' | StructuredSeriesConditionTarget,
) {
  if (artifact.artifact_type !== 'series' || !hasFiniteSeriesValue(artifact) || promoting.value) return
  if (!Number.isFinite(seriesConditionThreshold.value)) {
    promotionMessage.value = 'Enter a finite numeric threshold before promoting the series.'
    return
  }
  promoting.value = true
  promotionMessage.value = ''
  try {
    const assets = await api.get<Array<{ versions?: Array<{ id?: number; source?: string; output_contract?: string; parameter_schema?: Record<string, unknown>; default_parameters?: Record<string, unknown> }> }>>('/code/assets')
    const sourceVersion = (assets ?? []).flatMap(asset => asset.versions ?? []).find(version => version.id === run.code_version_id)
    if (!sourceVersion?.source) throw new Error('The immutable source code version for this series study is unavailable.')
    const declaredInstrumentIds = declaredStudyInstrumentIds(run)
    if (!declaredInstrumentIds.length) throw new Error('The study dataset has no declared canonical members; refusing to widen the promoted condition universe.')
    const seriesTarget = { operator: seriesConditionOperator.value, threshold: Number(seriesConditionThreshold.value) }
    const sourceRunConfig = run.run_config ?? {}
    const sourceManifest = run.dataset_manifest ?? {}
    const scanKey = structuredSeriesScanKey(run, artifact)
    let scan = promotedStructuredSeriesScans.value[scanKey]
    const lineage = {
      type: 'study_run_promotion',
      source_run_id: run.id,
      source_code_version_id: run.code_version_id,
      source_reproducibility_hash: run.reproducibility_hash ?? null,
      source_dataset_manifest: sourceManifest,
      source_run_config: sourceRunConfig,
      source_output_name: artifact.name,
      source_instrument_ids: declaredInstrumentIds,
      source_universe_source_id: structuredStudySourceId(run),
      source_membership_version: structuredStudyMembershipVersion(run),
      target,
      output_adapter: 'series_target_to_boolean',
      series_target: seriesTarget,
      semantics: 'study_series_threshold_as_boolean',
      point_in_time_source_preserved: false,
    }
    const kind = target === 'column' ? 'column' : 'condition'
    let codeVersionId = scan?.codeVersionId
    if (!codeVersionId) {
      const promoted = await api.post<{ id?: number; name?: string; versions?: Array<{ id?: number }> }>('/code/assets', {
        stable_key: `${run.id}-${artifact.name}-series-${kind}-${seriesConditionOperator.value}-${seriesConditionThreshold.value}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `study-series-${kind}`,
        name: `${artifact.name} ${target === 'column' ? 'Boolean column' : 'condition'}`,
        kind,
        initial_version: {
          source: sourceVersion.source,
          output_contract: 'boolean',
          output_name: artifact.name,
          parameter_schema: sourceVersion.parameter_schema ?? {},
          default_parameters: sourceVersion.default_parameters ?? {},
          lineage,
        },
      })
      const returnedCodeVersionId = promoted.versions?.[0]?.id ?? promoted.id
      if (typeof returnedCodeVersionId === 'number') codeVersionId = returnedCodeVersionId
    }
    if (typeof codeVersionId !== 'number') throw new Error('Series condition promotion did not return an immutable code version.')
    if (target === 'column') {
      promotionMessage.value = `Saved series artifact “${artifact.name}” as a thresholded Boolean column.`
      return
    }
    if (!scan) {
      const screener = await api.post<{ id: number; name?: string }>(`/screeners/from-python-condition/${codeVersionId}`, {
        name: `${artifact.name} ${seriesConditionOperator.value} ${seriesConditionThreshold.value} ${target === 'scan' ? 'Scan' : 'Filter'} ${run.id}`,
        description: `Current-data thresholded Boolean target promoted from structured Study run #${run.id}; source series, threshold, membership, and dataset lineage are retained.`,
        universe_type: 'custom',
        universe_instrument_ids: declaredInstrumentIds,
        timeframe: structuredStudyTimeframe(run),
        provenance: lineage,
      })
      scan = { id: screener.id, name: screener.name ?? `${artifact.name} threshold condition`, codeVersionId }
      promotedStructuredSeriesScans.value = { ...promotedStructuredSeriesScans.value, [scanKey]: scan }
    }
    if (target === 'filter') promotionMessage.value = `Saved series artifact “${artifact.name}” as a thresholded watchlist filter.`
    else if (target === 'scan') promotionMessage.value = `Promoted series artifact “${artifact.name}” to a thresholded scan.`
    else if (target === 'gauge') promotionMessage.value = `Series artifact “${artifact.name}” is available as a thresholded Market Gauge.`
    else {
      await api.post('/alerts/screener', { screener_id: scan.id, trigger_type: 'entered', repeat: true, notes: `Created from structured series study run ${run.id} (${artifact.name})` })
      promotionMessage.value = `Promoted series artifact “${artifact.name}” to a thresholded scan alert.`
    }
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? `Unable to promote the ${artifact.artifact_type} artifact to a thresholded condition`
  } finally {
    promoting.value = false
  }
}
async function promoteStructuredRangeCenterCondition(
  run: ResearchRunSummary,
  artifact: ResearchRunSummary['artifacts'][number],
  target: 'column' | StructuredSeriesConditionTarget,
) {
  if (artifact.artifact_type !== 'range' || !hasFiniteRangeCenterValue(artifact) || promoting.value) return
  if (!Number.isFinite(seriesConditionThreshold.value)) {
    promotionMessage.value = 'Enter a finite numeric threshold before promoting the range center.'
    return
  }
  promoting.value = true
  promotionMessage.value = ''
  try {
    const assets = await api.get<Array<{ versions?: Array<{ id?: number; source?: string; output_contract?: string; parameter_schema?: Record<string, unknown>; default_parameters?: Record<string, unknown> }> }>>('/code/assets')
    const sourceVersion = (assets ?? []).flatMap(asset => asset.versions ?? []).find(version => version.id === run.code_version_id)
    if (!sourceVersion?.source) throw new Error('The immutable source code version for this range study is unavailable.')
    const declaredInstrumentIds = declaredStudyInstrumentIds(run)
    if (!declaredInstrumentIds.length) throw new Error('The study dataset has no declared canonical members; refusing to widen the promoted condition universe.')
    const rangeTarget = { operator: seriesConditionOperator.value, threshold: Number(seriesConditionThreshold.value) }
    const sourceRunConfig = run.run_config ?? {}
    const sourceManifest = run.dataset_manifest ?? {}
    const scanKey = `${run.id}:${artifact.id}:${artifact.name}:range_center_target_to_boolean:${seriesConditionOperator.value}:${seriesConditionThreshold.value}`
    let scan = promotedStructuredRangeCenterScans.value[scanKey]
    const lineage = {
      type: 'study_run_promotion',
      source_run_id: run.id,
      source_code_version_id: run.code_version_id,
      source_reproducibility_hash: run.reproducibility_hash ?? null,
      source_dataset_manifest: sourceManifest,
      source_run_config: sourceRunConfig,
      source_output_name: artifact.name,
      source_instrument_ids: declaredInstrumentIds,
      source_universe_source_id: structuredStudySourceId(run),
      source_membership_version: structuredStudyMembershipVersion(run),
      target,
      output_adapter: 'range_center_target_to_boolean',
      series_target: rangeTarget,
      semantics: 'study_range_center_threshold_as_boolean',
      point_in_time_source_preserved: false,
    }
    const kind = target === 'column' ? 'column' : 'condition'
    let codeVersionId = scan?.codeVersionId
    if (!codeVersionId) {
      const promoted = await api.post<{ id?: number; name?: string; versions?: Array<{ id?: number }> }>('/code/assets', {
        stable_key: `${run.id}-${artifact.name}-range-center-${kind}-${seriesConditionOperator.value}-${seriesConditionThreshold.value}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `study-range-center-${kind}`,
        name: `${artifact.name} ${target === 'column' ? 'Boolean column' : 'condition'}`,
        kind,
        initial_version: {
          source: sourceVersion.source,
          output_contract: 'boolean',
          output_name: artifact.name,
          parameter_schema: sourceVersion.parameter_schema ?? {},
          default_parameters: sourceVersion.default_parameters ?? {},
          lineage,
        },
      })
      const returnedCodeVersionId = promoted.versions?.[0]?.id ?? promoted.id
      if (typeof returnedCodeVersionId === 'number') codeVersionId = returnedCodeVersionId
    }
    if (typeof codeVersionId !== 'number') throw new Error('Range center condition promotion did not return an immutable code version.')
    if (target === 'column') {
      promotionMessage.value = `Saved range center “${artifact.name}” as a thresholded Boolean column.`
      return
    }
    if (!scan) {
      const screener = await api.post<{ id: number; name?: string }>(`/screeners/from-python-condition/${codeVersionId}`, {
        name: `${artifact.name} ${seriesConditionOperator.value} ${seriesConditionThreshold.value} ${target === 'scan' ? 'Scan' : 'Filter'} ${run.id}`,
        description: `Current-data thresholded Boolean target promoted from structured Study run #${run.id}; range center, threshold, membership, and dataset lineage are retained.`,
        universe_type: 'custom',
        universe_instrument_ids: declaredInstrumentIds,
        timeframe: structuredStudyTimeframe(run),
        provenance: lineage,
      })
      scan = { id: screener.id, name: screener.name ?? `${artifact.name} range center condition`, codeVersionId }
      promotedStructuredRangeCenterScans.value = { ...promotedStructuredRangeCenterScans.value, [scanKey]: scan }
    }
    if (target === 'filter') promotionMessage.value = `Saved range center “${artifact.name}” as a thresholded watchlist filter.`
    else if (target === 'scan') promotionMessage.value = `Promoted range center “${artifact.name}” to a thresholded scan.`
    else if (target === 'gauge') promotionMessage.value = `Range center “${artifact.name}” is available as a thresholded Market Gauge.`
    else {
      await api.post('/alerts/screener', { screener_id: scan.id, trigger_type: 'entered', repeat: true, notes: `Created from structured range center study run ${run.id} (${artifact.name})` })
      promotionMessage.value = `Promoted range center “${artifact.name}” to a thresholded scan alert.`
    }
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the range center artifact to a thresholded condition'
  } finally {
    promoting.value = false
  }
}
async function promoteStudy(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await api.post<{ id: number; name: string }>(`/analysis/breadth/python/runs/${run.id}/promote-study`, {})
    promotionMessage.value = `Study Lab study “${promoted.name}” (#${promoted.id}) created. It preserves the breadth universe, target scope, condition, and historical dataset lineage.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to a Study Lab study'
  } finally {
    promoting.value = false
  }
}
async function promotePlot(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await api.post<{ id: number; name: string }>(`/analysis/breadth/python/runs/${run.id}/promote-plot`, {})
    promotionMessage.value = `Chart plot “${promoted.name}” (#${promoted.id}) created. It re-evaluates the member series on the selected symbol; the breadth run lineage remains attached.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to a chart plot'
  } finally {
    promoting.value = false
  }
}
async function promoteAggregatePlot(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await api.post<{ id: number; name: string }>(`/analysis/breadth/python/runs/${run.id}/promote-plot`, { aggregate: true })
    promotionMessage.value = `Aggregate chart plot “${promoted.name}” (#${promoted.id}) created. It re-evaluates the breadth percentage history; source tree, universe, and dataset lineage remain attached.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to an aggregate chart plot'
  } finally {
    promoting.value = false
  }
}
async function promoteColumn(run: ResearchRunSummary) {
  promoting.value = true
  promotionMessage.value = ''
  try {
    const promoted = await api.post<{ id: number; name: string }>(`/analysis/breadth/python/runs/${run.id}/promote-column`, {})
    promotionMessage.value = `Watchlist column “${promoted.name}” (#${promoted.id}) created. It re-evaluates the latest member-series value; the breadth run lineage remains attached.`
  } catch (cause: any) {
    promotionMessage.value = cause?.message ?? 'Unable to promote the breadth run to a watchlist column'
  } finally {
    promoting.value = false
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', updateDocumentVisibility)
  if (typeof IntersectionObserver !== 'undefined' && resultsRoot.value) {
    visibilityObserver = new IntersectionObserver(entries => {
      surfaceVisible.value = entries.some(entry => entry.isIntersecting && entry.intersectionRatio > 0)
    })
    visibilityObserver.observe(resultsRoot.value)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', updateDocumentVisibility)
  visibilityObserver?.disconnect()
  visibilityObserver = null
})
</script>

<style scoped>
.research-results-tool { display:grid; grid-template-rows:auto minmax(55px,.35fr) minmax(0,1fr); gap:6px; height:100%; min-height:0; padding:6px; color:#cbd5dc; background:#11161b; font:10px "Segoe UI",Arial,sans-serif; }.research-results-tool header { display:flex; align-items:center; gap:6px; }.research-results-tool header button { margin-left:auto; }.research-results-tool header button + button { margin-left:0; }.research-results-tool button { border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; cursor:pointer; }.research-results-tool button:disabled { opacity:.55; cursor:default; }.research-results-tool__runs { overflow:auto; display:grid; align-content:start; gap:3px; }.research-results-tool__run { display:grid; grid-template-columns:14px minmax(55px,1fr) auto auto; gap:5px; padding:5px; text-align:left; }.research-results-tool__run:hover,.research-results-tool__run--selected { background:#1d3543; border-color:#52748a; }.research-results-tool__run small,.research-results-tool__detail small,.research-results-tool__notice { color:#8195a3; }.research-results-tool__comparison { overflow:auto; border:1px solid #34424c; padding:5px; }.research-results-tool__comparison div { display:grid; grid-template-columns:70px 1fr; gap:5px; margin-top:3px; }.research-results-tool__comparison b { overflow-wrap:anywhere; font-weight:500; }.research-results-tool__same { color:#82c49b; }.research-results-tool__changed { color:#e7c274; }.research-results-tool__detail { border-top:1px solid #34424c; padding-top:5px; overflow:auto; }.research-results-tool__detail-header { display:flex; align-items:center; gap:4px; }.research-results-tool__detail-header button { padding:1px 4px; }.research-results-tool__detail-header button:first-of-type { margin-left:auto; }.research-results-tool__detail p { margin:4px 0; }.research-results-tool__artifacts { display:grid; gap:5px; }.research-results-tool__artifacts article { display:grid; gap:3px; border-top:1px solid #29343c; padding-top:4px; }.research-results-tool__artifact-header { display:flex; align-items:center; gap:4px; }.research-results-tool__artifact-header small { color:#8195a3; }.research-results-tool__artifact-header button { margin-left:auto; padding:1px 4px; }.research-results-tool__artifacts table { border-collapse:collapse; width:100%; }.research-results-tool__artifacts th,.research-results-tool__artifacts td { padding:2px 4px; border:1px solid #2c3943; text-align:left; }.research-results-tool__events { display:grid; gap:2px; }.research-results-tool__events button { display:grid; grid-template-columns:50px 1fr; padding:3px 4px; text-align:left; }.research-results-tool__events span { color:#91a8b4; }.research-results-tool__artifacts pre { margin:0; max-height:100px; overflow:auto; white-space:pre-wrap; }.research-results-tool__boolean--true { color:#80d5a5; }.research-results-tool__boolean--false { color:#f0a0a0; }.research-results-tool__error { color:#f0a2a2; }.research-results-tool__status--completed { color:#82c49b; }.research-results-tool__status--failed,.research-results-tool__status--canceled { color:#ed9696; }.research-results-tool__status--queued,.research-results-tool__status--running { color:#80bce8; }
.research-results-tool__run-details { margin:4px 0; border-top:1px solid #29343c; padding-top:3px; }.research-results-tool__run-details summary { color:#9db0bc; cursor:pointer; }.research-results-tool__run-details pre { margin:3px 0 0; max-height:90px; overflow:auto; white-space:pre-wrap; }
.research-results-tool__run-guidance { margin:3px 0; color:#91a8b4; line-height:1.35; }.research-results-tool__status--failed,.research-results-tool__status--canceled { color:#ed9696; }
.research-results-tool__events small { grid-column:2; color:#91a8b4; }.research-results-tool__breadth-history { display:grid; gap:3px; }.research-results-tool__breadth-history :deep(.generic-breadth-history) { height:150px; }
.research-results-tool__occurrence-filters { display:flex; align-items:center; flex-wrap:wrap; gap:5px; color:#91a8b4; }.research-results-tool__occurrence-filters label { display:flex; align-items:center; gap:3px; }.research-results-tool__occurrence-filters input,.research-results-tool__occurrence-filters select { min-width:80px; border:1px solid #3a4954; background:#121a20; color:#dce6ed; font:inherit; padding:2px 3px; }.research-results-tool__occurrence-filters span { margin-left:auto; }
.research-results-tool__event-promotions { display:flex; flex-wrap:wrap; gap:4px; }.research-results-tool__event-promotions button { padding:2px 4px; }
.research-results-tool__artifact-promotions { display:flex; flex-wrap:wrap; gap:4px; }.research-results-tool__artifact-promotions button { padding:2px 4px; }
.research-results-tool__series-condition { display:flex; align-items:center; flex-wrap:wrap; gap:4px; flex-basis:100%; color:#91a8b4; }.research-results-tool__series-condition label { display:flex; align-items:center; gap:3px; }.research-results-tool__series-condition select,.research-results-tool__series-condition input { min-width:52px; border:1px solid #3a4954; background:#121a20; color:#dce6ed; font:inherit; padding:2px 3px; }.research-results-tool__series-condition button { padding:2px 4px; }
</style>
