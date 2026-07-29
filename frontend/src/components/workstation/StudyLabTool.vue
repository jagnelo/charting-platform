<template>
  <section class="study-lab-tool">
    <header class="study-lab-tool__header">
      <input v-model.trim="name" aria-label="Study name" placeholder="Study name" />
      <input v-model.trim="symbol" aria-label="Study symbol" placeholder="Symbol" />
      <button type="button" :disabled="busy" @click="validate">Validate</button>
      <button type="button" :disabled="busy || !validation?.valid" @click="saveAndRun">Run</button>
    </header>
    <textarea v-model="source" aria-label="Study Python source" spellcheck="false" />
    <section v-if="validation" class="study-lab-tool__validation" :class="{ 'study-lab-tool__validation--bad': !validation.valid }">
      <strong>{{ validation.valid ? 'Validated for isolated execution' : 'Validation errors' }}</strong>
      <pre v-if="validation.diagnostics.length">{{ validation.diagnostics }}</pre>
      <span v-else>Dependencies: {{ validation.dependencies.join(', ') || 'none' }} · Lookback: {{ validation.lookback_hint ?? 'none' }}</span>
    </section>
    <section v-if="run" class="study-lab-tool__run">
      <div><strong>Run #{{ run.id }}</strong><span :class="`study-lab-tool__run-status--${run.status}`">{{ run.status }}</span><button v-if="canCancel" type="button" @click="cancel">Cancel</button></div>
      <p v-if="run.reproducibility_hash">Reproducibility {{ run.reproducibility_hash }}</p>
      <pre v-if="run.diagnostics?.length">{{ run.diagnostics }}</pre>
      <div v-if="scalarArtifacts.length" class="study-lab-tool__metrics"><article v-for="artifact in scalarArtifacts" :key="artifact.id"><small>{{ artifact.name }}</small><strong>{{ artifact.payload.value ?? '—' }}</strong></article></div>
      <article v-for="artifact in nonScalarArtifacts" :key="artifact.id">
        <strong>{{ artifact.name }}</strong><small>{{ artifact.artifact_type }}</small>
        <table v-if="artifact.artifact_type === 'table' && tableRows(artifact).length"><thead><tr><th v-for="column in tableColumns(artifact)" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in tableRows(artifact)" :key="index"><td v-for="column in tableColumns(artifact)" :key="column">{{ formatCell(row[column]) }}</td></tr></tbody></table>
        <StudySeriesUPlot v-else-if="artifact.artifact_type === 'series' && seriesData(artifact)" :name="artifact.name" :timestamps="seriesData(artifact)!.timestamps" :values="seriesData(artifact)!.values" />
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
import StudySeriesUPlot from './StudySeriesUPlot.vue'

interface Validation { valid: boolean; diagnostics: unknown[]; dependencies: string[]; lookback_hint: number | null }
interface Run { id: number; status: string; diagnostics?: unknown[]; reproducibility_hash?: string | null; artifacts?: Array<{ id: number; name: string; artifact_type: string; payload: Record<string, unknown> }> }
type Artifact = NonNullable<Run['artifacts']>[number]

const props = defineProps<{ activeSymbol: string }>()
const name = ref('Consecutive Positive Closes')
const symbol = ref(props.activeSymbol)
const source = ref("streaks = stats.positive_close_streaks(dataset)\noutput.scalar('current_streak', streaks['current'])\noutput.scalar('longest_streak', streaks['longest'])\noutput.scalar('average_streak', streaks['average'])\noutput.table('completed_streaks', streaks['records'])")
const busy = ref(false)
const validation = ref<Validation | null>(null)
const run = ref<Run | null>(null)
const error = ref('')
let poller: ReturnType<typeof setInterval> | null = null

const canCancel = computed(() => Boolean(run.value && !['completed', 'failed', 'canceled'].includes(run.value.status)))
const scalarArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => artifact.artifact_type === 'scalar'))
const nonScalarArtifacts = computed(() => (run.value?.artifacts ?? []).filter(artifact => artifact.artifact_type !== 'scalar'))
watch(() => props.activeSymbol, value => { if (!symbol.value || symbol.value === 'SPY') symbol.value = value })

function clearPoller() { if (poller) clearInterval(poller); poller = null }
function stableKey(value: string) { return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 56) || 'study' }
function artifactText(payload: Record<string, unknown>) { return JSON.stringify(payload.value ?? payload, null, 2) }
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
    run.value = await api.post<Run>('/research/runs', {
      code_version_id: asset.versions[0].id,
      run_config: { symbol: symbol.value.toUpperCase() },
      dataset_manifest: { source: 'canonical_database', requested_at: new Date().toISOString() },
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
.study-lab-tool { display:grid; height:100%; min-height:0; grid-template-rows:26px minmax(110px,1fr) auto auto auto; gap:5px; padding:6px; background:#11161b; color:#cbd5dc; font:10px "Segoe UI",Arial,sans-serif; }
.study-lab-tool__header { display:grid; grid-template-columns:minmax(80px,1fr) 56px 48px 38px; gap:4px; } input,textarea,button { min-width:0; border:1px solid #3a4954; background:#172027; color:#dce6ed; font:inherit; } input { padding:2px 4px; } textarea { width:100%; resize:none; padding:5px; font:11px/1.35 ui-monospace,SFMono-Regular,monospace; } button { cursor:pointer; } button:disabled { cursor:default; opacity:.5; }
.study-lab-tool__validation,.study-lab-tool__run { padding:5px; border:1px solid #34424c; background:#151b20; } .study-lab-tool__validation--bad,.study-lab-tool__error { border-color:#9e5757; color:#f0a2a2; } pre { max-height:100px; overflow:auto; margin:3px 0 0; color:#b8c6d0; white-space:pre-wrap; } .study-lab-tool__run > div { display:flex; align-items:center; gap:6px; } .study-lab-tool__run > div button { margin-left:auto; } .study-lab-tool__run p,.study-lab-tool__notice,.study-lab-tool__error { margin:0; color:#8195a3; } .study-lab-tool__run article { margin-top:5px; padding-top:4px; border-top:1px solid #29343c; } .study-lab-tool__run small { margin-left:5px; color:#779ab0; }.study-lab-tool__metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(70px,1fr)); gap:4px; margin-top:5px; }.study-lab-tool__metrics article { display:grid; gap:2px; margin:0; padding:4px; border:1px solid #29343c; background:#11161b; }.study-lab-tool__metrics strong { color:#b9e0f9; font-size:14px; }.study-lab-tool__run table { width:100%; margin-top:4px; border-collapse:collapse; font-size:9px; }.study-lab-tool__run th,.study-lab-tool__run td { padding:2px 4px; border:1px solid #2c3943; text-align:left; white-space:nowrap; }.study-lab-tool__run th { color:#91a8b8; background:#1b252d; }.study-lab-tool__run-status--completed { color:#82c49b; }.study-lab-tool__run-status--failed { color:#ed9696; }.study-lab-tool__run-status--queued,.study-lab-tool__run-status--running { color:#80bce8; }
</style>
