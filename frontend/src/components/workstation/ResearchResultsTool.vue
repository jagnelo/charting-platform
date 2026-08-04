<template>
  <section ref="resultsRoot" class="research-results-tool">
    <header>
      <strong>Persisted runs</strong>
      <button v-if="comparisonRuns.length === 2" type="button" @click="comparisonOpen = !comparisonOpen">{{ comparisonOpen ? 'Hide compare' : 'Compare' }}</button>
      <button type="button" :disabled="loading" @click="refresh">Refresh</button>
    </header>
    <p v-if="error" class="research-results-tool__error">{{ error }}</p>
    <p v-else-if="loading && !runs.length" class="research-results-tool__notice">Loading reproducible research runs…</p>
    <p v-else-if="!runs.length" class="research-results-tool__notice">No persisted studies yet. Run a study in the adjacent Study Lab pane.</p>
    <div v-else class="research-results-tool__runs" role="list">
      <button
        v-for="run in runs"
        :key="run.id"
        type="button"
        role="listitem"
        :class="{ 'research-results-tool__run--selected': selectedRun?.id === run.id }"
        class="research-results-tool__run"
        @click="selectedRun = run"
      >
        <input type="checkbox" :checked="comparisonIds.includes(run.id)" :aria-label="`Compare run ${run.id}`" @click.stop @change="toggleComparison(run.id)" />
        <strong>Run #{{ run.id }}</strong>
        <span :class="`research-results-tool__status--${run.status}`">{{ run.status }}</span>
        <small>{{ run.artifacts.length }} artifact{{ run.artifacts.length === 1 ? '' : 's' }}</small>
      </button>
    </div>
    <section v-if="comparisonOpen && comparisonRuns.length === 2" class="research-results-tool__comparison">
      <strong>Run {{ comparisonRuns[0].id }} vs {{ comparisonRuns[1].id }}</strong>
      <div><span>Code version</span><b :class="comparisonClass('code_version_id')">{{ comparisonRuns[0].code_version_id }} / {{ comparisonRuns[1].code_version_id }}</b></div>
      <div><span>Parameters</span><b :class="comparisonClass('run_config')">{{ compact(comparisonRuns[0].run_config) }} / {{ compact(comparisonRuns[1].run_config) }}</b></div>
      <div><span>Dataset</span><b :class="comparisonClass('dataset_manifest')">{{ compact(comparisonRuns[0].dataset_manifest) }} / {{ compact(comparisonRuns[1].dataset_manifest) }}</b></div>
      <div><span>Reproducibility</span><b :class="comparisonClass('reproducibility_hash')">{{ comparisonRuns[0].reproducibility_hash ?? '—' }} / {{ comparisonRuns[1].reproducibility_hash ?? '—' }}</b></div>
    </section>
    <article v-if="selectedRun" class="research-results-tool__detail">
      <div class="research-results-tool__detail-header"><strong>Run #{{ selectedRun.id }}</strong><button v-if="canCancel(selectedRun)" type="button" :disabled="canceling" @click="cancel(selectedRun)">Cancel</button><button type="button" :disabled="rerunning || canceling" @click="rerun(selectedRun, true)">Rerun snapshot</button><button type="button" :disabled="rerunning || canceling" @click="rerun(selectedRun, false)">Rerun latest</button></div>
      <small v-if="selectedRun.reproducibility_hash">{{ selectedRun.reproducibility_hash }}</small>
      <p v-if="selectedRun.diagnostics?.length">{{ selectedRun.diagnostics.join(' · ') }}</p>
      <div v-if="selectedRun.artifacts.length" class="research-results-tool__artifacts">
        <article v-for="artifact in selectedRun.artifacts" :key="artifact.id">
          <div class="research-results-tool__artifact-header"><strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small><button type="button" :title="`Export ${artifact.name}`" @click="exportArtifact(selectedRun!, artifact)">Export</button></div>
          <strong v-if="artifact.artifact_type === 'scalar' || artifact.artifact_type === 'boolean'" :class="{ 'research-results-tool__boolean--true': artifact.artifact_type === 'boolean' && artifact.payload.value === true, 'research-results-tool__boolean--false': artifact.artifact_type === 'boolean' && artifact.payload.value === false }">{{ formatMetric(artifact) }}</strong>
          <table v-else-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><thead><tr><th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
          <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
          <StudyBarsUPlot v-else-if="artifact.artifact_type === 'bar' && barData(artifact)" :name="artifact.name" :labels="barData(artifact)!.labels" :values="barData(artifact)!.values" />
          <StudyHistogramUPlot v-else-if="artifact.artifact_type === 'histogram' && histogramData(artifact)" :name="artifact.name" :bins="histogramData(artifact)!.bins" :current="histogramData(artifact)!.current" />
          <StudyRangeUPlot v-else-if="artifact.artifact_type === 'range' && rangeData(artifact)" :name="artifact.name" :timestamps="rangeData(artifact)!.timestamps" :lower="rangeData(artifact)!.lower" :upper="rangeData(artifact)!.upper" :center="rangeData(artifact)!.center" />
          <StudyScatterUPlot v-else-if="artifact.artifact_type === 'scatter' && scatterData(artifact)" :name="artifact.name" :x="scatterData(artifact)!.x" :y="scatterData(artifact)!.y" />
          <StudyHeatmap v-else-if="artifact.artifact_type === 'heatmap' && heatmapData(artifact)" :name="artifact.name" :rows="heatmapData(artifact)!.rows" :columns="heatmapData(artifact)!.columns" :values="heatmapData(artifact)!.values" />
          <StudyDashboard v-else-if="artifact.artifact_type === 'dashboard' && dashboardData(artifact)" :name="artifact.name" :panels="dashboardData(artifact)!" :artifacts="selectedRun.artifacts" @occurrence="emit('occurrence', $event)" />
          <div v-else-if="artifact.artifact_type === 'events'" class="research-results-tool__events"><button v-for="(event, index) in eventRows(artifact)" :key="`${event.symbol}-${event.timestamp}-${index}`" type="button" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.timestamp }}</span></button></div>
          <pre v-else>{{ artifactText(artifact.payload) }}</pre>
        </article>
      </div>
      <p v-else class="research-results-tool__notice">No structured artifacts have been produced yet.</p>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { api } from '@/lib/api'
import StudyBarsUPlot from './StudyBarsUPlot.vue'
import StudyHistogramUPlot from './StudyHistogramUPlot.vue'
import StudySeriesUPlot from './StudySeriesUPlot.vue'
import StudyScatterUPlot from './StudyScatterUPlot.vue'
import StudyHeatmap from './StudyHeatmap.vue'
import StudyDashboard from './StudyDashboard.vue'
import StudyRangeUPlot from './StudyRangeUPlot.vue'

interface ResearchRunSummary {
  id: number
  status: string
  code_version_id: number
  run_config: Record<string, unknown>
  dataset_manifest: Record<string, unknown>
  reproducibility_hash?: string | null
  diagnostics?: string[]
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
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string }] }>()
const comparisonRuns = computed(() => comparisonIds.value.map(id => runs.value.find(run => run.id === id)).filter((run): run is ResearchRunSummary => Boolean(run)))
const surfaceVisible = ref(true)
const documentVisible = ref(typeof document === 'undefined' || document.visibilityState !== 'hidden')
let visibilityObserver: IntersectionObserver | null = null
function updateDocumentVisibility() { documentVisible.value = document.visibilityState !== 'hidden' }
const runsQuery = useQuery({
  queryKey: ['workstation', 'research-runs'],
  queryFn: async () => (await api.get<ResearchRunSummary[]>('/research/runs', { limit: 25 })) ?? [],
  enabled: computed(() => surfaceVisible.value && documentVisible.value),
  staleTime: 5_000,
  refetchOnWindowFocus: true,
  refetchInterval: query => {
    const data = query.state.data
    return Array.isArray(data) && data.some(run => !['completed', 'failed', 'canceled'].includes(run.status)) ? 1_000 : false
  },
})
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

function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
function formatMetric(artifact: ResearchRunSummary['artifacts'][number]) { return artifact.artifact_type === 'boolean' ? artifact.payload.value === true ? 'True' : artifact.payload.value === false ? 'False' : '—' : artifact.payload.value ?? '—' }
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
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray((value as { panels?: unknown }).panels)) return null
  const panels = (value as { panels: unknown[] }).panels
  const normalized = panels.filter((panel): panel is { artifact: string; title: string; span: number } => Boolean(panel) && typeof panel === 'object' && typeof (panel as Record<string, unknown>).artifact === 'string' && typeof (panel as Record<string, unknown>).title === 'string' && typeof (panel as Record<string, unknown>).span === 'number')
  return normalized.length === panels.length ? normalized : null
}
function eventRows(artifact: ResearchRunSummary['artifacts'][number]): Array<{ symbol: string; timestamp: string; kind?: string }> {
  const value = artifact.payload.value
  return Array.isArray(value) ? value.filter((item): item is { symbol: string; timestamp: string; kind?: string } => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string') : []
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

async function refresh() {
  error.value = ''
  try { await runsQuery.refetch() }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to load persisted research runs' }
}
async function rerun(run: ResearchRunSummary, snapshot: boolean) {
  rerunning.value = true
  error.value = ''
  try {
    const queued = await api.post<ResearchRunSummary>(`/research/runs/${run.id}/rerun?snapshot=${snapshot}`, {})
    runs.value = [queued, ...runs.value.filter(item => item.id !== queued.id)]
    selectedRun.value = queued
    await runsQuery.refetch()
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
    runs.value = runs.value.map(item => item.id === run.id ? { ...item, ...canceled, status: canceled.status ?? 'canceled' } : item)
    if (selectedRun.value?.id === run.id) selectedRun.value = runs.value.find(item => item.id === run.id) ?? null
    await runsQuery.refetch()
  } catch (cause: any) {
    error.value = cause?.message ?? 'Unable to cancel research run'
  } finally {
    canceling.value = false
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
</style>
