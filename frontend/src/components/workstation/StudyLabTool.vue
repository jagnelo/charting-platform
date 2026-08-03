<template>
  <section class="study-lab-tool">
    <header class="study-lab-tool__header">
      <div class="study-lab-tool__header-main">
        <input v-model.trim="name" aria-label="Study name" placeholder="Study name" />
        <input v-model.trim="symbol" aria-label="Study symbol" placeholder="Symbol" />
        <button type="button" :disabled="busy" @click="validate">Validate</button>
        <button type="button" :disabled="busy || !validation?.valid" @click="saveAndRun">Run</button>
      </div>
      <div class="study-lab-tool__dataset" aria-label="Study dataset controls">
        <label>Timeframe <select v-model="timeframe" aria-label="Study timeframe"><option v-for="option in timeframeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <label>Benchmark <input v-model.trim="benchmark" aria-label="Study benchmark" placeholder="SPY" /></label>
        <label>Adjustment <select v-model="adjustment" aria-label="Study adjustment"><option value="split_adjusted">Split adjusted</option><option value="raw">Raw</option></select></label>
        <label>Session <select v-model="session" aria-label="Study session"><option value="regular">Regular</option><option value="all">All</option></select></label>
        <label>From <input v-model.trim="startDate" aria-label="Study start date" type="date" /></label>
        <label>To <input v-model.trim="endDate" aria-label="Study end date" type="date" /></label>
      </div>
    </header>
    <textarea v-model="source" aria-label="Study Python source" spellcheck="false" />
    <section v-if="validation" class="study-lab-tool__validation" :class="{ 'study-lab-tool__validation--bad': !validation.valid }">
      <strong>{{ validation.valid ? 'Validated for isolated execution' : 'Validation errors' }}</strong>
      <pre v-if="validation.diagnostics.length">{{ validation.diagnostics }}</pre>
      <span v-else>Dependencies: {{ validation.dependencies.join(', ') || 'none' }} · Lookback: {{ validation.lookback_hint ?? 'none' }} · Outputs: {{ validation.output_contracts.join(', ') || 'none' }}</span>
    </section>
    <section v-if="run" class="study-lab-tool__run">
      <div><strong>Run #{{ run.id }}</strong><span :class="`study-lab-tool__run-status--${run.status}`">{{ run.status }}</span><small v-if="progressLabel">{{ progressLabel }}</small><button v-if="canCancel" type="button" @click="cancel">Cancel</button></div>
      <p v-if="run.reproducibility_hash">Reproducibility {{ run.reproducibility_hash }}</p>
      <p class="study-lab-tool__dataset-summary">Dataset: {{ timeframe }} · {{ adjustment === 'split_adjusted' ? 'split adjusted' : 'raw' }} · {{ session }} session · benchmark {{ benchmark || 'none' }} ({{ benchmarkCoverageLabel }}) · {{ startDate || 'earliest available' }} → {{ endDate || 'latest available' }}</p>
      <pre v-if="run.diagnostics?.length">{{ run.diagnostics }}</pre>
      <div v-if="metricArtifacts.length" class="study-lab-tool__metrics"><article v-for="artifact in metricArtifacts" :key="artifact.id" :class="{ 'study-lab-tool__metric--true': artifact.artifact_type === 'boolean' && artifact.payload.value === true, 'study-lab-tool__metric--false': artifact.artifact_type === 'boolean' && artifact.payload.value === false }"><small>{{ artifact.name }}</small><strong>{{ formatMetric(artifact) }}</strong></article></div>
      <article v-for="artifact in nonScalarArtifacts" :key="artifact.id">
        <strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small>
        <table v-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><thead><tr><th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
        <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
        <StudyHistogramUPlot v-else-if="artifact.artifact_type === 'histogram' && histogramData(artifact)" :name="artifact.name" :bins="histogramData(artifact)!.bins" :current="histogramData(artifact)!.current" />
        <StudyScatterUPlot v-else-if="artifact.artifact_type === 'scatter' && scatterData(artifact)" :name="artifact.name" :x="scatterData(artifact)!.x" :y="scatterData(artifact)!.y" />
        <StudyHeatmap v-else-if="artifact.artifact_type === 'heatmap' && heatmapData(artifact)" :name="artifact.name" :rows="heatmapData(artifact)!.rows" :columns="heatmapData(artifact)!.columns" :values="heatmapData(artifact)!.values" />
        <StudyDashboard v-else-if="artifact.artifact_type === 'dashboard' && dashboardData(artifact)" :name="artifact.name" :panels="dashboardData(artifact)!" :artifacts="run?.artifacts ?? []" @occurrence="emit('occurrence', $event)" />
        <div v-else-if="artifact.artifact_type === 'events' && eventRows(artifact).length" class="study-lab-tool__events"><button v-for="(event, index) in eventRows(artifact)" :key="`${event.timestamp}-${index}`" type="button" @click="emit('occurrence', event)"><strong>{{ event.symbol }}</strong><span>{{ event.timestamp }}</span><small>{{ event.kind ?? 'Event' }}</small></button></div>
        <pre v-else>{{ artifactText(artifact.payload) }}</pre>
      </article>
    </section>
    <p v-if="error" class="study-lab-tool__error">{{ error }}</p>
    <p v-else class="study-lab-tool__notice">Canonical local data only · isolated no-network runner · results are versioned by code and dataset manifest.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '@/lib/api'
import StudyHistogramUPlot from './StudyHistogramUPlot.vue'
import StudyHeatmap from './StudyHeatmap.vue'
import StudyDashboard from './StudyDashboard.vue'
import StudyScatterUPlot from './StudyScatterUPlot.vue'
import StudySeriesUPlot from './StudySeriesUPlot.vue'

interface Validation { valid: boolean; diagnostics: unknown[]; dependencies: string[]; lookback_hint: number | null; output_contracts: string[] }
interface Run { id: number; status: string; progress?: { status?: string; completed_cells?: number; total_cells?: number }; diagnostics?: unknown[]; reproducibility_hash?: string | null; dataset_manifest?: { benchmark_coverage?: { status?: string; reason?: string } }; artifacts?: Array<{ id: number; name: string; artifact_type: string; payload: Record<string, unknown> }> }
type Artifact = NonNullable<Run['artifacts']>[number]

const props = defineProps<{ activeSymbol: string; configuration?: Record<string, unknown> }>()
const emit = defineEmits<{ occurrence: [event: { symbol: string; timestamp: string; kind?: string }]; configuration: [configuration: Record<string, unknown>] }>()
const name = ref('Consecutive Positive Closes')
const symbol = ref(props.activeSymbol)
const source = ref("streaks = stats.positive_close_streaks(dataset)\nindices = [record['end_index'] for record in streaks['records']]\noutput.scalar('current_streak', streaks['current'])\noutput.scalar('longest_streak', streaks['longest'])\noutput.scalar('average_streak', streaks['average'])\noutput.scalar('shortest_streak', streaks['shortest'])\noutput.table('completed_streaks', streaks['records'])\noutput.table('forward_returns', research.forward_returns(dataset, indices, [1, 5, 20]))\noutput.events('streak_events', research.occurrences(dataset, indices, 'positive_close_streak'))\noutput.histogram('streak_distribution', streaks['lengths'], 8, streaks['current'])")
const timeframeOptions = [
  { value: 'D1', label: 'Daily' },
  { value: 'W1', label: 'Weekly' },
  { value: 'MN', label: 'Monthly' },
  { value: 'M15', label: '15 minute' },
]
const configString = (key: string, fallback: string) => typeof props.configuration?.[key] === 'string' ? String(props.configuration[key]) : fallback
const normaliseTimeframe = (value: string) => value === 'MN1' ? 'MN' : timeframeOptions.some(option => option.value === value) ? value : 'D1'
const timeframe = ref(normaliseTimeframe(configString('timeframe', 'D1')))
const benchmark = ref(configString('benchmark', 'SPY'))
const adjustment = ref<'split_adjusted' | 'raw'>(configString('adjustment', 'split_adjusted') === 'raw' ? 'raw' : 'split_adjusted')
const session = ref<'regular' | 'all'>(configString('session', 'regular') === 'all' ? 'all' : 'regular')
const startDate = ref(configString('start_date', ''))
const endDate = ref(configString('end_date', ''))
const busy = ref(false)
const validation = ref<Validation | null>(null)
const run = ref<Run | null>(null)
const error = ref('')
let poller: ReturnType<typeof setInterval> | null = null

const canCancel = computed(() => Boolean(run.value && !['completed', 'failed', 'canceled'].includes(run.value.status)))
const progressLabel = computed(() => {
  const progress = run.value?.progress
  if (!progress || progress.status !== 'running') return ''
  const total = Number(progress.total_cells ?? 0)
  return total > 0 ? `running ${Number(progress.completed_cells ?? 0)}/${total}` : 'runner active'
})
const metricArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => ['scalar', 'boolean'].includes(artifact.artifact_type)))
const nonScalarArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => !['scalar', 'boolean'].includes(artifact.artifact_type)))
const benchmarkCoverageLabel = computed(() => {
  const status = run.value?.dataset_manifest?.benchmark_coverage?.status
  if (status === 'ready') return 'ready'
  if (status === 'unavailable') return `unavailable: ${run.value?.dataset_manifest?.benchmark_coverage?.reason ?? 'unknown'}`
  return 'pending'
})
watch(() => props.activeSymbol, value => { if (!symbol.value || symbol.value === 'SPY') symbol.value = value })
watch(() => props.configuration, configuration => {
  if (typeof configuration?.timeframe === 'string') timeframe.value = normaliseTimeframe(configuration.timeframe)
  if (configuration && !('benchmark' in configuration)) benchmark.value = ''
  else if (typeof configuration?.benchmark === 'string') benchmark.value = configuration.benchmark
  if (configuration?.adjustment === 'raw' || configuration?.adjustment === 'split_adjusted') adjustment.value = configuration.adjustment
  if (configuration?.session === 'all' || configuration?.session === 'regular') session.value = configuration.session
  if (configuration && !('start_date' in configuration)) startDate.value = ''
  else if (typeof configuration?.start_date === 'string') startDate.value = configuration.start_date
  if (configuration && !('end_date' in configuration)) endDate.value = ''
  else if (typeof configuration?.end_date === 'string') endDate.value = configuration.end_date
}, { deep: true })
watch([timeframe, benchmark, adjustment, session, startDate, endDate], () => {
  const configuration: Record<string, unknown> = { ...(props.configuration ?? {}), timeframe: timeframe.value, adjustment: adjustment.value, session: session.value }
  if (benchmark.value) configuration.benchmark = benchmark.value.toUpperCase()
  else delete configuration.benchmark
  if (startDate.value) configuration.start_date = startDate.value
  else delete configuration.start_date
  if (endDate.value) configuration.end_date = endDate.value
  else delete configuration.end_date
  emit('configuration', configuration)
})

function clearPoller() { if (poller) clearInterval(poller); poller = null }
function stableKey(value: string) { return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 56) || 'study' }
function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
function formatMetric(artifact: Artifact) { return artifact.artifact_type === 'boolean' ? artifact.payload.value === true ? 'True' : artifact.payload.value === false ? 'False' : '—' : artifact.payload.value ?? '—' }
function tableRows(artifact: Artifact): Array<Record<string, unknown>> {
  const value = artifact.payload.value
  return Array.isArray(value) && value.every(row => row && typeof row === 'object' && !Array.isArray(row)) ? value as Array<Record<string, unknown>> : []
}
function tableColumns(artifact: Artifact) { return [...new Set(tableRows(artifact).flatMap(row => Object.keys(row)))] }
function formatCell(value: unknown) { return value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(value) }
function seriesData(artifact: Artifact): { timestamps: string[]; values: Array<number | null> } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { timestamps?: unknown; values?: unknown }
  if (!Array.isArray(candidate.timestamps) || !candidate.timestamps.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || candidate.timestamps.length !== candidate.values.length || !candidate.values.every(item => item == null || typeof item === 'number')) return null
  return { timestamps: candidate.timestamps, values: candidate.values }
}
function histogramData(artifact: Artifact): { bins: Array<{ start: number; end: number; count: number }>; current: number | null } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const bins = (value as { bins?: unknown }).bins
  if (!Array.isArray(bins)) return null
  const normalized = bins.filter((bin): bin is { start: number; end: number; count: number } => Boolean(bin) && typeof bin === 'object' && Number.isFinite((bin as Record<string, unknown>).start) && Number.isFinite((bin as Record<string, unknown>).end) && Number.isFinite((bin as Record<string, unknown>).count))
  const current = (value as { current?: unknown }).current
  return normalized.length ? { bins: normalized, current: typeof current === 'number' && Number.isFinite(current) ? current : null } : null
}
function scatterData(artifact: Artifact): { x: number[]; y: number[] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { x?: unknown; y?: unknown }
  if (!Array.isArray(candidate.x) || !Array.isArray(candidate.y) || candidate.x.length !== candidate.y.length) return null
  const x = candidate.x.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  const y = candidate.y.filter((item): item is number => typeof item === 'number' && Number.isFinite(item))
  return x.length === candidate.x.length && y.length === candidate.y.length ? { x, y } : null
}
function heatmapData(artifact: Artifact): { rows: string[]; columns: string[]; values: number[][] } | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const candidate = value as { rows?: unknown; columns?: unknown; values?: unknown }
  if (!Array.isArray(candidate.rows) || !candidate.rows.every(item => typeof item === 'string') || !Array.isArray(candidate.columns) || !candidate.columns.every(item => typeof item === 'string') || !Array.isArray(candidate.values) || !candidate.values.every(row => Array.isArray(row) && row.every(item => typeof item === 'number' && Number.isFinite(item)))) return null
  const rows = candidate.rows as string[]
  const columns = candidate.columns as string[]
  const values = candidate.values as number[][]
  return values.length && values.every(row => row.length === columns.length) && values.length === rows.length ? { rows, columns, values } : null
}
function dashboardData(artifact: Artifact): Array<{ artifact: string; title: string; span: number }> | null {
  const value = artifact.payload.value
  if (!value || typeof value !== 'object' || Array.isArray(value) || !Array.isArray((value as { panels?: unknown }).panels)) return null
  const panels = (value as { panels: unknown[] }).panels
  const normalized = panels.filter((panel): panel is { artifact: string; title: string; span: number } => Boolean(panel) && typeof panel === 'object' && typeof (panel as Record<string, unknown>).artifact === 'string' && typeof (panel as Record<string, unknown>).title === 'string' && typeof (panel as Record<string, unknown>).span === 'number')
  return normalized.length === panels.length ? normalized : null
}
function eventRows(artifact: Artifact): Array<{ symbol: string; timestamp: string; kind?: string }> {
  const value = artifact.payload.value
  if (!Array.isArray(value)) return []
  return value.filter((item): item is { symbol: string; timestamp: string; kind?: string } => Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).symbol === 'string' && typeof (item as Record<string, unknown>).timestamp === 'string').map(item => ({ symbol: item.symbol, timestamp: item.timestamp, kind: item.kind }))
}

async function validate() {
  busy.value = true; error.value = ''
  try { validation.value = await api.post<Validation>('/code/validate', { source: source.value }) }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to validate study source' }
  finally { busy.value = false }
}
async function refreshRun() {
  if (!run.value) return
  try {
    run.value = await api.get<Run>(`/research/runs/${run.value.id}`)
    if (!canCancel.value) clearPoller()
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to refresh study run'; clearPoller() }
}
async function saveAndRun() {
  if (!validation.value?.valid) return
  busy.value = true; error.value = ''; clearPoller()
  try {
    const asset = await api.post<{ versions: Array<{ id: number }> }>('/code/assets', {
      stable_key: `${stableKey(name.value)}-${Date.now()}`,
      name: name.value,
      kind: 'study',
      initial_version: { source: source.value, output_contract: 'study' },
    })
    const datasetControls: Record<string, string> = {
      timeframe: timeframe.value,
      adjustment: adjustment.value,
      session: session.value,
    }
    if (benchmark.value) datasetControls.benchmark = benchmark.value.toUpperCase()
    if (startDate.value) datasetControls.start_date = startDate.value
    if (endDate.value) datasetControls.end_date = endDate.value
    run.value = await api.post<Run>('/research/runs', {
      code_version_id: asset.versions[0].id,
      run_config: { symbol: symbol.value.toUpperCase(), ...datasetControls },
      dataset_manifest: { source: 'canonical_database', requested_at: new Date().toISOString(), ...datasetControls },
    })
    poller = setInterval(() => { void refreshRun() }, 1000)
  } catch (cause: any) { error.value = cause?.message ?? 'Unable to start isolated study run' }
  finally { busy.value = false }
}
async function cancel() {
  if (!run.value) return
  try { run.value = await api.post<Run>(`/research/runs/${run.value.id}/cancel`, {}); clearPoller() }
  catch (cause: any) { error.value = cause?.message ?? 'Unable to cancel study run' }
}
onBeforeUnmount(clearPoller)
</script>

<style scoped>
.study-lab-tool { display:grid; height:100%; min-height:0; grid-template-rows:auto minmax(110px,1fr) auto auto auto; gap:5px; padding:6px; background:#11161b; color:#cbd5dc; font:10px "Segoe UI",Arial,sans-serif; }
.study-lab-tool__header { display:grid; gap:4px; } .study-lab-tool__header-main { display:grid; grid-template-columns:minmax(80px,1fr) 56px 48px 38px; gap:4px; } .study-lab-tool__dataset { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:4px; color:#8ea3b0; } .study-lab-tool__dataset label { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; gap:3px; white-space:nowrap; } .study-lab-tool__dataset input,.study-lab-tool__dataset select { width:100%; min-width:0; }
input,textarea,button,select { min-width:0; border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; } input,select { padding:2px 4px; } textarea { width:100%; resize:none; padding:5px; font:11px/1.35 ui-monospace,SFMono-Regular,monospace; } button { cursor:pointer; } button:disabled { cursor:default; opacity:.5; }
.study-lab-tool__validation,.study-lab-tool__run { padding:5px; border:1px solid #34424c; background:#151b20; } .study-lab-tool__validation--bad,.study-lab-tool__error { border-color:#9e5757; color:#f0a2a2; } pre { max-height:100px; overflow:auto; margin:3px 0 0; color:#b8c6d0; white-space:pre-wrap; } .study-lab-tool__run > div { display:flex; align-items:center; gap:6px; } .study-lab-tool__run > div button { margin-left:auto; } .study-lab-tool__run p,.study-lab-tool__notice,.study-lab-tool__error { margin:0; color:#8195a3; } .study-lab-tool__dataset-summary { font-size:9px; } .study-lab-tool__run article { margin-top:5px; padding-top:4px; border-top:1px solid #29343c; } .study-lab-tool__run small { margin-left:5px; color:#779ab0; }.study-lab-tool__metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(70px,1fr)); gap:4px; margin-top:5px; }.study-lab-tool__metrics article { display:grid; gap:2px; margin:0; padding:4px; border:1px solid #29343c; background:#11161b; }.study-lab-tool__metrics strong { color:#b9e0f9; font-size:14px; }.study-lab-tool__metric--true { border-color:#3f8263!important; }.study-lab-tool__metric--true strong { color:#80d5a5!important; }.study-lab-tool__metric--false { border-color:#875454!important; }.study-lab-tool__metric--false strong { color:#f0a0a0!important; }.study-lab-tool__run table { width:100%; margin-top:4px; border-collapse:collapse; font-size:9px; }.study-lab-tool__run th,.study-lab-tool__run td { padding:2px 4px; border:1px solid #2c3943; text-align:left; white-space:nowrap; }.study-lab-tool__run th { color:#91a8b8; background:#1b252d; }.study-lab-tool__events { display:grid; gap:2px; margin-top:4px; }.study-lab-tool__events button { display:grid; grid-template-columns:50px 1fr auto; gap:5px; padding:3px 4px; border:1px solid #2d3c46; background:#11161b; color:#cddbe5; text-align:left; }.study-lab-tool__events button:hover { background:#1d3543; }.study-lab-tool__events span,.study-lab-tool__events small { color:#91a8b4; }.study-lab-tool__run-status--completed { color:#82c49b; }.study-lab-tool__run-status--failed { color:#ed9696; }.study-lab-tool__run-status--queued,.study-lab-tool__run-status--running { color:#80bce8; }
</style>
